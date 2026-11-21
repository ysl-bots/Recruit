"""--offline 실행용. 네트워크 대신 tests/fixtures를 돌려준다."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

from .config import ROOT

FIX = ROOT / "tests" / "fixtures"
EMPTY_NEXT = '<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"__APOLLO_STATE__":{"ROOT_QUERY":{"activities({\\"filterBy\\":{\\"activityTypeID\\":\\"5\\"}})":{"nodes":[]}}}}}}</script>'


class FixtureHttp:
    def __init__(self):
        self.count: dict[str, int] = {}

    def allowed(self, url: str) -> bool:
        return True

    def _page(self, url: str, params: dict | None) -> int:
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        q.update({k: str(v) for k, v in (params or {}).items()})
        return int(q.get("page") or q.get("curpage") or 1)

    def get_text(self, url: str, params: dict | None = None, encoding: str | None = None) -> str:
        page = self._page(url, params)
        if "linkareer.com/list/recruit" in url:
            return (FIX / "linkareer_recruit_filtered.html").read_text(encoding="utf-8") if page == 1 else EMPTY_NEXT
        if "linkareer.com/activity/" in url:
            sid = url.rstrip("/").rsplit("/", 1)[-1]
            path = FIX / f"linkareer_detail_{sid}.html"
            if path.exists():
                return path.read_text(encoding="utf-8")
            raise FileNotFoundError(f"fixture 없음: {url}")
        raise FileNotFoundError(f"fixture 없음: {url}")

    def get_json(self, url: str, params: dict | None = None):
        page = self._page(url, params)
        if "jasoseol.com/api/v1/employment_companies/" in url:
            sid = urlparse(url).path.rsplit("/", 1)[-1]
            path = FIX / f"jasoseol_detail_{sid}.json"
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
            raise FileNotFoundError(f"fixture 없음: {url}")
        if "jasoseol.com/api/v1/employment_companies" in url:
            return json.loads((FIX / "jasoseol_filtered.json").read_text(encoding="utf-8")) if page == 1 else []
        if "catch.co.kr" in url:
            name = {1: "catch_list.json", 2: "catch_list_bigco.json"}.get(page)
            return json.loads((FIX / name).read_text(encoding="utf-8")) if name else {"recruitData": [], "intTotalRecordCount": 0}
        raise FileNotFoundError(f"fixture 없음: {url}")

    def get(self, url: str, params: dict | None = None):
        raise FileNotFoundError(f"오프라인 모드에서 바이너리 요청 불가: {url}")
