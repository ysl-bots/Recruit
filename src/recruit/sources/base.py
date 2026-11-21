"""소스 어댑터 공통 인터페이스.

대상 선별(신입·인턴 / IT 직군 / 기업 규모)은 사이트 필터가 맡는다. 어댑터는 필터 결과를 빠짐없이 Posting으로
옮길 뿐 자체적으로 버리지 않는다. 매일 결과 전체를 읽어, 결과에서 빠진 공고를 마감으로 판정할 수 있게 한다.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime

from ..http import HttpClient
from ..models import Posting

log = logging.getLogger(__name__)


class Source(ABC):
    name: str
    page_size: int = 20

    def __init__(self, client: HttpClient, now: datetime, max_pages: int = 10, filters: dict | None = None):
        self.client = client
        self.now = now
        self.max_pages = max_pages
        self.filters = filters or {}
        self.raw_count = 0  # 파싱한 항목 수. 0이면 파서 깨짐 의심
        self.complete = False  # 끝 페이지까지 읽었는지. 아니면 '빠진 공고 = 마감' 판정을 하지 않는다

    @abstractmethod
    def fetch_page(self, page: int) -> list[Posting]:
        """필터 결과 한 페이지."""

    def collect(self) -> list[Posting]:
        out: dict[str, Posting] = {}
        self.raw_count, self.complete = 0, False
        for page in range(1, self.max_pages + 1):
            items = self.fetch_page(page)
            self.raw_count += len(items)
            for p in items:
                out.setdefault(p.source_id, p)
            if len(items) < self.page_size:
                self.complete = True
                break
        else:
            log.warning("%s: max_pages(%d)에 도달해 끝까지 읽지 못함", self.name, self.max_pages)
        return list(out.values())
