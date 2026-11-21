"""상태 파일.

- data/state.json   : 내부 상태. 모든 병합 공고(마감 후 일정 기간 보존) + 메타(발행 이력, 소스 상태)
- data/postings.json: 에이전트용. 열린 공고 전체
- data/health.json  : 소스별 일일 수집 기록 (장애 감지)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .models import MergedPosting



@dataclass
class State:
    postings: list[MergedPosting] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @classmethod
    def load(cls, data_dir: Path) -> State:
        path = data_dir / "state.json"
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls([MergedPosting.model_validate(x) for x in raw.get("postings", [])], raw.get("meta", {}))

    def save(self, data_dir: Path) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        rows = sorted(self.postings, key=lambda m: (m.first_seen, m.id))
        body = {"meta": self.meta, "postings": [m.model_dump(mode="json", exclude_defaults=False) for m in rows]}
        _write(data_dir / "state.json", body)
        public = [m.model_dump(mode="json") for m in sorted(open_public(self.postings), key=_deadline_key)]
        _write(data_dir / "postings.json", {"updated": self.meta.get("last_collected"), "count": len(public), "postings": public})

    def close_unseen(self, seen: set[tuple[str, str]], complete: set[str], today: date) -> int:
        """끝까지 읽은 소스의 결과에서 빠진 공고는 마감(또는 필터 조건에서 벗어남)으로 본다.
        병합 공고는 모든 소스 링크가 '빠짐'일 때만 닫는다. 실패·미완료 소스의 링크는 판단하지 않는다(살아있다고 본다)."""
        n = 0
        for m in self.postings:
            if m.status != "open":
                continue
            alive = any((s.source, s.source_id) in seen or s.source not in complete for s in m.sources)
            if not alive:
                m.status = "closed"
                m.last_seen = m.last_seen or today
                n += 1
        return n

    def close_and_prune(self, today: date, retention_days: int) -> None:
        keep = []
        for m in self.postings:
            if m.status == "open":
                # 보통은 사이트 결과에서 빠져 close_unseen으로 닫힌다. 그날 수집이 실패해도 마감일이 지나면 닫는다
                if m.deadline and m.deadline < today:
                    m.status = "closed"
            # 닫힌 공고는 보존 기간 동안 남겨 같은 공고가 신규로 다시 잡히지 않게 한다
            ref = m.deadline or m.last_seen
            if m.status == "closed" and (today - ref) > timedelta(days=retention_days):
                continue
            keep.append(m)
        self.postings = keep


def open_public(items: list[MergedPosting]) -> list[MergedPosting]:
    return [m for m in items if m.status == "open"]


def _deadline_key(m: MergedPosting):
    return (m.deadline is None, m.deadline or date.max, m.company)


def _write(path: Path, body) -> None:
    path.write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def load_health(data_dir: Path) -> dict:
    path = data_dir / "health.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"days": [], "disabled": {}}


def save_health(data_dir: Path, health: dict) -> None:
    health["days"] = health.get("days", [])[-30:]
    _write(data_dir / "health.json", health)
