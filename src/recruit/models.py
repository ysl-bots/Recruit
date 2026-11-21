"""데이터 모델. Posting은 소스 1개의 정규화된 공고, MergedPosting은 소스 간 병합 결과.

대상 선별(신입·인턴 / IT 직군 / 기업 규모)은 사이트 필터가 하므로, 여기 들어온 공고는 모두 발행 대상이다.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

SourceName = Literal["linkareer", "jasoseol"]
Employment = Literal["신입", "채용연계형 인턴", "체험형 인턴", "인턴", "기타"]
DeadlineType = Literal["date", "rolling", "until_filled"]

SOURCE_LABEL = {"jasoseol": "자소설", "linkareer": "링커리어"}
# 대표값(제목·마감일 등) 우선순위. 자소설은 부문별 구조화 데이터가 있어 앞에 둔다
SOURCE_PRIORITY: tuple[SourceName, ...] = ("jasoseol", "linkareer")


class Division(BaseModel):
    """모집 부문 (자소설 employments). is_it: 필터에 쓴 IT 직무그룹에 속하는 부문."""

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
    job_tags: list[str] = Field(default_factory=list)  # 소스의 IT 직무 분류명 (분야 칸)
    employment: Employment = "기타"  # 표시용 라벨
    start_date: date | None = None
    deadline: date | None = None
    deadline_type: DeadlineType = "date"
    divisions: list[Division] = Field(default_factory=list)
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
    divisions: list[Division] | None = None
    it_divisions: list[str] = Field(default_factory=list)  # divisions 중 is_it 부문명
    first_seen: date
    last_seen: date
    published_weeks: list[str] = Field(default_factory=list)
    status: Literal["open", "closed"] = "open"
