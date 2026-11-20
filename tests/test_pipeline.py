from datetime import date

from conftest import FIX, NOW
from recruit import bigco
from recruit import normalize as N
from recruit.dedupe import merge
from recruit.extract import apply_divisions, needs_extract
from recruit.models import Division, Posting
from recruit.pipeline import select_sections
from recruit.render import esc, render, week_id

TODAY = date(2026, 11, 23)


def P(source, sid, company, title, deadline=date(2026, 11, 28), **kw):
    return Posting(source=source, source_id=sid, url=f"https://example.com/{sid}", company_raw=company,
                   company=N.company(company), title=title, deadline=deadline, collected_at=NOW, **kw)


def test_kind_parse():
    rows = bigco.parse_kind((FIX / "kind_stockMkt.html").read_bytes().decode("euc-kr", "ignore"), "코스피")
    assert len(rows) == 20 and rows[0]["code"]


def test_bigco_mark():
    listed = frozenset({N.company("삼성전자")})
    m = merge([], [P("linkareer", "1", "삼성디스플레이", "신입 채용")], TODAY, (set(), set()))[0]
    bigco.mark(m, listed)
    assert m.is_listed and m.is_bigco and m.parent_company == "삼성전자"
    m = merge([], [P("linkareer", "2", "작은회사", "2026 하반기 공채")], TODAY, (set(), set()))[0]
    bigco.mark(m, frozenset())
    assert m.is_bigco and not m.is_listed
    m = merge([], [P("linkareer", "3", "작은회사", "백엔드 개발자")], TODAY, (set(), set()))[0]
    bigco.mark(m, frozenset())
    assert not m.is_bigco


def test_extract_apply():
    m = merge([], [P("linkareer", "1", "A그룹", "2026 하반기 공채")], TODAY, (set(), set()))[0]
    m.is_bigco = True
    assert needs_extract(m)
    apply_divisions(m, [Division(name="경영지원"), Division(name="SW개발", is_it=True)])
    assert m.it_status == "it" and m.it_divisions == ["SW개발"] and not needs_extract(m)
    m2 = merge([], [P("linkareer", "2", "B그룹", "2026 하반기 공채")], TODAY, (set(), set()))[0]
    apply_divisions(m2, [])
    assert m2.it_status == "maybe" and m2.maybe_reason


def _it(m, **kw):
    m.it_status = "it"
    for k, v in kw.items():
        setattr(m, k, v)
    return m


def test_sections_and_render():
    ms = merge([], [
        P("catch", "1", "A사", "백엔드 신입", deadline=date(2026, 11, 25)),
        P("catch", "2", "B사", "데이터 인턴", deadline=date(2026, 12, 20)),
        P("catch", "3", "C사", "상시 개발자", deadline=None, deadline_type="rolling"),
        P("catch", "4", "D사", "IT기획 | 신입", deadline=date(2026, 12, 20)),
    ], date(2026, 11, 20), (set(), set()))
    for m in ms[:3]:
        _it(m)
    ms[3].it_status, ms[3].maybe_reason = "maybe", "혼동 키워드"
    sec = select_sections(ms, TODAY, None, 7)
    assert [len(sec[k]) for k in ("urgent", "new", "rolling", "maybe")] == [1, 1, 1, 1]
    # 이미 발행된 공고는 마감 임박일 때만 다시 나온다
    for m in ms:
        m.published_weeks = ["2026-W47"]
    sec2 = select_sections(ms, TODAY, date(2026, 11, 16), 7)
    assert [len(sec2[k]) for k in ("urgent", "new", "rolling", "maybe")] == [1, 0, 0, 0]
    body, extra = render(sec, TODAY, {"catch": "차단"}, "https://x/w.json", "https://x/p.json")
    assert "IT기획 \\| 신입" in body and "수집 실패" in body and not extra
    assert week_id(TODAY) == "2026-W48"


def test_render_split_long():
    ms = merge([], [P("catch", str(i), f"회사{i}", "개발자 " + "가" * 300, deadline=date(2026, 12, 20)) for i in range(400)],
               date(2026, 11, 20), (set(), set()))
    for m in ms:
        _it(m)
    body, extra = render(select_sections(ms, TODAY, None, 7), TODAY, {}, "https://x/w", "https://x/p")
    assert len(body) <= 65536 and extra and all(len(c) <= 65536 for c in extra)


def test_esc():
    assert esc("a|b [x](y)") == "a\\|b \\[x\\](y)"
