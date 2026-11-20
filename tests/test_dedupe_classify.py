from datetime import date

from conftest import NOW
from recruit import normalize as N
from recruit.classify import keyword_classify, it_tags
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


def test_deadline_text():
    assert N.parse_deadline_text("~11.30(월)", TODAY) == (date(2026, 11, 30), "date")
    assert N.parse_deadline_text("~01.05", TODAY) == (date(2027, 1, 5), "date")
    assert N.parse_deadline_text("D-3", TODAY) == (date(2026, 11, 24), "date")
    assert N.parse_deadline_text("상시채용", TODAY) == (None, "rolling")
    assert N.parse_deadline_text("채용시 마감", TODAY) == (None, "until_filled")


def test_merge_cross_source():
    out = merge([], [
        P("linkareer", "1", "카카오뱅크", "[카카오뱅크] 2026 하반기 신입 개발자 공채"),
        P("catch", "9", "(주)카카오뱅크", "2026년 하반기 신입 개발자 공채", deadline=date(2026, 12, 1)),
    ], TODAY, NO)
    assert len(out) == 1
    assert [s.source for s in out[0].sources] == ["catch", "linkareer"]
    assert out[0].title == "2026년 하반기 신입 개발자 공채"  # 캐치 우선


def test_no_merge_different_division_or_deadline():
    out = merge([], [
        P("linkareer", "1", "카카오뱅크", "AI 프로덕트 디자이너 (채용연계형 인턴)"),
        P("catch", "9", "카카오뱅크", "AI Native 인증 서비스 기획자 (채용연계형 인턴)"),
        P("jasoseol", "5", "카카오뱅크", "AI 프로덕트 디자이너 (채용연계형 인턴)", deadline=date(2026, 12, 20)),
    ], TODAY, NO)
    assert len(out) == 3


def test_no_merge_same_source():
    out = merge([], [P("catch", "1", "A사", "신입 채용"), P("catch", "2", "A사", "신입 채용")], TODAY, NO)
    assert len(out) == 2


def test_force_split_and_existing_update():
    pair = frozenset({"linkareer:1", "catch:9"})
    out = merge([], [P("linkareer", "1", "A사", "신입 공채"), P("catch", "9", "A사", "신입 공채")], TODAY, (set(), {pair}))
    assert len(out) == 2
    again = merge(out, [P("catch", "9", "A사", "신입 공채 (연장)", deadline=date(2026, 12, 5))], date(2026, 11, 22), NO)
    assert len(again) == 2
    m = next(m for m in again if m.sources[0].source == "catch")
    assert m.deadline == date(2026, 12, 5) and m.first_seen == TODAY and m.last_seen == date(2026, 11, 22)


def test_it_keywords():
    assert "개발" in it_tags("백엔드 개발자")
    assert "데이터·AI" in it_tags("AI엔지니어 신입")
    assert it_tags("IT영업 신입") == []
    assert it_tags("디지털마케팅 인턴") == []
    assert it_tags("경영지원 신입") == []


def _m(title, **kw):
    return merge([], [P("catch", "1", "A사", title, **kw)], TODAY, NO)[0]


def test_keyword_classify():
    m = _m("백엔드 개발 신입"); keyword_classify(m); assert m.it_status == "it"
    m = _m("IT영업 신입"); keyword_classify(m); assert m.it_status == "unknown"
    m = _m("물류 신입"); keyword_classify(m); assert m.it_status == "non_it"
    m = _m("2026 신입 공채", divisions=[Division(name="SW개발"), Division(name="경영지원")])
    keyword_classify(m)
    assert m.it_status == "it" and m.it_divisions == ["SW개발"]


def test_jasoseol_divisions_override_tags():
    p = P("jasoseol", "7", "AJ네트웍스", "수시채용 (신입/경력)", job_tags=["IT·인터넷", "영업"],
          divisions=[Division(name="IT장비 B2B영업 (신입)", is_it=False)])
    m = merge([], [p], TODAY, NO)[0]
    keyword_classify(m)
    assert m.it_status != "it"
