"""命令行：fcrawl profile | enrich | card | sites | probe | crawl | report | export"""
from __future__ import annotations

import argparse
import json
import logging
import sys

from . import config
from datetime import datetime

from .export import card_markdown, report_markdown, write_cards, write_csv
from .inputs import TeacherInput, load_inputs
from .models import SiteReport
from .profile import build_profile
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


def _api() -> Fetcher:
    # 学术 API：不受网站 robots 约束（官方开放接口），间隔 1 秒
    return Fetcher(min_interval=1.0, respect_robots=False)


def cmd_profile(a: argparse.Namespace) -> int:
    inp = TeacherInput(name=a.name, school=a.school, college=a.college, profile_url=a.url,
                       email=a.email, title=a.title, name_en=a.name_en)
    with Fetcher() as web, _api() as api:
        t = build_profile(inp, web=web, api=api, papers=not a.no_papers)
    store = Store()
    store.save_site("input", [t], SiteReport(site_id="input", teachers=1), mark_inactive=False)
    md = card_markdown(t)
    if a.out:
        out = config.EXPORT_DIR / "profiles"
        out.mkdir(parents=True, exist_ok=True)
        path = write_cards([t], out, clean=False)[0]
        print(f"画像卡已写入：{path}")
    print(md)
    return 0


def cmd_enrich(a: argparse.Namespace) -> int:
    inputs = load_inputs(a.input)
    if a.limit:
        inputs = inputs[: a.limit]
    store = Store()
    done = store.recent_keys("input", a.max_age_days) if not a.force else set()
    out_dir = config.EXPORT_DIR / (a.name or f"batch_{datetime.now():%Y%m%d_%H%M}")
    results = []
    with Fetcher() as web, _api() as api:
        for i, inp in enumerate(inputs, 1):
            cached = store.get_input(inp.name, inp.school, inp.profile_url) if done else None
            if cached and cached.key in done:
                results.append(cached)
                print(f"[{i}/{len(inputs)}] {inp.school} {inp.name}：{a.max_age_days} 天内已处理，跳过")
                continue
            try:
                t = build_profile(inp, web=web, api=api, papers=not a.no_papers)
            except Exception as e:  # 单个老师失败不影响整批
                print(f"[{i}/{len(inputs)}] {inp.school} {inp.name}：失败 {e}")
                continue
            store.save_site("input", [t], SiteReport(site_id="input", teachers=1), mark_inactive=False)
            results.append(t)
            print(f"[{i}/{len(inputs)}] {inp.school} {inp.name}：优先级 {t.priority}，"
                  f"论文 {t.metrics.get('papers_5y', 0)} 篇，邮箱 {t.email or '无'}，问题 {len(t.issues)} 个")
    results.sort(key=lambda t: (-t.priority, t.name))
    write_csv(results, out_dir / "teachers.csv")
    write_cards(results, out_dir / "cards")
    print(f"\n共 {len(results)} 位；名单 {out_dir / 'teachers.csv'}；画像卡 {out_dir / 'cards'}")
    print(f"网页请求 {web.stats['network']} 次，API 请求 {api.stats['network']} 次，缓存命中 {web.stats['cache'] + api.stats['cache']} 次")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fcrawl", description="高校教师画像抓取")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("profile", help="单个老师：抓主页 + 论文，输出画像卡")
    sp.add_argument("name")
    sp.add_argument("--school", required=True)
    sp.add_argument("--college")
    sp.add_argument("--url", help="个人主页链接")
    sp.add_argument("--email")
    sp.add_argument("--title")
    sp.add_argument("--name-en")
    sp.add_argument("--no-papers", action="store_true", help="不查论文")
    sp.add_argument("--out", action="store_true", help="同时把画像卡写到 data/export/profiles")
    sp.set_defaults(fn=cmd_profile)
    sp = sub.add_parser("enrich", help="批量：读取外部教师名单（csv/json/jsonl/xlsx），逐个生成画像")
    sp.add_argument("input")
    sp.add_argument("--name", help="输出目录名，默认 batch_时间")
    sp.add_argument("--limit", type=int)
    sp.add_argument("--max-age-days", type=float, default=30, help="多少天内处理过的老师直接复用")
    sp.add_argument("--force", action="store_true", help="全部重新处理")
    sp.add_argument("--no-papers", action="store_true")
    sp.set_defaults(fn=cmd_enrich)
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
