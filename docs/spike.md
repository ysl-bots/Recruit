# 소스 조사 결과 (2026-11-20~21)

모든 요청은 UA `ysl-bots-recruit/0.1 (+https://github.com/ysl-bots/Recruit)`로 보냈고, 요청 간격은 2초 이상이었다. 샘플은 `tests/fixtures/`에 있다.

| 항목 | 링커리어 | 자소설닷컴 |
|---|---|---|
| 방식 | 목록 HTML의 `__NEXT_DATA__` → `__APOLLO_STATE__` | JSON API |
| URL | `/list/recruit?filterBy_…&page=N` | `/api/v1/employment_companies?per_page=100&page=N&by_…` |
| robots | 허용 (`/stem/learn/*` 일부만 차단) | 허용 (`/crt/*`, `/core`, `/webview/` 등만 차단) |
| 서버 필터 | `filterBy_<키>=<값>` 반복 파라미터. `jobTypes`, `categoryIDs`, `orgTypeIDs` 동작 | `by_division`, `by_business_types`, `by_duty_group_ids`, `after_end_time` 동작. 접두어 없는 `division` 등은 무시됨 |
| 페이지 크기 | 20 고정 (`pageSize` 무시) | 100 |
| 필터 결과 (11/21) | 110건 | 18건 |
| 회사 | `organizationName` | `name`, `company_group.business_size` |
| 마감 | `recruitCloseAt`(epoch ms), `recruitType`(NORMAL / ASAP=채용시 / ALWAYS=상시) | `end_time`(ISO+09:00) |
| 고용형태 | `jobTypes`(NEW / INTERN …), `RecruitInformation.internTypes`(1 체험형, 2 채용연계형) | `employments[].division`(1 신입, 2 경력, 3 인턴, 4 계약직, 7 교육), `linkage_recruitment` |
| 직무 | `categories` → `Category`(IT/개발 = 100003, 하위 AI/ML 103007, 데이터분석 103006, DevOps/클라우드/보안 103005, QA 103009 …) | `employments[].duty_group_ids` → `/api/v1/duty-groups`(이름은 `config/jasoseol_duty_groups.json`) |
| 모집 부문 | 없음 | `employments[].field` |

## 자소설 필터 파라미터 확인 방법
검색 화면 번들의 `searchFiltersToApi`가 화면 상태를 다음처럼 바꿔 보낸다.
```
{keyword, per_page, page, by_division, by_business_types: businessTypes.join(","), by_duty_group_ids: dutyGroupIds.join(","), after_end_time}
```

## IT 직무그룹 (자소설, 필터에 쓰는 값)
160 QA, 164 시스템프로그래머, 165 응용프로그래머, 166 네트워크·보안·운영, 167 빅데이터·AI, 168 게임개발, 169 HW·임베디드, 170 SW·솔루션·ERP, 171 서비스기획·PM, 172 iOS개발, 173 안드로이드개발, 174 앱 기타, 175 프론트엔드개발, 176 서버·백엔드개발, 177 HTML·퍼블리싱, 178 웹 기타, 179 데이터엔지니어, 180 데이터분석, 181 DBA, 182 데이터 기타
