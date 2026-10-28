"""数据模型：每个字段都带来源证据。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Evidence(BaseModel):
    """某个字段取值的出处。"""

    field: str
    value: str
    source_url: str
    snippet: str = ""
    method: str = "template"  # template | heuristic | group_heading | llm | api
    confidence: float = 0.8
    fetched_at: datetime = Field(default_factory=now_utc)


class Publication(BaseModel):
    """一篇已归属到该老师的论文（来自 Europe PMC / PubMed）。"""

    pmid: str | None = None
    doi: str | None = None
    title: str
    journal: str | None = None
    year: int | None = None
    position: str = "middle"  # first / last / middle / solo
    n_authors: int = 0
    match: str = ""  # email / seed / orcid / full / initial
    confidence: float = 0.0
    author_aff: str = ""
    mesh: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    grants: list[str] = Field(default_factory=list)
    cited_by: int = 0
    abstract: str = ""

    @property
    def url(self) -> str:
        if self.pmid:
            return f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"
        if self.doi:
            return f"https://doi.org/{self.doi}"
        return ""


class Grant(BaseModel):
    agency: str
    grant_id: str | None = None
    year: int | None = None  # 由资助号推断
    kind: str | None = None  # 面上 / 青年 / 重点 / 人才类（由资助号推断）
    n_papers: int = 1
    source_url: str = ""


class TeacherStub(BaseModel):
    """列表页上得到的教师条目。"""

    name: str
    url: str | None = None
    group: str | None = None  # 列表页分组标题，如“教授”“副教授”“系所名”
    extra: dict[str, str] = Field(default_factory=dict)  # 列表页顺带拿到的字段


class Teacher(BaseModel):
    site_id: str
    school: str
    college: str
    name: str
    name_en: str | None = None
    title: str | None = None  # 归一化职称：教授/副教授/讲师/研究员...
    title_raw: str | None = None
    position: str | None = None  # 行政职务：院长/系主任/实验室主任
    supervisor: list[str] = Field(default_factory=list)  # 博士生导师/硕士生导师
    honors: list[str] = Field(default_factory=list)  # 院士/杰青/优青/长江...
    is_pi: bool | None = None
    department: str | None = None
    email: str | None = None
    phone: str | None = None
    office: str | None = None
    lab_name: str | None = None
    lab_url: str | None = None
    research_directions: list[str] = Field(default_factory=list)
    research_text: str | None = None
    techniques: list[str] = Field(default_factory=list)  # 推断的实验技术标签
    recommended_products: list[str] = Field(default_factory=list)
    joined_year: int | None = None  # 入职年份（新进教师信号）
    experience: list[str] = Field(default_factory=list)  # 学习与工作经历原文
    papers: list[str] = Field(default_factory=list)  # 主页列出的代表论文原文
    projects: list[str] = Field(default_factory=list)  # 主页列出的基金/项目原文
    recruiting: list[str] = Field(default_factory=list)  # 招生/招聘信号原文
    role: str | None = None  # 教研 / 支撑（实验技术、平台、行政）
    orcid: str | None = None
    publications: list[Publication] = Field(default_factory=list)  # 已确认归属的论文
    possible_publications: int = 0  # 同名、待人工确认的论文数
    grants: list[Grant] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)  # 论文与学术指标
    signals: list[str] = Field(default_factory=list)  # 销售信号标签
    priority: int = 0  # 销售优先级分数
    bio_text: str | None = None
    profile_url: str | None = None
    list_url: str | None = None
    fetched_at: datetime = Field(default_factory=now_utc)
    confidence: float = 0.0
    issues: list[str] = Field(default_factory=list)  # 校验问题
    evidence: list[Evidence] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)

    department_raw: str | None = None  # 列表页分组原文

    def group_text(self) -> str:
        return " ".join(x for x in (self.department or "", self.department_raw or "") if x)

    @property
    def key(self) -> str:
        return f"{self.site_id}::{self.name}::{self.profile_url or ''}"

    def add(self, field: str, value: Any, source_url: str, *, snippet: str = "",
            method: str = "template", confidence: float = 0.8, overwrite: bool = False) -> None:
        """设置字段并登记证据。已有值默认不覆盖（详情页先于列表页写入）。"""
        if value in (None, "", [], {}):
            return
        current = getattr(self, field, None)
        if current in (None, "", []) or overwrite:
            setattr(self, field, value)
        self.evidence.append(Evidence(
            field=field, value=str(value), source_url=source_url,
            snippet=snippet[:300], method=method, confidence=confidence,
        ))


class SiteReport(BaseModel):
    site_id: str
    started_at: datetime = Field(default_factory=now_utc)
    finished_at: datetime | None = None
    list_pages: int = 0
    stubs: int = 0
    stubs_with_url: int = 0
    detail_ok: int = 0
    detail_failed: int = 0
    teachers: int = 0
    coverage: float = 0.0
    fill_rates: dict[str, float] = Field(default_factory=dict)
    issue_counts: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
