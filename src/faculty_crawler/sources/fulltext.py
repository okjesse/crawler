"""开放获取论文全文：从“材料与方法”识别耗材/试剂品牌、国产/进口倾向、实验技术。

只看本人为第一或末位作者的论文，合作论文的方法部分反映的是别的课题组。
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from functools import lru_cache

import yaml

from .. import config
from ..fetcher import FetchError, Fetcher
from ..models import Publication

log = logging.getLogger(__name__)
FULLTEXT = "https://www.ebi.ac.uk/europepmc/webservices/rest/{}/fullTextXML"
METHOD_TITLE = re.compile(r"method|materials|experimental (procedures|section)|star\s*\*?\s*methods|实验", re.I)


@lru_cache(maxsize=1)
def brand_config() -> dict:
    d = yaml.safe_load((config.PKG_DIR / "brands.yaml").read_text("utf-8"))
    for name, spec in d["brands"].items():
        # 前后都要求词边界：roche 不匹配 rochester，sigma 只认 Sigma-Aldrich 或括号里的 “Sigma,”
        spec["_re"] = re.compile("|".join(f"(?<![a-z])(?:{p})(?![a-z])" for p in spec["patterns"]), re.I)
    d["_consumable_re"] = re.compile(r"(?<![a-z])(" + "|".join(re.escape(w) for w in d["consumable_words"]) + r")(?![a-z])", re.I)
    return d


def methods_text(xml: str) -> str:
    """取 JATS 全文中的方法章节文本；找不到方法章节返回空串。"""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        xml = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#)", "&amp;", xml)
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            return ""
    body = root.find(".//body")
    if body is None:
        return ""
    chunks = []
    for sec in body.iter("sec"):
        title = sec.findtext("title") or ""
        stype = sec.get("sec-type") or ""
        if "method" in stype.lower() or METHOD_TITLE.search(title):
            chunks.append(" ".join("".join(sec.itertext()).split()))
    # 去掉嵌套重复：保留不被其他片段包含的
    chunks.sort(key=len, reverse=True)
    out: list[str] = []
    for c in chunks:
        if not any(c in o for o in out):
            out.append(c)
    return "\n".join(out)


ABBREV = re.compile(r"(?:\b(?:st|inc|co|ltd|corp|cat|no|nos|fig|figs|approx|e\.g|i\.e|vs|dr|mr|ref|vol|ca|resp)\.|\b[A-Za-z]\.)$", re.I)


def sentences(text: str) -> list[str]:
    """按句号/分号断句，但不在 St. Inc. Co. Cat. 等缩写和单字母缩写后断开。"""
    out: list[str] = []
    for piece in re.split(r"(?<=[.;])\s+", text):
        prev = out[-1] if out else ""
        # 缩写后、括号未闭合、或片段太短时不断开
        if out and (ABBREV.search(prev) or prev.count("(") > prev.count(")") or len(piece) < 30):
            out[-1] += " " + piece
        else:
            out.append(piece)
    return out


def scan_brands(text: str, url: str) -> dict[str, dict]:
    """返回 {品牌: {kind, origin, mentions, consumable_mentions, snippet, url}}。"""
    cfg = brand_config()
    found: dict[str, dict] = {}
    for sent in sentences(text):
        for name, spec in cfg["brands"].items():
            if not spec["_re"].search(sent):
                continue
            f = found.setdefault(name, {"kind": spec["kind"], "origin": spec["origin"], "mentions": 0,
                                        "consumable_mentions": 0, "snippet": "", "url": url})
            f["mentions"] += 1
            is_cons = bool(cfg["_consumable_re"].search(sent))
            if is_cons:
                f["consumable_mentions"] += 1
            if not f["snippet"] or (is_cons and not f.get("_snip_cons")):
                f["snippet"] = sent[:220]
                f["_snip_cons"] = is_cons
    for f in found.values():
        f.pop("_snip_cons", None)
    return found


def mine(api: Fetcher, pubs: list[Publication], max_papers: int = 6) -> dict:
    cands = [p for p in pubs if p.open_access and p.pmcid and p.position in ("first", "last", "solo") and p.journal]
    cands.sort(key=lambda p: (-(p.year or 0), p.position != "last"))
    cands = cands[:max_papers]
    brands: dict[str, dict] = defaultdict(lambda: {"papers": 0, "consumable_papers": 0, "mentions": 0,
                                                   "consumable_mentions": 0, "examples": []})
    scanned, no_methods = [], 0
    texts = []
    for p in cands:
        try:
            page = api.get(FULLTEXT.format(p.pmcid), retries=1, cache_errors=True)  # 全文不开放时接口返回 4xx/5xx，不必反复重试
            if page.status != 200:
                raise FetchError(f"HTTP {page.status}")
            xml = page.html
        except FetchError as e:
            log.info("全文获取失败 %s: %s", p.pmcid, e)
            continue
        text = methods_text(xml)
        if not text:
            no_methods += 1
            continue
        scanned.append({"pmcid": p.pmcid, "year": p.year, "title": p.title[:120], "url": p.url})
        texts.append((text.lower(), p.url))
        for name, f in scan_brands(text, p.url).items():
            b = brands[name]
            b.update(kind=f["kind"], origin=f["origin"])
            b["papers"] += 1
            b["mentions"] += f["mentions"]
            b["consumable_mentions"] += f["consumable_mentions"]
            if f["consumable_mentions"]:
                b["consumable_papers"] += 1
            if len(b["examples"]) < 2:
                b["examples"].append({"snippet": f["snippet"], "url": f["url"], "year": p.year})
    origin = {"domestic": 0, "import": 0}
    for b in brands.values():
        origin[b["origin"]] = origin.get(b["origin"], 0) + b["papers"]
    total = origin["domestic"] + origin["import"]
    return {
        "candidates": len(cands),
        "scanned": scanned,
        "no_methods": no_methods,
        # 远赞 > 有耗材语境的耗材品牌 > 其他耗材品牌 > 试剂
        "brands": dict(sorted(brands.items(), key=lambda kv: (
            {"own": 0, "consumable": 1}.get(kv[1]["kind"], 2) + (0 if kv[1]["consumable_papers"] or kv[1]["kind"] != "consumable" else 0.5),
            -kv[1]["papers"], -kv[1]["mentions"]))),
        "domestic_share": round(origin["domestic"] / total, 2) if total else None,
        "_texts": texts,  # 供技术标签使用，不落库
    }
