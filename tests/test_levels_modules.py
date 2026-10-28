"""分级配置与 L3 新模块的离线测试。"""
import pytest

from faculty_crawler.levels import LevelError, resolve_plan
from faculty_crawler.models import Publication, Teacher
from faculty_crawler.names import name_forms


def test_levels_are_nested_and_configurable(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "x")
    l1, l2, l3 = (resolve_plan(lv) for lv in ("L1", "L2", "L3"))
    assert l1.modules == ["homepage"]
    assert set(l1.modules) < set(l2.modules) < set(l3.modules)
    # 单独加一个模块会自动补依赖
    p = resolve_plan("L1", with_=["fulltext_methods"])
    assert p.modules == ["homepage", "papers", "fulltext_methods"]
    assert any("自动加入" in n for n in p.notes)
    # 去掉 papers 会连带去掉依赖它的模块
    p = resolve_plan("L3", without=["papers"])
    assert p.modules == ["homepage", "lab_site"]
    # 规划中/未知模块报错
    with pytest.raises(LevelError, match="规划中"):
        resolve_plan("L2", with_=["college_news"])
    with pytest.raises(LevelError, match="未知"):
        resolve_plan("L9")
    # 自定义配置文件覆盖
    cfg = tmp_path / "levels.yaml"
    cfg.write_text("default_level: L1\nlevels:\n  L2:\n    modules: [homepage, papers]\n", "utf-8")
    assert resolve_plan(path=cfg).level == "L1"
    assert resolve_plan("L2", path=cfg).modules == ["homepage", "papers"]


def test_missing_api_key_skips_module(monkeypatch, tmp_path):
    from faculty_crawler import config
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    p = resolve_plan("L2")
    assert "openalex" not in p.modules and any("OPENALEX_API_KEY" in n for n in p.notes)


def _pub(year, position, authors, journal="J"):
    return Publication(title=f"t{year}{authors[0]}", year=year, position=position, authors=authors,
                       journal=journal, pmid=str(year) + authors[0][:2])


def test_group_members_from_last_author_papers():
    from datetime import date

    from faculty_crawler.group import infer_group
    y = date.today().year
    t = Teacher(site_id="t", school="s", college="c", name="曹博")
    t.publications = [
        _pub(y, "last", ["Wang Xiaoming", "Li Y", "Cao Bo"]),
        _pub(y - 1, "last", ["Zhang S", "Cao B"]),
        _pub(y - 1, "last", ["Wang Xiaoming", "Cao B"]),
        _pub(y - 2, "first", ["Cao B", "Dedon PC"]),       # 本人第一作者，不算成员
        _pub(y - 1, "middle", ["Liu Q", "Cao B", "Chen Z"]),  # 合作论文，不算
        _pub(y - 9, "last", ["Old Student", "Cao B"]),       # 超出时间窗
    ]
    g = infer_group(t, name_forms("曹博"))
    assert g["estimated_size"] == 2 and g["last_author_papers"] == 3
    assert {m["name"] for m in g["first_authors"]} == {"Wang Xiaoming", "Zhang S"}


JATS = """<article><body>
<sec><title>Introduction</title><p>Prior work used Corning plates.</p></sec>
<sec sec-type="methods"><title>Materials and Methods</title>
<p>Cells were cultured in T75 flasks (Corning) and seeded in 96-well plates (NEST Biotech).</p>
<p>RNA was extracted with the RNeasy kit (Qiagen) and reverse transcribed using HiScript (Vazyme).</p>
<p>Samples were spun in an Eppendorf 5424 centrifuge.</p>
<p>qPCR was performed on a CFX96 system (Bio-Rad).</p></sec>
<sec><title>Results</title><p>We used Sarstedt tubes.</p></sec>
</body></article>"""


def test_fulltext_methods_brand_scan():
    from faculty_crawler.sources.fulltext import methods_text, scan_brands
    text = methods_text(JATS)
    assert "Corning" in text and "Sarstedt" not in text  # 只看方法章节
    found = scan_brands(text, "u")
    assert found["Corning"]["consumable_mentions"] == 1 and found["Corning"]["kind"] == "consumable"
    assert found["NEST"]["origin"] == "domestic"
    assert found["Eppendorf"]["consumable_mentions"] == 0  # 离心机是仪器，不算耗材语境
    assert {"Qiagen", "Vazyme", "Bio-Rad"} <= set(found)


def test_fulltext_mine_only_own_papers(monkeypatch):
    from faculty_crawler.fetcher import Page
    from faculty_crawler.sources import fulltext

    class Api:
        def __init__(self):
            self.calls = []

        def get(self, url, **kw):
            self.calls.append(url)
            return Page(url=url, final_url=url, status=200, html=JATS)

    pubs = [Publication(title="a", year=2025, position="last", pmcid="PMC1", open_access=True, journal="J"),
            Publication(title="b", year=2025, position="middle", pmcid="PMC2", open_access=True, journal="J"),
            Publication(title="c", year=2024, position="first", pmcid=None, open_access=False, journal="J")]
    api = Api()
    r = fulltext.mine(api, pubs)
    assert len(api.calls) == 1 and "PMC1" in api.calls[0]
    assert r["brands"]["Corning"]["papers"] == 1
    assert r["domestic_share"] == round(2 / 6, 2)  # NEST、Vazyme 国产；Corning、Qiagen、Eppendorf、Bio-Rad 进口


def test_lab_site_members_and_instruments():
    from faculty_crawler.fetcher import Page
    from faculty_crawler.lab_site import scrape
    pages = {
        "http://lab.example.cn/": "<html><body><a href='/members.html'>团队成员</a><a href='/x.html'>新闻</a>"
                                  "<p>实验室配备流式细胞仪、激光共聚焦显微镜和移液工作站。</p>"
                                  "<p>课题组长期招聘博士后和科研助理，欢迎加入。</p></body></html>",
        "http://lab.example.cn/members.html": "<html><body><h2>成员</h2><p>博士后</p><p>王硕</p><p>博士生</p>"
                                              "<p>李明 张华</p><p>硕士生</p><p>赵六</p></body></html>",
    }

    class Web:
        def get(self, url, **kw):
            return Page(url=url, final_url=url, status=200, html=pages[url])

    r = scrape(Web(), "http://lab.example.cn/", None)
    assert r["members"] == ["王硕", "李明", "张华", "赵六"]
    assert {"流式细胞仪", "激光共聚焦显微镜", "移液工作站"} <= set(r["instruments"])
    assert r["recruiting"] and r["roles"]["博士后"] >= 1
    assert len(r["pages"]) == 2


def test_brand_false_positives_and_abbreviations():
    from faculty_crawler.sources.fulltext import scan_brands, sentences
    text = ("Code is at http://membrane.urmc.rochester.edu/x. The sigma factor RpoS was deleted. "
            "Cells were from Sigma-Aldrich (St. Louis, MO, USA). Matrigel (Corning) was used. "
            "Reagents (Sigma, USA) were added. Cultures were grown in 50 mL Falcon tubes.")
    assert any("St. Louis" in s for s in sentences(text))
    f = scan_brands(text, "u")
    assert "Roche" not in f
    assert f["Sigma-Aldrich"]["mentions"] == 2  # Sigma-Aldrich 与 “(Sigma, USA)”，不含 sigma factor
    assert f["Corning"]["consumable_mentions"] == 0 and f["Falcon"]["consumable_mentions"] == 1


def test_l4_is_planned_with_clear_message():
    with pytest.raises(LevelError, match="规划中"):
        resolve_plan("L4")


def test_lab_site_stops_on_captcha_and_reads_lab_name():
    from faculty_crawler.fetcher import Page
    from faculty_crawler.lab_site import scrape
    pages = {"http://a/": "<html><body>请完成人机验证 为了保护网站安全，请完成以下验证</body></html>",
             "http://b/": "<html><body><h1>小花椒课题组</h1><p>研究 DNA 硫修饰。</p></body></html>"}

    class Web:
        def get(self, url, **kw):
            return Page(url=url, final_url=url, status=200, html=pages[url])

    r = scrape(Web(), "http://a/", None)
    assert r["pages"] == [] and "人机验证" in r["errors"][0]
    assert scrape(Web(), "http://b/", None)["lab_name"] == "小花椒课题组"


def test_sentences_keep_parenthetical_catalog_numbers():
    from faculty_crawler.sources.fulltext import sentences
    text = "Cells were stained with DAPI (cat. no. D9542, Sigma-Aldrich). Then they were imaged on a confocal microscope."
    s = sentences(text)
    assert s[0].startswith("Cells were stained") and "Sigma-Aldrich)." in s[0]
