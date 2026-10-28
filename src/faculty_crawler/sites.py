"""站点模板：每个学院一份 YAML，描述列表页与详情页怎么取。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from . import config


class FieldRule(BaseModel):
    """从一个节点取值：attr 优先，其次 text；可选正则提取第 1 组。"""

    attr: str | None = None
    text: bool = True
    regex: str | None = None


class ListRule(BaseModel):
    urls: list[str]
    mode: Literal["grouped", "flat", "auto"] = "auto"
    scope: str | None = None  # 限定主内容区域，避免抓到导航栏
    section: str | None = None  # grouped：一级分组（如系所）
    section_title: str | None = None
    group: str | None = None  # grouped：二级分组（如职称）
    group_title: str | None = None
    item: str = "a"
    name: FieldRule = Field(default_factory=FieldRule)
    title: FieldRule | None = None
    url: FieldRule = Field(default_factory=lambda: FieldRule(attr="href", text=False))
    label: FieldRule | None = None  # 条目上的附加文字，如“博士生导师 张三”
    pagination: Literal["none", "webplus"] = "none"
    max_pages: int = 50


class DetailRule(BaseModel):
    content: str | None = None  # 正文区域选择器；为空则用整页去掉导航
    drop: list[str] = Field(default_factory=lambda: ["nav", "header", "footer", ".navbar", ".footer", ".nav", "script", "style"])
    title: str | None = None


class Site(BaseModel):
    id: str
    school: str
    college: str
    school_domains: list[str] = Field(default_factory=list)
    cms: str | None = None
    notes: str | None = None
    expected_min_teachers: int | None = None  # 覆盖率告警阈值
    list: ListRule
    detail: DetailRule = Field(default_factory=DetailRule)

    @classmethod
    def load(cls, path: Path) -> "Site":
        data: dict[str, Any] = yaml.safe_load(path.read_text("utf-8"))
        return cls.model_validate(data)


def all_sites(template_dir: Path | None = None) -> dict[str, Site]:
    d = template_dir or config.TEMPLATE_DIR
    sites = {}
    for p in sorted(d.glob("*.yaml")):
        s = Site.load(p)
        sites[s.id] = s
    return sites


def get_site(site_id: str) -> Site:
    sites = all_sites()
    if site_id not in sites:
        raise KeyError(f"未找到站点模板 {site_id}，可用：{', '.join(sites)}")
    return sites[site_id]
