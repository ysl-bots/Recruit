"""대기업·다부문 공고의 상세(텍스트+이미지)에서 VLM으로 모집 부문을 추출한다.

구조화 부문(자소설·캐치)이 없는 공고만 대상이다. 본문·이미지는 저장하지 않고 부문 목록만 남긴다.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ValidationError

from .classify import it_tags
from .config import ROOT, Settings
from .llm import LLM, LLMError
from .models import Division, MergedPosting
from .sources import SOURCES

log = logging.getLogger(__name__)

# 상세를 요청할 수 있는 소스 (캐치 본문은 robots 차단)
DETAIL_SOURCES = ("jasoseol", "linkareer")

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["divisions"],
    "properties": {
        "divisions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "is_it"],
                "properties": {"name": {"type": "string"}, "is_it": {"type": "boolean"}},
            },
        }
    },
}


class _Out(BaseModel):
    divisions: list[Division]


def needs_extract(m: MergedPosting) -> bool:
    return m.status == "open" and m.is_bigco and not m.divisions and not m.extract_attempted


def _finalize_failure(m: MergedPosting, reason: str) -> None:
    m.extract_attempted = True
    # 키워드·소스 신호로 이미 IT면 유지, 아니면 '가능성' 섹션
    if m.it_status != "it":
        m.it_status, m.it_reason, m.maybe_reason = "maybe", "fallback", reason


def apply_divisions(m: MergedPosting, divisions: list[Division]) -> None:
    m.extract_attempted = True
    if not divisions:
        _finalize_failure(m, "부문 확인 불가")
        return
    m.divisions = divisions
    m.divisions_from, m.divisions_source = "vlm", "vlm"
    m.it_divisions = [d.name for d in divisions if d.is_it]
    if m.it_divisions:
        m.it_status, m.it_reason, m.maybe_reason = "it", "vlm", None
        m.it_tags = sorted(set(m.it_tags) | set(it_tags(" ".join(m.it_divisions))))
    else:
        m.it_status, m.it_reason, m.maybe_reason = "non_it", "vlm", None


def extract_all(items: list[MergedPosting], settings: Settings, client, llm: LLM) -> int:
    targets = sorted((m for m in items if needs_extract(m)), key=lambda m: (m.deadline is None, m.deadline))
    if not targets:
        return 0
    system = (ROOT / "prompts" / "divisions.md").read_text(encoding="utf-8")
    done = 0
    for m in targets[: settings.detail_limit]:
        src = next((s for s in m.sources if s.source in DETAIL_SOURCES), None)
        if src is None:
            _finalize_failure(m, "상세 확인 불가 (캐치 단독)")
            continue
        if not llm.enabled:
            # 다음 실행(키 설정 후)에 재시도할 수 있게 attempted는 남기지 않는다
            if m.it_status != "it":
                m.it_status, m.it_reason, m.maybe_reason = "maybe", "fallback", "부문 추출 대기 (LLM 미사용)"
            continue
        source = SOURCES[src.source](client, None, None)
        try:
            detail = source.fetch_detail(src.url, src.source_id)
        except Exception as exc:  # noqa: BLE001 - 상세 실패는 maybe로 두고 계속
            log.warning("상세 수집 실패 %s: %s", src.url, exc)
            _finalize_failure(m, "상세 수집 실패")
            continue
        user = (
            f"회사: {m.company}\n제목: {m.title}\n직무 태그: {', '.join(m.job_tags) or '-'}\n\n"
            f"--- 본문 시작 ---\n{detail.text[: settings.text_char_limit]}\n--- 본문 끝 ---"
        )
        try:
            raw = llm.ask_json(system, user, SCHEMA, images=detail.image_urls[: settings.max_images], model=settings.vlm_model)
            out = _Out.model_validate(raw)
        except (LLMError, ValidationError) as exc:
            log.warning("부문 추출 실패 %s: %s", m.id, exc)
            _finalize_failure(m, "부문 추출 실패")
            continue
        apply_divisions(m, out.divisions)
        done += 1
        log.info("부문 추출 %s %s: %s", m.company, m.title[:30], [d.name for d in out.divisions][:6])
    return done
