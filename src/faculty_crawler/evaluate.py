"""批次质量评测：填充率、与独立来源交叉比对、论文归属分布、人工抽查清单。"""
from __future__ import annotations

import csv
import random
from collections import Counter
from pathlib import Path

from . import config
from .normalize import normalize_title
from .store import Store

FIELDS = [
    ("邮箱", lambda t: t.email), ("职称", lambda t: t.title), ("研究方向", lambda t: t.research_directions),
    ("入职年份", lambda t: t.joined_year), ("人才头衔", lambda t: t.honors), ("招生招聘", lambda t: t.recruiting),
    ("电话", lambda t: t.phone), ("办公地点", lambda t: t.office),
    ("可确认英文论文", lambda t: t.publications), ("ORCID", lambda t: t.orcid),
    ("h 指数", lambda t: (t.metrics.get("openalex") or {}).get("h_index") is not None),
    ("论文致谢基金号", lambda t: t.grants), ("课题组规模", lambda t: (t.metrics.get("group") or {}).get("estimated_size")),
    ("方法章节", lambda t: (t.metrics.get("fulltext") or {}).get("scanned")),
    ("品牌", lambda t: (t.metrics.get("fulltext") or {}).get("brands")),
    ("竞品耗材记录", lambda t: any(v.get("kind") in ("consumable", "own") and v.get("consumable_papers")
                              for v in ((t.metrics.get("fulltext") or {}).get("brands") or {}).values())),
    ("课题组网站", lambda t: t.metrics.get("lab_site")),
    ("实验技术标签", lambda t: t.techniques),
]


def _batch_teachers(store: Store, batch: str):
    path = config.EXPORT_DIR / batch / "teachers.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    out = []
    for r in rows:
        hits = store.find(r["姓名"])
        hits = [t for t in hits if t.site_id == "input" and t.school == r["学校"]
                and (not r["个人主页"] or (t.raw.get("input_url") or t.profile_url) == r["个人主页"])]
        if hits:
            out.append(hits[0])
    return out


def evaluate(batch: str, reference_site: str | None = None, sample: int = 20, seed: int = 7) -> str:
    store = Store()
    ts = _batch_teachers(store, batch)
    n = len(ts)
    L: list[str] = [f"# 批次质量评测：{batch}", "", f"- 人数：{n}", f"- 抓取级别：{Counter(t.raw.get('level') for t in ts).most_common()}", ""]

    L += ["## 字段填充率", "", "| 字段 | 人数 | 比例 |", "|---|---|---|"]
    for name, fn in FIELDS:
        k = sum(1 for t in ts if fn(t))
        L.append(f"| {name} | {k} | {k / n:.0%} |" if n else f"| {name} | 0 | - |")
    L.append("")

    # 职称：与学院列表页（独立来源）比对
    if reference_site:
        ref = {(r.name, r.profile_url): r for r in store.teachers(reference_site, active_only=False)}
        pairs = []
        for t in ts:
            r = ref.get((t.name, t.raw.get("input_url") or t.profile_url))
            if r and r.title_raw:
                pairs.append((t, normalize_title(r.title_raw), r.title_raw))
        agree = [p for p in pairs if p[0].title == p[1]]
        L += ["## 职称与学院列表页交叉比对", "",
              f"- 可比对 {len(pairs)} 人，一致 {len(agree)} 人（{len(agree) / len(pairs):.0%}）。" if pairs else "- 无可比对数据。"]
        for t, rnorm, rraw in [p for p in pairs if p[0].title != p[1]]:
            L.append(f"  - 不一致：{t.name}　主页抽取“{t.title_raw}”→{t.title}；列表页“{rraw}”→{rnorm}　[主页]({t.profile_url})")
        L.append("")

    # 邮箱
    dom_ok = sum(1 for t in ts if t.email and any(t.email.endswith(d) for d in t.raw.get("institution", {}).get("domains", [])))
    with_email = sum(1 for t in ts if t.email)
    src = Counter(next((e.method for e in t.evidence if e.field == "email" and e.value == t.email), "?") for t in ts if t.email)
    L += ["## 邮箱", "", f"- 有邮箱 {with_email} 人，其中本校域名 {dom_ok} 人。",
          f"- 来源：{', '.join(f'{k} {v}' for k, v in src.most_common())}（heuristic=主页，api=论文，input=名单）", ""]
    for t in ts:
        if t.email and not any(t.email.endswith(d) for d in t.raw.get("institution", {}).get("domains", [])):
            L.append(f"  - 非本校域名：{t.name} {t.email}")
    L.append("")

    # 论文归属
    pubs = [(t, p) for t in ts for p in t.publications]
    mix = Counter(p.match for _, p in pubs)
    anchored = sum(1 for t in ts if t.metrics.get("paper_anchors"))
    L += ["## 论文归属", "", f"- 已归属论文 {len(pubs)} 篇；依据：{', '.join(f'{k} {v}' for k, v in mix.most_common())}。",
          f"- 有强锚点（邮箱、主页论文、ORCID）的老师 {anchored}/{sum(1 for t in ts if t.publications)}。",
          f"- 待确认同名论文合计 {sum(t.possible_publications for t in ts)} 篇。", ""]
    notes = Counter(n.split("：")[0][:30] for t in ts for n in t.metrics.get("paper_notes", []))
    if notes:
        L.append("- 提示分布：" + "；".join(f"{k}…（{v}）" for k, v in notes.most_common(6)))
        L.append("")

    # 人工抽查清单：仅凭姓名+院系归属的论文
    weak = [(t, p) for t, p in pubs if p.match in ("full", "initial")]
    random.Random(seed).shuffle(weak)
    if weak:
        L += [f"## 人工抽查：仅凭姓名与院系归属的论文（随机 {min(sample, len(weak))} 篇）", "",
              "| 老师 | 研究方向 | 论文 | 作者单位 | 判断 |", "|---|---|---|---|---|"]
        for t, p in weak[:sample]:
            dirs = "；".join(t.research_directions[:2])[:40]
            L.append(f"| {t.name} | {dirs} | [{p.year} {p.title[:60]}]({p.url}) | {p.author_aff[:80]} |  |")
        L.append("")

    # 问题分布
    iss = Counter(i.split("篇")[0] if i.startswith("另有") else i for t in ts for i in t.issues)
    L += ["## 待核问题分布", ""] + [f"- {k}：{v}" for k, v in iss.most_common()] + [""]
    return "\n".join(L)


def write(batch: str, out: Path, **kw) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(evaluate(batch, **kw), "utf-8")
    return out
