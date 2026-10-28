"""给定一位教师（来自外部名单），抓取主页、论文、学术指标，生成画像。"""
from __future__ import annotations

import logging
import re
from datetime import date
from urllib.parse import urlsplit

from .detail_parser import extract_detail
from .enrich import enrich
from .fetcher import FetchError, Fetcher
from .inputs import TeacherInput
from .institutions import resolve
from .models import Teacher
from .names import name_forms
from .normalize import find_supervisor, normalize_title, school_domains
from .sites import DetailRule
from . import group as group_mod
from . import lab_site as lab_site_mod
from .levels import Plan, resolve_plan
from .sources import europepmc, fulltext, openalex
from .validate import validate_teacher

log = logging.getLogger(__name__)


def input_key(inp: TeacherInput) -> str:
    return inp.id or f"{inp.school}|{inp.college or ''}|{inp.name}|{inp.profile_url or ''}"


def build_profile(inp: TeacherInput, *, web: Fetcher, api: Fetcher, plan: Plan | None = None) -> Teacher:
    plan = plan or resolve_plan()
    P = plan.params
    t = Teacher(site_id="input", school=inp.school, college=inp.college or "", name=inp.name,
                profile_url=inp.profile_url, list_url=None)
    t.raw.update(input_url=inp.profile_url, input_id=inp.id, input_extra=inp.extra,
                 level=plan.level, modules=list(plan.modules), plan_notes=list(plan.notes))
    src = "input://" + input_key(inp)
    t.add("name", inp.name, src, method="input", confidence=1.0, overwrite=True)
    if inp.department:
        t.add("department", inp.department, src, method="input", confidence=0.95)
    if inp.title:
        t.add("title_raw", inp.title, src, method="input", confidence=0.9)
        t.add("title", normalize_title(inp.title), src, method="input", confidence=0.9)
        t.add("supervisor", find_supervisor(inp.title), src, method="input", confidence=0.9)
    if inp.email:
        t.add("email", inp.email.lower(), src, method="input", confidence=0.95)
    if inp.phone:
        t.add("phone", inp.phone, src, method="input", confidence=0.9)
    if inp.name_en:
        t.name_en = inp.name_en
    t.role = "教研"

    inst = resolve(inp.school)
    domains = set(inst.domains) | (school_domains(inp.profile_url) if inp.profile_url else set())
    t.raw["institution"] = {"en": inst.en, "ror": inst.ror, "domains": sorted(domains)}

    # ---- homepage ----
    if plan.has("homepage") and inp.profile_url:
        try:
            page = web.get(inp.profile_url)
            if page.status != 200:
                raise FetchError(f"HTTP {page.status}")
            extract_detail(t, page.html, page.final_url, DetailRule(content=None), domains)
            t.raw["final_url"] = page.final_url
        except FetchError as e:
            t.raw["detail_error"] = str(e)
            log.warning("主页抓取失败 %s：%s", inp.name, e)
        # 输入里给的职称、邮箱优先级高于页面启发式（输入来自你们的程序，通常更准）
        if inp.title:
            t.title_raw, t.title = inp.title, normalize_title(inp.title) or t.title
        if inp.email:
            t.email = inp.email.lower()

    nf = name_forms(inp.name, inp.name_en)

    # ---- papers（含 orcid_check） ----
    if plan.has("papers"):
        seed = "\n".join(t.papers)
        since = date.today().year - int(P["since_years"]) + 1
        pr = europepmc.find_papers(api, nf, inst, known_email=t.email, seed_text=seed, college=inp.college,
                                   since=since, max_results=int(P["max_papers"]),
                                   check_orcid=plan.has("orcid_check"))
        t.publications = pr.confirmed
        t.possible_publications = len(pr.possible)
        t.metrics.update(europepmc.summarize(pr.confirmed))
        t.metrics["paper_anchors"] = pr.anchors
        t.metrics["paper_notes"] = pr.notes
        t.raw["epmc_query"] = pr.query
        if pr.orcid:
            t.add("orcid", pr.orcid, "https://orcid.org/" + pr.orcid, method="api", confidence=0.9)
        if pr.confirmed:
            last5 = t.metrics.get("last_author_5y", 0)
            if last5 >= 3 and t.is_pi is None:
                t.add("is_pi", True, pr.confirmed[0].url, snippet=f"近 5 年末位作者论文 {last5} 篇",
                      method="api", confidence=0.7)

        # ---- grants ----
        if plan.has("grants"):
            t.grants = europepmc.collect_grants(pr.confirmed)

        # ---- paper_email ----
        if plan.has("paper_email") and pr.emails and not t.email:
            ranked = sorted(pr.emails, key=lambda e: (-_email_name_score(e, nf), not e.endswith(tuple(domains))))
            best = ranked[0]
            on_domain = best.endswith(tuple(domains))
            name_like = _email_name_score(best, nf) > 0
            if on_domain or name_like:
                first = next((p for p in pr.confirmed if best in p.author_aff.lower()), None)
                conf = 0.9 if (on_domain and name_like) else 0.6
                t.add("email", best, first.url if first else "europepmc", snippet=first.author_aff[:200] if first else "",
                      method="api", confidence=conf)
                if conf < 0.9:
                    t.raw["email_note"] = "邮箱来自论文，需核实"

        # ---- openalex ----
        if plan.has("openalex"):
            dois = [p.doi for p in t.publications if p.doi]
            oa = openalex.author_profile(api, nf, inst, t.orcid, known_dois=dois)
            if oa and oa.get("rejected"):
                t.metrics.setdefault("paper_notes", []).append(oa["rejected"])
            elif oa:
                t.metrics["openalex"] = oa
                if oa.get("orcid") and not t.orcid and oa.get("verified_by_doi", 0) > 0:
                    t.add("orcid", oa["orcid"], oa.get("openalex_id") or "", method="api", confidence=0.7)

        # ---- group_members ----
        if plan.has("group_members"):
            t.metrics["group"] = group_mod.infer_group(t, nf)

        # ---- fulltext_methods ----
        if plan.has("fulltext_methods"):
            ft = fulltext.mine(api, t.publications, max_papers=int(P["fulltext_max_papers"]))
            t.raw["_fulltext_texts"] = ft.pop("_texts", [])
            t.metrics["fulltext"] = ft

    # ---- lab_site ----
    if plan.has("lab_site") and t.lab_url:
        ls = lab_site_mod.scrape(web, t.lab_url, t.profile_url, max_pages=int(P["lab_site_max_pages"]))
        t.metrics["lab_site"] = ls
        if ls.get("lab_name") and not t.lab_name:
            t.add("lab_name", ls["lab_name"], ls["url"], snippet=ls["lab_name"], method="heuristic", confidence=0.7)
        for r in ls["recruiting"]:
            if r not in t.recruiting:
                t.recruiting.append(r)
                t.evidence.append(_ev_lab("recruiting", r, ls["url"]))

    enrich(t)
    t.raw.pop("_fulltext_texts", None)  # 全文只用于打标签，不落库
    validate_teacher(t, domains)
    if plan.has("papers") and not t.publications:
        t.issues.append("未找到可确认归属的英文论文")
    if t.raw.get("email_note"):
        t.issues.append("邮箱取自论文作者单位，未能与姓名对应，需核实")
    if t.possible_publications:
        t.issues.append(f"另有 {t.possible_publications} 篇同名论文待人工确认")
    return t


def _ev_lab(field: str, value: str, url: str):
    from .models import Evidence
    return Evidence(field=field, value=value[:200], source_url=url, snippet=value[:200], method="heuristic", confidence=0.7)


def _email_name_score(email: str, nf) -> int:
    """邮箱前缀和姓名拼音的相似度：2 = 含完整名或姓+名首字母组合，1 = 含姓，0 = 无关。"""
    local = re.sub(r"[^a-z]", "", email.split("@")[0].lower())
    givens = {nf.given} - {""}  # 只用本人拼音，不用学到的写法，避免把合作者邮箱当成本人的
    for sn in nf.surnames:
        if any(g in local for g in givens) and (sn in local or len(local) <= len(max(givens, key=len)) + 3):
            return 2
        if any(local in (sn + ini, ini + sn) for ini in nf.initials):
            return 2
    if any(g in local for g in givens if len(g) >= 4):
        return 2
    return 1 if any(sn in local for sn in nf.surnames) else 0


def teacher_key_for_input(inp: TeacherInput) -> str:
    host = urlsplit(inp.profile_url).netloc if inp.profile_url else ""
    return re.sub(r"\s+", "", f"input::{inp.school}::{inp.name}::{host}")
