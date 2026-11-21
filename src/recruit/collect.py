"""소스별 수집. 한 소스의 실패가 다른 소스를 멈추지 않는다."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .config import Settings, load_yaml, now_kst
from .http import Blocked, HttpClient, RobotsDisallowed
from .models import Posting
from .sources import SOURCES

log = logging.getLogger(__name__)


@dataclass
class CollectResult:
    postings: list[Posting] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    raw: dict[str, int] = field(default_factory=dict)
    complete: set[str] = field(default_factory=set)  # 끝까지 읽은 소스 → 결과에서 빠진 공고를 마감 처리
    errors: dict[str, str] = field(default_factory=dict)  # source → 사유
    blocked: set[str] = field(default_factory=set)


def blocklisted(p: Posting) -> bool:
    bl = load_yaml("blocklist.yaml")
    if p.source in (bl.get("sources") or []):
        return True
    from .normalize import company

    if p.company in {company(c) for c in bl.get("companies") or []}:
        return True
    return any(str(x.get("source")) == p.source and str(x.get("source_id")) == p.source_id for x in bl.get("postings") or [])


def collect_all(
    settings: Settings,
    client: HttpClient,
    only: list[str] | None = None,
    disabled: dict | None = None,
) -> CollectResult:
    cfg = load_yaml("sources.yaml")
    now = now_kst()
    res = CollectResult()
    for name, cls in SOURCES.items():
        sc = cfg.get(name, {})
        if only and name not in only:
            continue
        if not sc.get("enabled", True):
            log.info("%s: sources.yaml에서 꺼져 있어 건너뜀", name)
            continue
        if name in (disabled or {}):
            log.warning("%s: 차단 반복으로 자동 off 상태 (data/health.json disabled에서 지우면 재개)", name)
            res.errors[name] = "자동 off (차단 반복)"
            continue
        src = cls(client, now.date(), now, max_pages=int(sc.get("max_list_pages", 10)), filters=sc.get("filters"))
        try:
            items = src.collect()
        except Blocked as exc:
            log.error("%s 차단: %s", name, exc)
            res.errors[name] = f"차단({exc})"
            res.blocked.add(name)
            continue
        except RobotsDisallowed as exc:
            log.error("%s robots.txt 차단: %s", name, exc)
            res.errors[name] = "robots.txt 차단"
            continue
        except Exception as exc:  # noqa: BLE001 - 소스 격리: 나머지 소스는 계속 수집
            log.exception("%s 수집 실패", name)
            res.errors[name] = f"{type(exc).__name__}: {exc}"[:200]
            continue
        items = [p for p in items if not blocklisted(p)]
        res.counts[name] = len(items)
        res.raw[name] = getattr(src, "raw_count", 0)
        if res.raw[name] == 0:
            res.errors[name] = "목록 0건 (파서 깨짐 의심)"
        elif getattr(src, "complete", False):
            res.complete.add(name)
        res.postings += items
        log.info("%s: %d건", name, len(items))
    return res
