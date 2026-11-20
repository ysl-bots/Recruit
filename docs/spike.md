# 1단계 스파이크 결과 (2026-11-20)

모든 요청은 UA `ysl-bots-recruit/0.1 (+https://github.com/ysl-bots/Recruit)`로 보냈고, 요청 간격은 2초 이상이었다. 샘플은 `tests/fixtures/`에 저장했다.

## 소스별 수집 방법 확정표

| 항목 | 링커리어 | 자소설닷컴 | 캐치 |
|---|---|---|---|
| 목록 방식 | HTML `__NEXT_DATA__` → `__APOLLO_STATE__` | JSON API | JSON API |
| 목록 URL | `/list/recruit?page=N&filterBy_jobTypes=NEW&filterBy_jobTypes=INTERN` | `/api/v1/employment_companies?per_page=100&page=N` | `/api/v1.0/recruit/information/getRecruitList?curpage=N&pageSize=30&onRecruitYN=Y&Career=1,4&Sort=0` |
| robots | 허용 | 허용 (`/api/v1/*`은 차단 목록에 없음) | 허용 (차단은 `/api/v1.0/recruit/log`, `/recruit/detail/log`뿐) |
| 페이지 크기 | 20 고정 (`pageSize` 무시) | 100 | 30 |
| 서버 필터 | `filterBy_jobTypes`(반복 파라미터), `filterBy_categoryIDs` 동작 | 쿼리 필터 무시됨 → 로컬 필터 | `Career`(1 신입, 2 경력, 4 인턴, 0 경력무관), `Size`(1 대기업, 3 중견, 2 중소, 4 공기업, 5 외국계, 6 스타트업), `Sort`(0 최신, 2 마감, 3 인기) 동작 |
| 규모 (11/20) | 신입+인턴 1,789건 / IT 카테고리 247건 | 응답 헤더 `total-page` (전체, 마감 포함 가능) | 신입+인턴 1,074건 / 그중 대기업 307건 |
| 정렬 | 최신순(RECENT) | `created_at` 내림차순 (100건 ≈ 8일) | `Sort=0` 최신순 |
| 증분 수집 | 최신순으로 받다가 이미 본 ID가 나오면 중단 | 같음, 하루 1~2페이지 | 같음 |
| 회사 | `organizationName` | `name` | `CompName`, `CompID` |
| 마감 | `recruitCloseAt` (epoch ms) | `end_time` (ISO+09:00), 부문별 `employments[].end_time` | `ApplyEndDatetime` (UTC ISO), `Dday` |
| 고용형태 | `jobTypes` (NEW/INTERN/EXPERIENCED/CONTRACT), `RecruitInformation.internTypes` | `employments[].division` (1 신입, 2 경력, 3 인턴, 4 계약직, 7 교육) | `CareerGubunCode` (신입/경력…), `GubunCode` (정규직/인턴/계약직) |
| 직무 | `categories` → `Category` (IT/개발 = 100003, 하위 AI/ML 103007, DevOps/클라우드/보안 103005, QA 103009 …) | 부문별 `employments[].duty_group_ids` → `/api/v1/duty-groups` (IT·인터넷 = 94, 하위 160~171) | `Depth` (쉼표 구분 직무명) |
| 부문명 | 없음 (상세 본문) | **`employments[].field`** (부문별 구조화) | **`AssignedTaskNameListString`** |
| 기업 분류 | 없음 | 목록 필터에 `big_business` 등 존재 (응답 필드는 `company_group`에서 확인 필요) | `PopularCategory` (예: 코스닥, 매출액 1조 클럽, 수도권 공공기관) |
| 상세 | `/activity/{id}` `__NEXT_DATA__` → `detailText.text` (HTML, 공고 이미지는 `media-cdn.linkareer.com`) | `/api/v1/employment_companies/{id}?skip_read_log=true` → `content` (HTML) | 본문은 iframe `/controls/recruitDetail/{id}`이고 **robots 차단(`/controls`)** → 사용 불가 |
| Playwright | 불필요 | 불필요 | **불필요** |

## 상장사 데이터 (KRX KIND)
- `https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&marketType=stockMkt|kosdaqMkt`
- EUC-KR HTML 표. 컬럼: 회사명, 시장구분, 종목코드, 업종, 주요제품, 상장일, 결산월, 대표자명, 홈페이지, 지역
- 코스피 약 828개사. 응답 200을 확인했다. robots.txt는 404이므로 제한이 없는 것으로 본다.
- fixture는 앞 20행만 남겼다.

## SPEC에 반영한 변경
1. **Playwright 제외**: 캐치 목록을 JSON API로 받을 수 있다. Playwright는 API가 막혔을 때 쓸 대체 수단으로만 남긴다.
2. **부문 정보는 구조화 데이터를 먼저 쓴다**: 자소설은 `employments[].field`와 `duty_group_ids`, 캐치는 `AssignedTaskNameListString`과 `Depth`를 쓴다. VLM 상세 추출은 이 정보가 없을 때만, 즉 링커리어 단독 공고나 부문 정보가 비어 있는 공고에만 한다.
3. **캐치 상세는 수집하지 않는다** (robots 차단).
4. **상장사 보조 신호**: 캐치 `PopularCategory`가 코스피·코스닥이면 상장사로 본다.

## 남은 확인 사항 (2단계 구현 중)
- 자소설 응답에 마감된 공고가 섞이는지 확인해야 한다. `end_time`으로 로컬에서 걸러낸다.
- 링커리어 `ActivityInternType` 값별 의미(채용연계형/체험형)
- 캐치 `Career=1,4` 결과에 "신입/경력" 혼합 공고가 섞인다. `CareerGubunCode`에 신입이 들어 있으면 포함한다.
- 캐치 `PopularCategory` 값의 전체 목록
