"""JSON 출력 LLM/VLM 호출. 백엔드는 OpenRouter(운영) 또는 `codex exec`(로컬 테스트).

호출부는 ask_json(system, user, schema, images)만 쓰고, 결과는 호출부에서 pydantic으로 검증한다.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path

import requests

from .config import Settings

log = logging.getLogger(__name__)


class LLMError(Exception):
    pass


def _strip_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").removeprefix("json").strip()
    return raw


class LLM:
    def __init__(self, settings: Settings, http=None):
        self.s = settings
        self.http = http  # 이미지 다운로드용 HttpClient (codex 백엔드)
        self._client = None

    @property
    def enabled(self) -> bool:
        return self.s.llm_enabled

    def ask_json(self, system: str, user: str, schema: dict, images: list[str] | None = None, model: str | None = None) -> dict:
        if not self.enabled:
            raise LLMError("LLM 비활성 (OPENROUTER_API_KEY 없음, LLM_BACKEND=none)")
        if self.s.llm_backend == "codex":
            return self._codex(system, user, schema, images or [])
        return self._openrouter(system, user, schema, images or [], model or self.s.classifier_fallback_model)

    # --- OpenRouter -------------------------------------------------------
    def _openrouter(self, system, user, schema, images, model) -> dict:
        from openai import OpenAI

        if self._client is None:
            self._client = OpenAI(api_key=self.s.openrouter_api_key, base_url=self.s.openrouter_base_url)
        content: list[dict] = [{"type": "text", "text": user}]
        content += [{"type": "image_url", "image_url": {"url": u}} for u in images]
        messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]
        try:
            resp = self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                response_format={"type": "json_schema", "json_schema": {"name": "out", "strict": True, "schema": schema}},
            )
            return json.loads(_strip_fence(resp.choices[0].message.content or ""))
        except Exception as exc:  # noqa: BLE001 - 호출부가 대체 경로(maybe)로 처리
            raise LLMError(f"OpenRouter {model}: {exc}") from exc

    # --- codex exec (로컬) --------------------------------------------------
    def _codex(self, system, user, schema, images) -> dict:
        with tempfile.TemporaryDirectory(prefix="recruit-codex-") as tmp:
            d = Path(tmp)
            (d / "schema.json").write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
            args = [
                "codex", "exec", "--ephemeral", "--skip-git-repo-check", "-s", "read-only",
                "-C", str(d), "--output-schema", str(d / "schema.json"), "-o", str(d / "out.json"),
            ]
            for i, url in enumerate(images):
                path = self._download(url, d / f"img{i}")
                if path:
                    args += ["-i", str(path)]
            prompt = f"{system}\n\n{user}\n\n파일을 읽거나 명령을 실행하지 말고, 스키마에 맞는 JSON만 답하세요."
            args.append("--")
            args.append(prompt)
            try:
                proc = subprocess.run(args, capture_output=True, text=True, timeout=600, stdin=subprocess.DEVNULL)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise LLMError(f"codex exec 실행 실패: {exc}") from exc
            out = d / "out.json"
            if proc.returncode != 0 or not out.exists():
                raise LLMError(f"codex exec 실패 rc={proc.returncode}: {proc.stderr[-500:]}")
            try:
                return json.loads(_strip_fence(out.read_text(encoding="utf-8")))
            except json.JSONDecodeError as exc:
                raise LLMError(f"codex 출력 JSON 아님: {exc}") from exc

    def _download(self, url: str, stem: Path) -> Path | None:
        try:
            resp = self.http.get(url) if self.http else requests.get(url, timeout=30)
        except Exception as exc:  # noqa: BLE001 - 이미지 하나 실패는 텍스트만으로 진행
            log.warning("이미지 다운로드 실패 %s: %s", url, exc)
            return None
        ctype = resp.headers.get("Content-Type", "")
        ext = {"image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}.get(ctype.split(";")[0], ".jpg")
        path = stem.with_suffix(ext)
        path.write_bytes(resp.content)
        return path
