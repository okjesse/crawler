"""HTML 工具：编码探测、转纯文本、链接补全。"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urldefrag

from selectolax.lexbor import LexborHTMLParser as HTMLParser, LexborNode as Node

_META_CHARSET_RE = re.compile(rb"""charset=["']?\s*([\w\-]+)""", re.I)
BLOCK_TAGS = {
    "p", "div", "br", "li", "ul", "ol", "tr", "td", "th", "table", "h1", "h2", "h3", "h4",
    "h5", "h6", "section", "article", "header", "footer", "dd", "dt", "dl", "blockquote", "pre",
}
DROP_TAGS = {"script", "style", "noscript", "iframe", "svg", "template"}


def decode_html(content: bytes, header_charset: str | None = None) -> str:
    """按 响应头 → meta → 常见中文编码 的顺序解码。"""
    candidates: list[str] = []
    if header_charset:
        candidates.append(header_charset)
    m = _META_CHARSET_RE.search(content[:4096])
    if m:
        candidates.append(m.group(1).decode("ascii", "ignore"))
    candidates += ["utf-8", "gb18030"]
    seen: set[str] = set()
    for enc in candidates:
        enc_l = enc.lower().replace("gb2312", "gb18030").replace("gbk", "gb18030")
        if enc_l in seen:
            continue
        seen.add(enc_l)
        try:
            return content.decode(enc_l)
        except (UnicodeDecodeError, LookupError):
            continue
    return content.decode("utf-8", "ignore")


def parse(html: str) -> HTMLParser:
    return HTMLParser(html)


def absolutize(base_url: str, href: str | None) -> str | None:
    if not href:
        return None
    href = href.strip()
    if href.startswith(("javascript:", "mailto:", "#", "tel:")):
        return None
    url, _frag = urldefrag(urljoin(base_url, href))
    return url


def clean_ws(text: str) -> str:
    text = text.replace("\xa0", " ").replace("　", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def node_text(node: Node | None, sep: str = " ") -> str:
    if node is None:
        return ""
    return clean_ws(node.text(separator=sep, strip=True))


def html_to_text(html_or_node: str | Node | HTMLParser) -> str:
    """把 HTML 转成保留块级换行的纯文本，供启发式抽取和 LLM 使用。"""
    if isinstance(html_or_node, str):
        tree = HTMLParser(html_or_node)
        root = tree.body or tree.root
    elif isinstance(html_or_node, HTMLParser):
        root = html_or_node.body or html_or_node.root
    else:
        root = html_or_node
    if root is None:
        return ""
    parts: list[str] = []

    def walk(n: Node) -> None:
        for child in n.iter(include_text=True):
            tag = child.tag
            if tag == "-text":
                t = child.text(deep=False)
                if t:
                    parts.append(t)
                continue
            if tag in DROP_TAGS:
                continue
            is_block = tag in BLOCK_TAGS
            if is_block:
                parts.append("\n")
            walk(child)
            if is_block:
                parts.append("\n")

    walk(root)
    return clean_ws("".join(parts))


def css_path(node: Node, depth: int = 3) -> str:
    """生成简短的 CSS 路径，用于模板调试。"""
    segs: list[str] = []
    cur: Node | None = node
    while cur is not None and cur.tag not in ("html", "body", None) and len(segs) < depth:
        seg = cur.tag
        attrs = cur.attributes or {}
        if attrs.get("id") and not re.search(r"\d", attrs["id"]):
            seg += f"#{attrs['id']}"
        elif attrs.get("class"):
            # 忽略带序号的 class（n1、column-2、i4、active），否则同一列表的每项会被拆成不同结构
            classes = [c for c in attrs["class"].split()
                       if c and not re.search(r"\d", c) and c not in ("active", "selected", "on", "current", "first", "last")]
            if classes:
                seg += "." + ".".join(classes[:2])
        segs.append(seg)
        cur = cur.parent
    return " > ".join(reversed(segs))
