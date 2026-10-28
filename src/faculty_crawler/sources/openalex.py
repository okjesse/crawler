"""OpenAlex：作者 h 指数、论文总数、研究主题。需要 OPENALEX_API_KEY（免费申请），未配置时跳过。"""
from __future__ import annotations

import json
import logging
import os
import re
from urllib.parse import quote, urlencode

from .. import config
from ..fetcher import FetchError, Fetcher
from ..institutions import Institution
from ..names import NameForms, norm_token

log = logging.getLogger(__name__)
API = "https://api.openalex.org"


def api_key() -> str | None:
    key = os.environ.get("OPENALEX_API_KEY")
    if key:
        return key.strip()
    env = config.DATA_DIR / ".env"
    if env.exists():
        for ln in env.read_text("utf-8").splitlines():
            if ln.startswith("OPENALEX_API_KEY="):
                return ln.split("=", 1)[1].strip() or None
    return None


def _get(api: Fetcher, path: str, params: dict) -> dict:
    key = api_key()
    params = {**params, "api_key": key}
    page = api.get(f"{API}{path}?{urlencode(params)}")
    if page.status != 200:
        raise FetchError(f"OpenAlex HTTP {page.status}")
    return json.loads(page.html)


def _name_matches(display_name: str, nf: NameForms) -> bool:
    """OpenAlex 显示名与本人是否一致：拼音全名、学到的写法、带中间名、或主页学到的缩写（Po-Hsiang → PH）。"""
    raw = [t for t in re.split(r"[\s,]+", display_name) if t]
    if len(raw) < 2:
        return False
    for last_i, given_parts in ((-1, raw[:-1]), (0, raw[1:])):
        if norm_token(raw[last_i]) not in nf.surnames:
            continue
        joined = norm_token("".join(given_parts))
        first = norm_token(given_parts[0])
        initials = "".join(norm_token(x)[:1] for p in given_parts for x in re.split(r"[-‐‑–—]", p) if norm_token(x))
        if joined == nf.given or first == nf.given or joined in nf.alt_given or first in nf.alt_given:
            return True
        if initials in nf.learned_initials:
            return True
    return False


def _summary(a: dict, n_cands: int, overlap: int) -> dict:
    stats = a.get("summary_stats", {}) or {}
    return {
        "openalex_id": a.get("id"),
        "h_index": stats.get("h_index"),
        "i10_index": stats.get("i10_index"),
        "works_count": a.get("works_count"),
        "cited_by_count": a.get("cited_by_count"),
        "topics": [t.get("display_name") for t in (a.get("topics") or [])[:5]],
        "same_name_same_school": n_cands,
        "verified_by_doi": overlap,
        "orcid": (a.get("orcid") or "").replace("https://orcid.org/", "") or None,
    }


def author_profile(api: Fetcher, nf: NameForms, inst: Institution, orcid: str | None,
                   known_dois: list[str] | None = None) -> dict | None:
    """取 OpenAlex 作者档案。

    1. 有已确认论文：用前几篇的 DOI 反查作者编号（作者姓名须与本人一致），取多数一致的编号。
       OpenAlex 偶尔把同一人拆成多个编号，此时指标只覆盖其中一部分，会在结果里注明。
    2. 没有可用 DOI：只接受经 ORCID 精确取到的档案，并标注“未经论文验证”；不采用按姓名搜索的结果。
    """
    if not api_key():
        return None
    dois = [d for d in (known_dois or []) if d]
    try:
        if dois:
            from collections import Counter
            votes: Counter[str] = Counter()
            sample = list(dict.fromkeys(dois[:2] + dois[-3:]))  # 新旧论文都抽：新论文常挂在碎片档案上
            for doi in sample:
                try:
                    w = _get(api, f"/works/https://doi.org/{quote(doi)}", {"select": "id,authorships"})
                except FetchError:
                    continue
                for au in w.get("authorships", []):
                    if not (au.get("author") or {}).get("id"):
                        continue  # 没有作者编号的署名跳过
                    if _name_matches(au["author"].get("display_name", ""), nf):
                        votes[au["author"]["id"]] += 1
            if not votes:
                return {"rejected": "OpenAlex 中找不到与已确认论文对应的作者档案，未采用其指标"}
            # 这些档案都至少包含一篇已确认论文；取论文最多的那个作为主档案
            authors = []
            for aid, _ in votes.most_common(4):
                try:
                    authors.append(_get(api, f"/authors/{aid.rsplit('/', 1)[-1]}", {}))
                except FetchError:
                    continue
            if not authors:
                return {"rejected": "OpenAlex 作者档案读取失败，未采用其指标"}
            a = max(authors, key=lambda x: x.get("works_count", 0))
            out = _summary(a, len(votes), votes[a["id"]])
            if len(votes) > 1:
                out["note"] = f"OpenAlex 把本人拆成了 {len(votes)} 个作者档案，指标只取论文最多的一个，可能偏低"
            return out
        if orcid:
            a = _get(api, f"/authors/https://orcid.org/{quote(orcid)}", {})
            out = _summary(a, 1, -1)
            out["note"] = "没有可用于交叉验证的论文，指标按 ORCID 取得，未经论文验证"
            return out
        return None
    except (FetchError, json.JSONDecodeError, KeyError) as e:
        log.warning("OpenAlex 查询失败：%s", e)
        return None
