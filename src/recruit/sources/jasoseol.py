"""자소설닷컴. 검색 화면과 같은 필터(by_*)를 건 /api/v1/employment_companies JSON API를 읽는다."""

from __future__ import annotations

import json
from functools import cache

from .. import normalize as N
from ..config import CONFIG_DIR
from ..models import Division, Posting
from .base import Source

BASE = "https://jasoseol.com"
NEWBIE, INTERN = 1, 3  # employments[].division


@cache
def duty_names() -> dict[int, str]:
    path = CONFIG_DIR / "jasoseol_duty_groups.json"
    return {int(k): v for k, v in json.loads(path.read_text(encoding="utf-8")).items()} if path.exists() else {}


def list_params(page: int, filters: dict) -> dict:
    """자소설 검색 화면이 API로 보내는 형식 그대로 (searchFiltersToApi: by_<키>=쉼표 목록)."""
    params: dict = {"per_page": 100, "page": page}
    for key, vals in filters.items():
        params[f"by_{key}"] = ",".join(map(str, vals if isinstance(vals, list) else [vals]))
    return params


def _emp_label(e: dict, title: str) -> str:
    """표시용 고용형태 라벨. 신입·인턴 여부는 by_division 필터가 이미 보장한다."""
    div = set(e.get("division") or [])
    if INTERN in div:
        if e.get("linkage_recruitment"):
            return "채용연계형 인턴"
        guess = N.employment(" ".join(filter(None, [e.get("field"), title])))
        return guess if guess in ("채용연계형 인턴", "체험형 인턴") else "인턴"
    return "신입" if NEWBIE in div else "기타"


def parse_item(x: dict, now, filter_duties: set[int]) -> Posting:
    """필터를 통과한 공고 하나. 부문(employments)은 모두 남기고, 필터의 직무그룹에 속한 부문만 is_it로 표시한다(분야 칸용)."""
    title = (x.get("title") or "").strip()
    divisions, tags, labels = [], set(), []
    for e in x.get("employments") or []:
        matched = set(e.get("duty_group_ids") or []) & filter_duties
        label = _emp_label(e, title)
        labels.append(label)
        tags |= matched
        if e.get("field"):
            divisions.append(Division(name=e["field"].strip(), is_it=bool(matched), employment=label))
    employment = next((v for v in ("신입", "채용연계형 인턴", "체험형 인턴", "인턴") if v in labels), "기타")
    group = x.get("company_group") or {}
    name = x.get("name") or group.get("name") or ""
    return Posting(
        source="jasoseol",
        source_id=str(x["id"]),
        url=f"{BASE}/recruit/{x['id']}",
        company_raw=name,
        company=N.company(name),
        title=title,
        job_tags=[duty_names().get(g, f"duty:{g}") for g in sorted(tags)],
        employment=employment,
        start_date=N.to_date(x.get("start_time")),
        deadline=N.to_date(x.get("end_time")),
        deadline_type="date" if x.get("end_time") else "rolling",
        divisions=divisions,
        apply_url=N.clean_url(x.get("employment_page_url")),
        collected_at=now,
    )


def parse_list(data: list[dict], now, filter_duties: set[int]) -> list[Posting]:
    return [parse_item(x, now, filter_duties) for x in data]


class Jasoseol(Source):
    name = "jasoseol"
    page_size = 100

    def fetch_page(self, page: int) -> list[Posting]:
        params = list_params(page, self.filters)
        # 검색 화면의 '마감 공고 제외'와 같은 파라미터
        params["after_end_time"] = self.now.date().isoformat()
        data = self.client.get_json(f"{BASE}/api/v1/employment_companies", params)
        if not isinstance(data, list):
            raise ValueError("employment_companies 응답이 배열이 아님 (API 변경 가능성)")
        return parse_list(data, self.now, set(map(int, self.filters.get("duty_group_ids") or [])))
