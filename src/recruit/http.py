"""호스트별 지연·재시도·요청 상한·robots.txt 확인을 적용한 HTTP 클라이언트."""

from __future__ import annotations

import logging
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

log = logging.getLogger(__name__)


class RobotsDisallowed(Exception):
    """robots.txt가 막은 경로. 우회하지 않고 해당 요청을 포기한다."""


class BudgetExceeded(Exception):
    """소스별 실행당 요청 상한 초과."""


class Blocked(Exception):
    """403/429. 차단으로 보고 소스를 건너뛴다(재시도·우회하지 않음)."""


class HttpClient:
    def __init__(self, user_agent: str, delay: float = 2.0, timeout: float = 20.0, retries: int = 2):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.user_agent = user_agent
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self._last: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self.budget: dict[str, int] = {}  # host → 남은 요청 수. 없으면 무제한
        self.count: dict[str, int] = {}

    def _wait(self, url: str) -> None:
        host = urlparse(url).netloc
        elapsed = time.monotonic() - self._last.get(host, 0.0)
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last[host] = time.monotonic()

    def allowed(self, url: str) -> bool:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self._robots:
            rp = RobotFileParser()
            try:
                self._wait(base)
                resp = self.session.get(f"{base}/robots.txt", timeout=self.timeout)
                # 4xx는 robots 없음(전체 허용), 5xx·네트워크 오류는 보수적으로 전체 차단
                if resp.status_code >= 500:
                    rp.disallow_all = True
                elif resp.status_code >= 400:
                    rp.allow_all = True
                else:
                    rp.parse(resp.text.splitlines())
            except requests.RequestException as exc:
                log.warning("robots.txt 조회 실패 %s: %s", base, exc)
                rp.disallow_all = True
            self._robots[base] = rp
        return self._robots[base].can_fetch(self.user_agent, url)

    def _charge(self, url: str) -> None:
        host = urlparse(url).netloc
        self.count[host] = self.count.get(host, 0) + 1
        if host in self.budget:
            if self.budget[host] <= 0:
                raise BudgetExceeded(host)
            self.budget[host] -= 1

    def get(self, url: str, params: dict | None = None) -> requests.Response:
        if not self.allowed(url):
            raise RobotsDisallowed(url)
        self._charge(url)
        for attempt in range(self.retries + 1):
            self._wait(url)
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                if resp.status_code in (403, 429):
                    raise Blocked(f"{resp.status_code} {url}")
                resp.raise_for_status()
                return resp
            except requests.RequestException as exc:
                if attempt == self.retries:
                    raise
                log.warning("GET %s 실패 (%s), 재시도 %d", url, exc, attempt + 1)
                time.sleep(2**attempt)
        raise AssertionError("unreachable")

    def get_text(self, url: str, params: dict | None = None, encoding: str | None = None) -> str:
        resp = self.get(url, params)
        if encoding:
            resp.encoding = encoding
        elif not resp.encoding or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = "utf-8"
        return resp.text

    def get_json(self, url: str, params: dict | None = None):
        return self.get(url, params).json()
