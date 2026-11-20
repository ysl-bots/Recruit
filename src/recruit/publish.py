"""GitHub Issue 발행. 발행 저장소의 구독자 메일 오염을 막으려고 Issue는 잠그고 상호작용을 협업자로 제한한다."""

from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)
API = "https://api.github.com"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def create_issue(token: str, repo: str, title: str, body: str, labels: list[str]) -> int:
    if not token:
        raise RuntimeError("ISSUE_TOKEN이 없습니다 (발행 저장소 Issues 쓰기 권한 필요)")
    resp = requests.post(f"{API}/repos/{repo}/issues", headers=_headers(token), json={"title": title, "body": body, "labels": labels}, timeout=30)
    resp.raise_for_status()
    return int(resp.json()["number"])


def comment(token: str, repo: str, number: int, body: str) -> None:
    resp = requests.post(f"{API}/repos/{repo}/issues/{number}/comments", headers=_headers(token), json={"body": body}, timeout=30)
    resp.raise_for_status()


def lock_issue(token: str, repo: str, number: int) -> None:
    resp = requests.put(f"{API}/repos/{repo}/issues/{number}/lock", headers=_headers(token), timeout=30)
    resp.raise_for_status()


def renew_interaction_limit(token: str, repo: str) -> None:
    try:
        resp = requests.put(
            f"{API}/repos/{repo}/interaction-limits",
            headers=_headers(token),
            json={"limit": "collaborators_only", "expiry": "six_months"},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("상호작용 제한 갱신 실패 (Administration 권한 확인): %s", exc)


def open_alert(token: str, repo: str, title: str, body: str) -> None:
    """같은 제목의 열린 alert Issue가 있으면 댓글, 없으면 새로 만든다."""
    if not token:
        log.error("알림 토큰이 없어 alert를 남기지 못함: %s", title)
        return
    try:
        q = requests.get(f"{API}/repos/{repo}/issues", headers=_headers(token), params={"labels": "alert", "state": "open"}, timeout=30)
        q.raise_for_status()
        for it in q.json():
            if it.get("title") == title:
                comment(token, repo, int(it["number"]), body)
                return
        create_issue(token, repo, title, body, ["alert"])
    except requests.RequestException as exc:
        log.error("alert 발행 실패: %s", exc)
