# AGENTS.md — 코드 리뷰·작업 지침

## 프로젝트 개요
- 채용 사이트(링커리어·자소설닷컴·캐치)의 신입·인턴 공고를 매일 수집·병합하고, IT 공고만 주간 Issue로 `Recruit-Subscribe-IT`에 발행합니다. 설계는 [SPEC.md](SPEC.md).
- 파이프라인: `collect(사이트 필터 결과 전체) → dedupe.merge → state.close_unseen → pipeline.label → state.save`, 주간 `pipeline.weekly → render → publish`.
- IT 직군·기업 규모·고용형태는 사이트 필터(`config/sources.yaml`)를 그대로 따릅니다. 봇 자체 키워드·LLM 판정을 다시 넣는 변경은 근거를 확인합니다.
- Python 3.12, `pytest`. 테스트는 네트워크 없이 `tests/fixtures`와 `offline.FixtureHttp`로 돌아가야 합니다.

## 리뷰 원칙
- 한국어로 리뷰하고 위치는 `파일:줄`로 짚습니다. 정확성 버그 우선, 각 지적에 구체적 실패 시나리오를 붙입니다.
- 심각도: `🔴 반드시 수정` / `🟡 권장` / `💬 질문`.
- `data/`만 바뀐 `chore(state): …` 봇 커밋은 리뷰하지 않습니다.

## 중점 검토 항목
- **수집 정책**: 모든 요청은 `HttpClient`(robots.txt 확인, 2초 간격, 상한, 403/429 즉시 중단)를 거쳐야 합니다. robots가 막은 경로(예: 캐치 `/controls`)를 호출하거나 UA 위장·우회를 추가하면 🔴.
- **상태 호환성**: `state.json`은 운영 데이터입니다. 모델 필드 추가는 기본값이 있어야 하고 의미 변경은 마이그레이션이 필요합니다.
- **병합**: `dedupe.similar` 변경은 오병합(서로 다른 공고가 사라짐)을 더 심각하게 봅니다. 양성·음성 회귀 테스트가 있어야 합니다.
- **마감 처리**: `close_unseen`은 끝까지 읽은(`complete`) 소스만 기준으로 삼아야 합니다. 실패·상한 도달 소스 때문에 열린 공고가 닫히면 🔴.
- **발행**: dry-run에서 Issue 생성·상태 저장이 없어야 하고, Issue 생성 후 실패가 나도 발행 기록이 저장돼 중복 발행이 없어야 합니다. 렌더링은 외부 텍스트를 `render.esc`로 이스케이프하고 링크는 https만 허용합니다.
- **저작권**: 공고 본문·이미지를 저장하거나 발행하는 변경은 🔴.

## 코드 스타일
- 주석·로그는 한국어, "왜"를 설명하는 주석만.
- 넓은 `except Exception`은 대체 경로가 있고 `# noqa: BLE001 - 사유`가 붙은 경우만.
