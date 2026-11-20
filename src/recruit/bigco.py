"""대기업·다부문 공채 판정과 상장사(KRX KIND) 목록.

is_bigco: ① 직무 태그 3개 이상 ② 제목에 공채·대졸 신입 ③ 본인 또는 모기업이 코스피·코스닥 상장사 — 하나라도.
"""

from __future__ import annotations

import json
import logging
import re
from functools import cache
from pathlib import Path

from bs4 import BeautifulSoup

from . import normalize as N
from .config import Settings, load_yaml
from .models import MergedPosting

log = logging.getLogger(__name__)

KIND_URL = "https://kind.krx.co.kr/corpgeneral/corpList.do"
MARKETS = {"stockMkt": "코스피", "kosdaqMkt": "코스닥"}
LISTED_CATEGORIES = {"코스피", "코스닥", "유가증권"}


def parse_kind(html: str, market: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.find_all("tr"):
        tds = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(tds) >= 3 and tds[0]:
            rows.append({"name": tds[0], "market": market, "code": tds[2], "norm": N.company(tds[0])})
    return rows


def update_listed(settings: Settings, client) -> int:
    rows: list[dict] = []
    for mkt, label in MARKETS.items():
        try:
            html = client.get_text(KIND_URL, {"method": "download", "marketType": mkt}, encoding="euc-kr")
        except Exception as exc:  # noqa: BLE001 - 실패 시 기존 파일 유지
            log.error("KIND %s 다운로드 실패: %s (기존 listed.json 유지)", label, exc)
            return 0
        part = parse_kind(html, label)
        if len(part) < 100:
            log.error("KIND %s 결과가 %d건뿐이라 저장하지 않음 (형식 변경 가능성)", label, len(part))
            return 0
        rows += part
    path = settings.data_dir / "listed.json"
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8")
    listed_names.cache_clear()
    return len(rows)


@cache
def listed_names(path: Path | None = None) -> frozenset[str]:
    from .config import DATA_DIR

    path = path or DATA_DIR / "listed.json"
    if not path.exists():
        log.warning("listed.json 없음: 상장사 조건(③)은 캐치 기업 분류로만 판정")
        return frozenset()
    return frozenset(r["norm"] for r in json.loads(path.read_text(encoding="utf-8")))


@cache
def parents() -> dict[str, str]:
    return {N.company(k): str(v) for k, v in (load_yaml("parent_company.yaml") or {}).items()}


@cache
def _title_pat() -> re.Pattern:
    words = load_yaml("it_keywords.yaml").get("bigco_title") or ["공채", "대졸 신입"]
    return re.compile("|".join(re.escape(w).replace(r"\ ", r"\s*") for w in words))


def mark(m: MergedPosting, listed: frozenset[str] | None = None) -> None:
    listed = listed_names() if listed is None else listed
    parent = parents().get(m.company)
    m.parent_company = parent
    m.is_listed = (
        m.company in listed
        or (parent is not None and N.company(parent) in listed)
        or (m.company_category or "") in LISTED_CATEGORIES
    )
    many_tags = len([t for t in m.job_tags if t]) >= 3
    m.is_bigco = many_tags or bool(_title_pat().search(m.title)) or m.is_listed
