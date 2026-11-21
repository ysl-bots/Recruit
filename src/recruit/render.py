"""주간 Issue 마크다운."""

from __future__ import annotations

import re
from datetime import date, timedelta

from .models import SOURCE_LABEL, MergedPosting

MAX_BODY = 65000  # GitHub Issue 본문 상한 65,536자에 여유를 둔다
_SAFE_URL = re.compile(r"^https://[^\s()<>\[\]|]+$")


def esc(text: str) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    for ch in "\\|[]<>`*_~":
        t = t.replace(ch, "\\" + ch)
    return t


def week_id(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def week_label(d: date) -> str:
    """'11월 4째주'. 주(월~일)는 목요일이 속한 달로 센다 (ISO 주차와 같은 기준)."""
    thu = d - timedelta(days=d.weekday()) + timedelta(days=3)
    return f"{thu.month}월 {(thu.day - 1) // 7 + 1}째주"


def source_names() -> str:
    from .config import load_yaml

    cfg = load_yaml("sources.yaml")
    labels = {"linkareer": "링커리어", "jasoseol": "자소설닷컴"}
    return " · ".join(v for k, v in labels.items() if cfg.get(k, {}).get("enabled", True))


def week_range(d: date) -> tuple[date, date]:
    start = d - timedelta(days=d.weekday())
    return start, start + timedelta(days=6)


def deadline_cell(m: MergedPosting, today: date) -> str:
    if m.deadline_type == "rolling":
        return "상시"
    if m.deadline_type == "until_filled":
        return "채용시 마감"
    if not m.deadline:
        return "-"
    dday = (m.deadline - today).days
    return f"{m.deadline:%m/%d} (D-{dday})" if dday > 0 else f"{m.deadline:%m/%d} (D-day)"


def field_cell(m: MergedPosting) -> str:
    vals = m.it_divisions or m.job_tags
    s = ", ".join(vals[:4]) + (f" 외 {len(vals) - 4}" if len(vals) > 4 else "")
    return esc(s) or "-"


def links_cell(m: MergedPosting) -> str:
    out = []
    for s in m.sources:
        if _SAFE_URL.match(s.url):
            out.append(f"[{SOURCE_LABEL[s.source]}]({s.url})")
    return " · ".join(out)


def table(items: list[MergedPosting], today: date) -> list[str]:
    head = "| 마감 | 회사 | 공고 | 유형 | 분야 | 링크 |"
    sep = "| --- | --- | --- | --- | --- | --- |"
    rows = [head, sep]
    for m in items:
        row = f"| {deadline_cell(m, today)} | {esc(m.company_name or m.company)} | {esc(m.title)} | {m.employment} | {field_cell(m)} | {links_cell(m)} |"
        rows.append(row)
    return rows


def render(sections: dict[str, list[MergedPosting]], today: date, failed: dict[str, str], json_url: str, all_url: str) -> tuple[str, list[str]]:
    """(본문, 이어 붙일 댓글들)."""
    names = {"jasoseol": "자소설닷컴", "linkareer": "링커리어"}
    head = [
        f"> 수집 소스: {source_names()} | 수집일 {today:%Y-%m-%d}",
        "> 공고 원문은 각 링크에서 확인하세요. 봇이 수집한 정보는 틀릴 수 있습니다.",
    ]
    if failed:
        head.append("> ⚠️ 이번 주 수집 실패: " + ", ".join(f"{names.get(k, k)}({esc(v)[:40]})" for k, v in failed.items()))
    blocks: list[list[str]] = []
    titles = {
        "urgent": "## 마감 임박 (D-7 이내)",
        "new": "## 이번 주 신규",
        "rolling": "## 상시 · 채용시 마감",
    }
    for key, title in titles.items():
        items = sections.get(key, [])
        if not items:
            blocks.append([title, "", "_해당 공고 없음_"])
            continue
        blocks.append([title, "", *table(items, today)])
    foot = ["---", f"에이전트용 데이터: [이번 주 JSON]({json_url}) · [열린 공고 전체 postings.json]({all_url})"]

    # 길이 초과 시 블록·행 단위로 댓글로 넘긴다
    parts: list[str] = []
    cur = "\n".join(head) + "\n\n"
    for block in blocks:
        text = "\n".join(block) + "\n\n"
        if len(cur) + len(text) <= MAX_BODY:
            cur += text
            continue
        # 표를 행 단위로 쪼갠다
        title, _, *rows = block
        header, rows = rows[:2], rows[2:]
        chunk = f"{title} (이어서)\n\n" + "\n".join(header) + "\n"
        for r in rows:
            if len(chunk) + len(r) + 1 > MAX_BODY:
                parts.append(chunk)
                chunk = f"{title} (이어서)\n\n" + "\n".join(header) + "\n"
            chunk += r + "\n"
        parts.append(chunk)
    body = cur + "\n".join(foot)
    if parts:
        body = body.replace("\n---\n", "\n_표가 길어 일부를 댓글로 이어 붙였습니다._\n\n---\n", 1)
    return body, parts
