from pathlib import Path

from faculty_crawler.list_parser import auto_detect, parse_list, webplus_page_urls
from faculty_crawler.sites import FieldRule, ListRule

FIX = Path(__file__).parent / "fixtures"


def grouped_rule() -> ListRule:
    return ListRule(
        urls=["http://example.edu.cn/T/Index/zc"], mode="grouped", scope=".jiao-con",
        section=".shengwu", section_title="h5", group=".sheng-div", group_title=".sheng-tit span",
        item=".sheng-ul li a", name=FieldRule(attr="title"), title=FieldRule(attr="data-name", text=False),
    )


def test_grouped_list_extracts_groups_titles_and_urls():
    html = (FIX / "grouped_list.html").read_text("utf-8")
    stubs = parse_list(html, "http://example.edu.cn/T/Index/zc", grouped_rule())
    names = [s.name for s in stubs]
    assert names == ["张三", "李四", "王五", "赵六", "张三"]  # 去重在流水线里做
    zs = stubs[0]
    assert zs.group == "生物化学与分子生物学系 / 教授（研究员）"
    assert zs.extra["title"] == "特聘教授"
    assert stubs[1].url == "http://example.edu.cn/teacher/lisi"
    assert stubs[3].group.startswith("实验技术中心")


def test_flat_webplus_list_cleans_supervisor_prefix_and_paginates():
    html = (FIX / "webplus_list.html").read_text("utf-8")
    rule = ListRule(urls=["http://x.edu.cn/9902/list.htm"], mode="flat", scope=".col_news_list",
                    item=".news_title a", name=FieldRule(attr="title"), label=FieldRule(attr="title"),
                    pagination="webplus")
    stubs = parse_list(html, "http://x.edu.cn/9902/list.htm", rule)
    assert [s.name for s in stubs] == ["刘一", "陈二", "欧阳三三", "孙四", "周五"]
    assert stubs[0].extra["label"] == "博士生导师 刘一"
    assert webplus_page_urls(html, "http://x.edu.cn/9902/list.htm", 50) == [
        "http://x.edu.cn/9902/list2.htm", "http://x.edu.cn/9902/list3.htm"]


def test_auto_detect_ignores_navigation_and_numbered_classes():
    html = (FIX / "webplus_list.html").read_text("utf-8")
    stubs = auto_detect(html, "http://x.edu.cn/9902/list.htm")
    assert [s.name for s in stubs] == ["刘一", "陈二", "欧阳三三", "孙四", "周五"]
    html = (FIX / "grouped_list.html").read_text("utf-8")
    names = {s.name for s in auto_detect(html, "http://example.edu.cn/", min_cluster=3)}
    assert {"张三", "李四", "王五", "赵六"} <= names
    assert "学院简介" not in names
