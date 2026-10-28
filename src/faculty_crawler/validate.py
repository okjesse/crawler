"""字段级校验、置信度打分、站点级质量报告。"""
from __future__ import annotations

from collections import Counter

from .models import SiteReport, Teacher
from .normalize import TITLE_ENUM, is_plausible_name

KEY_FIELDS = ["title", "email", "research_directions", "phone", "office", "papers", "projects", "joined_year", "techniques"]
WEIGHTS = {"name": 0.15, "title": 0.2, "email": 0.25, "research_directions": 0.2, "profile_url": 0.1, "techniques": 0.1}


def validate_teacher(t: Teacher, school_domains: set[str]) -> None:
    issues: list[str] = []
    if not is_plausible_name(t.name):
        issues.append("姓名格式可疑")
    if not t.profile_url:
        issues.append("无详情页链接")
    elif t.raw.get("detail_error"):
        issues.append("详情页抓取失败")
    if not t.title:
        issues.append("缺职称")
    elif t.title not in TITLE_ENUM:
        issues.append("职称不在枚举内")
    if not t.email:
        issues.append("缺邮箱")
    elif school_domains and not any(t.email.endswith(d) for d in school_domains):
        issues.append("邮箱非本校域名")
    if not t.research_directions:
        issues.append("缺研究方向")
    if t.raw.get("text_len", 0) and t.raw["text_len"] < 80:
        issues.append("详情页内容过少")
    t.issues = issues

    score = 0.0
    for f, w in WEIGHTS.items():
        v = getattr(t, f, None)
        if v:
            score += w
    if "邮箱非本校域名" in issues:
        score -= 0.1
    t.confidence = round(max(min(score, 1.0), 0.0), 2)


def mark_duplicates(teachers: list[Teacher]) -> None:
    by_name = Counter(t.name for t in teachers)
    for t in teachers:
        if by_name[t.name] > 1:
            t.issues.append("站内同名，需人工确认")


def site_report(report: SiteReport, teachers: list[Teacher], expected_min: int | None) -> SiteReport:
    n = len(teachers)
    report.teachers = n
    report.coverage = round(report.detail_ok / report.stubs, 3) if report.stubs else 0.0
    report.fill_rates = {f: round(sum(1 for t in teachers if getattr(t, f)) / n, 3) if n else 0.0 for f in KEY_FIELDS}
    c: Counter[str] = Counter()
    for t in teachers:
        c.update(t.issues)
    report.issue_counts = dict(c.most_common())
    if report.coverage < 0.95:
        report.notes.append(f"详情页覆盖率 {report.coverage:.0%} 低于 95% 门槛")
    if expected_min and n < expected_min:
        report.notes.append(f"教师数 {n} 低于预期下限 {expected_min}，列表页可能不完整，需找其他来源")
    if n and report.fill_rates.get("email", 0) < 0.8:
        report.notes.append("邮箱填充率低于 80%，检查是否为图片/JS 混淆")
    return report
