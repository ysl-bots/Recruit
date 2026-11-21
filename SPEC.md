# Recruit 봇 설계 (SPEC)

> 2026-11-21 개정. 처음 설계(자체 키워드·LLM IT 분류, 대기업 판정, VLM 부문 추출 등)는 git 이력에 있다.

## 1. 개요

링커리어와 자소설닷컴에서 **신입·인턴 / IT 직군 / 대기업·중견기업·공기업** 채용 공고를 매일 수집하고, 소스 간 중복을 합친 뒤 매주 `ysl-bots/Recruit-Subscribe-IT`에 GitHub Issue로 발행한다. 구독자는 저장소를 Watch해서 알림을 받고, 에이전트는 `data/postings.json`을 읽는다.

| 저장소 | 역할 |
|---|---|
| `ysl-bots/Recruit` | 수집·병합·발행 코드, 상태 데이터(`data/`) |
| `ysl-bots/Recruit-Subscribe-IT` | 발행 전용. Issue만 올라간다 |

**원칙: 대상 선별은 사이트 필터에 맡긴다.** 봇은 IT 여부, 기업 규모, 고용형태를 따로 판정하지 않는다. 필터 결과에 있는 공고는 모두 발행 대상이다.

## 2. 범위

| 항목 | 내용 |
|---|---|
| 소스 | 링커리어, 자소설닷컴 |
| 대상 | 각 사이트 검색 필터 결과 (3장) |
| 수집 | 매일 1회, 필터 결과 전체 |
| 발행 | 주 1회, 월요일 08:17 KST |
| 저장·발행하는 것 | 메타데이터(회사, 제목, 마감, 고용형태, 직무 분류, 부문명)와 원문 링크 |
| 하지 않는 것 | 공고 본문·이미지 저장, 로그인 페이지, 차단 우회 |

## 3. 소스와 필터

필터 값은 `config/sources.yaml`의 `filters`에 있고, 각 사이트 검색 화면의 필터를 그대로 옮긴 것이다. `filters`가 없는 소스는 실행하지 않는다(필터 없이 돌면 전체 공고가 들어오기 때문).

### 링커리어
- 요청: `https://linkareer.com/list/recruit?filterBy_activityTypeID=5&filterBy_status=OPEN&filterBy_<키>=<값>…&orderBy_field=RECENT&page=N`
- 필터: `categoryIDs=100003`(IT/개발), `jobTypes=NEW,INTERN`, `orgTypeIDs=1,3,5`(대기업·공기업·중견기업)
- 파싱: 페이지에 내장된 `__NEXT_DATA__` → `__APOLLO_STATE__` → `ROOT_QUERY.activities(…).nodes`. 페이지당 20건이다.
- 규모(2026-11-21): 110건

### 자소설닷컴
- 요청: `https://jasoseol.com/api/v1/employment_companies?per_page=100&page=N&by_<키>=<쉼표 목록>&after_end_time=<오늘>`
  - 검색 화면(`/search`)이 API로 보내는 형식(`searchFiltersToApi`) 그대로다. `by_` 접두어가 없는 파라미터는 서버가 무시한다.
- 필터: `division=1,3`(신입·인턴), `business_types=big_business,middle_market,public_institution`, `duty_group_ids=160,164~182`(IT 직무)
- 파싱: JSON 배열. 공고마다 `employments[]`(모집 부문: `field`, `division`, `duty_group_ids`)가 있다.
- 규모(2026-11-21): 18건

### 공통 수집 규칙 (`http.py`)
- 실행 시작 시 robots.txt를 확인하고 허용 경로만 요청한다. 두 사이트 모두 위 경로를 허용한다.
- 같은 호스트 요청 간격 2초 이상, 실패 시 지수 백오프로 2회 재시도
- 403·429는 차단으로 보고 그 소스를 바로 중단한다. 프록시, UA 위장, 실행 위치 변경 같은 우회는 하지 않는다.
- User-Agent: `ysl-bots-recruit/0.1 (+https://github.com/ysl-bots/Recruit)`

## 4. 데이터 모델 (`models.py`)

### Posting (소스 1개의 공고)
| 필드 | 설명 |
|---|---|
| source, source_id, url | `linkareer` / `jasoseol`, 소스 내 ID, 원문 링크 |
| company_raw, company | 원본 회사명, 정규화명 |
| title | 공고 제목 |
| job_tags | 소스의 IT 직무 분류명. 링커리어는 IT/개발 하위 직무, 자소설은 필터에 걸린 직무그룹 이름 |
| employment | 표시용 라벨: 신입 / 채용연계형 인턴 / 체험형 인턴 / 인턴 |
| start_date, deadline, deadline_type | 접수 시작일, 마감일, `date` / `rolling`(상시) / `until_filled`(채용시 마감) |
| divisions | 모집 부문(자소설만). `is_it`는 필터의 직무그룹에 속한 부문 |

### MergedPosting (병합 공고)
| 필드 | 설명 |
|---|---|
| id | 최초 생성 시 해시 (이후 고정) |
| company, company_name, title, deadline, employment … | 대표값. 자소설 → 링커리어 순으로 우선 |
| sources | 병합된 모든 소스 링크 |
| job_tags, divisions, it_divisions | 소스 분류 합집합, 자소설 부문, 그중 IT 부문명 |
| first_seen, last_seen | 최초·최근 수집일 (신규 판정 기준) |
| published_weeks | 실린 주차 (재등장 판정) |
| status | `open` / `closed` |

## 5. 병합 (`dedupe.py`)

아래 세 조건을 모두 만족하면 같은 공고로 합친다.
1. 정규화한 회사명이 같다. `(주)`, `주식회사` 등과 공백을 지우고 소문자로 바꾼다. 그룹사 표기는 `data/company_alias.json`으로 맞춘다.
2. 마감일이 같거나 ±2일 이내다. 둘 다 마감일이 없어도 같은 것으로 본다.
3. 정규화한 제목의 `rapidfuzz.token_set_ratio`가 85 이상이다. `[회사명]` 접두어, 연도·반기 표기, 특수문자는 지우고 비교한다.

- 같은 소스의 다른 공고끼리는 합치지 않는다. 잘못 합쳐지면 공고가 조용히 사라지므로 이쪽을 더 경계한다.
- 오병합·미병합 사례는 `data/dedupe_overrides.json`의 `force_merge` / `force_split`(`"source:id"` 쌍)에 기록한다.

## 6. 상태와 마감 (`state.py`)

| 파일 | 내용 |
|---|---|
| `data/state.json` | 내부 상태. 모든 병합 공고(마감 후 30일 보존)와 메타(`published`, `last_collected`) |
| `data/postings.json` | 에이전트용. 열린 공고 전체 |
| `data/health.json` | 소스별 일일 수집 기록, 연속 차단 일수, 자동 off(`disabled`) |
| `data/weekly/YYYY-Www.json` | 주간 Issue에 실린 공고와 섹션 |

**마감 처리**
- 사이트 결과에서 빠진 공고는 닫는다(`close_unseen`). 끝 페이지까지 읽은 소스(`complete`)만 기준으로 삼는다. 병합 공고는 모든 소스 링크가 빠졌을 때만 닫고, 실패했거나 페이지 상한에 걸린 소스의 링크는 살아 있다고 본다.
- 그날 수집이 실패했더라도 마감일이 지난 공고는 닫는다.
- 닫힌 공고는 30일 보존해서 같은 공고가 다시 신규로 잡히지 않게 한다. 사이트에 다시 나타나면 다시 연다.

## 7. 주간 발행 (`pipeline.weekly`, `render.py`)

- 제목: `[IT 공채] 11월 4째주 (11/23~11/29) 신규 n건 · 마감임박 n건`
  - 월~일 주가 두 달에 걸치면 목요일이 속한 달로 센다. 발행 기록과 파일명은 ISO 주차(`2026-W48`)를 쓴다.
- 라벨: `weekly`, `it`

| 섹션 | 조건 |
|---|---|
| 마감 임박 (D-7 이내) | 열린 공고 중 마감일이 D-0~D-7. 지난주에 실린 공고도 다시 싣는다 |
| 이번 주 신규 | 지난 발행 이후 처음 수집됐고 아직 실린 적 없는 공고. 마감일이 있고 마감 임박이 아닌 것 |
| 상시 · 채용시 마감 | 신규 중 마감일이 없는 것 |

- 표 칸: 마감 / 회사 / 공고 / 유형 / 분야 / 링크
  - **분야**: 자소설 IT 부문명이 있으면 그것을, 없으면 소스 직무 분류를 쓴다.
  - **링크**: 병합된 모든 소스 링크를 건다.
- 상단에 면책 문구, 수집일, 최근 7일 내 수집에 실패한 소스를 표시한다.
- 외부 텍스트는 마크다운 이스케이프하고, 링크는 https만 허용한다.
- 본문이 65,000자를 넘으면 표를 행 단위로 잘라 댓글로 이어 붙인다.
- Issue는 바로 잠그고, 저장소 상호작용을 협업자로 제한한다(구독자 메일 오염 방지).
- **중복 방지**: `state.json` `meta.published[주차]`가 있으면 건너뛴다(`--force`로 재발행). Issue를 만든 뒤에는 댓글이 실패해도 발행 기록을 저장한다.

## 8. 워크플로

| 워크플로 | 시각 (KST) | 내용 |
|---|---|---|
| `collect.yml` | 매일 07:23 | `recruit daily` → `data/` 커밋. 이상이 있으면 이 저장소에 `alert` Issue |
| `publish.yml` | 월 08:17 | `recruit publish` → Issue 발행, `data/` 커밋 |
| `test.yml` | PR·push | pytest + fixture로 오프라인 파이프라인 실행 |

- 세 워크플로 모두 `concurrency: recruit-state`로 상태 파일 동시 수정을 막는다.
- 수동 실행(`workflow_dispatch`)은 기본값이 dry_run이다.
- Secret: `ISSUE_TOKEN`(발행 저장소 Issues 쓰기, 선택으로 Administration). alert는 `github.token`을 쓴다.

## 9. 장애 대응

- **즉시 alert**: 소스 오류(파싱 실패, robots 차단, 403·429)나 결과 0건
- **건수 급감 alert**: 결과 건수가 직전 7일 평균의 30% 미만 (평균 10건 이상일 때만)
- **자동 off**: 403·429가 2일 연속이면 `health.json` `disabled`에 기록하고 수집을 멈춘다. 사람이 지우면 재개한다.
- **부분 실패**: 한 소스가 실패해도 나머지 소스로 진행하고, 주간 Issue에 실패를 표시한다.
- **삭제 요청**: `config/blocklist.yaml`(소스·회사·공고 ID)로 즉시 제외한다.
- **회귀 테스트**: `tests/fixtures`의 필터 결과 샘플로 파서를 테스트한다. 사이트 구조가 바뀌면 새 샘플로 교체한다.

## 10. 정책과 리스크

| 리스크 | 대응 |
|---|---|
| 약관상 자동 접근 제한 | 하루 1회·요청 약 10회의 저부하 수집, 식별 가능한 UA, 요청이 오면 즉시 중단 |
| DB권·저작권 | 본문·이미지는 저장하지 않음. 메타데이터와 원문 링크만 발행 |
| 잘못된 정보 | 면책 문구, 원문 확인 안내, 수집일 표기 |
| 실행 환경 IP 차단 | 해당 소스 off. 우회하지 않음 |

## 11. 저장소 구조

```
.github/workflows/  collect.yml, publish.yml, test.yml
src/recruit/
  cli.py, __main__.py   collect / daily / publish (--dry-run, --offline)
  config.py, http.py    설정, robots·간격·재시도·차단 처리
  sources/              base.py, linkareer.py, jasoseol.py
  collect.py            소스 격리 수집, blocklist
  normalize.py          회사명·제목·날짜 정규화, 고용형태 라벨
  dedupe.py             병합
  state.py              상태 파일, 마감 처리
  pipeline.py           daily / weekly, 장애 감지
  render.py, publish.py Issue 렌더링·발행
  offline.py            fixture HTTP
config/  sources.yaml, blocklist.yaml, jasoseol_duty_groups.json
data/    state.json, postings.json, health.json, weekly/, company_alias.json, dedupe_overrides.json
tests/   fixtures/ (필터 결과 샘플), test_dedupe.py, test_pipeline.py
docs/    spike.md, subscribe-README.md
```
