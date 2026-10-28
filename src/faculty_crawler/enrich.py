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


def tag_techniques(t: Teacher) -> None:
    pm = product_map()
    text = _corpus(t)
    low = text.lower()
    hits: list[tuple[str, int, str]] = []
    for tech, spec in pm["techniques"].items():
        n, first = 0, ""
        for kw in spec["keywords"]:
            k = kw.lower()
            c = low.count(k)
            if c:
                n += c
                first = first or kw
        if n:
            hits.append((tech, n, first))
    hits.sort(key=lambda x: -x[1])
    for tech, n, kw in hits:
        if tech not in t.techniques:
            t.techniques.append(tech)
            src = t.profile_url or t.list_url or ""
            t.evidence.append(_ev("techniques", tech, src, f"关键词“{kw}”命中 {n} 次"))
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

    is_new = t.joined_year is not None and t.joined_year >= this_year - 2 and rank >= 3
    if is_new:
        signals.append(f"新进 PI（{t.joined_year} 年入职）：建实验室采购窗口")
        score += 30
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
