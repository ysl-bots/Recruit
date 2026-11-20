"""링커리어 채용 공고. /list/recruit 페이지에 내장된 __NEXT_DATA__(Apollo 캐시)를 읽는다."""

from __future__ import annotations

import json
import re

from .. import normalize as N
from ..models import Posting
from .base import Detail, Source, html_images, html_to_text

BASE = "https://linkareer.com"
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
IT_CATEGORY_ROOT = "100003"  # IT/개발
RECRUIT_TYPE = {"ASAP": "until_filled", "ALWAYS": "rolling"}


def list_url(page: int) -> str:
    return f"{BASE}/list/recruit?filterBy_jobTypes=NEW&filterBy_jobTypes=INTERN&page={page}"


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
    job_types = set(act.get("jobTypes") or [])
    intern_names = []
    for ri in act.get("recruitInformations") or []:
        info = _deref(state, ri)
        intern_names += [_deref(state, t).get("name", "") for t in info.get("internTypes") or []]
    if "INTERN" in job_types:
        names = " ".join(intern_names)
        guess = N.employment(names + " " + act.get("title", ""))
        return guess if guess != "기타" and guess != "신입" else "인턴"
    if "NEW" in job_types:
        return "신입"
    return "기타"


def parse_list(html: str, now) -> tuple[list[Posting | None], list[str]]:
    state = apollo_state(html)
    nodes = _list_nodes(state)
    items: list[Posting | None] = []
    ids = []
    for act in nodes:
        if not act or "id" not in act:
            continue
        ids.append(str(act["id"]))
        emp = _employment(state, act)
        if emp == "기타":
            items.append(None)
            continue
        cats = [_deref(state, c) for c in act.get("categories") or []]
        tags, source_it = [], False
        for c in cats:
            name = c.get("name", "")
            parent = _deref(state, c.get("parent")).get("id") if c.get("parent") else None
            if name and name != "전체":
                tags.append(name)
            if str(c.get("id")) == IT_CATEGORY_ROOT or str(parent) == IT_CATEGORY_ROOT:
                source_it = True
        deadline_type = RECRUIT_TYPE.get(act.get("recruitType") or "", "date")
        items.append(
            Posting(
                source="linkareer",
                source_id=str(act["id"]),
                url=f"{BASE}/activity/{act['id']}",
                company_raw=act.get("organizationName") or "",
                company=N.company(act.get("organizationName") or ""),
                title=(act.get("title") or "").strip(),
                job_tags=tags,
                employment=emp,
                deadline=N.to_date(act.get("recruitCloseAt")) if deadline_type == "date" else None,
                deadline_type=deadline_type,
                source_it=source_it,
                collected_at=now,
            )
        )
    return items, ids


def parse_detail(html: str, source_id: str) -> Detail:
    state = apollo_state(html)
    act = state.get(f"Activity:{source_id}")
    if not act:
        raise ValueError(f"Activity:{source_id} 없음")
    body = _deref(state, act.get("detailText")).get("text", "") or ""
    return Detail(text=html_to_text(body), image_urls=html_images(body))


class Linkareer(Source):
    name = "linkareer"

    def fetch_page_with_ids(self, page: int):
        return parse_list(self.client.get_text(list_url(page)), self.now)

    def fetch_page(self, page: int):
        return self.fetch_page_with_ids(page)[0]

    def fetch_detail(self, posting_url: str, source_id: str) -> Detail:
        return parse_detail(self.client.get_text(posting_url), source_id)
