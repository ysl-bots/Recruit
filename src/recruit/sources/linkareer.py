"""링커리어 채용 공고. 필터를 건 /list/recruit 페이지에 내장된 __NEXT_DATA__(Apollo 캐시)를 읽는다."""

from __future__ import annotations

import json
import re

from .. import normalize as N
from ..models import Posting
from .base import Source

BASE = "https://linkareer.com"
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
IT_CATEGORY_ROOT = "100003"  # IT/개발. 분야 칸에 하위 직무명을 쓰기 위해서만 쓴다
RECRUIT_TYPE = {"ASAP": "until_filled", "ALWAYS": "rolling"}


def list_url(page: int, filters: dict) -> str:
    """사이트 필터를 filterBy_<키>=<값> 반복 파라미터로 붙인다 (링커리어 목록 URL 형식 그대로)."""
    q = ["filterBy_activityTypeID=5", "filterBy_status=OPEN"]
    for key, vals in filters.items():
        q += [f"filterBy_{key}={v}" for v in (vals if isinstance(vals, list) else [vals])]
    q += ["orderBy_direction=DESC", "orderBy_field=RECENT", f"page={page}"]
    return f"{BASE}/list/recruit?" + "&".join(q)


def apollo_state(html: str) -> dict:
    m = NEXT_DATA.search(html)
    if not m:
        raise ValueError("__NEXT_DATA__ 없음 (페이지 구조 변경 가능성)")
    state = json.loads(m.group(1)).get("props", {}).get("pageProps", {}).get("__APOLLO_STATE__")
    if not isinstance(state, dict):
        raise ValueError("__APOLLO_STATE__ 없음 (페이지 구조 변경 가능성)")
    return state


def _deref(state: dict, ref) -> dict:
    if isinstance(ref, dict) and "__ref" in ref:
        return state.get(ref["__ref"], {})
    return ref or {}


def _list_nodes(state: dict) -> list[dict]:
    root = state.get("ROOT_QUERY", {})
    for key, val in root.items():
        if key.startswith("activities(") and isinstance(val, dict) and '"activityTypeID":"5"' in key:
            return [_deref(state, n) for n in val.get("nodes", [])]
    raise ValueError("ROOT_QUERY.activities 없음 (페이지 구조 변경 가능성)")


def _employment(state: dict, act: dict) -> str:
    """표시용 고용형태 라벨. 신입·인턴 여부는 jobTypes 필터가 이미 보장한다."""
    job_types = set(act.get("jobTypes") or [])
    title = act.get("title", "")
    # 신입·인턴이 함께 표시된 공고는 제목에 '인턴'이 있을 때만 인턴으로 본다 (예: '신입 정규직 채용'에 INTERN이 붙은 경우)
    if "INTERN" in job_types and ("NEW" not in job_types or "인턴" in title):
        intern_names = [
            _deref(state, t).get("name", "")
            for ri in act.get("recruitInformations") or []
            for t in _deref(state, ri).get("internTypes") or []
        ]
        guess = N.employment(" ".join(intern_names) + " " + title)
        return guess if guess in ("채용연계형 인턴", "체험형 인턴") else "인턴"
    return "신입" if "NEW" in job_types else "기타"


def _it_tags(state: dict, act: dict) -> list[str]:
    tags = []
    for ref in act.get("categories") or []:
        c = _deref(state, ref)
        parent = _deref(state, c.get("parent")).get("id") if c.get("parent") else None
        if IT_CATEGORY_ROOT in (str(c.get("id")), str(parent)):
            name = c.get("name", "")
            tags.append("IT/개발" if name in ("", "전체") else name)
    return list(dict.fromkeys(tags))


def parse_list(html: str, now) -> list[Posting]:
    state = apollo_state(html)
    items = []
    for act in _list_nodes(state):
        if not act or "id" not in act:
            continue
        deadline_type = RECRUIT_TYPE.get(act.get("recruitType") or "", "date")
        org = act.get("organizationName") or ""
        items.append(
            Posting(
                source="linkareer",
                source_id=str(act["id"]),
                url=f"{BASE}/activity/{act['id']}",
                company_raw=org,
                company=N.company(org),
                title=(act.get("title") or "").strip(),
                job_tags=_it_tags(state, act),
                employment=_employment(state, act),
                deadline=N.to_date(act.get("recruitCloseAt")) if deadline_type == "date" else None,
                deadline_type=deadline_type,
                collected_at=now,
            )
        )
    return items


class Linkareer(Source):
    name = "linkareer"
    page_size = 20

    def fetch_page(self, page: int) -> list[Posting]:
        return parse_list(self.client.get_text(list_url(page, self.filters)), self.now)
