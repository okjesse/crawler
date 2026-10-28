"""本地增强：实验技术标签、产品推荐、销售信号与优先级。"""
from __future__ import annotations

import re
from datetime import date
from functools import lru_cache

import yaml

from . import config
from .models import Teacher
from .normalize import TITLE_RANK


@lru_cache(maxsize=1)
def product_map() -> dict:
    return yaml.safe_load(config.PRODUCT_MAP_PATH.read_text("utf-8"))


def _corpus(t: Teacher) -> str:
    # 不放办公地址、联系方式，避免“生物药学楼”之类误触发
    bio = t.bio_text or ""
    if t.office:
        bio = bio.replace(t.office, "")
    parts = [" ".join(t.research_directions), t.research_text or "", bio,
             " ".join(t.papers[:15]), " ".join(t.projects), t.group_text()]
    return "\n".join(parts)


def _paper_texts(t: Teacher, years: int = 5) -> list[tuple[str, str]]:
    this_year = date.today().year
    out = []
    for p in t.publications:
        if p.year and p.year < this_year - years + 1:
            continue
        txt = " ".join([p.title, " ".join(p.mesh), " ".join(p.keywords), p.abstract[:800]]).lower()
        out.append((txt, p.url))
    return out


@lru_cache(maxsize=64)
def _en_patterns_cached(tech: str, kws: tuple[str, ...]) -> list[re.Pattern]:
    # 词首边界：plant 不匹配 implant/transplant，rice 不匹配 price
    return [re.compile(r"(?<![a-z])" + re.escape(k.lower())) for k in kws]


def _en_patterns(tech: str, kws: list[str]) -> list[re.Pattern]:
    return _en_patterns_cached(tech, tuple(kws))


def tag_techniques(t: Teacher) -> None:
    """技术标签 = 主页中文关键词命中次数 + 近 5 年论文英文关键词命中篇数×2。"""
    pm = product_map()
    low = _corpus(t).lower()
    papers = _paper_texts(t)
    hits: list[tuple[str, int, str]] = []
    for tech, spec in pm["techniques"].items():
        n, why = 0, ""
        for kw in spec["keywords"]:
            c = low.count(kw.lower())
            if c:
                n += c
                why = why or f"主页关键词“{kw}”"
        en_pats = _en_patterns(tech, spec.get("keywords_en", []))
        paper_hits = [url for txt, url in papers if any(p.search(txt) for p in en_pats)]
        if paper_hits:
            n += 2 * len(paper_hits)
            why = (why + "；" if why else "") + f"近 5 年 {len(paper_hits)} 篇论文涉及"
        if n:
            hits.append((tech, n, why))
    hits.sort(key=lambda x: -x[1])
    # 只保留有一定强度的标签：至少 2 分，且不低于最高分的 15%，最多 6 个
    if hits:
        top = hits[0][1]
        hits = [h for h in hits if h[1] >= 2 and h[1] >= 0.15 * top][:6] or hits[:1]
    t.techniques = []
    for tech, n, why in hits:
        t.techniques.append(tech)
        src = t.profile_url or (t.publications[0].url if t.publications else "") or t.list_url or ""
        t.evidence.append(_ev("techniques", tech, src, why))
    t.raw["technique_scores"] = {tech: n for tech, n, _ in hits}
    # 产品推荐：按技术命中强度累加
    score: dict[str, int] = {}
    for tech, n, _ in hits:
        for i, p in enumerate(pm["techniques"][tech]["products"]):
            score[p] = score.get(p, 0) + n * (10 - i)
    t.recommended_products = [pm["products"][p] for p, _ in sorted(score.items(), key=lambda kv: -kv[1])][:5]


def _ev(field: str, value: str, url: str, snippet: str):
    from .models import Evidence
    return Evidence(field=field, value=value, source_url=url, snippet=snippet, method="rule", confidence=0.6)


def score_signals(t: Teacher) -> None:
    pm = product_map()
    this_year = date.today().year
    rank = TITLE_RANK.get(t.title or "", 1)
    signals: list[str] = []
    score = 0

    if t.role == "支撑":
        signals.append("支撑岗位：可能是实验室/平台采购执行人")
        score += 5
    else:
        score += {5: 10, 4: 6, 3: 4}.get(rank, 0)

    wet = [x for x in t.techniques if pm["techniques"][x].get("wet", True)]
    dry_only = bool(t.techniques) and not wet
    score += min(len(wet), 5) * 5
    if dry_only:
        signals.append("疑似干实验课题组，耗材需求低")
        score -= 20

    is_recent = t.joined_year is not None and t.joined_year >= this_year - 2 and rank >= 3
    pi_evidence = bool(t.is_pi) or rank >= 5 or t.metrics.get("last_author_5y", 0) >= 2
    is_new = is_recent and pi_evidence
    if is_new:
        signals.append(f"新进 PI（{t.joined_year} 年入职）：建实验室采购窗口")
        score += 30
    elif is_recent:
        signals.append(f"新入职教师（{t.joined_year} 年）：未见独立课题组证据，可能在他人课题组")
        score += 15
    if t.honors:
        signals.append("人才头衔：" + "、".join(t.honors[:3]))
        score += 10
    if t.recruiting:
        signals.append("正在招收/招聘：课题组扩张")
        score += 10
    if is_new and t.honors and t.recruiting:
        signals.insert(0, "★ 新进 PI + 人才头衔 + 在招人：最高优先级")
        score += 20
    elif is_new and (t.honors or t.recruiting):
        signals.insert(0, "★ 新进 PI 叠加头衔或招人：高优先级")
        score += 10
    recent_proj = [p for p in t.projects if any(str(y) in p for y in range(this_year - 3, this_year + 1))]
    if recent_proj:
        signals.append(f"近 3 年在研项目 {len(recent_proj)} 项：有预算")
        score += 10
    m = t.metrics
    if m.get("papers_2y", 0) >= 3:
        signals.append(f"近 2 年发表 {m['papers_2y']} 篇英文论文：课题组活跃")
        score += 10
    elif t.publications and (m.get("latest_year") or 0) < this_year - 3:
        signals.append(f"最近一篇可确认论文在 {m.get('latest_year')} 年：可能不活跃或转向")
        score -= 5
    recent_grants = [g for g in t.grants if g.year and g.year >= this_year - 4]
    if recent_grants and not recent_proj:
        kinds = "、".join(sorted({g.kind for g in recent_grants if g.kind}))
        signals.append(f"论文致谢中近 4 年国家自然科学基金 {len(recent_grants)} 项（{kinds}）：有预算")
        score += 10
    if any(g.kind and "人才" in g.kind for g in t.grants) and not t.honors:
        signals.append("论文致谢含优青/杰青等人才类基金号")
        score += 5
    if t.position and re.search(r"院长|主任|书记|所长", t.position):
        signals.append(f"行政职务：{t.position}（决策链）")
        score += 10
    if "博士生导师" in t.supervisor:
        score += 5
    t.signals = signals
    t.priority = max(score, 0)


def enrich(t: Teacher) -> None:
    tag_techniques(t)
    score_signals(t)
