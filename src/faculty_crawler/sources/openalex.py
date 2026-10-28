"""OpenAlex：作者 h 指数、论文总数、研究主题。需要 OPENALEX_API_KEY（免费申请），未配置时跳过。"""
from __future__ import annotations

import json
import logging
import os
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


def author_profile(api: Fetcher, nf: NameForms, inst: Institution, orcid: str | None) -> dict | None:
    """优先按 ORCID 精确取作者；没有 ORCID 时按姓名 + 机构 ROR 检索，且要求姓名完全一致。"""
    if not api_key():
        return None
    try:
        if orcid:
            d = _get(api, f"/authors/https://orcid.org/{quote(orcid)}", {})
            cands = [d]
        else:
            if not inst.ror:
                return None
            name = f"{nf.given.capitalize()} {nf.surnames[0].capitalize()}"
            d = _get(api, "/authors", {
                "search": name,
                "filter": f"affiliations.institution.ror:{inst.ror}",
                "per_page": 10,
            })
            cands = []
            for a in d.get("results", []):
                toks = [norm_token(t) for t in a.get("display_name", "").split()]
                if len(toks) >= 2 and toks[-1] in nf.surnames and "".join(toks[:-1]) == nf.given:
                    cands.append(a)
            if len(cands) > 1:
                log.info("OpenAlex 同名同校作者 %d 个，取论文最多的一个", len(cands))
            cands.sort(key=lambda a: -a.get("works_count", 0))
        if not cands:
            return None
        a = cands[0]
        stats = a.get("summary_stats", {}) or {}
        return {
            "openalex_id": a.get("id"),
            "h_index": stats.get("h_index"),
            "i10_index": stats.get("i10_index"),
            "works_count": a.get("works_count"),
            "cited_by_count": a.get("cited_by_count"),
            "topics": [t.get("display_name") for t in (a.get("topics") or [])[:5]],
            "same_name_same_school": len(cands) if not orcid else 1,
            "orcid": (a.get("orcid") or "").replace("https://orcid.org/", "") or None,
        }
    except (FetchError, json.JSONDecodeError, KeyError) as e:
        log.warning("OpenAlex 查询失败：%s", e)
        return None
