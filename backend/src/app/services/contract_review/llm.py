from __future__ import annotations

import json
import re
from typing import Any
from urllib import error, request

from app.core.config import Settings


class ContractReviewLLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_configured(self) -> bool:
        return bool(
            self.settings.answer_generation_base_url
            and self.settings.answer_generation_model
            and self.settings.answer_generation_api_key
        )

    def chat_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0,
    ) -> dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("Answer generation model is not configured.")

        payload = {
            "model": self.settings.answer_generation_model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        req = request.Request(
            self._chat_completion_endpoint(),
            data=json.dumps(payload).encode("utf-8"),
            headers=self._chat_completion_headers(),
            method="POST",
        )
        try:
            with request.urlopen(
                req,
                timeout=self.settings.answer_generation_timeout_seconds,
            ) as response:
                body = response.read()
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(
                f"Answer generation API returned HTTP {exc.code}: {detail}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(
                f"Answer generation API request failed: {exc.reason}"
            ) from exc

        return self._parse_chat_completion_response(body)

    def _chat_completion_endpoint(self) -> str:
        base_url = self.settings.answer_generation_base_url
        if not base_url:
            raise RuntimeError("ANSWER_GENERATION_BASE_URL is required")
        return f"{base_url.rstrip('/')}/chat/completions"

    def _chat_completion_headers(self) -> dict[str, str]:
        api_key = self.settings.answer_generation_api_key
        if not api_key:
            raise RuntimeError("ANSWER_GENERATION_API_KEY is required")
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _parse_chat_completion_response(payload: bytes) -> dict[str, Any]:
        try:
            parsed = json.loads(payload.decode("utf-8"))
            content = parsed["choices"][0]["message"]["content"]
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise RuntimeError("Invalid answer generation response payload") from exc

        if isinstance(content, list):
            content = "".join(
                str(item.get("text", "")) if isinstance(item, dict) else str(item)
                for item in content
            )

        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Answer generation API returned empty content")

        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, re.DOTALL)
        if fenced:
            content = fenced.group(1)

        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or start > end:
            raise RuntimeError("Answer generation API did not return a JSON object")

        try:
            return json.loads(content[start : end + 1])
        except ValueError as exc:
            raise RuntimeError("Answer generation API returned invalid JSON") from exc
