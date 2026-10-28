"""主流水线：列表页 → 详情页 → 抽取 → 增强 → 校验 → 存储 → 导出。"""
from __future__ import annotations

import logging
import re

from . import config
from .detail_parser import extract_detail, normalize_list_title
from .enrich import enrich
from .export import report_markdown, write_cards, write_csv
from .fetcher import FetchError, Fetcher
from .list_parser import parse_list, webplus_page_urls
from .models import SiteReport, Teacher, TeacherStub, now_utc
from .normalize import find_supervisor, normalize_title, school_domains
from .sites import Site
from .store import Store
from .validate import mark_duplicates, site_report, validate_teacher

log = logging.getLogger(__name__)

SUPPORT_GROUP_RE = re.compile(r"支撑|实验技术|工程技术|平台|行政|管理|教辅|实验中心|技术人员")


def collect_stubs(site: Site, fetcher: Fetcher, report: SiteReport) -> list[tuple[TeacherStub, str]]:
    out: list[tuple[TeacherStub, str]] = []
    queue = list(site.list.urls)
    seen_pages: set[str] = set()
    while queue:
        url = queue.pop(0)
        if url in seen_pages:
            continue
        seen_pages.add(url)
        try:
            page = fetcher.get(url)
        except FetchError as e:
            report.errors.append(str(e))
            continue
        report.list_pages += 1
        stubs = parse_list(page.html, page.final_url, site.list)
        log.info("列表页 %s：%d 条", url, len(stubs))
        out += [(s, url) for s in stubs]
        if site.list.pagination == "webplus" and url in site.list.urls:
            queue += webplus_page_urls(page.html, url, site.list.max_pages)
    # 去重：同一详情页只保留一次；无详情页的按姓名去重
    dedup: dict[str, tuple[TeacherStub, str]] = {}
    for s, src in out:
        k = s.url or f"name:{s.name}"
        if k not in dedup:
            dedup[k] = (s, src)
        else:  # 合并分组信息（同一人出现在多个系所）
            prev = dedup[k][0]
            if s.group and prev.group and s.group not in prev.group:
                prev.group = f"{prev.group}；{s.group}"
    return list(dedup.values())


def build_teacher(site: Site, stub: TeacherStub, list_url: str) -> Teacher:
    t = Teacher(site_id=site.id, school=site.school, college=site.college, name=stub.name,
                profile_url=stub.url, list_url=list_url)
    t.add("name", stub.name, list_url, snippet=stub.extra.get("label", stub.name), method="template", confidence=0.9, overwrite=True)
    if stub.group:
        dept = stub.group.split(" / ")[0]
        t.department_raw = stub.group
        t.add("department", dept, list_url, snippet=stub.group, method="group_heading", confidence=0.9)
        if SUPPORT_GROUP_RE.search(stub.group):
            t.role = "支撑"
        # 分组标题本身常常就是职称
        g_title = stub.group.split(" / ")[-1]
        if normalize_title(g_title) and "title" not in stub.extra:
            normalize_list_title(t, g_title, list_url)
    normalize_list_title(t, stub.extra.get("title"), list_url)
    label = stub.extra.get("label", "")
    sup = find_supervisor(label)
    if sup:
        t.add("supervisor", sup, list_url, snippet=label, method="template", confidence=0.9)
    t.role = t.role or "教研"
    return t


def crawl_site(site: Site, *, fetcher: Fetcher | None = None, store: Store | None = None,
               limit: int | None = None, export: bool = True) -> tuple[list[Teacher], SiteReport]:
    own_fetcher = fetcher is None
    fetcher = fetcher or Fetcher()
    store = store or Store()
    report = SiteReport(site_id=site.id)
    domains = set(site.school_domains) or school_domains(*site.list.urls)
    try:
        stubs = collect_stubs(site, fetcher, report)
        report.stubs = len(stubs)
        if limit:
            stubs = stubs[:limit]
            report.stubs = len(stubs)
        report.stubs_with_url = sum(1 for s, _ in stubs if s.url)
        teachers: list[Teacher] = []
        for i, (stub, list_url) in enumerate(stubs, 1):
            t = build_teacher(site, stub, list_url)
            if stub.url:
                try:
                    page = fetcher.get(stub.url)
                    if page.status != 200:
                        raise FetchError(f"HTTP {page.status}")
                    extract_detail(t, page.html, page.final_url, site.detail, domains)
                    report.detail_ok += 1
                except FetchError as e:
                    t.raw["detail_error"] = str(e)
                    report.detail_failed += 1
                    report.errors.append(f"{stub.name}: {e}")
            enrich(t)
            validate_teacher(t, domains)
            teachers.append(t)
            if i % 20 == 0:
                log.info("%s 进度 %d/%d", site.id, i, len(stubs))
        mark_duplicates(teachers)
        report.finished_at = now_utc()
        site_report(report, teachers, site.expected_min_teachers)
        teachers.sort(key=lambda t: (-t.priority, t.name))
        store.save_site(site.id, teachers, report)
        if export:
            export_site(site.id, teachers, report)
        return teachers, report
    finally:
        if own_fetcher:
            fetcher.close()


def export_site(site_id: str, teachers: list[Teacher], report: SiteReport) -> dict[str, str]:
    base = config.EXPORT_DIR / site_id
    csv_path = write_csv(teachers, base / f"{site_id}_teachers.csv")
    cards = write_cards(teachers, base / "cards")
    rep = base / f"{site_id}_report.md"
    rep.write_text(report_markdown(site_id, report, teachers), "utf-8")
    return {"csv": str(csv_path), "cards_dir": str(base / "cards"), "report": str(rep), "cards": str(len(cards))}
