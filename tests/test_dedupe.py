from datetime import date

from conftest import NOW
from recruit import normalize as N
from recruit.dedupe import merge
from recruit.models import Division, Posting

TODAY = date(2026, 11, 21)


def P(source, sid, company, title, deadline=date(2026, 11, 30), **kw):
    return Posting(source=source, source_id=sid, url=f"https://x/{sid}", company_raw=company,
                   company=N.company(company), title=title, deadline=deadline, collected_at=NOW, **kw)


NO = (set(), set())


def test_normalize_company_and_title():
    assert N.company("(주)카카오뱅크") == N.company("카카오뱅크 주식회사")
    assert N.company("삼성에스디에스") == N.company("삼성SDS")
    assert N.title("[카카오뱅크] 2026년 하반기 신입 공채", "카카오뱅크") == N.title("2026 하반기 신입 공채")


def test_merge_cross_source():
    out = merge([], [
        P("linkareer", "1", "카카오뱅크", "[카카오뱅크] 2026 하반기 신입 개발자 공채"),
        P("jasoseol", "9", "(주)카카오뱅크", "2026년 하반기 신입 개발자 공채", deadline=date(2026, 12, 1)),
    ], TODAY, NO)
    assert len(out) == 1
    assert [s.source for s in out[0].sources] == ["jasoseol", "linkareer"]
    assert out[0].title == "2026년 하반기 신입 개발자 공채"  # 자소설 우선


def test_no_merge_different_division_or_deadline():
    out = merge([], [
        P("linkareer", "1", "카카오뱅크", "AI 프로덕트 디자이너 (채용연계형 인턴)"),
        P("linkareer", "9", "카카오뱅크", "AI Native 인증 서비스 기획자 (채용연계형 인턴)"),
        P("jasoseol", "5", "카카오뱅크", "AI 프로덕트 디자이너 (채용연계형 인턴)", deadline=date(2026, 12, 20)),
        P("jasoseol", "6", "카카오뱅크", "AI Native 인증 서비스 기획자 (채용연계형 인턴)", deadline=date(2026, 12, 20)),
    ], TODAY, NO)
    assert len(out) == 4


def test_no_merge_same_source():
    out = merge([], [P("linkareer", "1", "A사", "신입 채용"), P("linkareer", "2", "A사", "신입 채용")], TODAY, NO)
    assert len(out) == 2


def test_force_split_and_existing_update():
    pair = frozenset({"linkareer:1", "jasoseol:9"})
    out = merge([], [P("linkareer", "1", "A사", "신입 공채"), P("jasoseol", "9", "A사", "신입 공채")], TODAY, (set(), {pair}))
    assert len(out) == 2
    again = merge(out, [P("jasoseol", "9", "A사", "신입 공채 (연장)", deadline=date(2026, 12, 5))], date(2026, 11, 22), NO)
    assert len(again) == 2
    m = next(m for m in again if m.sources[0].source == "jasoseol")
    assert m.deadline == date(2026, 12, 5) and m.first_seen == TODAY and m.last_seen == date(2026, 11, 22)
