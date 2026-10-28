"""导出：销售用 CSV（Excel 可直接打开）、画像卡 Markdown、站点质量报告。"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

from .models import SiteReport, Teacher

CSV_COLUMNS = [
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


def write_cards(teachers: list[Teacher], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for t in teachers:
        p = out_dir / f"{t.priority:03d}_{_safe(t.name)}.md"
        p.write_text(card_markdown(t), "utf-8")
        paths.append(p)
    return paths


def report_markdown(site_id: str, r: SiteReport, teachers: list[Teacher]) -> str:
    lines = [f"# 抓取质量报告：{site_id}", ""]
    lines.append(f"- 列表页数：{r.list_pages}")
    lines.append(f"- 列表条目：{r.stubs}")
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
