from faculty_crawler.html_utils import decode_html
from faculty_crawler.normalize import (clean_name, find_honors, find_position, is_plausible_name,
                                       normalize_title, school_domains)


def test_titles():
    assert normalize_title("讲席教授") == "教授"
    assert normalize_title("长聘教轨副教授") == "副教授"
    assert normalize_title("特聘研究员") == "研究员"
    assert normalize_title("副研究员") == "副研究员"
    assert normalize_title("高级实验师") == "高级工程师/实验师"
    assert normalize_title("博士后") == "博士后"


def test_names():
    assert clean_name("博士生导师 刘世轩") == "刘世轩"
    assert clean_name("王  伟") == "王伟"
    assert clean_name("张三教授") == "张三"
    assert is_plausible_name("欧阳三三")
    assert not is_plausible_name("学院简介")
    assert not is_plausible_name("科学研究")
    assert not is_plausible_name("生物系")


def test_honor_context():
    assert find_honors("师从某某院士。入选国家级青年人才。") == ["国家级青年人才"]
    assert find_honors("委员会主任。973计划首席科学家，获奖") == ["首席科学家"]


def test_position_skips_former_roles():
    assert find_position("原生命科学技术学院院长") is None
    assert find_position("2009年至2024年任重点实验室主任") is None
    assert find_position("现任生化系副系主任").endswith("生化系副系主任")


def test_domains_and_decoding():
    assert school_domains("https://life.sjtu.edu.cn/x") == {"sjtu.edu.cn"}
    gbk = "<meta charset=gbk><p>教授</p>".encode("gbk")
    assert "教授" in decode_html(gbk)
