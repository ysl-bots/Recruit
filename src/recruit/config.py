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
    openrouter_api_key: str = field(default_factory=lambda: os.environ.get("OPENROUTER_API_KEY", ""))
    openrouter_base_url: str = field(default_factory=lambda: _env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"))
    # openrouter | codex | none. codex는 로컬 테스트용으로 `codex exec`를 호출한다
    llm_backend: str = field(default_factory=lambda: _env("LLM_BACKEND", "openrouter"))
    vlm_model: str = field(default_factory=lambda: _env("VLM_MODEL", "qwen/qwen3.7-flash"))
    vlm_fallback_model: str = field(default_factory=lambda: _env("VLM_FALLBACK_MODEL", "deepseek/deepseek-v4.1-flash"))
    classifier_fallback_model: str = field(default_factory=lambda: _env("CLASSIFIER_FALLBACK_MODEL", "qwen/qwen3.7-flash"))
    detail_limit: int = field(default_factory=lambda: int(_env("DETAIL_LIMIT", "30")))
    classify_batch: int = field(default_factory=lambda: int(_env("CLASSIFY_BATCH", "30")))
    request_delay: float = field(default_factory=lambda: float(_env("REQUEST_DELAY", "2.0")))
    max_images: int = 3
    text_char_limit: int = 6000
    urgent_days: int = 7
    closed_retention_days: int = 30
    user_agent: str = USER_AGENT
    github_token: str = field(default_factory=lambda: os.environ.get("ISSUE_TOKEN", ""))
    issue_repo: str = field(default_factory=lambda: _env("ISSUE_REPO", "ysl-bots/Recruit-Subscribe-IT"))
    alert_repo: str = field(default_factory=lambda: _env("ALERT_REPO", "ysl-bots/Recruit"))
    code_repo: str = field(default_factory=lambda: _env("CODE_REPO", "ysl-bots/Recruit"))
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", str(DATA_DIR))))

    @property
    def llm_enabled(self) -> bool:
        if self.llm_backend == "codex":
            return True
        return self.llm_backend == "openrouter" and bool(self.openrouter_api_key)
