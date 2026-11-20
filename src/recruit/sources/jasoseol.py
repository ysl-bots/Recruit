"""자소설닷컴. /api/v1/employment_companies JSON API(최신순, 서버 필터 없음)를 읽고 로컬에서 거른다."""

from __future__ import annotations

from .. import normalize as N
from ..models import Division, Posting
from .base import Detail, Source, html_images, html_to_text

BASE = "https://jasoseol.com"
# employments[].division
NEWBIE, CAREER, INTERN = 1, 2, 3
# /api/v1/duty-groups 의 IT·인터넷(94) 하위. 171(서비스기획·PM)은 애매하므로 제외
IT_DUTY_GROUPS = set(range(160, 171))
BUSINESS_SIZE = {"big_business": "대기업", "middle_market": "중견기업", "public_institution": "공공기관"}


def list_url(page: int) -> str:
    return f"{BASE}/api/v1/employment_companies?per_page=100&page={page}"


def _emp_of(e: dict, title: str) -> str | None:
    div = set(e.get("division") or [])
    text = " ".join(filter(None, [e.get("field"), title]))
    if INTERN in div:
        guess = N.employment(text)
        if e.get("linkage_recruitment"):
            return "채용연계형 인턴"
        return guess if guess in ("채용연계형 인턴", "체험형 인턴") else "인턴"
    if NEWBIE in div:
        return "신입"
    return None


def parse_item(x: dict, now) -> Posting | None:
    title = (x.get("title") or "").strip()
    divisions: list[Division] = []
    tags: set[int] = set()
    source_it = False
    emps = []
    for e in x.get("employments") or []:
        emp = _emp_of(e, title)
        if not emp:
            continue
        groups = set(e.get("duty_group_ids") or [])
        is_it = bool(groups & IT_DUTY_GROUPS)
        source_it |= is_it
        tags |= groups
        emps.append(emp)
        if e.get("field"):
            divisions.append(Division(name=e["field"].strip(), is_it=is_it, employment=emp))
    if not emps:
        return None
    # 대표 고용형태: 신입이 하나라도 있으면 신입, 아니면 인턴 계열 중 첫 값
    employment = "신입" if "신입" in emps else emps[0]
    group = x.get("company_group") or {}
    return Posting(
        source="jasoseol",
        source_id=str(x["id"]),
        url=f"{BASE}/recruit/{x['id']}",
        company_raw=x.get("name") or group.get("name") or "",
        company=N.company(x.get("name") or group.get("name") or ""),
        title=title,
        job_tags=[f"duty:{g}" for g in sorted(tags)],
        employment=employment,
        start_date=N.to_date(x.get("start_time")),
        deadline=N.to_date(x.get("end_time")),
        deadline_type="date" if x.get("end_time") else "rolling",
        divisions=divisions,
        source_it=source_it,
        company_category=BUSINESS_SIZE.get(group.get("business_size") or ""),
        collected_at=now,
    )


def parse_list(data: list[dict], now) -> tuple[list[Posting | None], list[str]]:
    items, ids = [], []
    for x in data:
        ids.append(str(x["id"]))
        p = parse_item(x, now)
        # 이미 마감된 공고는 버린다
        if p and p.deadline and p.deadline < now.date():
            p = None
        items.append(p)
    return items, ids


def parse_detail(data: dict) -> Detail:
    body = data.get("content") or ""
    return Detail(text=html_to_text(body), image_urls=html_images(body))


class Jasoseol(Source):
    name = "jasoseol"

    def fetch_page_with_ids(self, page: int):
        data = self.client.get_json(list_url(page))
        if not isinstance(data, list):
            raise ValueError("employment_companies 응답이 배열이 아님 (API 변경 가능성)")
        return parse_list(data, self.now)

    def fetch_page(self, page: int):
        return self.fetch_page_with_ids(page)[0]

    def fetch_detail(self, posting_url: str, source_id: str) -> Detail:
        return parse_detail(self.client.get_json(f"{BASE}/api/v1/employment_companies/{source_id}", {"skip_read_log": "true"}))
