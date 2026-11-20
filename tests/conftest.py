from datetime import datetime
from pathlib import Path

import pytest

from recruit.config import KST

FIX = Path(__file__).parent / "fixtures"
# fixture 수집 시점
NOW = datetime(2026, 11, 20, 23, 55, tzinfo=KST)


@pytest.fixture
def now():
    return NOW


def read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")
