import json
import re
from collections.abc import Sequence
from typing import Any
from urllib import error, request

from app.core.config import Settings


class DocumentRerankService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_enabled(self) -> bool:
        return self.settings.rerank_enabled and self.is_configured()

    def is_configured(self) -> bool:
        return self._api_configured() or self._llm_configured()

    def rerank(
        self,
        query: str,
        docs: Sequence[dict[str, Any]],
        top_k: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        doc_list = [dict(doc) for doc in docs]
        candidate_count = len(doc_list)
        max_candidates = max(self.settings.rerank_max_candidates, top_k)
        candidates = doc_list[:max_candidates]
        remainder = doc_list[max_candidates:]
        meta = self._default_meta(candidate_count, len(candidates), top_k)

        if not doc_list:
            meta["rerank_skipped_reason"] = "no_candidates"
            return [], meta

        if not self.settings.rerank_enabled:
            meta["rerank_skipped_reason"] = "rerank_disabled"
            return doc_list[:top_k], meta

        if not self.is_configured():
            meta["rerank_skipped_reason"] = "rerank_not_configured"
            return doc_list[:top_k], meta

        try:
            if self._api_configured():
                reranked = self._api_rerank(query, candidates, top_k)
                meta["rerank_provider"] = "api"
                meta["rerank_model"] = self.settings.rerank_model
                meta["rerank_endpoint"] = self._rerank_endpoint()
            else:
                reranked = self._llm_rerank(query, candidates, top_k)
                meta["rerank_provider"] = "llm"
                meta["rerank_model"] = self._llm_model()
                meta["rerank_endpoint"] = self._llm_endpoint()

            meta["rerank_applied"] = True
            return (reranked + remainder)[:top_k], meta
        except Exception as exc:
            meta["rerank_error"] = str(exc)
            meta["rerank_skipped_reason"] = "rerank_failed"
            return doc_list[:top_k], meta

    def _default_meta(
        self,
        candidate_count: int,
        truncated_candidate_count: int,
        top_k: int,
    ) -> dict[str, Any]:
        return {
            "rerank_enabled": self.settings.rerank_enabled,
            "rerank_configured": self.is_configured(),
            "rerank_applied": False,
            "rerank_provider": None,
            "rerank_model": None,
            "rerank_endpoint": None,
            "rerank_error": None,
            "rerank_skipped_reason": None,
            "rerank_candidate_count": candidate_count,
            "rerank_truncated_candidate_count": truncated_candidate_count,
            "rerank_top_n": top_k,
        }

    def _api_configured(self) -> bool:
        return bool(
            self.settings.rerank_base_url
            and self.settings.rerank_model
            and self.settings.rerank_api_key
        )

    def _llm_configured(self) -> bool:
        return bool(
            self.settings.rerank_llm_fallback_enabled
            and self._llm_base_url()
            and self._llm_model()
            and self._llm_api_key()
        )

    def _api_rerank(
        self,
        query: str,
        docs: Sequence[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        payload = {
            "model": self.settings.rerank_model,
            "query": query,
            "documents": [str(doc.get("content", "")) for doc in docs],
            "top_n": min(top_k, len(docs)),
            "return_documents": False,
        }
        response = self._post_json(
            self._rerank_endpoint(),
            payload,
            self.settings.rerank_api_key,
            self.settings.rerank_timeout_seconds,
        )
        results = response.get("results")
        if not isinstance(results, list) or not results:
            raise RuntimeError("Rerank API returned no results")

        ranked_indices: list[int] = []
        ranked_scores: dict[int, float] = {}
        for item in results:
            if not isinstance(item, dict):
                continue
            index = item.get("index")
            if not isinstance(index, int) or not (0 <= index < len(docs)):
                continue
            if index in ranked_indices:
                continue
            ranked_indices.append(index)
            try:
                ranked_scores[index] = float(item.get("relevance_score", 0.0))
            except (TypeError, ValueError):
                ranked_scores[index] = 0.0

        if not ranked_indices:
            raise RuntimeError("Rerank API returned invalid ranking indices")
        return self._apply_ranking(docs, ranked_indices, ranked_scores, "api")

    def _llm_rerank(
        self,
        query: str,
        docs: Sequence[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        response = self._chat_completion_json(
            system_prompt=(
                "你是法律检索重排器。"
                "请根据用户问题判断候选片段对最终回答的支持度。"
                "优先排序直接回答争议点、包含法律概念、构成要件、举证责任或裁判要旨的片段。"
                "只输出 JSON。"
            ),
            user_prompt=(
                "用户问题如下：\n"
                f"{query}\n\n"
                "候选片段如下：\n"
                f"{self._format_docs(docs)}\n\n"
                "请输出 JSON，字段如下：\n"
                "{"
                '"ranking":[按相关性从高到低排列的来源编号],'
                '"top_source_numbers":[最值得保留的前几个来源编号]'
                "}\n\n"
                f"要求：\n1. ranking 必须覆盖 1 到 {len(docs)} 的所有编号且不能重复。\n"
                f"2. top_source_numbers 最多返回 {min(top_k, len(docs))} 个编号。\n"
                "3. 只输出 JSON。"
            ),
        )
        ranking = response.get("ranking", [])
        if not isinstance(ranking, list):
            raise RuntimeError("LLM rerank returned an invalid ranking field")

        ranked_indices: list[int] = []
        for value in ranking:
            try:
                index = int(value) - 1
            except (TypeError, ValueError):
                continue
            if 0 <= index < len(docs) and index not in ranked_indices:
                ranked_indices.append(index)

        if not ranked_indices:
            raise RuntimeError("LLM rerank returned no usable ranking")

        ranked_scores = {
            index: float(len(docs) - rank)
            for rank, index in enumerate(ranked_indices, start=1)
        }
        return self._apply_ranking(docs, ranked_indices, ranked_scores, "llm")

    def _apply_ranking(
        self,
        docs: Sequence[dict[str, Any]],
        ranked_indices: Sequence[int],
        ranked_scores: dict[int, float],
        provider: str,
    ) -> list[dict[str, Any]]:
        ordered_indices = list(ranked_indices)
        for index in range(len(docs)):
            if index not in ordered_indices:
                ordered_indices.append(index)

        reranked_docs: list[dict[str, Any]] = []
        for rank, index in enumerate(ordered_indices, start=1):
            item = dict(docs[index])
            metadata = dict(item.get("metadata", {}))
            original_score = float(item.get("score", 0.0))
            rerank_score = float(
                ranked_scores.get(index, max(len(docs) - rank, 0))
            )
            metadata["retrieval_score"] = original_score
            metadata["rerank_score"] = rerank_score
            metadata["rerank_rank"] = rank
            metadata["rerank_provider"] = provider
            item["metadata"] = metadata
            item["score"] = rerank_score
            reranked_docs.append(item)

        return reranked_docs

    def _rerank_endpoint(self) -> str:
        base_url = self.settings.rerank_base_url
        if not base_url:
            raise RuntimeError("RERANK_BASE_URL is required")
        normalized = base_url.strip().rstrip("/")
        if normalized.endswith("/rerank") or normalized.endswith("/v1/rerank"):
            return normalized
        return f"{normalized}/v1/rerank"

    def _llm_base_url(self) -> str | None:
        return (
            self.settings.answer_generation_base_url
            or self.settings.query_rewrite_base_url
            or self.settings.embedding_base_url
        )

    def _llm_model(self) -> str | None:
        return (
            self.settings.answer_generation_model
            or self.settings.query_rewrite_model
        )

    def _llm_api_key(self) -> str | None:
        return (
            self.settings.answer_generation_api_key
            or self.settings.query_rewrite_api_key
            or self.settings.embedding_api_key
        )

    def _llm_endpoint(self) -> str:
        base_url = self._llm_base_url()
        if not base_url:
            raise RuntimeError("No LLM base URL is available for rerank fallback")
        return f"{base_url.rstrip('/')}/chat/completions"

    def _chat_completion_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        model = self._llm_model()
        api_key = self._llm_api_key()
        if not model or not api_key:
            raise RuntimeError("No LLM credentials are available for rerank fallback")

        payload = {
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        response = self._post_json(
            self._llm_endpoint(),
            payload,
            api_key,
            self.settings.rerank_timeout_seconds,
        )

        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, TypeError, IndexError) as exc:
            raise RuntimeError("LLM rerank returned an invalid payload") from exc

        if isinstance(content, list):
            content = "".join(
                str(item.get("text", "")) if isinstance(item, dict) else str(item)
                for item in content
            )

        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("LLM rerank returned empty content")

        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, re.DOTALL)
        if fenced:
            content = fenced.group(1)

        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or start > end:
            raise RuntimeError("LLM rerank did not return a JSON object")

        try:
            return json.loads(content[start : end + 1])
        except ValueError as exc:
            raise RuntimeError("LLM rerank returned invalid JSON") from exc

    @staticmethod
    def _post_json(
        url: str,
        payload: dict[str, Any],
        api_key: str,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        req = request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(
                f"Rerank API returned HTTP {exc.code}: {detail}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(f"Rerank API request failed: {exc.reason}") from exc
        except ValueError as exc:
            raise RuntimeError("Rerank API returned invalid JSON") from exc

    def _format_docs(self, docs: Sequence[dict[str, Any]]) -> str:
        blocks: list[str] = []
        for index, item in enumerate(docs, start=1):
            blocks.append(
                f"[{index}] 文件: {item.get('original_filename', '')}\n"
                f"页码: {int(item.get('page_number') or 0)}\n"
                f"内容: {str(item.get('content', '')).strip()[:self.settings.rerank_max_content_chars]}"
            )
        return "\n\n".join(blocks)
