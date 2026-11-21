# Recruit-Subscribe-IT

IT 직무 신입·인턴 공채 공고를 매주 월요일 아침 Issue로 받아보는 저장소입니다. 링커리어·자소설닷컴에서 수집해 같은 공고를 하나로 합쳤습니다.

## 구독
오른쪽 위 **Watch → Custom → Issues**를 체크하면 매주 메일·알림이 옵니다.

## Issue 구성
- **마감 임박 (D-7 이내)**: 지난주에 이미 소개한 공고도 마감이 가까우면 다시 나옵니다.
- **이번 주 신규**: 지난 발행 이후 새로 올라온 공고 (마감일 순)
- **상시 · 채용시 마감**

대상은 각 사이트 필터 기준 **신입·인턴 / IT 직군 / 대기업·중견기업·공기업** 공고입니다. "분야" 칸에는 사이트의 IT 직무 분류(자소설은 IT 부문명)를 표시합니다.

## 에이전트로 나에게 맞는 공고 고르기
Codex·Claude Code 같은 에이전트에 다음처럼 요청하세요.

```
https://raw.githubusercontent.com/ysl-bots/Recruit/main/data/postings.json 을 읽고,
내 이력([이력 페이지 URL 또는 파일])과 비교해 지원할 만한 공고를 마감일 순으로 정리해줘.
divisions 필드가 있으면 내 직무와 맞는 부문만 골라줘.
```

- `data/postings.json`: 지금 열려 있는 공고 전체 (매일 갱신)
- `data/weekly/YYYY-Www.json`: 해당 주 Issue에 실린 공고

주요 필드: `company_name`, `title`, `deadline`, `deadline_type`(date/rolling/until_filled), `employment`, `job_tags`(사이트 IT 직무 분류), `divisions`(모집 부문, 자소설만), `it_divisions`, `sources`(원문 링크).

## 주의
- 봇이 수집한 정보는 틀릴 수 있습니다. 지원 전 반드시 원문을 확인하세요.
- 공고 본문은 저장·재게시하지 않고 원문 링크만 제공합니다.
