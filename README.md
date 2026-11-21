# Recruit

링커리어·자소설닷컴의 신입·인턴 채용 공고를 매일 모아 중복을 합치고, IT 직무 공고만 골라 매주 GitHub Issue로 발행하는 봇입니다.

- 구독: **[ysl-bots/Recruit-Subscribe-IT](https://github.com/ysl-bots/Recruit-Subscribe-IT)** ← Watch
- 이 저장소: 수집·병합·분류 코드, 워크플로, 상태 데이터(`data/`)
- 캐치는 GitHub Actions IP에서 403(Cloudflare)이 나서 2026-11-21부터 제외했습니다. 정책상 우회하지 않습니다(`config/sources.yaml`).
- 설계: [SPEC.md](SPEC.md) · 스파이크 결과: [docs/spike.md](docs/spike.md)

## 동작 방식
```
[daily-collect]  매일 07:23 KST
  collect(소스별 최신순 증분) → merge(회사명+마감±2일+제목 유사도) → 대기업 판정(태그3+ / 공채 키워드 / 상장사)
  → IT 분류(구조화 부문 > 소스 직무 > 키워드 > LLM) → 대기업 공고 중 부문 정보가 없는 건만 VLM 부문 추출
  → data/state.json, data/postings.json, data/health.json 커밋

[weekly-publish] 월요일 08:17 KST
  마감 임박(D-7) · 이번 주 신규 · 상시 · IT 관련 가능성 → Recruit-Subscribe-IT Issue
  → data/weekly/YYYY-Www.json 커밋

[weekly-listed]  일요일 06:41 KST
  KRX KIND 상장사 목록 → data/listed.json
```

## 데이터
| 파일 | 내용 |
|---|---|
| `data/postings.json` | 에이전트용. 현재 열린 IT·가능성 공고 전체 (매일 갱신) |
| `data/weekly/YYYY-Www.json` | 주간 Issue에 실린 공고와 섹션 |
| `data/state.json` | 내부 상태. 비IT 포함 전체 병합 공고, 발행 이력 |
| `data/health.json` | 소스별 일일 수집 기록, 자동 off 목록(`disabled`) |
| `data/listed.json` | 코스피·코스닥 상장사 |
| `data/company_alias.json` / `data/dedupe_overrides.json` | 회사명 별칭 / 병합 강제 규칙(`force_merge`, `force_split`에 `"source:id"` 쌍) |

설정은 `config/`에 있습니다: `sources.yaml`(소스 on/off·페이지 상한), `it_keywords.yaml`(IT 키워드), `parent_company.yaml`(모기업), `blocklist.yaml`(삭제 요청).

## 설정 (Settings → Secrets and variables → Actions)
| 종류 | 이름 | 필수 | 설명 |
|---|---|---|---|
| Secret | `ISSUE_TOKEN` | ✅ | fine-grained PAT. Recruit-Subscribe-IT에 `Issues: Read and write`, (선택) `Administration: Read and write` |
| Secret | `OPENROUTER_API_KEY` | ✅ | 없으면 LLM 재판정·VLM 추출을 건너뛰고 해당 공고를 "IT 관련 가능성"으로 보냄 |
| Variable | `ISSUE_REPO` | 선택 | 기본 `ysl-bots/Recruit-Subscribe-IT` |
| Variable | `VLM_MODEL` / `VLM_FALLBACK_MODEL` | 선택 | 부문 추출 모델 (기본 `qwen/qwen3.7-flash`) |
| Variable | `CLASSIFIER_FALLBACK_MODEL` | 선택 | 혼동 키워드 재판정 모델 (기본 `qwen/qwen3.7-flash`) |
| Variable | `DETAIL_LIMIT` | 선택 | 실행당 상세 추출 상한 (기본 30) |

Workflow permissions는 **Read and write**여야 상태를 커밋할 수 있습니다.

## 로컬 실행
```bash
uv venv -p 3.12 && uv pip install -e ".[dev]"
pytest -q                                              # 오프라인 단위 테스트
python -m recruit collect --sources catch              # 목록 수집 결과만 out/collect/에 저장
DATA_DIR=/tmp/r python -m recruit daily --offline      # fixture로 전체 파이프라인 (DATA_DIR 미지정 시 저장 안 함)
python -m recruit daily --dry-run                      # 실제 소스, 저장 없이 요약
python -m recruit publish --dry-run --out issue.md     # 주간 Issue 마크다운 미리보기
python -m recruit listed                               # 상장사 목록 갱신
```
로컬에서는 `LLM_BACKEND=codex`로 OpenRouter 대신 `codex exec`를 씁니다(`LLM_BACKEND=none`이면 LLM 없이 실행).

## 운영
- 소스 차단(403/429)이 2일 연속이면 그 소스를 자동으로 끄고 `alert` Issue를 엽니다. 재개하려면 `data/health.json`의 `disabled`에서 지웁니다. 프록시·UA 위장 같은 우회는 하지 않습니다.
- 삭제 요청은 `config/blocklist.yaml`에 추가합니다.
- 공고 본문·이미지는 저장하지 않습니다. 메타데이터, 모집 부문명, 원문 링크만 발행합니다.
