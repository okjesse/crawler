"""论文归属消歧的离线测试：构造 Europe PMC 返回结构，不联网。"""
from faculty_crawler.institutions import Institution
from faculty_crawler.names import match_author, name_forms
from faculty_crawler.sources.europepmc import collect_grants, nsfc_grant, resolve_papers, summarize

INST = Institution(zh="示例大学", en="Example University", aliases=["Example Univ"], domains=["example.edu.cn"])
LIFE = "School of Life Sciences and Biotechnology, Example University, City, China."
INSTR = "Department of Instrument Science, School of Electronic Information, Example University, City, China."


def author(last, first, initials, aff, orcid=None):
    a = {"lastName": last, "firstName": first, "initials": initials,
         "authorAffiliationDetailsList": {"authorAffiliation": [{"affiliation": aff}]}}
    if orcid:
        a["authorId"] = {"type": "ORCID", "value": orcid}
    return a


def rec(rid, title, year, authors, grants=(), source="MED", journal="J Test"):
    return {"id": rid, "pmid": rid, "title": title, "pubYear": str(year), "source": source,
            "journalInfo": {"journal": {"medlineAbbreviation": journal}},
            "authorList": {"author": authors},
            "grantsList": {"grant": [{"agency": a, "grantId": g} for a, g in grants]}}


def test_name_forms_and_matching():
    nf = name_forms("刘世轩")
    assert nf.surnames == ["liu"] and nf.given == "shixuan"
    assert match_author(nf, "Liu", "Shi-Xuan", "SX") == "full"
    assert match_author(nf, "Liu", "S", "S") == "initial"
    assert match_author(nf, "Liu", "Shuang", "S") is None  # 名字不同是另一个人
    assert name_forms("吕布").surnames == ["lv", "lu", "lyu"]
    assert name_forms("欧阳三三").surnames == ["ouyang"]
    assert name_forms("单雄信").surnames == ["shan"]


def test_email_anchor_orcid_and_department_disambiguation():
    nf = name_forms("曹博")
    raw = [
        # 主页邮箱出现在作者单位里 → 强锚点，拿到 ORCID
        rec("1", "Anchor paper on RNA modification mapping methods", 2025,
            [author("Wu", "Xi", "X", LIFE), author("Cao", "Bo", "B", LIFE + " Electronic address: caobo@example.edu.cn.", "0000-0001")]),
        # 同 ORCID → 归属
        rec("2", "Another paper by same ORCID", 2024, [author("Cao", "Bo", "B", "MIT, USA", "0000-0001")]),
        # 同名同校、生命学院 → 归属（院系一致）
        rec("3", "Small RNA library preparation", 2026, [author("Cao", "Bo", "B", LIFE), author("Li", "Wei", "W", LIFE)]),
        # 同名同校、仪器系 → 待确认
        rec("4", "Paper-based colorimetric device", 2023, [author("Cao", "Bo", "B", INSTR)]),
        # 不同 ORCID → 另一个人
        rec("5", "Different person with ORCID", 2024, [author("Cao", "Bo", "B", LIFE, "0000-9999")]),
        # 本人单位不是本校 → 排除
        rec("6", "Hospital study elsewhere", 2024, [author("Cao", "Bo", "B", "Other Hospital, Beijing, China")]),
    ]
    pr = resolve_papers(nf, INST, raw, known_email="caobo@example.edu.cn", seed_text="", college="生命科学技术学院")
    got = {p.pmid: p.match for p in pr.confirmed}
    assert got == {"1": "email", "2": "orcid", "3": "full"}
    assert [p.pmid for p in pr.possible] == ["4"]
    assert pr.orcid == "0000-0001"
    assert "caobo@example.edu.cn" in pr.emails


def test_without_anchor_requires_college_hint():
    nf = name_forms("曹博")
    raw = [rec("3", "Small RNA library preparation", 2026, [author("Cao", "B", "B", LIFE)]),
           rec("4", "Paper-based colorimetric device", 2023, [author("Cao", "B", "B", INSTR)])]
    pr = resolve_papers(nf, INST, raw, known_email=None, seed_text="", college="生命科学技术学院")
    assert [p.pmid for p in pr.confirmed] == ["3"]
    assert any("没有邮箱或主页论文锚点" in n for n in pr.notes)
    pr = resolve_papers(nf, INST, raw, known_email=None, seed_text="", college=None)
    assert pr.confirmed == [] and len(pr.possible) == 2


def test_seed_title_anchor_and_preprint_dedupe():
    nf = name_forms("曹博")
    seed = "Cao B*, et al. Nick-seq for single-nucleotide resolution genomic maps of DNA modifications. NAR 2020."
    raw = [rec("7", "Nick-seq for single-nucleotide resolution genomic maps of DNA modifications and damage", 2020,
               [author("Cao", "Bo", "B", "Qufu Normal University, China", "0000-0001")]),
           rec("8", "Nick-seq for single-nucleotide resolution genomic maps of DNA modifications and damage", 2019,
               [author("Cao", "Bo", "B", "Qufu Normal University, China", "0000-0001")], source="PPR", journal=None)]
    pr = resolve_papers(nf, INST, raw, known_email=None, seed_text=seed, college=None)
    assert len(pr.confirmed) == 1 and pr.confirmed[0].journal == "J Test"
    assert summarize(pr.confirmed)["papers_total_found"] == 1


def test_nsfc_grant_number_parsing():
    assert nsfc_grant("32170045") == (2021, "面上")
    assert nsfc_grant("31900652") == (2019, "青年")
    assert nsfc_grant("31930003") == (2019, "重点")
    assert nsfc_grant("2017YFA0205304") == (None, None)
    pubs = resolve_papers(name_forms("曹博"), INST, [
        rec("9", "Grant paper", 2024, [author("Cao", "Bo", "B", LIFE + " caobo@example.edu.cn")],
            grants=[("National Natural Science Foundation of China", "32170045")])],
        known_email="caobo@example.edu.cn", seed_text="", college=None).confirmed
    g = collect_grants(pubs)
    assert g[0].year == 2021 and g[0].kind == "面上"


def test_learn_name_forms_from_homepage_papers():
    from faculty_crawler.names import learn_from_seeds
    nf = learn_from_seeds(name_forms("王柏翔"), "Wang, P. H., Wu, T. Y. Title one. 2020\nLee T, Wang, P. H.*, Lin X. Title two. 2021")
    assert "ph" in nf.learned_initials
    assert match_author(nf, "Wang", "Po-Hsiang", "PH") == "full"
    assert match_author(nf, "Wang", "Bo", "B") == "initial"
    nf = learn_from_seeds(name_forms("陈光玉"), "Li C, Chen GE*. Title. Sci Adv 2026\nWang Y, Chen GE*, Zhang Q. Two. Cell")
    assert match_author(nf, "Chen", "Guang-E", "GE") == "full"
    # 同姓合作者只出现一次且没有标记，不学
    nf = learn_from_seeds(name_forms("陈光玉"), "Chen Y, Chen GE*. A. 2020\nChen GE*, Li X. B. 2021\nChen GE*. C. 2022")
    assert "y" not in nf.learned_initials and match_author(nf, "Chen", "Yu", "Y") is None


def test_do_not_learn_same_surname_advisor():
    from faculty_crawler.names import learn_from_seeds
    seeds = ("Xiao-Nan Zhang (co-first author), Albert Lam, Yong Zhang*. Discovery of an analogue. Chem Sci 2022\n"
             "Zhefu Dai, Xiao-Nan Zhang (co-first author), Yong Zhang*. Site-specific conjugates. J Control Release 2021\n"
             "Zhefu Dai, Xiao-Nan Zhang, Yong Zhang*. Synthesis of conjugates. Sci Adv 2020")
    nf = learn_from_seeds(name_forms("张肖楠"), seeds)
    assert "yong" not in nf.alt_given
    assert match_author(nf, "Zhang", "Yong", "Y") is None
    assert match_author(nf, "Zhang", "Xiao-Nan", "XN") == "full"


class _FakeApi:
    def __init__(self, payload):
        self.payload = payload

    def get(self, url, headers=None, force=False):
        import json as _json
        from faculty_crawler.fetcher import Page
        return Page(url=url, final_url=url, status=200, html=_json.dumps(self.payload))


def test_orcid_name_check_rejects_coauthor_orcid():
    from faculty_crawler.sources.europepmc import orcid_name_ok
    nf = name_forms("魏冬青")
    khan = {"name": {"given-names": {"value": "Abdul Aziz"}, "family-name": {"value": "Khan"}}}
    wei = {"name": {"given-names": {"value": "Dong-Qing"}, "family-name": {"value": "Wei"}}}
    hidden = {"name": None}
    assert orcid_name_ok(_FakeApi(khan), "0000-0000", nf) is False
    assert orcid_name_ok(_FakeApi(wei), "0000-0000", nf) is True
    assert orcid_name_ok(_FakeApi(hidden), "0000-0000", nf) is None


def test_bad_orcid_is_ignored_in_attribution():
    nf = name_forms("曹博")
    raw = [rec("1", "Anchor paper on RNA modification mapping methods", 2025,
               [author("Cao", "Bo", "B", LIFE + " caobo@example.edu.cn", "0000-BAD")]),
           rec("2", "Coauthor paper tagged with wrong ORCID", 2024,
               [author("Cao", "Bo", "B", "Somewhere Else Institute, USA", "0000-BAD")])]
    pr = resolve_papers(nf, INST, raw, known_email="caobo@example.edu.cn", seed_text="", college=None,
                        bad_orcids={"0000-BAD"})
    assert pr.orcid is None
    assert [p.pmid for p in pr.confirmed] == ["1"]


def test_openalex_name_matching_variants():
    from faculty_crawler.names import learn_from_seeds
    from faculty_crawler.sources.openalex import _name_matches
    nf = learn_from_seeds(name_forms("王柏翔"), "Wang, P. H., Wu T. A. 2020\nLee T, Wang, P. H.*, Lin X. B. 2021")
    assert _name_matches("Po-Hsiang Wang", nf) and _name_matches("Po\u2010Hsiang Wang", nf)
    assert not _name_matches("Ping Wang", nf)
    nf = name_forms("陈光玉")
    assert _name_matches("Guangyu E. Chen", nf) and _name_matches("Chen Guangyu", nf)
    assert not _name_matches("Guang Chen", nf)


def test_seed_titles_messy_homepage_formats():
    from faculty_crawler.sources.europepmc import _seed_titles
    seed = ("Feng Chen(Corresponding author).The Maturing Development of Gut Microbiota in Commercial Piglets during the Weaning Transition. Front Microbiol 2017\n"
            "Detoxification of Zearalenone by viable and inactivated cells of Planococcus sp，Food Control 2011")
    t = _seed_titles(seed)
    assert t[0] == "The Maturing Development of Gut Microbiota in Commercial Piglets during the Weaning Transition"
    assert t[1] == "Detoxification of Zearalenone by viable and inactivated cells of Planococcus sp"


def test_rare_anchor_unit_does_not_admit_namesake():
    nf = name_forms("张雁")
    med = "Department of Gastroenterology, Renji Hospital, School of Medicine, Example University, City, China."
    raw = [rec(str(i), f"Anchor microbial paper {i} about nucleotide metabolism", 2025,
               [author("Zhang", "Yan", "Y", LIFE + " zhangyan@example.edu.cn")]) for i in range(5)]
    raw.append(rec("9", "Anchor with a hospital co-affiliation", 2024,
                   [author("Zhang", "Yan", "Y", med + " | " + LIFE + " zhangyan@example.edu.cn")]))
    raw.append(rec("10", "Cirrhosis clinical study", 2026, [author("Zhang", "Yan", "Y", med)]))
    pr = resolve_papers(nf, INST, raw, known_email="zhangyan@example.edu.cn", seed_text="", college="生命科学技术学院")
    assert "10" not in {p.pmid for p in pr.confirmed}
    assert "10" in {p.pmid for p in pr.possible}
