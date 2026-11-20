"""명령행 진입점."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .config import Settings

log = logging.getLogger("recruit")


def _client(settings: Settings):
    from .http import HttpClient

    return HttpClient(settings.user_agent, delay=settings.request_delay)


def cmd_collect(args, settings: Settings) -> int:
    from .collect import collect_all

    res = collect_all(settings, _client(settings), only=args.sources)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name in {p.source for p in res.postings}:
        rows = [p.model_dump(mode="json") for p in res.postings if p.source == name]
        (out / f"{name}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"counts": res.counts, "errors": res.errors}, ensure_ascii=False))
    return 1 if res.errors and not res.postings else 0


def cmd_daily(args, settings: Settings) -> int:
    from .pipeline import daily

    return daily(settings, _client(settings), offline=args.offline, dry_run=args.dry_run, only=args.sources)


def cmd_publish(args, settings: Settings) -> int:
    from .pipeline import weekly

    return weekly(settings, dry_run=args.dry_run, out=args.out, force=args.force)


def cmd_listed(args, settings: Settings) -> int:
    from .bigco import update_listed

    n = update_listed(settings, _client(settings))
    print(f"상장사 {n}개 저장")
    return 0 if n else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="recruit")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("collect", help="소스별 목록 수집 결과만 JSON으로 저장 (상태 변경 없음)")
    p.add_argument("--sources", nargs="*", default=None)
    p.add_argument("--out", default="out/collect")
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("daily", help="수집→정규화→병합→분류→상세 추출→data/ 갱신")
    p.add_argument("--sources", nargs="*", default=None)
    p.add_argument("--offline", action="store_true", help="tests/fixtures로 실행 (네트워크 없음)")
    p.add_argument("--dry-run", action="store_true", help="data/를 쓰지 않고 결과 요약만 출력")
    p.set_defaults(func=cmd_daily)

    p = sub.add_parser("publish", help="주간 Issue 발행")
    p.add_argument("--dry-run", action="store_true", help="Issue를 만들지 않고 마크다운을 출력")
    p.add_argument("--out", default=None, help="dry-run 마크다운 저장 경로")
    p.add_argument("--force", action="store_true", help="이번 주 이미 발행했어도 다시 발행")
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("listed", help="KRX KIND 상장사 목록 갱신")
    p.set_defaults(func=cmd_listed)

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return args.func(args, Settings())
