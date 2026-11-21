import json
from datetime import date

from conftest import NOW, read
from recruit import normalize as N
from recruit.dedupe import merge
from recruit.models import Posting
from recruit.pipeline import label, select_sections
from recruit.render import esc, render, week_id, week_label
from recruit.sources import jasoseol, linkareer
from recruit.state import State

TODAY = date(2026, 11, 23)
NO = (set(), set())


def P(source, sid, company, title, deadline=date(2026, 11, 28), **kw):
    return Posting(source=source, source_id=sid, url=f"https://example.com/{sid}", company_raw=company,
                   company=N.company(company), title=title, deadline=deadline, collected_at=NOW, **kw)


def test_linkareer_filter_url():
    url = linkareer.list_url(2, {"categoryIDs": [100003], "jobTypes": ["NEW", "INTERN"], "orgTypeIDs": [1, 3, 5]})
    for q in ["filterBy_categoryIDs=100003", "filterBy_jobTypes=NEW", "filterBy_jobTypes=INTERN",
              "filterBy_orgTypeIDs=1", "filterBy_orgTypeIDs=3", "filterBy_orgTypeIDs=5", "filterBy_status=OPEN", "page=2"]:
        assert q in url


def test_jasoseol_filter_params():
    p = jasoseol.list_params(1, {"division": [1, 3], "business_types": ["big_business", "middle_market"], "duty_group_ids": [160, 164]})
    assert p == {"per_page": 100, "page": 1, "by_division": "1,3", "by_business_types": "big_business,middle_market", "by_duty_group_ids": "160,164"}


def test_filtered_fixtures():
    items, ids = linkareer.parse_list(read("linkareer_recruit_filtered.html"), NOW)
    kept = [p for p in items if p]
    assert len(ids) == 20 and kept and all(p.source_it and p.job_tags for p in kept)
    assert "전체" not in {t for p in kept for t in p.job_tags}
    groups = jasoseol.it_duty_groups({"duty_group_ids": [160, *range(164, 183)]})
    items, ids = jasoseol.parse_list(json.loads(read("jasoseol_filtered.json")), NOW, groups)
    kept = [p for p in items if p]
    assert len(ids) == 18 and kept and any(d.is_it for p in kept for d in p.divisions)


def test_close_unseen():
    ms = merge([], [P("linkareer", "1", "A사", "신입"), P("jasoseol", "2", "B사", "인턴"),
                    P("linkareer", "3", "C사", "개발자 신입"), P("jasoseol", "3", "C사", "개발자 신입")], date(2026, 11, 20), NO)
    st = State(ms)
    # 링커리어만 끝까지 읽었고 1번·C사 링커리어 링크가 빠짐 → A사만 닫힘 (C사는 자소설 링크가 미확인이라 유지)
    n = st.close_unseen({("jasoseol", "2")}, {"linkareer"}, TODAY)
    status = {m.company: m.status for m in st.postings}
    assert n == 1 and status == {N.company("A사"): "closed", N.company("B사"): "open", N.company("C사"): "open"}
    # 두 소스 모두 끝까지 읽었는데 C사가 없으면 닫힘
    assert st.close_unseen({("jasoseol", "2")}, {"linkareer", "jasoseol"}, TODAY) == 1


def test_sections_and_render():
    ms = merge([], [
        P("linkareer", "1", "A사", "백엔드 신입", deadline=date(2026, 11, 25), job_tags=["백엔드/서버개발"]),
        P("linkareer", "2", "B사", "데이터 | 인턴", deadline=date(2026, 12, 20)),
        P("linkareer", "3", "C사", "상시 개발자", deadline=None, deadline_type="rolling"),
    ], date(2026, 11, 20), NO)
    for m in ms:
        label(m)
    sec = select_sections(ms, TODAY, None, 7)
    assert [len(sec[k]) for k in ("urgent", "new", "rolling")] == [1, 1, 1]
    for m in ms:
        m.published_weeks = ["2026-W47"]
    sec2 = select_sections(ms, TODAY, date(2026, 11, 16), 7)
    assert [len(sec2[k]) for k in ("urgent", "new", "rolling")] == [1, 0, 0]
    body, extra = render(sec, TODAY, {"jasoseol": "차단"}, "https://x/w.json", "https://x/p.json")
    assert "데이터 \\| 인턴" in body and "백엔드/서버개발" in body and "수집 실패" in body and not extra
    assert "IT 관련 가능성" not in body
    assert week_id(TODAY) == "2026-W48"


def test_render_split_long():
    ms = merge([], [P("linkareer", str(i), f"회사{i}", "개발자 " + "가" * 300, deadline=date(2026, 12, 20)) for i in range(400)],
               date(2026, 11, 20), NO)
    for m in ms:
        label(m)
    body, extra = render(select_sections(ms, TODAY, None, 7), TODAY, {}, "https://x/w", "https://x/p")
    assert len(body) <= 65536 and extra and all(len(c) <= 65536 for c in extra)


def test_esc():
    assert esc("a|b [x](y)") == "a\\|b \\[x\\](y)"


def test_week_label():
    assert week_label(date(2026, 11, 23)) == "11월 4째주"
    assert week_label(date(2026, 11, 30)) == "12월 1째주"  # 11/30~12/6: 목요일 12/3
    assert week_label(date(2026, 12, 28)) == "12월 5째주"
