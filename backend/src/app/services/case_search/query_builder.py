from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
import json
import re
from typing import Any
from urllib import error, request

from app.core.config import Settings
from app.services.loaders.base import LoadedFragment


class CaseSearchQueryBuilder:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build_from_text(self, query_text: str) -> str:
        normalized = self._normalize(query_text)
        if not normalized:
            return ""
        llm_result = self._try_llm_prepare_query(normalized)
        return llm_result or normalized

    def build_from_fragments(self, fragments: Sequence[LoadedFragment]) -> tuple[str, str]:
        joined = "\n".join(
            fragment.content.strip() for fragment in fragments if fragment.content.strip()
        )
        normalized = self._normalize(joined)
        excerpt = normalized[:280]
        if not normalized:
            return "", excerpt

        summary_parts: list[str] = []
        if excerpt:
            summary_parts.append(excerpt)

        keywords = self._extract_keywords(normalized)
        if keywords:
            summary_parts.append("Keywords: " + ", ".join(keywords[:8]))

        prepared = "\n".join(summary_parts + [normalized[:1800]])
        llm_result = self._try_llm_prepare_query(prepared)
        return llm_result or prepared, excerpt

    def _normalize(self, value: str) -> str:
        cleaned = re.sub(r"\s+", " ", value or "").strip()
        return cleaned[:4000]

    def _extract_keywords(self, content: str) -> list[str]:
        tokens = re.findall(r"[\u4e00-\u9fff]{2,12}", content)
        stop_words = {
            "人民法院",
            "本院认为",
            "原告主张",
            "被告辩称",
            "相关证据",
            "事实如下",
            "案件事实",
            "依法判决",
            "进行审理",
            "中华人民共和国",
        }
        counter = Counter(token for token in tokens if token not in stop_words)
        return [token for token, _count in counter.most_common(12)]

    def _try_llm_prepare_query(self, content: str) -> str | None:
        endpoint_info = self._resolve_endpoint_info()
        if endpoint_info is None:
            return None

        payload = {
            "model": endpoint_info["model"],
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You rewrite legal case material into a concise retrieval query. "
                        "Return plain text only. Keep cause of action, disputed facts, "
                        "liability questions, evidence disputes, and judgment factors."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Rewrite this material into a concise case-search query:\n{content}",
                },
            ],
        }
        req = request.Request(
            endpoint_info["endpoint"],
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {endpoint_info['api_key']}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=20) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (error.URLError, error.HTTPError, TimeoutError, ValueError):
            return None

        try:
            content_value: Any = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return None

        if isinstance(content_value, list):
            content_value = "".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in content_value
            )

        if not isinstance(content_value, str):
            return None

        normalized = self._normalize(content_value)
        return normalized or None

    def _resolve_endpoint_info(self) -> dict[str, str] | None:
        if (
            self.settings.answer_generation_base_url
            and self.settings.answer_generation_model
            and self.settings.answer_generation_api_key
        ):
            return {
                "endpoint": self.settings.answer_generation_base_url.rstrip("/")
                + "/chat/completions",
                "model": self.settings.answer_generation_model,
                "api_key": self.settings.answer_generation_api_key,
            }
        if (
            self.settings.query_rewrite_base_url
            and self.settings.query_rewrite_model
            and self.settings.query_rewrite_api_key
        ):
            return {
                "endpoint": self.settings.query_rewrite_base_url.rstrip("/")
                + "/chat/completions",
                "model": self.settings.query_rewrite_model,
                "api_key": self.settings.query_rewrite_api_key,
            }
        return None
