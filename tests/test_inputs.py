import json

from faculty_crawler.inputs import load_inputs


def test_csv_with_chinese_headers(tmp_path):
    p = tmp_path / "in.csv"
    p.write_text("姓名,学校,学院,个人主页,备注\n张三,示例大学,生命学院,http://x.edu.cn/t/zs,重点客户\n,示例大学,,,\n", "utf-8-sig")
    rows = load_inputs(p)
    assert len(rows) == 1
    r = rows[0]
    assert (r.name, r.school, r.college, r.profile_url) == ("张三", "示例大学", "生命学院", "http://x.edu.cn/t/zs")
    assert r.extra == {"备注": "重点客户"}


def test_json_and_jsonl(tmp_path):
    p = tmp_path / "in.json"
    p.write_text(json.dumps({"data": [{"name": "李四", "university": "示例大学", "email": "ls@x.edu.cn"}]}), "utf-8")
    assert load_inputs(p)[0].email == "ls@x.edu.cn"
    p = tmp_path / "in.jsonl"
    p.write_text('{"name": "王五", "school": "示例大学"}\n', "utf-8")
    assert load_inputs(p)[0].name == "王五"
