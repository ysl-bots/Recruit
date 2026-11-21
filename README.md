# Recruit

링커리어·자소설닷컴의 신입·인턴 채용 공고를 매일 모아 중복을 합치고, IT 직무 공고만 골라 매주 GitHub Issue로 발행하는 봇입니다.

- 구독: **[ysl-bots/Recruit-Subscribe-IT](https://github.com/ysl-bots/Recruit-Subscribe-IT)** ← Watch
- 이 저장소: 수집·병합·분류 코드, 워크플로, 상태 데이터(`data/`)
- 캐치는 GitHub Actions IP에서 403(Cloudflare)이 나서 2026-11-21부터 제외했습니다. 정책상 우회하지 않습니다(`config/sources.yaml`).
- 설계: [SPEC.md](SPEC.md) · 스파이크 결과: [docs/spike.md](docs/spike.md)

## 동작 방식
```
[daily-collect]  매일 07:23 KST
  각 사이트 검색 필터(신입·인턴 / IT 직군 / 대기업·중견기업·공기업) 결과 전체를 수집
  → merge(회사명+마감±2일+제목 유사도) → 결과에서 빠진 공고는 마감 처리
  → data/state.json, data/postings.json, data/health.json 커밋

[weekly-publish] 월요일 08:17 KST
  마감 임박(D-7) · 이번 주 신규 · 상시 → Recruit-Subscribe-IT Issue ("[IT 공채] 11월 4째주 …")
  → data/weekly/YYYY-Www.json 커밋
```
IT 여부·기업 규모·고용형태는 봇이 따로 판정하지 않고 사이트 필터를 그대로 따릅니다. 필터 값은 `config/sources.yaml`에 있습니다.

| 소스 | 필터 (사이트 화면 기준) |
|---|---|
| 링커리어 | 직무 IT/개발, 신입·인턴, 기업형태 대기업·공기업·중견기업 |
| 자소설닷컴 | 신입·인턴, 대기업·중견기업·공공기관, IT 직무(160, 164~182) |

## 데이터
| 파일 | 내용 |
|---|---|
| `data/postings.json` | 에이전트용. 현재 열린 공고 전체 (매일 갱신) |
| `data/weekly/YYYY-Www.json` | 주간 Issue에 실린 공고와 섹션 |
| `data/state.json` | 내부 상태. 마감 30일 이내 공고 포함 전체 병합 공고, 발행 이력 |
| `data/health.json` | 소스별 일일 수집 기록, 자동 off 목록(`disabled`) |
| `data/company_alias.json` / `data/dedupe_overrides.json` | 회사명 별칭 / 병합 강제 규칙(`force_merge`, `force_split`에 `"source:id"` 쌍) |

설정: `config/sources.yaml`(소스 on/off·필터·페이지 상한), `config/blocklist.yaml`(삭제 요청).

## 설정 (Settings → Secrets and variables → Actions)
| 종류 | 이름 | 필수 | 설명 |
|---|---|---|---|
| Secret | `ISSUE_TOKEN` | ✅ | fine-grained PAT. Recruit-Subscribe-IT에 `Issues: Read and write`, (선택) `Administration: Read and write` |
| Variable | `ISSUE_REPO` | 선택 | 기본 `ysl-bots/Recruit-Subscribe-IT` |

Workflow permissions는 **Read and write**여야 상태를 커밋할 수 있습니다.

## 로컬 실행
```bash
uv venv -p 3.12 && uv pip install -e ".[dev]"
pytest -q                                              # 오프라인 단위 테스트
python -m recruit collect --sources catch              # 목록 수집 결과만 out/collect/에 저장
DATA_DIR=/tmp/r python -m recruit daily --offline      # fixture로 전체 파이프라인 (DATA_DIR 미지정 시 저장 안 함)
python -m recruit daily --dry-run                      # 실제 소스, 저장 없이 요약
python -m recruit publish --dry-run --out issue.md     # 주간 Issue 마크다운 미리보기
```

## 운영
- 소스 차단(403/429)이 2일 연속이면 그 소스를 자동으로 끄고 `alert` Issue를 엽니다. 재개하려면 `data/health.json`의 `disabled`에서 지웁니다. 프록시·UA 위장 같은 우회는 하지 않습니다.
- 삭제 요청은 `config/blocklist.yaml`에 추가합니다.
- 공고 본문·이미지는 저장하지 않습니다. 메타데이터와 원문 링크만 발행합니다.
