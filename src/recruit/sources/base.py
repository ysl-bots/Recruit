"""소스 어댑터 공통 인터페이스.

수집은 최신순 증분이다. 한 페이지의 공고가 모두 이미 본 ID면 멈춘다(첫 실행은 max_pages까지).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime

from bs4 import BeautifulSoup

from ..http import HttpClient
from ..models import Posting

log = logging.getLogger(__name__)


@dataclass
class Detail:
    text: str
    image_urls: list[str] = field(default_factory=list)


class Source(ABC):
    name: str

    def __init__(self, client: HttpClient, today: date, now: datetime, max_pages: int = 10):
        self.client = client
        self.today = today
        self.now = now
        self.max_pages = max_pages

    @abstractmethod
    def fetch_page(self, page: int) -> list[Posting | None]:
        """목록 한 페이지. 필터에 걸러진 항목은 None으로 두어 '이 페이지에 새 항목이 있었는지' 판단에 쓴다."""

    def raw_ids(self, page_items: list[Posting | None]) -> list[str]:
        return [p.source_id for p in page_items if p]

    def collect(self, seen: set[str] | None = None) -> list[Posting]:
        seen = seen or set()
        out: dict[str, Posting] = {}
        for page in range(1, self.max_pages + 1):
            items, page_ids = self.fetch_page_with_ids(page)
            if not page_ids:
                break
            for p in items:
                if p and p.source_id not in out:
                    out[p.source_id] = p
            if seen and all(i in seen for i in page_ids):
                log.info("%s: %d페이지에서 이미 본 공고만 나와 중단", self.name, page)
                break
        return list(out.values())

    def fetch_page_with_ids(self, page: int) -> tuple[list[Posting | None], list[str]]:
        """(필터 통과 항목, 페이지의 원본 ID 전체). 기본은 fetch_page 결과에서 ID를 뽑는다."""
        items = self.fetch_page(page)
        return items, self.raw_ids(items)

    def fetch_detail(self, posting_url: str, source_id: str) -> Detail:
        raise NotImplementedError(f"{self.name}는 상세 수집을 지원하지 않는다")


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    lines = (line.strip() for line in soup.get_text("\n").splitlines())
    return "\n".join(line for line in lines if line)


def html_images(html: str, prefixes: tuple[str, ...] = ("http",)) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if src.startswith(prefixes) and src not in urls:
            urls.append(src)
    return urls
