"""列表页解析：模板模式 + 自动模式（人名链接聚类）。"""
from __future__ import annotations

import re
from collections import defaultdict

from selectolax.lexbor import LexborHTMLParser as HTMLParser, LexborNode as Node

from .html_utils import absolutize, css_path, node_text
from .models import TeacherStub
from .normalize import clean_name, is_plausible_name
from .sites import FieldRule, ListRule


def _apply(node: Node, rule: FieldRule | None) -> str | None:
    if rule is None:
        return None
    val: str | None = None
    if rule.attr:
        val = (node.attributes or {}).get(rule.attr)
    if not val and rule.text:
        val = node_text(node)
    if val and rule.regex:
        m = re.search(rule.regex, val)
        val = m.group(1) if m else None
    return val.strip() if val else None


def _stub_from_node(a: Node, rule: ListRule, base_url: str, group: str | None) -> TeacherStub | None:
    raw_name = _apply(a, rule.name) or ""
    label = _apply(a, rule.label) if rule.label else raw_name
    name = clean_name(raw_name)
    if not is_plausible_name(name):
        return None
    url = absolutize(base_url, _apply(a, rule.url))
    extra: dict[str, str] = {}
    if rule.title:
        t = _apply(a, rule.title)
        if t:
            extra["title"] = t
    if label and label != name:
        extra["label"] = label
    return TeacherStub(name=name, url=url, group=group, extra=extra)


def parse_list(html: str, base_url: str, rule: ListRule) -> list[TeacherStub]:
    tree = HTMLParser(html)
    if rule.mode == "auto":
        return auto_detect(html, base_url)
    scope: Node | None = tree.css_first(rule.scope) if rule.scope else (tree.body or tree.root)
    if scope is None:
        return []
    out: list[TeacherStub] = []
    if rule.mode == "grouped" and rule.section:
        for sec in scope.css(rule.section):
            sec_title = node_text(sec.css_first(rule.section_title)) if rule.section_title else ""
            groups = sec.css(rule.group) if rule.group else [sec]
            for g in groups:
                g_title = node_text(g.css_first(rule.group_title)) if rule.group_title else ""
                group = " / ".join(x for x in (sec_title, g_title) if x) or None
                for a in g.css(rule.item):
                    stub = _stub_from_node(a, rule, base_url, group)
                    if stub:
                        out.append(stub)
    else:
        for a in scope.css(rule.item):
            stub = _stub_from_node(a, rule, base_url, None)
            if stub:
                out.append(stub)
    return out


def webplus_page_urls(html: str, first_url: str, max_pages: int) -> list[str]:
    """博达 WebPlus 分页：list.htm, list2.htm, ... listN.htm。"""
    m = re.search(r'class="all_pages"[^>]*>\s*(\d+)\s*<', html)
    total = int(m.group(1)) if m else 1
    total = min(total, max_pages)
    if total <= 1 or not first_url.endswith("list.htm"):
        return []
    stem = first_url[: -len("list.htm")]
    return [f"{stem}list{i}.htm" for i in range(2, total + 1)]


def auto_detect(html: str, base_url: str, min_cluster: int = 5) -> list[TeacherStub]:
    """没有模板时：把“文字像人名的链接”按父级结构聚类，取最大的簇。

    导航栏里的“学院简介”等会被 is_plausible_name 过滤，剩下的最大簇通常就是师资列表。
    """
    tree = HTMLParser(html)
    clusters: dict[str, list[Node]] = defaultdict(list)
    for a in tree.css("a"):
        name = clean_name((a.attributes or {}).get("title") or node_text(a))
        if not is_plausible_name(name):
            continue
        parent = a.parent
        key = css_path(parent, depth=3) if parent is not None else "root"
        # 列表项一般是 li/td/span 包一层，用祖父节点做键可以把同一列表的项合并
        if parent is not None and parent.tag in ("li", "td", "span", "p", "div") and parent.parent is not None:
            key = css_path(parent.parent, depth=3) + " > " + parent.tag
        clusters[key].append(a)
    if not clusters:
        return []
    # 分组列表的各组结构相同，css 路径一致，已经落在同一个簇里；不同路径的簇（导航栏等）不合并
    ranked = sorted(clusters.items(), key=lambda kv: len(kv[1]), reverse=True)
    _best_key, merged = ranked[0]
    if len(merged) < min_cluster:
        return []
    out: list[TeacherStub] = []
    seen: set[tuple[str, str | None]] = set()
    for a in merged:
        attrs = a.attributes or {}
        name = clean_name(attrs.get("title") or node_text(a))
        url = absolutize(base_url, attrs.get("href"))
        if (name, url) in seen:
            continue
        seen.add((name, url))
        label = attrs.get("title") or node_text(a)
        extra = {"label": label} if label != name else {}
        out.append(TeacherStub(name=name, url=url, extra=extra))
    return out


def describe_clusters(html: str, top: int = 5) -> list[tuple[str, int, list[str]]]:
    """供接入新站点时查看：每个候选簇的选择器、人数、示例姓名。"""
    tree = HTMLParser(html)
    clusters: dict[str, list[str]] = defaultdict(list)
    for a in tree.css("a"):
        name = clean_name((a.attributes or {}).get("title") or node_text(a))
        if not is_plausible_name(name):
            continue
        parent = a.parent
        key = css_path(parent, depth=3) if parent is not None else "root"
        if parent is not None and parent.tag in ("li", "td", "span", "p", "div") and parent.parent is not None:
            key = css_path(parent.parent, depth=3) + " > " + parent.tag
        clusters[key].append(name)
    ranked = sorted(clusters.items(), key=lambda kv: len(kv[1]), reverse=True)[:top]
    return [(k, len(v), v[:8]) for k, v in ranked]
