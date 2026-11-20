"""IT 직무 분류.

순서: 구조화 부문(IT 부문 존재) / 소스 직무 분류 / 키워드 → it.
혼동 키워드만 있으면 LLM 재판정 대상으로 남기고, 재판정이 불가하거나 애매하면 maybe.
"""

from __future__ import annotations

import logging
import re
from functools import cache

from pydantic import BaseModel, ValidationError

from .config import ROOT, load_yaml
from .llm import LLM, LLMError
from .models import MergedPosting

log = logging.getLogger(__name__)


def _pattern(words: list[str]) -> re.Pattern:
    parts = []
    for w in sorted(set(words), key=len, reverse=True):
        esc = re.escape(w).replace(r"\ ", r"\s*")
        if re.fullmatch(r"[A-Za-z/&. ]+", w):
            # 영문은 영문자 경계(한글과 붙어 있어도 매칭: 'SW개발', 'AI엔지니어')
            esc = rf"(?<![A-Za-z]){esc}(?![A-Za-z])"
            # 짧은 대문자 약어는 대소문자 구분 ('it', 'ai'가 일반 단어에 걸리지 않게)
            if len(w) <= 3 and w.isupper():
                esc = rf"(?-i:{esc})"
        parts.append(esc)
    return re.compile("|".join(parts), re.I)


@cache
def _rules():
    cfg = load_yaml("it_keywords.yaml")
    cats = {name: _pattern(words) for name, words in (cfg.get("categories") or {}).items()}
    amb = _pattern(cfg.get("ambiguous") or ["__none__"])
    exc = _pattern(cfg.get("exclude") or ["__none__"])
    conflict = _pattern(cfg.get("conflict") or ["__none__"])
    return cats, amb, exc, conflict


def it_tags(text: str) -> list[str]:
    cats, _, exc, _ = _rules()
    t = exc.sub(" ", text or "")
    return [name for name, pat in cats.items() if pat.search(t)]


def is_ambiguous(text: str) -> bool:
    _, amb, _, _ = _rules()
    return bool(amb.search(text or ""))


def has_conflict(text: str) -> bool:
    return bool(_rules()[3].search(text or ""))


def keyword_classify(m: MergedPosting) -> None:
    """키워드·소스 신호로 1차 판정. LLM이 필요한 건은 it_status='unknown' + maybe_reason='혼동 키워드'."""
    # 캐치 부문은 is_it 정보가 없으므로 이름으로 판정
    if m.divisions:
        for d in m.divisions:
            if not d.is_it and m.divisions_source == "catch":
                d.is_it = bool(it_tags(d.name))
    it_div = [d.name for d in m.divisions or [] if d.is_it]
    # 자소설 부문은 직무그룹으로 IT 여부가 정해져 있으므로 태그(상위 그룹명 'IT·인터넷' 등) 키워드는 보지 않는다
    authoritative = m.divisions_source == "jasoseol"
    text = " ".join([m.title, *([] if authoritative else m.job_tags), *(d.name for d in m.divisions or [])])
    tags = it_tags(text)
    m.it_divisions = it_div
    m.it_tags = tags
    if it_div:
        m.it_status, m.it_reason = "it", "source_division"
    elif m.source_it:
        m.it_status, m.it_reason = "it", "source_tag"
    elif it_tags(" ".join([m.title, *([] if authoritative else m.job_tags)])):
        if has_conflict(m.title):
            m.it_status, m.it_reason, m.maybe_reason = "unknown", None, "IT 키워드 + 비IT 직무어"
        else:
            m.it_status, m.it_reason = "it", "keyword"
    elif is_ambiguous(text):
        m.it_status, m.it_reason, m.maybe_reason = "unknown", None, "혼동 키워드"
    else:
        m.it_status, m.it_reason = "non_it", "keyword"


class _Verdict(BaseModel):
    id: str
    verdict: str  # it | non_it | unsure
    tags: list[str]


class _Batch(BaseModel):
    results: list[_Verdict]


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["results"],
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "verdict", "tags"],
                "properties": {
                    "id": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["it", "non_it", "unsure"]},
                    "tags": {"type": "array", "items": {"type": "string", "enum": ["개발", "데이터·AI", "인프라", "보안", "IT 일반"]}},
                },
            },
        }
    },
}


def llm_classify(items: list[MergedPosting], llm: LLM, batch: int = 30) -> None:
    """혼동 키워드 공고를 LLM으로 재판정한다. 실패·unsure는 maybe."""
    targets = [m for m in items if m.it_status == "unknown"]
    if not targets:
        return
    if not llm.enabled:
        for m in targets:
            m.it_status, m.maybe_reason = "maybe", "혼동 키워드 (LLM 미사용)"
        return
    system = (ROOT / "prompts" / "classify.md").read_text(encoding="utf-8")
    for i in range(0, len(targets), batch):
        chunk = targets[i : i + batch]
        lines = [
            f"- id={m.id} | 회사={m.company} | 제목={m.title} | 직무태그={', '.join(m.job_tags) or '-'}"
            f" | 부문={', '.join(d.name for d in m.divisions or []) or '-'}"
            for m in chunk
        ]
        try:
            raw = llm.ask_json(system, "\n".join(lines), SCHEMA)
            out = {v.id: v for v in _Batch.model_validate(raw).results}
        except (LLMError, ValidationError) as exc:
            log.warning("LLM 분류 실패 (%d건 maybe 처리): %s", len(chunk), exc)
            out = {}
        for m in chunk:
            v = out.get(m.id)
            if v and v.verdict == "it":
                m.it_status, m.it_reason, m.maybe_reason = "it", "llm", None
                m.it_tags = sorted(set(m.it_tags) | set(v.tags))
            elif v and v.verdict == "non_it":
                m.it_status, m.it_reason, m.maybe_reason = "non_it", "llm", None
            else:
                m.it_status, m.it_reason = "maybe", "llm" if v else "fallback"
                m.maybe_reason = "IT 여부 애매" if v else "혼동 키워드 (LLM 실패)"
