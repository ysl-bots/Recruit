"""소스 간 중복 병합.

같은 공고 판정: 정규화 회사명 일치 + 마감일 ±2일(둘 다 날짜 없음도 같음) + 정규화 제목 token_set_ratio ≥ 85.
오병합은 공고가 조용히 사라지므로, 같은 소스의 다른 공고끼리는 병합하지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date

from rapidfuzz import fuzz

from . import normalize as N
from .config import DATA_DIR
from .models import SOURCE_PRIORITY, MergedPosting, Posting, SourceLink

log = logging.getLogger(__name__)

TITLE_THRESHOLD = 85
DEADLINE_TOLERANCE = 2


def key(source: str, source_id: str) -> str:
    return f"{source}:{source_id}"


def load_overrides(path=None) -> tuple[set[frozenset[str]], set[frozenset[str]]]:
    path = path or DATA_DIR / "dedupe_overrides.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raw = {}
    merge = {frozenset(map(str, pair)) for pair in raw.get("force_merge", [])}
    split = {frozenset(map(str, pair)) for pair in raw.get("force_split", [])}
    return merge, split


def display_company(raw: str) -> str:
    return " ".join(N._CORP_TOKENS.sub(" ", raw or "").split())


def make_id(p: Posting) -> str:
    base = f"{p.company}|{N.title(p.title, p.company_raw)}|{p.deadline or p.deadline_type}|{p.source}:{p.source_id}"
    return hashlib.sha1(base.encode()).hexdigest()[:12]


def _deadline_close(a: date | None, a_type: str, b: date | None, b_type: str) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs((a - b).days) <= DEADLINE_TOLERANCE


def similar(p: Posting, m: MergedPosting) -> bool:
    if p.company != m.company:
        return False
    if not _deadline_close(p.deadline, p.deadline_type, m.deadline, m.deadline_type):
        return False
    return fuzz.token_set_ratio(N.title(p.title, p.company_raw), N.title(m.title)) >= TITLE_THRESHOLD


def _rank(source: str) -> int:
    return SOURCE_PRIORITY.index(source)


def _apply(m: MergedPosting, p: Posting, today: date) -> None:
    """소스 하나의 최신 값을 병합 공고에 반영한다. 대표값은 우선순위가 높은 소스가 이긴다."""
    best = min((_rank(s.source) for s in m.sources), default=99)
    link = SourceLink(source=p.source, source_id=p.source_id, url=p.url)
    m.sources = [s for s in m.sources if (s.source, s.source_id) != (p.source, p.source_id)] + [link]
    m.sources.sort(key=lambda s: _rank(s.source))
    if _rank(p.source) <= best:
        m.title = p.title or m.title
        m.company_name = display_company(p.company_raw) or m.company_name
        if p.deadline or p.deadline_type != "date":
            m.deadline, m.deadline_type = p.deadline, p.deadline_type
        m.start_date = p.start_date or m.start_date
        if p.employment != "기타":
            m.employment = p.employment
    else:
        m.deadline = m.deadline or p.deadline
        m.start_date = m.start_date or p.start_date
    m.job_tags = list(dict.fromkeys([*m.job_tags, *p.job_tags]))
    # 모집 부문은 자소설만 제공한다
    if p.divisions:
        m.divisions = [d.model_copy() for d in p.divisions]
        m.it_divisions = [d.name for d in p.divisions if d.is_it]
    m.last_seen = today
    m.status = "open"


def new_merged(p: Posting, today: date) -> MergedPosting:
    m = MergedPosting(
        id=make_id(p),
        company=p.company,
        title=p.title,
        deadline=p.deadline,
        deadline_type=p.deadline_type,
        start_date=p.start_date,
        employment=p.employment,
        first_seen=today,
        last_seen=today,
    )
    _apply(m, p, today)
    return m


def merge(existing: list[MergedPosting], incoming: list[Posting], today: date, overrides=None) -> list[MergedPosting]:
    """existing(이전 상태)에 incoming(오늘 수집)을 합친다. 반환은 갱신된 전체 목록."""
    force_merge, force_split = overrides if overrides is not None else load_overrides()
    by_key: dict[str, MergedPosting] = {}
    by_company: dict[str, list[MergedPosting]] = {}
    for m in existing:
        for s in m.sources:
            by_key[key(s.source, s.source_id)] = m
        by_company.setdefault(m.company, []).append(m)
    merged = list(existing)

    # 우선순위 높은 소스부터 넣어야 대표값·id가 안정적이다
    for p in sorted(incoming, key=lambda x: _rank(x.source)):
        k = key(p.source, p.source_id)
        if k in by_key:
            _apply(by_key[k], p, today)
            continue
        target = None
        for m in by_company.get(p.company, []):
            if m.status == "closed":
                continue
            member_keys = {key(s.source, s.source_id) for s in m.sources}
            if any(frozenset({k, mk}) in force_split for mk in member_keys):
                continue
            if any(frozenset({k, mk}) in force_merge for mk in member_keys):
                target = m
                break
            if any(s.source == p.source for s in m.sources):
                continue
            if similar(p, m):
                target = m
                break
        if target is None:
            target = new_merged(p, today)
            merged.append(target)
            by_company.setdefault(p.company, []).append(target)
        else:
            log.debug("병합: %s ← %s", target.id, k)
            _apply(target, p, today)
        by_key[k] = target
    return merged
