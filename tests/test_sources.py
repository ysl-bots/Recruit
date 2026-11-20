import json

from conftest import read
from recruit.sources import catch, jasoseol, linkareer


def test_linkareer_list(now):
    items, ids = linkareer.parse_list(read("linkareer_recruit_list.html"), now)
    assert len(ids) == 20
    kept = [p for p in items if p]
    assert kept and all(p.employment != "기타" for p in kept)
    assert all(p.url.startswith("https://linkareer.com/activity/") for p in kept)


def test_linkareer_it_category(now):
    items, _ = linkareer.parse_list(read("linkareer_recruit_list_it.html"), now)
    kept = [p for p in items if p]
    assert kept and all(p.source_it for p in kept)


def test_linkareer_detail():
    d = linkareer.parse_detail(read("linkareer_detail_366068.html"), "366068")
    assert d.image_urls and d.image_urls[0].startswith("https://media-cdn.linkareer.com")


def test_jasoseol_list(now):
    items, ids = jasoseol.parse_list(json.loads(read("jasoseol_list.json")), now)
    assert len(ids) == 100
    kept = [p for p in items if p]
    assert kept
    assert all(p.employment in ("신입", "인턴", "채용연계형 인턴", "체험형 인턴") for p in kept)
    assert any(p.source_it for p in kept)
    assert any(d.is_it for p in kept for d in p.divisions)


def test_catch_list(now):
    items, ids = catch.parse_list(json.loads(read("catch_list_bigco.json")), now)
    kept = [p for p in items if p]
    assert kept and len(ids) <= 30
    assert all(p.divisions or p.job_tags for p in kept)
    assert any(p.company_category for p in kept)
