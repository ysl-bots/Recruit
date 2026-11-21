"""캐치. /api/v1.0/recruit/information/getRecruitList JSON API.

상세 본문은 iframe /controls/recruitDetail/{id}로 제공되는데 robots.txt가 /controls를 막으므로 요청하지 않는다.
대신 목록의 AssignedTaskNameListString(모집 부문)·Depth(직무)를 쓴다.
"""

from __future__ import annotations

from .. import normalize as N
from ..models import Division, Posting
from .base import Source

BASE = "https://www.catch.co.kr"
API = f"{BASE}/api/v1.0/recruit/information/getRecruitList"
PAGE_SIZE = 30


def list_params(page: int) -> dict:
    # Career: 1 신입, 4 인턴 / Sort: 0 최신순
    return {"curpage": page, "pageSize": PAGE_SIZE, "onRecruitYN": "Y", "Career": "1,4", "Sort": 0}


def _split(s: str | None) -> list[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def parse_item(x: dict, now) -> Posting | None:
    career = x.get("CareerGubunCode") or ""
    gubun = x.get("GubunCode") or ""
    title = (x.get("RecruitTitle") or "").strip()
    if "인턴" in gubun:
        guess = N.employment(title)
        employment = guess if guess in ("채용연계형 인턴", "체험형 인턴") else "인턴"
    elif "신입" in career and "정규직" in gubun:
        employment = "신입"
    else:
        return None  # 경력·경력무관, 신입 계약직
    end_code = x.get("ApplyEndCode") or ""
    if "채용시" in end_code:
        deadline_type, deadline = "until_filled", None
    elif "상시" in end_code:
        deadline_type, deadline = "rolling", None
    else:
        deadline_type, deadline = "date", N.to_date(x.get("ApplyEndDatetime"))
    if deadline and deadline < now.date():
        return None
    return Posting(
        source="catch",
        source_id=str(x["RecruitID"]),
        url=f"{BASE}/NCS/RecruitInfoDetails/{x['RecruitID']}",
        company_raw=x.get("CompName") or "",
        company=N.company(x.get("CompName") or ""),
        title=title,
        job_tags=_split(x.get("Depth")),
        employment=employment,
        start_date=N.to_date(x.get("ApplyStartDatetime")),
        deadline=deadline,
        deadline_type=deadline_type,
        divisions=[Division(name=n) for n in _split(x.get("AssignedTaskNameListString"))],
        company_category=x.get("PopularCategory"),
        collected_at=now,
    )


def parse_list(data: dict, now) -> tuple[list[Posting | None], list[str]]:
    rows = data.get("recruitData")
    if not isinstance(rows, list):
        raise ValueError("recruitData 없음 (API 변경 가능성)")
    items, ids = [], []
    for x in rows:
        if x.get("IsAdvertise") or x.get("IsProduct"):
            # 광고 슬롯은 최신순이 아니므로 증분 중단 판단에서 뺀다
            p = parse_item(x, now)
            items.append(p)
            continue
        ids.append(str(x["RecruitID"]))
        items.append(parse_item(x, now))
    return items, ids


class Catch(Source):
    name = "catch"
    page_size = PAGE_SIZE

    def fetch_page_with_ids(self, page: int):
        return parse_list(self.client.get_json(API, list_params(page)), self.now)

    def fetch_page(self, page: int):
        return self.fetch_page_with_ids(page)[0]
