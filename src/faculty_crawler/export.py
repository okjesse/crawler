"""导出：销售用 CSV（Excel 可直接打开）、画像卡 Markdown、站点质量报告。"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

from .models import SiteReport, Teacher

CSV_COLUMNS = [
    ("编号", lambda t: t.raw.get("input_id") or ""),
    ("优先级", lambda t: t.priority),
    ("学校", lambda t: t.school),
    ("学院", lambda t: t.college),
    ("系所/分组", lambda t: t.department or ""),
    ("姓名", lambda t: t.name),
    ("职称", lambda t: t.title or ""),
    ("职称原文", lambda t: t.title_raw or ""),
    ("导师资格", lambda t: "、".join(t.supervisor)),
    ("人才头衔", lambda t: "、".join(t.honors)),
    ("行政职务", lambda t: t.position or ""),
    ("岗位类型", lambda t: t.role or ""),
    ("邮箱", lambda t: t.email or ""),
    ("电话", lambda t: t.phone or ""),
    ("办公地点", lambda t: t.office or ""),
    ("入职年份", lambda t: t.joined_year or ""),
    ("研究方向", lambda t: "；".join(t.research_directions)),
    ("实验技术", lambda t: "、".join(t.techniques)),
    ("推荐产品", lambda t: "、".join(t.recommended_products)),
    ("销售信号", lambda t: "；".join(t.signals)),
    ("主页论文数", lambda t: len(t.papers)),
    ("主页项目数", lambda t: len(t.projects)),
    ("近5年英文论文", lambda t: t.metrics.get("papers_5y", "")),
    ("近5年末位作者", lambda t: t.metrics.get("last_author_5y", "")),
    ("最近发表年份", lambda t: t.metrics.get("latest_year") or ""),
    ("主要期刊", lambda t: "；".join(t.metrics.get("top_journals", []))),
    ("基金号(论文致谢)", lambda t: "；".join(f"{g.grant_id}({g.year or ''}{g.kind or ''})" for g in t.grants if "china" in g.agency.lower())[:200]),
    ("h指数", lambda t: (t.metrics.get("openalex") or {}).get("h_index", "")),
    ("ORCID", lambda t: t.orcid or ""),
    ("论文归属依据", lambda t: "、".join(t.metrics.get("paper_anchors", [])) or ("仅姓名+单位" if t.publications else "")),
    ("待确认同名论文", lambda t: t.possible_publications or ""),
    ("招生招聘", lambda t: "；".join(t.recruiting)[:200]),
    ("数据置信度", lambda t: t.confidence),
    ("待核问题", lambda t: "；".join(t.issues)),
    ("个人主页", lambda t: t.profile_url or ""),
    ("列表来源", lambda t: t.list_url or ""),
    ("抓取时间", lambda t: t.fetched_at.strftime("%Y-%m-%d")),
]


def write_csv(teachers: list[Teacher], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([c for c, _ in CSV_COLUMNS])
        for t in teachers:
            w.writerow([fn(t) for _, fn in CSV_COLUMNS])
    return path


def _safe(s: str) -> str:
    return re.sub(r"[\\/:*?\"<>|\s]+", "_", s)[:60]


def card_markdown(t: Teacher) -> str:
    ev = defaultdict(list)
    for e in t.evidence:
        ev[e.field].append(e)

    def src(field: str) -> str:
        es = ev.get(field)
        if not es:
            return ""
        e = max(es, key=lambda x: x.confidence)
        return f" [来源]({e.source_url})"

    lines = [f"# {t.name}｜{t.school} {t.college}", ""]
    lines.append(f"**优先级 {t.priority}**　数据置信度 {t.confidence:.0%}　抓取于 {t.fetched_at:%Y-%m-%d}")
    lines.append("")
    if t.signals:
        lines.append("## 销售信号")
        lines += [f"- {s}" for s in t.signals]
        lines.append("")
    lines.append("## 基本信息")
    rows = [
        ("系所/分组", t.department, "department"),
        ("职称", f"{t.title}（{t.title_raw}）" if t.title and t.title_raw and t.title_raw != t.title else t.title, "title"),
        ("导师资格", "、".join(t.supervisor), "supervisor"),
        ("人才头衔", "、".join(t.honors), "honors"),
        ("行政职务", t.position, "position"),
        ("入职年份", t.joined_year, "joined_year"),
        ("邮箱", t.email, "email"),
        ("电话", t.phone, "phone"),
        ("办公地点", t.office, "office"),
        ("实验室", t.lab_name, "lab_name"),
        ("课题组网站", t.lab_url, "lab_url"),
        ("个人主页", t.profile_url, None),
    ]
    for label, val, field in rows:
        if val:
            lines.append(f"- **{label}**：{val}{src(field) if field else ''}")
    lines.append("")
    if t.research_directions:
        lines.append("## 研究方向" + src("research_directions"))
        lines += [f"- {d}" for d in t.research_directions]
        lines.append("")
    if t.techniques:
        lines.append("## 推断实验技术与推荐产品")
        lines.append(f"- 实验技术：{'、'.join(t.techniques)}")
        lines.append(f"- 推荐产品：{'、'.join(t.recommended_products) or '无'}")
        lines.append("- 说明：由研究方向、简介、论文与项目文本中的关键词推断，需销售在沟通中确认。")
        lines.append("")
    m = t.metrics
    if t.publications or m.get("paper_notes"):
        lines.append("## 论文概况（Europe PMC / PubMed）")
        if t.publications:
            lines.append(f"- 近 5 年可确认英文论文 {m.get('papers_5y', 0)} 篇，其中末位作者 {m.get('last_author_5y', 0)} 篇、第一作者 {m.get('first_author_5y', 0)} 篇；最近一篇发表于 {m.get('latest_year')} 年。")
            if m.get("top_journals"):
                lines.append(f"- 主要期刊：{'、'.join(m['top_journals'])}")
            if m.get("top_mesh"):
                lines.append(f"- 高频主题词：{'、'.join(m['top_mesh'][:8])}")
            anchors = {"email": "论文单位中的邮箱", "seed": "主页所列论文", "orcid": "ORCID"}
            basis = "、".join(anchors.get(a, a) for a in m.get("paper_anchors", [])) or "仅姓名与单位（同名风险较高）"
            lines.append(f"- 归属依据：{basis}")
        if t.orcid:
            lines.append(f"- ORCID：[{t.orcid}](https://orcid.org/{t.orcid})")
        oa = m.get("openalex")
        if oa:
            lines.append(f"- OpenAlex：h 指数 {oa.get('h_index')}，论文 {oa.get('works_count')} 篇，被引 {oa.get('cited_by_count')} 次；主题：{'、'.join(oa.get('topics') or [])}")
            if oa.get("note"):
                lines.append(f"- 注意：{oa['note']}")
        for note in m.get("paper_notes", []):
            lines.append(f"- 注意：{note}")
        lines.append("")
        if t.publications:
            lines.append("### 近期论文（前 8 篇）")
            pos = {"first": "第一作者", "last": "末位/通讯", "solo": "唯一作者", "middle": "合作者"}
            for p in t.publications[:8]:
                lines.append(f"- {p.year} *{p.journal or ''}* [{p.title[:150]}]({p.url})（{pos.get(p.position, p.position)}）")
            lines.append("")
    china = [g for g in t.grants if "china" in g.agency.lower() or "中国" in g.agency]
    if china:
        lines.append("## 论文致谢中的国内基金（资助号推断年份与类别）")
        for g in china[:10]:
            lines.append(f"- {g.agency} {g.grant_id or ''}｜{g.year or '年份未知'} {g.kind or ''}｜出现在 {g.n_papers} 篇论文 [来源]({g.source_url})")
        lines.append("")
    if t.experience:
        lines.append("## 经历" + src("experience"))
        lines += [f"- {x}" for x in t.experience[:8]]
        lines.append("")
    if t.projects:
        lines.append("## 主页列出的项目" + src("projects"))
        lines += [f"- {x}" for x in t.projects[:8]]
        lines.append("")
    if t.papers:
        lines.append("## 代表论文（主页列出，前 5 篇）" + src("papers"))
        lines += [f"- {x[:300]}" for x in t.papers[:5]]
        lines.append("")
    if t.recruiting:
        lines.append("## 招生/招聘" + src("recruiting"))
        lines += [f"- {x[:200]}" for x in t.recruiting]
        lines.append("")
    if t.issues:
        lines.append("## 待核问题")
        lines += [f"- {x}" for x in t.issues]
        lines.append("")
    return "\n".join(lines)


def write_cards(teachers: list[Teacher], out_dir: Path, clean: bool = True) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    if clean:  # 优先级变化后文件名会变，先清掉旧卡片
        for old in out_dir.glob("*.md"):
            old.unlink()
    paths = []
    for t in teachers:
        p = out_dir / f"{t.priority:03d}_{_safe(t.name)}.md"
        p.write_text(card_markdown(t), "utf-8")
        paths.append(p)
    return paths


def report_markdown(site_id: str, r: SiteReport, teachers: list[Teacher]) -> str:
    lines = [f"# 抓取质量报告：{site_id}", ""]
    lines.append(f"- 列表页数：{r.list_pages}")
    lines.append(f"- 列表条目：{r.stubs}（有个人主页 {r.stubs_with_url}）")
    lines.append(f"- 详情页成功/失败：{r.detail_ok}/{r.detail_failed}")
    lines.append(f"- 覆盖率：{r.coverage:.0%}")
    lines.append(f"- 入库教师：{r.teachers}")
    lines.append("")
    lines.append("## 字段填充率")
    lines.append("| 字段 | 填充率 |")
    lines.append("|---|---|")
    for k, v in r.fill_rates.items():
        lines.append(f"| {k} | {v:.0%} |")
    lines.append("")
    if r.issue_counts:
        lines.append("## 问题分布")
        lines += [f"- {k}：{v}" for k, v in r.issue_counts.items()]
        lines.append("")
    if r.notes or r.errors:
        lines.append("## 告警")
        lines += [f"- {x}" for x in r.notes]
        lines += [f"- 错误：{x}" for x in r.errors[:20]]
        lines.append("")
    top = sorted(teachers, key=lambda t: -t.priority)[:15]
    if top:
        lines.append("## 优先级前 15")
        lines.append("| 姓名 | 职称 | 优先级 | 信号 |")
        lines.append("|---|---|---|---|")
        for t in top:
            lines.append(f"| {t.name} | {t.title or ''} | {t.priority} | {'；'.join(t.signals)[:80]} |")
    return "\n".join(lines)
