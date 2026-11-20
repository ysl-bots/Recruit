"""데이터 모델. Posting은 소스 1개의 정규화된 공고, MergedPosting은 소스 간 병합 결과."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

SourceName = Literal["linkareer", "jasoseol", "catch"]
Employment = Literal["신입", "채용연계형 인턴", "체험형 인턴", "인턴", "기타"]
DeadlineType = Literal["date", "rolling", "until_filled"]
ItStatus = Literal["it", "maybe", "non_it", "unknown"]

SOURCE_LABEL = {"catch": "캐치", "jasoseol": "자소설", "linkareer": "링커리어"}
# 대표값 우선순위
SOURCE_PRIORITY: tuple[SourceName, ...] = ("catch", "jasoseol", "linkareer")


class Division(BaseModel):
    name: str
    is_it: bool = False
    employment: Employment | None = None


class Posting(BaseModel):
    source: SourceName
    source_id: str
    url: str
    company_raw: str
    company: str = ""
    title: str
    job_tags: list[str] = Field(default_factory=list)
    employment: Employment = "기타"
    start_date: date | None = None
    deadline: date | None = None
    deadline_type: DeadlineType = "date"
    # 소스가 구조화해 제공하는 모집 부문 (자소설 employments, 캐치 AssignedTaskNameListString)
    divisions: list[Division] = Field(default_factory=list)
    # 소스가 주는 IT 판정 근거 (자소설 IT duty group, 링커리어 IT 카테고리)
    source_it: bool = False
    # 기업 분류 힌트 (캐치 PopularCategory 등)
    company_category: str | None = None
    collected_at: datetime


class SourceLink(BaseModel):
    source: SourceName
    source_id: str
    url: str


class MergedPosting(BaseModel):
    id: str
    company: str  # 정규화명 (비교용)
    company_name: str = ""  # 표시명
    title: str
    deadline: date | None = None
    deadline_type: DeadlineType = "date"
    start_date: date | None = None
    employment: Employment = "기타"
    sources: list[SourceLink] = Field(default_factory=list)
    job_tags: list[str] = Field(default_factory=list)
    source_it: bool = False
    company_category: str | None = None
    is_listed: bool = False
    parent_company: str | None = None
    is_bigco: bool = False
    divisions: list[Division] | None = None
    divisions_from: Literal["source", "vlm"] | None = None
    divisions_source: str | None = None
    it_divisions: list[str] = Field(default_factory=list)
    it_status: ItStatus = "unknown"
    it_tags: list[str] = Field(default_factory=list)
    it_reason: str | None = None
    maybe_reason: str | None = None
    extract_attempted: bool = False
    first_seen: date
    last_seen: date
    published_weeks: list[str] = Field(default_factory=list)
    status: Literal["open", "closed"] = "open"

    def source_ids(self) -> set[tuple[str, str]]:
        return {(s.source, s.source_id) for s in self.sources}
