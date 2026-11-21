"""daily: 수집(사이트 필터)→병합→마감 처리→상태 저장. weekly: 주간 Issue 발행.

IT 직군·기업 규모·신입/인턴 판정은 각 사이트의 필터 결과를 그대로 따른다 (자체 판정 없음).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path

from .collect import CollectResult, collect_all
from .sources import SOURCES
from .config import Settings, now_kst, today_kst
from .dedupe import merge
from .models import MergedPosting
from .publish import comment, create_issue, lock_issue, open_alert, renew_interaction_limit
from .render import render, week_id, week_label, week_range
from .state import State, load_health, open_public, save_health

log = logging.getLogger(__name__)

LOW_RATIO = 0.3
BLOCK_DAYS_TO_DISABLE = 2


def _health(settings: Settings, res: CollectResult, today: date, dry_run: bool) -> list[str]:
    """소스별 이상 감지. 반환은 alert 메시지들."""
    health = load_health(settings.data_dir)
    days = health.setdefault("days", [])
    alerts = []
    for name in SOURCES:
        if name in res.errors:
            alerts.append(f"- `{name}`: {res.errors[name]}")
            continue
        past = [d["raw"].get(name, 0) for d in days[-7:] if name in d.get("raw", {})]
        avg = sum(past) / len(past) if past else 0
        if avg >= 10 and res.raw.get(name, 0) < avg * LOW_RATIO:
            alerts.append(f"- `{name}`: 원본 {res.raw.get(name, 0)}건 (7일 평균 {avg:.0f}건의 30% 미만)")
    # 차단 연속 일수 → 자동 off
    streak = health.setdefault("block_streak", {})
    for name in SOURCES:
        streak[name] = streak.get(name, 0) + 1 if name in res.blocked else 0
        if streak[name] >= BLOCK_DAYS_TO_DISABLE and name not in health.setdefault("disabled", {}):
            health["disabled"][name] = f"{today} 403/429 {streak[name]}일 연속"
            alerts.append(f"- `{name}`: 차단이 {streak[name]}일 연속이라 자동 off. 재개하려면 data/health.json의 disabled에서 지우세요.")
    days.append({"date": str(today), "raw": res.raw, "new": res.counts, "errors": res.errors})
    if not dry_run:
        save_health(settings.data_dir, health)
    return alerts


def daily(settings: Settings, client, offline: bool = False, dry_run: bool = False, only: list[str] | None = None) -> int:
    today = today_kst()
    state = State.load(settings.data_dir)
    if offline:
        from .config import DATA_DIR
        from .offline import FixtureHttp

        client = FixtureHttp()
        if settings.data_dir.resolve() == DATA_DIR.resolve() and not dry_run:
            log.warning("오프라인 결과로 저장소 data/를 덮지 않도록 dry-run으로 실행 (저장하려면 DATA_DIR 지정)")
            dry_run = True
    health = load_health(settings.data_dir)
    res = collect_all(settings, client, only=only, disabled=health.get("disabled"))
    if not res.postings and len(res.errors) == len(SOURCES):
        log.error("모든 소스 실패: %s", res.errors)
    before = len(state.postings)
    state.postings = merge(state.postings, res.postings, today)
    seen = {(p.source, p.source_id) for p in res.postings}
    n_gone = state.close_unseen(seen, res.complete, today)
    state.close_and_prune(today, settings.closed_retention_days)
    state.meta["last_collected"] = now_kst().isoformat(timespec="seconds")
    state.meta["last_errors"] = res.errors
    alerts = _health(settings, res, today, dry_run)

    pub = open_public(state.postings)
    summary = {
        "collected": res.counts,
        "errors": res.errors,
        "merged_total": len(state.postings),
        "new_merged": len(state.postings) - before,
        "closed_unseen": n_gone,
        "open": len(pub),
    }
    print(json.dumps(summary, ensure_ascii=False))
    if dry_run:
        return 0
    state.save(settings.data_dir)
    if alerts and not offline:
        token = os.environ.get("ALERT_TOKEN") or os.environ.get("GITHUB_TOKEN") or settings.github_token
        open_alert(token, settings.alert_repo, "[alert] 수집 이상 감지", f"{today} 수집 결과\n\n" + "\n".join(alerts))
    return 0


def select_sections(items: list[MergedPosting], today: date, last_published: date | None, urgent_days: int) -> dict[str, list[MergedPosting]]:
    pub = open_public(items)
    since = last_published or date.min

    def is_new(m: MergedPosting) -> bool:
        return m.first_seen > since and not m.published_weeks

    urgent = [m for m in pub if m.deadline and 0 <= (m.deadline - today).days <= urgent_days]
    urgent_ids = {m.id for m in urgent}
    new = [m for m in pub if is_new(m) and m.id not in urgent_ids and m.deadline_type == "date"]
    rolling = [m for m in pub if is_new(m) and m.deadline_type != "date"]
    key = lambda m: (m.deadline is None, m.deadline or date.max, m.company)  # noqa: E731
    return {k: sorted(v, key=key) for k, v in {"urgent": urgent, "new": new, "rolling": rolling}.items()}


def weekly(settings: Settings, dry_run: bool = False, out: str | None = None, force: bool = False) -> int:
    today = today_kst()
    wid = week_id(today)
    start, end = week_range(today)
    state = State.load(settings.data_dir)
    published = state.meta.setdefault("published", {})
    if wid in published and not force:
        log.info("%s 이미 발행됨 (#%s). --force로 재발행", wid, published[wid].get("number"))
        return 0
    last = max((date.fromisoformat(v["date"]) for v in published.values()), default=None)
    sections = select_sections(state.postings, today, last, settings.urgent_days)
    # 최근 7일 내 수집 실패 소스
    failed: dict[str, str] = {}
    for d in load_health(settings.data_dir).get("days", []):
        if date.fromisoformat(d["date"]) > today - timedelta(days=7):
            failed.update(d.get("errors") or {})
    # 설정에서 끈 소스는 '실패'가 아니라 제외이므로 경고하지 않는다
    from .config import load_yaml

    cfg = load_yaml("sources.yaml")
    failed = {k: v for k, v in failed.items() if cfg.get(k, {}).get("enabled", True)}
    raw = f"https://raw.githubusercontent.com/{settings.code_repo}/main/data"
    body, extra = render(sections, today, failed, f"{raw}/weekly/{wid}.json", f"{raw}/postings.json")
    n_new = len(sections["new"]) + len(sections["rolling"])
    title = f"[IT 공채] {week_label(today)} ({start:%m/%d}~{end:%m/%d}) 신규 {n_new}건 · 마감임박 {len(sections['urgent'])}건"
    weekly_json = {
        "week": wid,
        "published": str(today),
        "sections": {k: [m.id for m in v] for k, v in sections.items()},
        "postings": [m.model_dump(mode="json") for v in sections.values() for m in v],
    }
    if dry_run:
        text = f"# {title}\n\n{body}\n" + "".join(f"\n\n<!-- 댓글 -->\n{c}" for c in extra)
        if out:
            Path(out).write_text(text, encoding="utf-8")
        print(text if not out else f"{out}에 저장 ({len(text)}자)")
        return 0
    number = create_issue(settings.github_token, settings.issue_repo, title, body, ["weekly", "it"])
    # Issue를 만든 뒤에는 어떤 실패가 나도 발행 기록을 저장해야 중복 발행이 생기지 않는다
    for c in extra:
        try:
            comment(settings.github_token, settings.issue_repo, number, c)
        except Exception as exc:  # noqa: BLE001 - 이어 붙이기 실패는 로그만
            log.error("댓글 이어 붙이기 실패 #%d: %s", number, exc)
    try:
        lock_issue(settings.github_token, settings.issue_repo, number)
    except Exception as exc:  # noqa: BLE001 - 잠금 실패는 발행 성공을 되돌리지 않는다
        log.warning("Issue 잠금 실패: %s", exc)
    renew_interaction_limit(settings.github_token, settings.issue_repo)
    for v in sections.values():
        for m in v:
            if wid not in m.published_weeks:
                m.published_weeks.append(wid)
    published[wid] = {"date": str(today), "number": number, "counts": {k: len(v) for k, v in sections.items()}}
    (settings.data_dir / "weekly").mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "weekly" / f"{wid}.json").write_text(json.dumps(weekly_json, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    state.save(settings.data_dir)
    log.info("발행 완료 %s #%d", settings.issue_repo, number)
    return 0
