# Recruit 봇 설계 (SPEC)

## 1. 개요

링커리어, 자소설닷컴, 캐치에서 신입·인턴 공채 공고를 매일 수집한다. 수집한 공고는 중복을 제거하고 IT 직무만 골라 `ysl-bots/Recruit-Subscribe-IT` 저장소에 주간 GitHub Issue로 발행한다. 구독자는 이 저장소를 Watch해서 알림을 받고, 각자 쓰는 에이전트(Codex, Claude Code)가 Issue와 JSON을 읽어 자기 이력과 맞는 공고를 찾는다. 운영 방식과 코드 구조는 `ysl-bots/Contest`를 따른다.

| 저장소 | 역할 |
|---|---|
| `ysl-bots/Recruit` | 수집, 정규화, 중복 제거, 분류, 상세 추출, 발행 코드. 상태 JSON 보관 |
| `ysl-bots/Recruit-Subscribe-IT` | 발행 전용. Issue만 올라가고 구독자는 Watch |

## 2. 목표와 범위

### 목표 (PoC)
- 3개 소스의 공고를 수집해서 하나의 목록으로 합친다.
- 여러 소스에 올라온 같은 공고는 1건으로 묶고, 소스 링크는 모두 표시한다.
- IT 직무 공고만 발행한다. 대기업·다부문 공채는 상세 페이지를 확인해서 IT 부문이 있을 때만 포함한다.
- 신규, 마감임박, 상시 공고를 구분해서 표시한다.
- 에이전트가 읽기 쉬운 JSON을 함께 제공한다.

### 비목표 (PoC에서 제외)
- 공고 상세 본문, 자격요건, 자소서 문항의 저장과 재게시. 상세 페이지는 대기업·다부문 공고에 한해 열람하고, 저장하는 것은 **추출한 모집 부문 목록**뿐이다.
- 경력 공고, 경력무관 공고
- 기업 리서치(DART, IR, 뉴스)와 DART 기반 모기업 자동 매핑 (2단계)
- Non-IT 구독 저장소 (2단계)
- 로그인이 필요한 페이지, 지원 기능

### 범위

| 항목 | PoC 범위 |
|---|---|
| 소스 | 링커리어, 자소설닷컴, 캐치 |
| 공고 유형 | 신입, 인턴(채용연계형·체험형 모두) |
| 직무 | IT (7장 기준) |
| 수집 주기 | 매일 1회. 상세 추출도 그날 새로 들어온 공고만 매일 처리 |
| 발행 주기 | 주 1회, 월요일 08:xx KST |

## 3. 아키텍처

```
[collect.yml] 매일 07:xx KST
  collect   : 소스별 collector → RawPosting[]
  normalize : 회사명·제목·날짜 정규화 → Posting[]
  dedupe    : 소스 간 중복 병합 → MergedPosting[]
  classify  : 키워드 판정 → 애매한 건은 LLM 재판정
  bigco     : 대기업·다부문 판정 → 신규 건만 상세 fetch → VLM으로 모집 부문 추출 → IT 부문 필터
  state     : data/state.json(내부 전체 상태)과 병합, 마감 처리 → data/postings.json(에이전트용) 생성
  commit    : data/*.json 갱신 커밋

[publish.yml] 월요일 08:xx KST (정각 회피, 예: 08:17)
  publish   : 주간 Issue를 Recruit-Subscribe-IT에 생성
              data/weekly/YYYY-Www.json 저장·커밋, Issue에 링크

[listed.yml] 주 1회
  KRX KIND 상장법인 목록 갱신 → data/listed.json
```

- 실행 환경: GitHub Actions (Public 저장소 무료 범위)
- 상태 저장: DB 없이 `data/` 아래 JSON을 Git으로 관리한다. 이력은 커밋 로그로 남는다.
- 수동 실행: `workflow_dispatch` + `dry_run` 입력(기본값 true). dry_run이면 Issue를 만들지 않고 결과 마크다운을 Job Summary에 출력한다. Contest와 같다.
- 같은 주에 수동 발행 기록이 있으면 cron 발행은 건너뛴다. Contest와 같다.

### 기술 스택 (Contest와 통일)

| 용도 | 선택 |
|---|---|
| 언어 | Python 3.12, uv |
| HTTP | requests (타임아웃·재시도는 `http.py` 공통 모듈에서 처리) |
| HTML 파싱 | beautifulsoup4 |
| JS 렌더링 | 쓰지 않음 (세 소스 모두 SSR 데이터나 JSON API로 수집 가능. 대체 수단으로만 보류) |
| 유사도 | rapidfuzz |
| 스키마 | pydantic v2 |
| LLM/VLM | OpenRouter (openai SDK). 모델은 Contest 기본값을 Variable로 공유 |
| 테스트 | pytest, 오프라인 fixture |
| Issue 발행 | GitHub REST API (requests) |

### Secrets / Variables

| 종류 | 이름 | 필수 | 설명 |
|---|---|---|---|
| Secret | `ISSUE_TOKEN` | ✅ | Fine-grained PAT. Recruit-Subscribe-IT에 `Issues: Read and write` 권한 |
| Secret | `OPENROUTER_API_KEY` | ✅ | 없으면 LLM 재판정과 VLM 추출을 건너뛴다. 이때 대상 공고는 "IT 관련 가능성" 섹션으로 간다. |
| Variable | `ISSUE_REPO` | 선택 | 기본값 `ysl-bots/Recruit-Subscribe-IT` |
| Variable | `VLM_MODEL` / `VLM_FALLBACK_MODEL` | 선택 | Contest와 같은 기본값 |
| Variable | `CLASSIFIER_FALLBACK_MODEL` | 선택 | 애매한 IT 판정에 쓸 LLM |
| Variable | `DETAIL_LIMIT` | 선택 | 실행당 상세 추출 상한. 기본값 30 |

Workflow permissions는 Read and write로 둔다(data 커밋용).

## 4. 데이터 모델

### Posting (정규화 후, 소스 1개의 공고)

| 필드 | 타입 | 설명 |
|---|---|---|
| source | enum | `linkareer` / `jasoseol` / `catch` |
| source_id | str | 소스 내 공고 ID |
| url | str | 원문 링크 |
| company_raw | str | 원본 회사명 |
| company | str | 정규화한 회사명 |
| title | str | 공고 제목 |
| job_tags | list[str] | 소스가 제공하는 직무 분류 |
| employment | enum | `신입` / `채용연계형 인턴` / `체험형 인턴` / `인턴(미상)` / `기타` |
| start_date | date? | 접수 시작일 |
| deadline | date? | 마감일. 상시채용이나 채용시 마감이면 null |
| deadline_type | enum | `date` / `rolling` / `until_filled` |
| image_urls | list[str] | 상세 페이지의 공고 이미지 URL (상세를 가져온 경우만, 저장하지 않음) |
| collected_at | datetime | 수집 시각 (KST) |

`employment`가 `기타`이거나 경력·경력무관이면 수집 단계에서 버린다.

### MergedPosting (중복 병합 후)

| 필드 | 설명 |
|---|---|
| id | `company + 정규화 제목 + 마감일`로 만든 해시 |
| company, title, deadline, deadline_type, employment | 대표값. 우선순위는 캐치 → 자소설닷컴 → 링커리어이고, 값이 비어 있으면 다음 소스 값을 쓴다. |
| sources | `[{source, source_id, url}]` 전체 소스 링크 |
| job_tags | 모든 소스의 직무 태그 합집합 |
| is_listed | 본인 또는 모기업이 코스피·코스닥 상장사인지 여부 |
| parent_company | 모기업명 (사전에 있을 때만) |
| is_bigco | 대기업·다부문 판정 결과 (8장) |
| divisions | VLM으로 추출한 모집 부문 전체 목록. 추출하지 않았으면 null |
| it_divisions | 위 목록 중 IT 부문 |
| it_status | `it` / `maybe` / `non_it` |
| it_tags | 매칭된 IT 분류 (예: 개발, 데이터·AI) |
| it_reason | 판정 근거: `source_tag` / `keyword` / `llm` / `vlm` / `fallback` |
| first_seen | 최초 수집일 (신규 판정 기준) |
| last_seen | 마지막 수집일 |
| published_weeks | 발행된 주차 목록 (재등장 판정용) |
| status | `open` / `closed` |

공고 본문, 자격요건, 자소서 문항, 이미지 파일은 저장하지 않는다.

## 5. 소스별 수집 전략

### 공통 규칙
- 실행을 시작할 때 robots.txt를 읽고 허용된 경로만 요청한다. 차단되면 그 소스를 건너뛰고 로그에 남긴다. 내부 API를 쓸 때도 robots.txt가 막은 경로는 호출하지 않는다.
- 요청 간격은 최소 2초다. 소스별 실행당 상한은 목록 요청 50회, 상세 요청 `DETAIL_LIMIT`(3개 소스 합산)회다.
- User-Agent: `ysl-bots-recruit/0.1 (+https://github.com/ysl-bots/Recruit)`.
- 실패하면 지수 백오프로 2회 재시도하고, 그래도 실패하면 그 소스를 건너뛴다. 다른 소스 수집은 계속한다.
- 상세 페이지는 대기업·다부문 판정을 받은 신규 공고에 대해서만 요청한다. 목록에 마감일이 없을 때도 요청한다.

### 소스별

스파이크로 확정한 방식이다. 상세 내용은 [docs/spike.md](docs/spike.md)에 있다.

| 소스 | 목록 | 부문·직무 | 상세 |
|---|---|---|---|
| 링커리어 | `/list/recruit?page=N&filterBy_jobTypes=NEW&filterBy_jobTypes=INTERN`의 `__NEXT_DATA__` → `__APOLLO_STATE__` (페이지당 20건). Contest 파서를 옮겨 쓴다. | `categories` (IT/개발 = 100003 하위) | `/activity/{id}` `detailText` (HTML + 이미지). VLM 대상 |
| 자소설닷컴 | `/api/v1/employment_companies?per_page=100&page=N` (최신순, 서버 필터 없음 → 로컬 필터) | `employments[]`: `field`(부문명), `division`(1 신입·3 인턴), `duty_group_ids`(IT = 160~170) | `/api/v1/employment_companies/{id}?skip_read_log=true` `content`. 부문이 구조화되어 있어 보통은 필요 없다. |
| 캐치 | `/api/v1.0/recruit/information/getRecruitList?curpage=N&pageSize=30&onRecruitYN=Y&Career=1,4&Sort=0` | `Depth`(직무), `AssignedTaskNameListString`(부문명), `PopularCategory`(기업 분류) | 본문 iframe `/controls/…`가 **robots 차단**이므로 요청하지 않는다. |

- 세 소스 모두 최신순으로 증분 수집한다. 이미 본 ID가 나오면 멈춘다. 첫 실행(백필)만 페이지 상한까지 받는다.
- Playwright는 쓰지 않는다. 캐치 API가 막히면 그때 Playwright를 대체 수단으로 검토한다(결정 기록 유지).

## 6. 정규화와 중복 제거

### 정규화
- 회사명: `(주)`, `㈜`, `주식회사`, `(유)`, 공백을 지우고 영문 대소문자를 통일한다. 그룹사 표기는 `data/company_alias.json` 별칭 사전으로 맞춘다(예: 삼성SDS = 삼성에스디에스).
- 제목: `[회사명]` 접두어, 연도·반기 표기(2026년 하반기, 26년 하반기), 이모지, 특수문자를 지우고 소문자로 바꾼다.
- 날짜: 소스별 형식(`~11.30(월)`, `D-3`, `상시채용`, epoch ms)을 date와 deadline_type으로 변환한다. 연도가 없는 날짜는 수집일 기준으로 가장 가까운 미래 날짜로 해석한다.
- 고용형태: 제목과 태그에서 `채용연계`, `체험형`, `인턴`, `신입`, `경력`, `경력무관` 키워드를 찾아 판정한다.

### 중복 판정
아래 세 조건을 모두 만족하면 같은 공고로 병합한다.
1. 정규화한 회사명이 같다.
2. 마감일이 같거나 ±2일 이내다. 둘 다 rolling·until_filled여도 같은 것으로 본다.
3. 정규화한 제목의 유사도(`rapidfuzz.fuzz.token_set_ratio`)가 85 이상이다.

- 임계값은 PoC 1주차에 약 100쌍을 직접 라벨링해서 조정한다.
- 잘못 병합되거나 병합이 안 된 사례는 `data/dedupe_overrides.json`에 기록한다(`force_merge` / `force_split`).

## 7. IT 직무 분류

위에서부터 순서대로 판정한다.

1. **소스 직무 태그**에 IT 계열(개발, IT, 데이터, SW 등)이 있으면 `it`
2. **키워드 매칭**: 제목이나 직무 태그에 IT 키워드가 있으면 `it`
3. **혼동 키워드**(IT영업, IT기획, 디지털마케팅 등)만 있으면 → LLM 재판정
4. LLM 재판정 결과가 확신 높음이면 `it`/`non_it`, 확신 낮음이거나 호출 실패면 `maybe`
5. 아무것도 맞지 않으면 `non_it`

대기업·다부문 공고(8장)는 이 단계의 결과와 상관없이 후보로 남긴다. 최종 판정은 상세 추출 결과로 한다.

| 분류 | 키워드 예시 |
|---|---|
| 개발 | SW, 소프트웨어, 개발, 백엔드, 프론트엔드, 풀스택, 앱, 임베디드, 펌웨어 |
| 데이터·AI | 데이터, AI, 인공지능, ML, 머신러닝, 데이터 엔지니어, 데이터 분석 |
| 인프라 | 클라우드, 인프라, DevOps, SRE, 네트워크, 시스템 엔지니어, 데이터센터 |
| 보안 | 보안, 정보보호, 정보보안 |
| IT 일반 | IT, 디지털, ICT, 전산 |

- 키워드 사전(분류 키워드와 혼동 키워드)은 `config/it_keywords.yaml`로 분리해서 PR로 개선할 수 있게 한다.

## 8. 대기업·다부문 공채 상세 확인

### 판정 (`is_bigco`): 아래 중 **하나라도** 맞으면 true
1. 소스 직무 태그(병합 후 합집합)가 **3개 이상**이다.
2. 제목에 `공채` 또는 `대졸 신입`(띄어쓰기 변형 포함)이 있다.
3. 회사 **본인 또는 모기업이 코스피·코스닥 상장사**다.

### 상장사 데이터
- `listed.yml`이 주 1회 KRX KIND 상장법인 목록(코스피, 코스닥)을 받아 `data/listed.json`(회사명, 정규화명, 시장, 종목코드)에 저장한다. 다운로드가 실패하면 기존 파일을 그대로 쓴다.
- 모기업 매핑은 `config/parent_company.yaml`에 직접 관리한다(자회사 정규화명 → 모기업명). 예: `삼성디스플레이: 삼성전자`
- 판정: `company`가 listed에 있거나, `parent_company`가 listed에 있으면 `is_listed = true`

- 보조 신호: 캐치 `PopularCategory`가 `코스피`나 `코스닥`이면 상장사로 본다.

### 부문 확보 순서
1. **구조화 데이터**: 자소설 `employments[].field`와 `duty_group_ids`, 캐치 `AssignedTaskNameListString`과 `Depth`. 병합된 공고에 이 값이 있으면 그대로 `divisions`로 쓴다(`it_reason = source_tag`). VLM은 호출하지 않는다.
2. **VLM 상세 추출**: 구조화 부문이 없는 경우(주로 링커리어 단독 공고)에만 한다.

### 상세 추출
- 대상: `is_bigco`이고 `divisions`가 아직 없는 신규 공고. 마감일이 가까운 순으로 실행당 `DETAIL_LIMIT`건까지 처리한다. 남은 건은 다음 날 처리한다.
- 대표 소스(캐치 → 자소설닷컴 → 링커리어 순)의 상세 페이지를 가져와 본문 텍스트와 공고 이미지를 VLM에 넣고, 모집 부문 목록을 JSON으로 받는다. Contest의 `extract.py` 패턴과 `prompts/extract.md` 형식을 따른다.
  - 출력: `{"divisions": [{"name": "SW개발", "is_it": true}, ...]}`
- `divisions`에 IT 부문이 있으면 `it_status = it`이고, `it_divisions`를 채운다(`it_reason = vlm`).
- IT 부문이 하나도 없으면 `non_it`으로 보고 발행에서 뺀다.
- **추출이 실패하거나**(VLM 오류, 이미지 없음, 응답 검증 실패) API 키가 없으면 `maybe`로 둔다(`it_reason = fallback`). 이런 공고는 "IT 관련 가능성" 섹션에 실리고, 실행할 때마다 다시 시도하지는 않는다. 다만 상한 때문에 처리하지 못한 건은 다음 실행에서 처리한다.
- 상세 본문과 이미지는 메모리에서만 쓰고 저장하지 않는다.

## 9. 발행 형식

### 주간 Issue (월요일 08:xx KST)
- 제목: `[IT 공채] 2026-W48 (11/23~11/29) 신규 32건 · 마감임박 12건`
- 라벨: `weekly`, `it`
- 수록 기준
  - **마감 임박**: 발행일 기준 D-7 이내인 열린 공고. 지난주에 이미 발행한 공고도 여기에는 다시 나온다.
  - **이번 주 신규**: 지난 발행 이후 `first_seen`이 찍힌 공고 중 마감임박이 아닌 것
  - **상시·채용시 마감**: deadline_type이 rolling·until_filled인 신규 공고
  - **IT 관련 가능성**: `it_status = maybe`인 신규 공고
  - 이미 발행했고 마감임박도 아닌 공고는 Issue에서 빼고 JSON(`postings.json`)에만 남긴다.

```markdown
> 수집 소스: 링커리어 · 자소설닷컴 · 캐치 | 수집일 2026-11-23
> 공고 원문은 각 링크에서 확인하세요. 봇이 수집한 정보는 틀릴 수 있습니다.
> ⚠️ 이번 주 캐치 수집 실패 (해당 시에만 표시)

## 마감 임박 (D-7 이내)
| 마감 | 회사 | 공고 | 유형 | 분야 | 링크 |
| --- | --- | --- | --- | --- | --- |
| 11/25 (D-2) | ○○ | 2026 하반기 신입 공채 | 신입 | SW개발, 데이터분석 | 캐치 · 자소설 |

## 이번 주 신규
(같은 표, 마감일 순)

## 상시 · 채용시 마감
(같은 표)

## IT 관련 가능성
(같은 표 + 사유 칸: "IT기획 혼동", "부문 추출 실패" 등)

---
에이전트용 데이터: [data/weekly/2026-W48.json](raw URL) · [전체 열린 공고 data/postings.json](raw URL)
```

- **분야** 칸에는 `it_divisions`가 있으면 그 IT 부문명을 쓰고, 없으면 `it_tags`를 쓴다.
- **링크** 칸에는 병합된 모든 소스 링크를 표시한다. 트래픽을 원 출처로 돌려주기 위해서다.
- 본문이 65,536자를 넘으면 표를 나눠 댓글로 이어 붙인다.

### 에이전트용 JSON
- `data/weekly/YYYY-Www.json`: 그 주에 발행한 MergedPosting[]와 섹션 구분 필드
- `data/postings.json`: 현재 열린 공고 전체(IT·maybe만). 매일 갱신된다.
- 구독자용 프롬프트 예시는 Recruit-Subscribe-IT의 README에 둔다.

```
https://raw.githubusercontent.com/ysl-bots/Recruit/main/data/postings.json 을 읽고,
내 이력 페이지([Notion URL])와 비교해 지원할 만한 공고를 마감일 순으로 정리해줘.
divisions 필드가 있으면 내 직무와 맞는 부문만 골라줘.
```

### 마감 임박 Issue (2단계)
- D-3 공고가 있는 날에만 짧은 Issue를 발행한다. 알림 피로를 고려해 PoC에서는 꺼둔다.

## 10. 로드맵

| 단계 | 기간 (추정) | 내용 | 완료 기준 |
|---|---|---|---|
| 1. 스파이크 ✅ | 완료 (11/20) | 자소설 API 파라미터, 캐치 목록 API 존재 여부 또는 Playwright 경로, 링커리어 recruit 필드, KIND 다운로드 방식 확인. 샘플 저장 | 소스별 수집 방법 확정 표, fixture |
| 2. 수집기 | 3~4일 | collector 3종, 정규화, 로컬 CLI | 소스별 1회 실행 결과 JSON |
| 3. 병합·분류 | 2~3일 | dedupe, 키워드와 LLM 분류, 직접 라벨링한 100쌍으로 임계값 조정 | 오병합률·누락률 측정값 |
| 4. 대기업 상세 | 2~3일 | 상장사 목록, 모기업 사전, bigco 판정, VLM 부문 추출 | 대기업 공채 20건 추출 정확도 확인 |
| 5. 발행 | 1~2일 | Issue 렌더링, Actions 3종, 토큰 설정, dry_run | 테스트 저장소에 Issue 1건 발행 |
| 6. 운영 | 2주 | 매일 수집과 주간 발행, 오류 모니터링 | 2주 연속 끊김 없이 발행 |

## 11. 저장소 구조

```
ysl-bots/Recruit/
├── .github/workflows/
│   ├── collect.yml          # 매일 수집·병합·분류·상세 추출·커밋
│   ├── publish.yml          # 주간 Issue 발행
│   ├── listed.yml           # 주간 상장사 목록 갱신
│   └── test.yml
├── src/recruit/
│   ├── __main__.py, cli.py  # collect / daily / publish / listed (--dry-run, --offline)
│   ├── config.py, http.py   # Contest 패턴
│   ├── sources/
│   │   ├── base.py          # robots 확인, rate limit, 재시도
│   │   ├── catch.py         # getRecruitList JSON API
│   │   ├── jasoseol.py
│   │   └── linkareer.py
│   ├── normalize.py
│   ├── dedupe.py
│   ├── classify.py          # 키워드 + LLM
│   ├── bigco.py             # 대기업 판정, 상장사·모기업
│   ├── extract.py           # 상세 → VLM 부문 추출
│   ├── llm.py
│   ├── collect.py           # 소스 격리 수집, blocklist
│   ├── pipeline.py          # daily / weekly, 장애 감지
│   ├── offline.py           # fixture HTTP (--offline)
│   ├── render.py
│   ├── publish.py
│   ├── state.py
│   └── models.py
├── prompts/
│   ├── classify.md
│   └── divisions.md
├── config/
│   ├── sources.yaml         # 소스별 URL, 요청 상한, on/off
│   ├── it_keywords.yaml
│   ├── parent_company.yaml
│   └── blocklist.yaml
├── data/
│   ├── state.json           # 내부 상태: 전체 병합 공고(비IT·마감 30일 포함), 발행 이력
│   ├── postings.json        # 에이전트용: 열린 IT·maybe 공고
│   ├── listed.json          # KRX 상장사
│   ├── company_alias.json
│   ├── dedupe_overrides.json
│   ├── health.json          # 소스별 일일 수집 건수 (장애 감지용)
│   └── weekly/
├── tests/
│   └── fixtures/            # 소스별 샘플 HTML/JSON
├── AGENTS.md
├── SPEC.md
└── README.md
```

## 12. 운영과 장애 대응
- **파서 깨짐 감지**: 소스별 수집 건수가 직전 7일 평균의 30% 미만이면 실패로 본다. 이때 Recruit 저장소에 `alert` 라벨 Issue를 만든다(이미 열린 alert가 있으면 댓글을 단다).
- **부분 실패**: 한 소스가 실패해도 나머지 소스로 발행하고, 주간 Issue 상단에 실패한 소스를 표시한다.
- **회귀 테스트**: `tests/fixtures`에 저장한 HTML·JSON으로 파서를 오프라인 테스트한다.
- **소스 차단 대응**: 403·429가 2일 연속 반복되면 그 소스를 off하고 alert를 보낸다. `sources.yaml`은 사람이 PR로 다시 켠다. 프록시나 UA 위장 같은 우회는 하지 않는다.
- **VLM 비용 관리**: 실행당 `DETAIL_LIMIT`을 넘지 않는다. 추출 실패는 maybe로 처리하고 재시도는 하지 않는다.
- **삭제 요청**: 플랫폼이나 기업이 요청하면 `config/blocklist.yaml`(소스, 회사, 공고 ID)로 즉시 제외한다.

## 13. 정책과 리스크

| 리스크 | 대응 |
|---|---|
| 약관상 자동 접근 제한 해석 (링커리어 제39조 등) | 하루 1회 저빈도·저부하 수집, 식별 가능한 UA, 요청이 오면 즉시 중단 |
| DB권·저작권 (재배포) | 본문과 이미지는 저장하지 않음. 메타데이터, 추출한 부문명, 원문 링크만 발행 |
| 상세 페이지 열람 증가 | 대기업·다부문 신규 공고만, 실행당 상한 적용 |
| 캐치 상세 robots 차단 | 상세는 요청하지 않고 목록 API의 부문·직무 필드만 사용 |
| 잘못된 정보 배포 | Issue 상단에 면책 문구, 원문 확인 안내, 수집일 표기. 애매한 건은 별도 섹션 |
| GitHub Actions IP 차단 | 해당 소스 off. 따로 우회하지 않음 |

## 14. 결정 기록 (2026-11-20)

| 항목 | 결정 |
|---|---|
| 스택 | Contest와 같게 (requests, bs4, pydantic, OpenRouter) |
| IT 분류 | 키워드 우선, 애매한 건만 LLM. 그래도 애매하면 "IT 관련 가능성" 섹션 |
| JS 렌더링 소스 | robots 허용 JSON API 사용. 스파이크에서 세 소스 모두 Playwright 없이 수집 가능함을 확인 |
| 발행 | 월요일 08:xx KST. 신규, 마감임박, 상시, 가능성 섹션 |
| 공고 유형 | 신입, 인턴(채용연계형·체험형) |
| 대기업 공채 | 태그 3개 이상, 제목 키워드, 상장사(본인·모기업) 중 하나라도 맞으면 상세를 VLM으로 확인 |
| 상장사 데이터 | KRX KIND 목록 + 직접 관리하는 모기업 사전 |
| 추출 실패 | IT 관련 가능성 섹션 |
| 주기 | 매일 수집, 주 1회 발행 |
| JSON | `data/weekly/` + `data/postings.json` |

## 15. 열린 질문 (스파이크 이후)
- ~~캐치 목록 API가 robots 허용 경로인지~~ → 허용 경로임을 확인했고 Playwright는 쓰지 않는다 (2026-11-20 스파이크).
- KIND 다운로드는 로컬에서 정상 동작을 확인했다. Actions IP에서 되는지는 첫 실행 때 확인하고, 안 되면 data.go.kr 금융위 기업기본정보 API로 대체한다.
- 상장사 조건을 넣으면 상세 추출 대상이 늘어난다. 첫 주에 실제 건수를 보고 `DETAIL_LIMIT`을 조정한다.

## 16. 구현 메모 (2026-11-21)

구현하면서 SPEC 본문과 달라졌거나 구체화한 점이다.

- **상태 파일 분리**: 증분 수집과 병합에는 비IT·마감 공고까지 필요하다. 그래서 내부 상태는 `data/state.json`에 두고, `data/postings.json`은 에이전트용(열린 IT·maybe 공고만)으로 만든다.
- **증분 수집 중단 조건**: 최신순으로 받다가, 한 페이지에서 필터를 통과한 공고가 모두 이미 본 것이면 멈춘다. 상태에는 통과한 공고만 남기 때문이다.
- **마감 처리**: 마감일이 지나면 closed로 바꾼다. 상시·채용시 마감 공고는 최초 수집 후 60일이 지나면 closed로 바꾼다. closed 공고는 30일 보존해서 다시 신규로 잡히지 않게 한다.
- **IT 분류 규칙 추가** (`config/it_keywords.yaml`)
  - `개발`, `보안`, `QA`, `솔루션`, `디지털`처럼 넓은 단어는 ambiguous로 옮겨 LLM 재판정에 맡긴다. 실데이터에서 소재개발, 품질 QA 같은 오탐이 확인됐다.
  - IT 키워드와 함께 영업·Sales·마케팅 같은 `conflict` 단어가 나오면 LLM 재판정으로 보낸다.
  - 3자 이하 대문자 약어(IT, AI, SW)는 대소문자를 구분해 매칭한다.
  - 자소설 공고는 부문별 직무 그룹으로 IT 여부가 정해지므로, 태그(상위 그룹명 'IT·인터넷' 등)는 키워드 판정에 쓰지 않는다.
  - LLM·VLM 판정 결과는 다음 실행에서 다시 계산하지 않는다.
- **캐치 고용형태**: 신입이면서 정규직이 아닌 공고(계약직만)는 제외한다. 인턴은 계약 형태와 관계없이 포함한다.
- **부문 확보 우선순위**: 자소설 > 캐치 > VLM 순이다(`divisions_source`).
- **대기업 판정 ①(태그 3개 이상)**: 자소설은 부문별 직무 그룹이 합쳐져 대부분 이 조건을 만족한다. 다만 이런 공고는 이미 구조화 부문이 있어서 VLM 비용이 늘지 않는다.
- **VLM 추출 실패 처리**: 키워드나 소스 신호로 이미 IT로 판정된 공고는 IT를 유지하고, 그렇지 않으면 maybe로 둔다. 캐치에만 있는 공고는 상세를 볼 수 없으므로 maybe("상세 확인 불가")로 둔다.
- **자동 off**: `sources.yaml`을 고쳐 쓰는 대신 `data/health.json`의 `disabled`에 기록한다. 사람이 지우면 재개된다.
- **장애 감지**: 소스 오류나 원본 0건이면 즉시 alert를 연다. 일일 원본 건수가 7일 평균의 30% 미만이라는 기준은 평균이 10건 이상일 때만 적용한다. 증분 수집이라 일일 건수가 원래 들쭉날쭉하기 때문이다.
- **주간 발행 중복 방지**: `state.json` `meta.published[주차]`로 판단한다. Contest처럼 artifact로 판단하지 않는다. Issue를 만든 뒤에는 댓글 실패가 있어도 발행 기록을 저장한다.
- **로컬 LLM**: `LLM_BACKEND=codex`이면 `codex exec --output-schema`로 OpenRouter 호출을 대신한다. 이미지는 내려받아 `-i`로 넘긴다.

## 17. 운영 변경 (2026-11-21)

- **캐치 제외**: 첫 Actions 수집에서 `getRecruitList`가 403을 돌려줬다. 로컬에서는 같은 UA로 200이므로 Cloudflare가 데이터센터 IP 대역을 막은 것으로 본다. 12장 정책("Actions IP 차단 → 해당 소스 off, 별도 우회 없음")에 따라 `sources.yaml`에서 끈다. 다른 클라우드나 자체 서버로 옮겨 피해 가는 방식은 쓰지 않고, 캐치에서 허용 회신을 받으면 다시 켠다. 이미 수집한 캐치 공고는 마감될 때까지 유지한다.
- **주간 Issue 제목**: `[IT 공채] 11월 4째주 (11/23~11/29) 신규 n건 · 마감임박 n건`. 월~일 주가 두 달에 걸치면 목요일이 속한 달로 센다. 발행 기록과 `data/weekly/` 파일명은 ISO 주차(`2026-W48`)를 그대로 쓴다.
