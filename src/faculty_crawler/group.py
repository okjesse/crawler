"""课题组成员推断：以本人为末位（通讯）作者的论文中的第一作者，多为在读学生或博后。"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from .models import Teacher
from .names import NameForms, match_author, norm_token


def _split(full: str) -> tuple[str, str, str]:
    """Europe PMC fullName 形如 "Cao B" 或 "Liu Shixuan"：返回 (姓, 名, 首字母)。"""
    parts = full.replace(",", " ").split()
    if not parts:
        return "", "", ""
    last, rest = parts[0], parts[1:]
    rest_s = " ".join(rest)
    initials = rest_s if rest_s.isupper() and len(rest_s.replace(" ", "")) <= 3 else "".join(w[0] for w in rest if w)
    return last, rest_s, initials


def infer_group(t: Teacher, nf: NameForms, window_years: int = 4) -> dict:
    this_year = date.today().year
    since = this_year - window_years + 1
    members: dict[str, dict] = defaultdict(lambda: {"papers": 0, "latest_year": 0, "example": ""})
    n_papers = 0
    for p in t.publications:
        if p.position not in ("last", "solo") or not p.year or p.year < since or not p.authors or not p.journal:
            continue
        n_papers += 1
        first = p.authors[0]
        last, given, initials = _split(first)
        if match_author(nf, last, given, initials):
            continue  # 本人自己是第一作者
        key = norm_token(first)
        m = members[key]
        m["name"] = first
        m["papers"] += 1
        if p.year >= m["latest_year"]:
            m["latest_year"], m["example"] = p.year, p.url
    ranked = sorted(members.values(), key=lambda m: (-m["latest_year"], -m["papers"]))
    recent = [m for m in ranked if m["latest_year"] >= this_year - 1]
    return {
        "window_years": window_years,
        "last_author_papers": n_papers,
        "first_authors": ranked[:15],
        "estimated_size": len(ranked),
        "recent_members": len(recent),
        "note": "按末位作者论文的第一作者估计，是课题组规模的下限；不含未发表论文的成员",
    }
