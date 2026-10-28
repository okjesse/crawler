"""命令行：fcrawl sites | probe | crawl | report | card | export"""
from __future__ import annotations

import argparse
import json
import logging
import sys

from . import config
from .export import card_markdown, report_markdown
from .fetcher import Fetcher
from .list_parser import auto_detect, describe_clusters
from .pipeline import crawl_site, export_site
from .sites import all_sites, get_site
from .store import Store


def cmd_sites(_: argparse.Namespace) -> int:
    for s in all_sites().values():
        print(f"{s.id:16s} {s.school} {s.college}  [{s.cms}]  {s.list.urls[0]}")
    return 0


def cmd_probe(a: argparse.Namespace) -> int:
    """接入新学院：看看列表页里哪些链接簇像教师名单。"""
    with Fetcher(min_interval=1.0) as f:
        page = f.get(a.url, force=True)
    print(f"状态 {page.status}，最终 URL {page.final_url}，HTML {len(page.html)} 字符")
    print("\n候选教师链接簇（选择器 / 人数 / 示例）：")
    for key, n, names in describe_clusters(page.html):
        print(f"  {n:4d}  {key}\n        {'、'.join(names)}")
    stubs = auto_detect(page.html, page.final_url)
    print(f"\n自动模式识别到 {len(stubs)} 位教师。前 5 位：")
    for s in stubs[:5]:
        print(f"  {s.name}  {s.url}")
    if len(stubs) < 5:
        print("\n人数过少：可能是 JS 渲染、图片列表或分页，需要人工查看或启用 Playwright。")
    return 0


def cmd_crawl(a: argparse.Namespace) -> int:
    ids = list(all_sites()) if a.site == "all" else [a.site]
    rc = 0
    with Fetcher(use_cache=not a.no_cache, max_age_hours=a.max_age) as f:
        store = Store()
        for sid in ids:
            site = get_site(sid)
            teachers, rep = crawl_site(site, fetcher=f, store=store, limit=a.limit)
            print(f"\n== {sid}: 列表 {rep.stubs} 条，详情成功 {rep.detail_ok}，失败 {rep.detail_failed}，覆盖率 {rep.coverage:.0%}")
            print("字段填充率：" + "，".join(f"{k} {v:.0%}" for k, v in rep.fill_rates.items()))
            for n in rep.notes:
                print(f"  告警：{n}")
            print(f"  导出目录：{config.EXPORT_DIR / sid}")
            if rep.coverage < 0.95:
                rc = 2
        print(f"\n网络请求 {f.stats['network']} 次，缓存命中 {f.stats['cache']} 次，失败 {f.stats['errors']} 次")
    return rc


def cmd_report(a: argparse.Namespace) -> int:
    store = Store()
    rep = store.last_report(a.site)
    if not rep:
        print("还没有运行记录，先执行 fcrawl crawl", a.site)
        return 1
    print(report_markdown(a.site, rep, store.teachers(a.site)))
    return 0


def cmd_card(a: argparse.Namespace) -> int:
    hits = Store().find(a.name)
    if a.school:
        hits = [t for t in hits if a.school in t.school]
    if not hits:
        print("未找到。可先用 fcrawl crawl <site> 抓取对应学院。")
        return 1
    for t in hits:
        print(card_markdown(t))
        print("\n---\n")
    return 0


def cmd_export(a: argparse.Namespace) -> int:
    store = Store()
    rep = store.last_report(a.site)
    teachers = store.teachers(a.site)
    if not rep:
        print("还没有运行记录")
        return 1
    print(json.dumps(export_site(a.site, teachers, rep), ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fcrawl", description="高校教师画像抓取")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sites", help="列出已配置的学院").set_defaults(fn=cmd_sites)
    sp = sub.add_parser("probe", help="分析一个新的师资列表页")
    sp.add_argument("url")
    sp.set_defaults(fn=cmd_probe)
    sp = sub.add_parser("crawl", help="抓取学院（site id 或 all）")
    sp.add_argument("site")
    sp.add_argument("--limit", type=int, help="只抓前 N 位，用于调试")
    sp.add_argument("--no-cache", action="store_true", help="忽略本地缓存，全部重新抓")
    sp.add_argument("--max-age", type=float, default=None, help="缓存超过 N 小时则重抓")
    sp.set_defaults(fn=cmd_crawl)
    sp = sub.add_parser("report", help="查看最近一次质量报告")
    sp.add_argument("site")
    sp.set_defaults(fn=cmd_report)
    sp = sub.add_parser("card", help="输出教师画像卡")
    sp.add_argument("name")
    sp.add_argument("--school")
    sp.set_defaults(fn=cmd_card)
    sp = sub.add_parser("export", help="重新导出 CSV 与画像卡")
    sp.add_argument("site")
    sp.set_defaults(fn=cmd_export)
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
