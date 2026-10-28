"""读取外部程序给出的教师名单：CSV / JSON / JSONL / XLSX，表头中英文别名都认。"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from pydantic import BaseModel, Field

ALIASES = {
    "name": ["name", "姓名", "教师姓名", "老师", "pi", "pi姓名", "teacher"],
    "school": ["school", "学校", "高校", "大学", "university", "单位"],
    "college": ["college", "学院", "院系", "院", "faculty"],
    "department": ["department", "系所", "系", "研究所", "部门", "dept"],
    "profile_url": ["profile_url", "url", "主页", "个人主页", "主页链接", "链接", "homepage", "详情页"],
    "email": ["email", "邮箱", "电子邮箱", "e-mail", "mail"],
    "title": ["title", "职称", "职务职称", "position_title"],
    "name_en": ["name_en", "英文名", "english_name", "姓名英文"],
    "phone": ["phone", "电话", "办公电话"],
    "id": ["id", "编号", "teacher_id", "uid"],
}
_LOOKUP = {a.lower(): k for k, al in ALIASES.items() for a in al}


class TeacherInput(BaseModel):
    name: str
    school: str
    college: str | None = None
    department: str | None = None
    profile_url: str | None = None
    email: str | None = None
    title: str | None = None
    name_en: str | None = None
    phone: str | None = None
    id: str | None = None
    extra: dict[str, str] = Field(default_factory=dict)


def _map_row(row: dict) -> TeacherInput | None:
    data: dict = {"extra": {}}
    for k, v in row.items():
        if k is None:
            continue
        v = "" if v is None else str(v).strip()
        key = _LOOKUP.get(str(k).strip().lower())
        if key:
            if v and not data.get(key):
                data[key] = v
        elif v:
            data["extra"][str(k)] = v
    if not data.get("name") or not data.get("school"):
        return None
    return TeacherInput(**data)


def load_inputs(path: str | Path) -> list[TeacherInput]:
    p = Path(path)
    suffix = p.suffix.lower()
    rows: list[dict]
    if suffix in (".csv", ".tsv", ".txt"):
        text = p.read_text("utf-8-sig")
        dialect = csv.excel_tab if suffix == ".tsv" or "\t" in text.splitlines()[0] else csv.excel
        rows = list(csv.DictReader(text.splitlines(), dialect=dialect))
    elif suffix == ".json":
        d = json.loads(p.read_text("utf-8"))
        rows = d if isinstance(d, list) else d.get("teachers") or d.get("data") or []
    elif suffix == ".jsonl":
        rows = [json.loads(ln) for ln in p.read_text("utf-8").splitlines() if ln.strip()]
    elif suffix in (".xlsx", ".xlsm"):
        try:
            from openpyxl import load_workbook
        except ImportError as e:
            raise SystemExit("读取 Excel 需要 openpyxl：pip install openpyxl") from e
        ws = load_workbook(p, read_only=True, data_only=True).active
        it = ws.iter_rows(values_only=True)
        header = [str(h or "").strip() for h in next(it)]
        rows = [dict(zip(header, r)) for r in it]
    else:
        raise SystemExit(f"不支持的文件格式：{suffix}（支持 csv/tsv/json/jsonl/xlsx）")
    out = [t for t in (_map_row(r) for r in rows) if t]
    skipped = len(rows) - len(out)
    if skipped:
        print(f"跳过 {skipped} 行：缺少姓名或学校")
    return out
