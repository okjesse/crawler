from datetime import date
from pathlib import Path

from faculty_crawler.detail_parser import extract_detail, research_items, split_sections
from faculty_crawler.enrich import enrich
from faculty_crawler.models import Teacher
from faculty_crawler.sites import DetailRule

FIX = Path(__file__).parent / "fixtures"
URL = "http://example.edu.cn/teacher/zhangsan"


def make(name: str = "张三") -> Teacher:
    return Teacher(site_id="t", school="示例大学", college="生命学院", name=name, profile_url=URL)


def test_sectioned_profile():
    t = make()
    html = (FIX / "detail_sections.html").read_text("utf-8")
    extract_detail(t, html, URL, DetailRule(), {"example.edu.cn"})
    assert t.title == "教授" and t.title_raw == "特聘教授"
    assert t.email == "zhangsan@example.edu.cn"  # [at] 混淆被还原
    assert t.phone == "021-34201234"
    assert t.office.startswith("生命科学楼")
    assert "博士生导师" in t.supervisor
    assert t.is_pi is True
    assert t.honors == ["国家杰出青年科学基金"]  # “合作导师为某某院士”不算本人头衔
    assert t.position is None  # “曾任…主任”是卸任职务
    assert t.research_directions == ["肿瘤类器官模型与药物筛选", "单细胞测序解析肿瘤微环境"]
    assert len(t.papers) == 2 and len(t.projects) == 2
    assert t.joined_year == 2024
    assert t.recruiting
    # 每个字段都有来源
    fields = {e.field for e in t.evidence}
    assert {"email", "title", "research_directions", "joined_year"} <= fields


def test_freetext_profile_join_year_does_not_cross_sentences():
    t = make("李四")
    html = (FIX / "detail_freetext.html").read_text("utf-8")
    extract_detail(t, html, URL, DetailRule(content=".wp_articlecontent"), {"example.edu.cn"})
    assert t.email == "lisi@example.edu.cn"
    assert t.joined_year == 2025  # 不是 2021（那年加入的是另一单位）
    assert "国家级青年人才" in t.honors
    assert t.research_directions[0].startswith("肿瘤免疫治疗药物（融合蛋白、环状RNA")
    assert "蛋白替代疗法和体内工程化免疫细胞疗法" in t.research_directions
    assert t.recruiting


def test_signals_rank_new_pi_with_talent_title_and_recruiting_highest():
    t = make("李四")
    extract_detail(t, (FIX / "detail_freetext.html").read_text("utf-8"), URL,
                   DetailRule(content=".wp_articlecontent"), {"example.edu.cn"})
    t.title = "教授"
    enrich(t)
    if t.joined_year >= date.today().year - 2:
        assert t.signals[0].startswith("★ 新进 PI + 人才头衔 + 在招人")
    assert "免疫学" in t.techniques


def test_split_sections_keeps_longest_duplicate_heading():
    text = "首页\n研究方向\n代表论著\n张三\n研究方向\n方向A\n方向B\n代表论著\n论文1 ... 2020"
    sec = split_sections(text)
    assert sec["research"] == "方向A\n方向B"


def test_research_items_inline_heading_and_numbering():
    assert research_items("⑴恶性肿瘤的精准治疗；\n⑵肿瘤耐药机制；\n⑶抗肿瘤生物治疗。") == [
        "恶性肿瘤的精准治疗", "肿瘤耐药机制", "抗肿瘤生物治疗"]
    body = "方向一：宿主与菌群互作\n肠道如何识别微生物？我们关注上皮细胞，解析机制。\n方向二：工程菌设计"
    assert research_items(body) == ["宿主与菌群互作", "工程菌设计"]
