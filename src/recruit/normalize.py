"""회사명·제목·날짜·고용형태 정규화."""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime
from functools import cache

from .config import DATA_DIR, KST

_CORP_TOKENS = re.compile(r"\(주\)|\(유\)|\(재\)|\(사\)|㈜|㈐|주식회사|유한회사|재단법인|사단법인|\bco\.?,?\s*ltd\.?|\binc\.?", re.I)
_NON_WORD = re.compile(r"[^0-9a-z가-힣]+")
_YEAR_HALF = re.compile(r"(20)?\d{2}\s*년?\s*(도)?\s*(상반기|하반기|상|하)?(?=\s|$|[^0-9])")
_BRACKET_PREFIX = re.compile(r"^\s*[\[【(<]([^\]】)>]{1,40})[\]】)>]\s*")


@cache
def _aliases() -> dict[str, str]:
    path = DATA_DIR / "company_alias.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    # {"대표명": ["별칭", ...]} → 정규화 별칭 → 정규화 대표명
    out: dict[str, str] = {}
    for canon, names in raw.items():
        c = _basic_company(canon)
        out[c] = c
        for n in names:
            out[_basic_company(n)] = c
    return out


def _basic_company(name: str) -> str:
    s = unicodedata.normalize("NFKC", name or "")
    s = _CORP_TOKENS.sub("", s)
    return _NON_WORD.sub("", s.lower())


def company(name: str) -> str:
    c = _basic_company(name)
    return _aliases().get(c, c)


def title(raw: str, company_raw: str = "") -> str:
    s = unicodedata.normalize("NFKC", raw or "")
    m = _BRACKET_PREFIX.match(s)
    if m:
        s = s[m.end():]
    s = s.lower()
    comp = company(company_raw)
    if comp:
        # 제목 앞에 붙은 회사명 제거
        s_flat = _NON_WORD.sub("", s)
        if s_flat.startswith(comp):
            s = re.sub(r"^\s*" + r"\s*".join(map(re.escape, company_raw.strip())) + r"\s*", "", s, flags=re.I)
    s = _YEAR_HALF.sub(" ", s)
    s = _NON_WORD.sub(" ", s)
    return " ".join(s.split())


def parse_datetime(value) -> datetime | None:
    """epoch ms(int) 또는 ISO 문자열을 KST datetime으로."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, KST)
    s = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt.astimezone(KST)


def to_date(value) -> date | None:
    dt = parse_datetime(value)
    return dt.date() if dt else None


def employment(*texts: str) -> str:
    """제목·태그에서 고용형태를 판정한다. 경력 전용이면 '기타'."""
    t = " ".join(x for x in texts if x)
    if "채용연계" in t or "채용 연계" in t or "전환형" in t:
        return "채용연계형 인턴"
    if "체험형" in t:
        return "체험형 인턴"
    if "인턴" in t:
        return "인턴"
    if "신입" in t or "공채" in t or "공개채용" in t:
        return "신입"
    return "기타"
