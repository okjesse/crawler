"""Europe PMC：论文、作者单位、MeSH、资助号。逐篇核对作者本人单位并用锚点消歧。"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlencode

from ..fetcher import FetchError, Fetcher
from ..institutions import Institution
from ..models import Grant, Publication
from ..names import NameForms, learn_from_seeds, match_author, norm_token

log = logging.getLogger(__name__)
API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# 院系比对时忽略的泛词：只保留有区分度的词（如 life, biotechnology, instrument, electronic）
STOP = {"of", "and", "the", "for", "school", "university", "college", "department", "dept", "china", "pr", "p", "r",
        "key", "laboratory", "laboratories", "lab", "state", "national", "center", "centre", "institute", "road",
        "science", "sciences", "engineering", "research", "technology", "technologies", "joint", "international",
        "ministry", "education", "province", "provincial", "municipal", "shanghai", "beijing", "nanjing", "jiangsu",
        "academy", "medical", "hospital", "affiliated", "people", "republic", "division", "program", "faculty"}
# 学院中文名中的关键词 → 论文单位里常见的英文写法
COLLEGE_HINTS = {
    "生命科学": ["life science"], "生物药物": ["biopharm", "life science and technology"], "药": ["pharm"],
    "医": ["medic", "hospital", "clinical"], "农": ["agricult"], "化学": ["chemi"], "化工": ["chemical engineering"],
    "生物工程": ["bioengineering", "biological engineering"], "环境": ["environment"], "食品": ["food"],
    "基础医学": ["basic medic"], "公共卫生": ["public health"], "海洋": ["marine", "ocean"],
    "植物": ["plant"], "动物": ["animal"], "园艺": ["horticult"], "林": ["forest"], "Bio-X": ["bio-x"],
}


def college_hints(college: str | None, inst: Institution) -> list[str]:
    """学院名 → 英文院系关键词。只用最具体（最长）的中文键，并去掉校名里本来就有的词。"""
    if not college:
        return []
    keys = sorted((k for k in COLLEGE_HINTS if k in college), key=len, reverse=True)
    if not keys:
        return []
    school_names = " ".join(inst.aff_patterns())
    return [h for h in COLLEGE_HINTS[keys[0]] if h not in school_names]


@dataclass
class PaperResult:
    confirmed: list[Publication] = field(default_factory=list)
    possible: list[Publication] = field(default_factory=list)
    orcid: str | None = None
    emails: list[str] = field(default_factory=list)
    anchors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    query: str = ""


def _q(s: str) -> str:
    return '"' + s.replace('"', "") + '"'


def build_query(nf: NameForms, inst: Institution, since: int | None) -> str:
    auth = " OR ".join(f"AUTH:{_q(n)}" for n in nf.query_names())
    affs = [inst.en, *inst.aliases] if inst.en else [inst.zh]
    aff = " OR ".join(f"AFF:{_q(a)}" for a in dict.fromkeys(affs) if a)
    q = f"({auth}) AND ({aff})"
    if since:
        q += f" AND PUB_YEAR:[{since} TO {date.today().year}]"
    return q


def fetch_raw(api: Fetcher, query: str, max_results: int = 300) -> list[dict]:
    out: list[dict] = []
    cursor = "*"
    while len(out) < max_results:
        params = {"query": query, "resultType": "core", "format": "json", "pageSize": 100,
                  "cursorMark": cursor, "sort": "P_PDATE_D desc"}
        page = api.get(f"{API}?{urlencode(params)}")
        d = json.loads(page.html)
        res = d.get("resultList", {}).get("result", [])
        out += res
        nxt = d.get("nextCursorMark")
        if not res or not nxt or nxt == cursor:
            break
        cursor = nxt
    return out[:max_results]


def _norm_title(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _position(i: int, n: int) -> str:
    if n == 1:
        return "solo"
    return "first" if i == 0 else "last" if i == n - 1 else "middle"


def nsfc_grant(grant_id: str) -> tuple[int | None, str | None]:
    """国家自然科学基金 8 位资助号：第 1 位学部，第 2-3 位年份，第 4 位项目类别（推断）。"""
    m = re.search(r"\b([1-9])(\d{2})(\d)\d{4}\b", grant_id or "")
    if not m:
        return None, None
    year = 2000 + int(m.group(2))
    if year > date.today().year or year < 2000:
        return None, None
    kind = {"7": "面上", "0": "青年", "3": "重点", "2": "人才类（优青/杰青等）"}.get(m.group(3), "其他")
    return year, kind


def _dept_segment(aff: str, inst: Institution) -> str:
    """作者本人在本校的那一段单位（学校名之前的院系部分）。"""
    for chunk in aff.split("|"):
        low = chunk.lower()
        cut = min((low.find(p) for p in inst.aff_patterns() if p in low), default=-1)
        if cut > 0:
            return low[:cut]
    return ""


def _distinct(seg: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z\-]{2,}", seg)) - STOP


UNIT_RE = re.compile(r"\b(?:school|college|department|dept\.?|faculty)\s+of\s+([a-z][a-z &\-]+?)(?=,|\.|;|\||$| and school| and department)")


def _units(seg: str) -> set[str]:
    """院系一级单位（School of … / Department of …），不含全校共用的重点实验室。"""
    return {re.sub(r"\s+", " ", m.group(1).replace("&", "and")).strip() for m in UNIT_RE.finditer(seg)}


def resolve_papers(nf: NameForms, inst: Institution, raw: list[dict], *, known_email: str | None,
                   seed_text: str, college: str | None, bad_orcids: set[str] | None = None) -> PaperResult:
    pr = PaperResult()
    bad_orcids = bad_orcids or set()
    seed_norm = _norm_title(seed_text)
    known_email = (known_email or "").lower()
    hints = college_hints(college, inst)

    cands = []  # (record, author_index, match_kind, aff, orcid, emails)
    seen_ids: set[str] = set()
    for r in raw:
        rid = r.get("id") or r.get("pmid") or r.get("doi") or r.get("title")
        if rid in seen_ids:
            continue
        seen_ids.add(rid)
        authors = r.get("authorList", {}).get("author", [])
        best = None
        for i, a in enumerate(authors):
            m = match_author(nf, a.get("lastName"), a.get("firstName"), a.get("initials"))
            if not m:
                continue
            affs = [x.get("affiliation", "") for x in a.get("authorAffiliationDetailsList", {}).get("authorAffiliation", [])]
            aff = " | ".join(x for x in affs if x)
            aid = a.get("authorId") or {}
            orcid = aid.get("value") if aid.get("type") == "ORCID" else None
            if orcid in bad_orcids:
                orcid = None  # 实名核对不通过的 ORCID 当作没有
            score = (2 if m == "full" else 1) + (2 if any(p in aff.lower() for p in inst.aff_patterns()) else 0)
            if best is None or score > best[0]:
                best = (score, i, m, aff, orcid, [e.lower().rstrip(".") for e in EMAIL_RE.findall(aff)])
        if best:
            cands.append((r, *best[1:]))

    # 第一轮：强锚点（邮箱、主页论文标题）
    anchors_orcid: set[str] = set()
    anchor_dept: set[str] = set()  # 锚点论文中本人在本校的院系词
    anchor_units: set[str] = set()  # 锚点论文中本人在本校的学院/系
    kinds: dict[int, tuple[str, float]] = {}
    for idx, (r, i, m, aff, orcid, emails) in enumerate(cands):
        title_n = _norm_title(r.get("title", ""))
        if known_email and known_email in emails:
            kinds[idx] = ("email", 0.97)
        elif seed_norm and len(title_n) >= 30 and title_n[:60] in seed_norm:
            kinds[idx] = ("seed", 0.95)
        else:
            continue
        if orcid:
            anchors_orcid.add(orcid)
        anchor_dept |= _distinct(_dept_segment(aff, inst))
        anchor_units |= _units(_dept_segment(aff, inst))
    if anchors_orcid:
        pr.orcid = sorted(anchors_orcid)[0]
        if len(anchors_orcid) > 1:
            pr.notes.append(f"锚点论文出现多个 ORCID：{', '.join(sorted(anchors_orcid))}")
    # 同一 ORCID 的论文也算锚点，用来补充院系画像
    for idx, (r, i, m, aff, orcid, emails) in enumerate(cands):
        if idx not in kinds and orcid and orcid in anchors_orcid:
            kinds[idx] = ("orcid", 0.95)
            anchor_dept |= _distinct(_dept_segment(aff, inst))
            anchor_units |= _units(_dept_segment(aff, inst))
    pr.anchors = sorted({k for k, _ in kinds.values()})

    # 第二轮：其余候选。院系要和锚点或学院名一致，否则只列为待确认
    for idx, (r, i, m, aff, orcid, emails) in enumerate(cands):
        if idx in kinds:
            continue
        if orcid and anchors_orcid:
            continue  # ORCID 不同 = 另一个人
        seg = _dept_segment(aff, inst)
        if not seg and not any(p in aff.lower() for p in inst.aff_patterns()):
            continue  # 本人单位不是本校
        toks = _distinct(seg)
        units = _units(seg)
        hint_ok = any(h in u for u in units for h in hints) if units else any(h in seg for h in hints)
        if units and anchor_units:
            anchor_ok = bool(units & anchor_units)  # 有学院/系名时必须一致
        else:
            anchor_ok = bool(anchor_dept) and len(toks & anchor_dept) >= 3
        if hint_ok or anchor_ok:
            kinds[idx] = ("full", 0.8) if m == "full" else ("initial", 0.7)
        else:
            kinds[idx] = ("possible", 0.4)

    for idx, (kind, conf) in kinds.items():
        r, i, m, aff, orcid, emails = cands[idx]
        authors = r.get("authorList", {}).get("author", [])
        grants = []
        for g in r.get("grantsList", {}).get("grant", []) or []:
            gid = g.get("grantId")
            grants.append(f"{g.get('agency', '')}|{gid or ''}")
        is_preprint = r.get("source") == "PPR"
        pub = Publication(
            pmid=r.get("pmid"), doi=r.get("doi"), title=(r.get("title") or "").rstrip("."),
            pmcid=r.get("pmcid"), open_access=(r.get("isOpenAccess") == "Y" or r.get("inEPMC") == "Y") and bool(r.get("pmcid")),
            authors=[(a.get("fullName") or f"{a.get('lastName', '')} {a.get('initials', '')}").strip() for a in authors[:40]],
            journal=None if is_preprint else ((r.get("journalInfo", {}).get("journal", {}) or {}).get("medlineAbbreviation")
                                              or (r.get("journalInfo", {}).get("journal", {}) or {}).get("title")),
            year=int(r["pubYear"]) if str(r.get("pubYear", "")).isdigit() else None,
            position=_position(i, len(authors)), n_authors=len(authors), match=kind, confidence=conf,
            author_aff=aff[:400],
            mesh=[mh.get("descriptorName") for mh in r.get("meshHeadingList", {}).get("meshHeading", []) if mh.get("descriptorName")],
            keywords=r.get("keywordList", {}).get("keyword", []) or [],
            grants=grants, cited_by=int(r.get("citedByCount") or 0),
            abstract=(r.get("abstractText") or "")[:1500],
        )
        if kind == "possible":
            pr.possible.append(pub)
        else:
            pr.confirmed.append(pub)
            for e in emails:
                if e not in pr.emails:
                    pr.emails.append(e)
    # 预印本与正式发表版本去重：同标题只保留正式版本
    def dedupe(pubs: list[Publication]) -> list[Publication]:
        best: dict[str, Publication] = {}
        for p in pubs:
            k = _norm_title(p.title)[:80]
            cur = best.get(k)
            if cur is None or (cur.journal is None and p.journal) or (bool(cur.journal) == bool(p.journal) and p.confidence > cur.confidence):
                best[k] = p
        return list(best.values())

    pr.confirmed = dedupe(pr.confirmed)
    pr.possible = [p for p in dedupe(pr.possible) if _norm_title(p.title)[:80] not in {_norm_title(c.title)[:80] for c in pr.confirmed}]
    pr.confirmed.sort(key=lambda p: (-(p.year or 0), p.title))
    if not pr.anchors and pr.confirmed:
        pr.notes.append("没有邮箱或主页论文锚点，论文归属仅凭姓名和单位判断，同名风险较高")
    return pr


def summarize(pubs: list[Publication], years: int = 5) -> dict:
    this_year = date.today().year
    pubs = [p for p in pubs if p.journal]  # 不统计预印本
    recent = [p for p in pubs if p.year and p.year >= this_year - years + 1]
    journals = Counter(p.journal for p in recent if p.journal)
    return {
        "papers_total_found": len(pubs),
        f"papers_{years}y": len(recent),
        "papers_2y": sum(1 for p in pubs if p.year and p.year >= this_year - 1),
        "last_author_5y": sum(1 for p in recent if p.position in ("last", "solo")),
        "first_author_5y": sum(1 for p in recent if p.position == "first"),
        "latest_year": max((p.year for p in pubs if p.year), default=None),
        "citations_5y": sum(p.cited_by for p in recent),
        "top_journals": [f"{j}（{n}）" for j, n in journals.most_common(5)],
        "top_mesh": [m for m, _ in Counter(m for p in recent for m in p.mesh
                                           if m not in ("Humans", "Animals", "Mice", "Female", "Male")).most_common(10)],
    }


def collect_grants(pubs: list[Publication]) -> list[Grant]:
    agg: dict[tuple[str, str], Grant] = {}
    for p in pubs:
        for g in p.grants:
            agency, _, gid = g.partition("|")
            gid = gid.strip() or None
            key = (agency.strip(), gid or "")
            if key in agg:
                agg[key].n_papers += 1
                continue
            year, kind = (nsfc_grant(gid) if gid and "natural science foundation of china" in agency.lower() else (None, None))
            agg[key] = Grant(agency=agency.strip(), grant_id=gid, year=year, kind=kind, source_url=p.url)
    return sorted(agg.values(), key=lambda g: (-(g.year or 0), -g.n_papers))


def _seed_titles(seed_text: str, limit: int = 4) -> list[str]:
    """从主页论文条目中取标题。

    兼容三种写法：引号包住标题；“作者. 标题. 期刊”；“作者, 作者, 标题, 期刊, 年份”。
    标题段的特征：至少 6 个词、含两个以上小写开头的词、不含 * # et al。
    """
    titles = []
    for ln in seed_text.split("\n"):
        q = re.search(r"[\"“]([^\"”]{25,300})[\"”]", ln)
        if q:
            titles.append(q.group(1).strip(" ."))
        else:
            segs = re.split(r"[.?!][\"”]?\s+|,\s+|;\s+", re.sub(r"^\s*\d+[.、]\s*", "", ln))
            cands = [x.strip() for x in segs
                     if len(x.split()) >= 6 and sum(1 for w in x.split() if w[:1].islower()) >= 2
                     and not re.search(r"[*#]|et al|^\d", x)]
            if cands:
                t = max(cands, key=len)
                # 去掉粘在标题前的作者名（如 “Fan: Promiscuous …”“Yu H: Mechanistic …”）
                t = re.sub(r"^(?:[A-Z][a-zA-Z\-]*\s?){1,3}:\s+(?=[A-Z])", "", t)
                titles.append(t[:200])
        if len(titles) >= limit:
            break
    return titles


ORCID_API = "https://pub.orcid.org/v3.0/{}/person"


def orcid_name_ok(api: Fetcher, orcid: str, nf: NameForms) -> bool | None:
    """ORCID 官方登记的姓名是否与本人一致。True 一致，False 不一致，None 查不到/未公开。"""
    try:
        page = api.get(ORCID_API.format(orcid), headers={"Accept": "application/json"})
        d = json.loads(page.html)
    except (FetchError, json.JSONDecodeError):
        return None
    name = d.get("name") or {}
    fam = norm_token(((name.get("family-name") or {}).get("value")) or "")
    giv = norm_token(((name.get("given-names") or {}).get("value")) or "")
    if not fam and not giv:
        return None
    # 姓名顺序可能填反
    for f, g in ((fam, giv), (giv, fam)):
        if f in nf.surnames and (not g or g == nf.given or g in nf.alt_given or g[:1] in {i[:1] for i in nf.initials}):
            return True
    return False


def find_papers(api: Fetcher, nf: NameForms, inst: Institution, *, known_email: str | None = None,
                seed_text: str = "", college: str | None = None, since: int | None = None,
                max_results: int = 300, check_orcid: bool = True) -> PaperResult:
    """检索顺序：主页论文标题（精确，拿 ORCID）→ ORCID 全量 → 姓名 + 学校。"""
    learn_from_seeds(nf, seed_text)
    q = build_query(nf, inst, since)
    raw: list[dict] = []
    capped = False
    try:
        for title in _seed_titles(seed_text):
            words = " ".join(w for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]*", title)[:12])
            if len(words.split()) >= 5:
                raw += fetch_raw(api, f'TITLE:"{words}"', 3)
        pr = resolve_papers(nf, inst, raw, known_email=known_email, seed_text=seed_text, college=college)
        bad: set[str] = set()
        # ORCID 实名核对：论文元数据有时把合作者的 ORCID 标到本人名下
        while check_orcid and pr.orcid and orcid_name_ok(api, pr.orcid, nf) is False:
            bad.add(pr.orcid)
            pr = resolve_papers(nf, inst, raw, known_email=known_email, seed_text=seed_text, college=college, bad_orcids=bad)
        if pr.orcid:
            yr = f" AND PUB_YEAR:[{since} TO {date.today().year}]" if since else ""
            raw += fetch_raw(api, f'AUTHORID:"{pr.orcid}"{yr}', max_results)
        main = fetch_raw(api, q, max_results)
        capped = len(main) >= max_results
        raw += main
        pr = resolve_papers(nf, inst, raw, known_email=known_email, seed_text=seed_text, college=college, bad_orcids=bad)
        while check_orcid and pr.orcid and pr.orcid not in bad and orcid_name_ok(api, pr.orcid, nf) is False:
            bad.add(pr.orcid)
            pr = resolve_papers(nf, inst, raw, known_email=known_email, seed_text=seed_text, college=college, bad_orcids=bad)
        if bad:
            pr.notes.append(f"论文元数据中的 ORCID {', '.join(sorted(bad))} 登记姓名与本人不符（多为合作者），已忽略")
    except (FetchError, json.JSONDecodeError) as e:
        pr = PaperResult(query=q)
        pr.notes.append(f"Europe PMC 查询失败：{e}")
        return pr
    pr.query = q
    if capped:
        pr.notes.append(f"姓名检索结果超过 {max_results} 条（常见姓名），只核对了最新的 {max_results} 条；"
                        + ("已用 ORCID 补全本人论文" if pr.orcid else "建议提供邮箱或英文名以提高准确率"))
    if pr.possible:
        pr.notes.append(f"{len(pr.possible)} 篇论文作者同名同校但院系对不上，未计入统计")
    return pr
