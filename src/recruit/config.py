"""설정값. 환경변수가 있으면 우선하고, 없으면 기본값을 쓴다. 키워드·소스 설정은 config/*.yaml에 둔다."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from functools import cache
from pathlib import Path

import yaml

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
USER_AGENT = "ysl-bots-recruit/0.1 (+https://github.com/ysl-bots/Recruit)"


def now_kst() -> datetime:
    return datetime.now(KST)


def today_kst() -> date:
    return now_kst().date()


def _env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


@cache
def load_yaml(name: str) -> dict:
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@dataclass
class Settings:
    request_delay: float = field(default_factory=lambda: float(_env("REQUEST_DELAY", "2.0")))
    urgent_days: int = 7
    closed_retention_days: int = 30
    user_agent: str = USER_AGENT
    github_token: str = field(default_factory=lambda: os.environ.get("ISSUE_TOKEN", ""))
    issue_repo: str = field(default_factory=lambda: _env("ISSUE_REPO", "ysl-bots/Recruit-Subscribe-IT"))
    alert_repo: str = field(default_factory=lambda: _env("ALERT_REPO", "ysl-bots/Recruit"))
    code_repo: str = field(default_factory=lambda: _env("CODE_REPO", "ysl-bots/Recruit"))
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", str(DATA_DIR))))
