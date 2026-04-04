from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.schemas.answer import AnswerCitation, AnswerResponse
from app.schemas.search import SearchResultItem
from app.services.vectors import DocumentVectorService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GeneratedAnswerDraft:
    answer: str
    used_source_numbers: list[int]
    grounding_status: str
    missing_information: str


class DocumentAnswerService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.vector_service = DocumentVectorService(db=db, settings=settings)

    def answer(
        self,
        query: str,
        top_k: int | None = None,
        document_ids: Sequence[str] | None = None,
    ) -> AnswerResponse:
        normalized_query = query.strip()
        if not normalized_query:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query must not be empty.",
            )

        search_response = self.vector_service.search(
            query=normalized_query,
            top_k=top_k,
            document_ids=document_ids,
        )
        sources = search_response.items[: self.settings.answer_generation_max_context_items]

        if not sources:
            return AnswerResponse(
                answer=(
                    "未检索到可支持回答的依据。请尝试换一种问法，"
                    "或者放宽文档筛选范围后重新提问。"
                ),
                citations=[],
                meta={
                    "generation_mode": "no_results",
                    "grounding_status": "insufficient",
                    "used_source_count": 0,
                    "answer_generation_enabled": self.settings.answer_generation_enabled,
                    "answer_generation_configured": self.is_configured(),
                    "answer_generation_skipped_reason": "no_retrieval_results",
                    "answer_generation_error": None,
                    "search_meta": search_response.meta,
                },
            )

        if not self.settings.answer_generation_enabled:
            return self._build_extractive_fallback(
                query=normalized_query,
                sources=sources,
                search_meta=search_response.meta,
                skipped_reason="answer_generation_disabled",
            )

        if not self.is_configured():
            return self._build_extractive_fallback(
                query=normalized_query,
                sources=sources,
                search_meta=search_response.meta,
                skipped_reason="answer_model_not_configured",
            )

        try:
            draft = self._generate_grounded_answer(normalized_query, sources)
            citations = self._build_citations(
                sources,
                draft.used_source_numbers,
                draft.answer,
            )
            answer_text = draft.answer.strip()
            if citations and not self._extract_citation_numbers(answer_text):
                answer_text = (
                    f"{answer_text}\n\n参考依据："
                    + "".join(f"[{citation.citation_number}]" for citation in citations)
                )
            return AnswerResponse(
                answer=answer_text,
                citations=citations,
                meta={
                    "generation_mode": "llm",
                    "grounding_status": draft.grounding_status,
                    "missing_information": draft.missing_information,
                    "used_source_count": len(citations),
                    "answer_generation_enabled": True,
                    "answer_generation_configured": True,
                    "answer_generation_skipped_reason": None,
                    "answer_generation_error": None,
                    "search_meta": search_response.meta,
                },
            )
        except Exception as exc:
            logger.warning(
                "Answer generation failed; returning extractive fallback",
                extra={
                    "event": "answer_generation_failed",
                    "query_length": len(normalized_query),
                    "top_k": top_k or self.settings.vector_search_top_k,
                    "document_filter_count": len(document_ids or []),
                    "error": str(exc),
                },
            )
            return self._build_extractive_fallback(
                query=normalized_query,
                sources=sources,
                search_meta=search_response.meta,
                skipped_reason="answer_generation_failed",
                generation_error=str(exc),
            )

    def is_configured(self) -> bool:
        return bool(
            self.settings.answer_generation_base_url
            and self.settings.answer_generation_model
            and self.settings.answer_generation_api_key
        )

    def _generate_grounded_answer(
        self,
        query: str,
        sources: Sequence[SearchResultItem],
    ) -> GeneratedAnswerDraft:
        response = self._chat_completion_json(
            system_prompt=(
                "你是法律知识库问答助手。"
                "你必须严格依据给定来源回答，不能编造法条、案号、事实或结论。"
                "如果来源不足以支撑完整回答，要明确说明信息不足。"
                "你必须把引用编号直接放在对应句子后面，格式为 [1][2]。"
                "只输出 JSON。"
            ),
            user_prompt=(
                "用户问题如下：\n"
                f"{query}\n\n"
                "可用来源如下：\n"
                f"{self._format_sources(sources)}\n\n"
                "请输出 JSON，字段如下：\n"
                "{"
                '"answer":"中文回答，必须在对应句子后面添加 [n] 引用编号",'
                '"used_source_numbers":[1,2],'
                '"grounding_status":"grounded | partial | insufficient",'
                '"missing_information":"如果信息不足，简要说明缺失点；否则空字符串"'
                "}\n\n"
                "要求：\n"
                "1. 只能使用给定来源编号。\n"
                "2. 回答要先给结论，再说明依据。\n"
                "3. 不要输出 JSON 以外的任何文字。"
            ),
        )

        answer = str(response.get("answer", "")).strip()
        if not answer:
            raise RuntimeError("Answer model returned empty answer")

        grounding_status = str(response.get("grounding_status", "")).strip().lower()
        if grounding_status not in {"grounded", "partial", "insufficient"}:
            raise RuntimeError("Answer model returned an invalid grounding_status")

        used_source_numbers = [
            int(item)
            for item in response.get("used_source_numbers", [])
            if self._is_valid_source_number(item, len(sources))
        ]
        referenced_numbers = self._extract_citation_numbers(answer)
        all_source_numbers = sorted(set(used_source_numbers) | set(referenced_numbers))

        if not all_source_numbers and grounding_status != "insufficient":
            all_source_numbers = [1]

        return GeneratedAnswerDraft(
            answer=answer,
            used_source_numbers=all_source_numbers,
            grounding_status=grounding_status,
            missing_information=str(response.get("missing_information", "")).strip(),
        )

    def _build_extractive_fallback(
        self,
        *,
        query: str,
        sources: Sequence[SearchResultItem],
        search_meta: dict[str, Any],
        skipped_reason: str,
        generation_error: str | None = None,
    ) -> AnswerResponse:
        citations = self._build_citations(
            sources,
            list(range(1, min(len(sources), 2) + 1)),
            "",
        )
        lead = (
            "当前答案模型不可用，先返回最相关依据摘要。"
            if generation_error or skipped_reason != "answer_model_not_configured"
            else "当前还没有配置答案模型，先返回最相关依据摘要。"
        )
        lines = [lead, "", f"问题：{query}", ""]
        for citation in citations:
            lines.append(
                f"[{citation.citation_number}] 《{citation.original_filename}》"
                f"第 {citation.page_number or 0} 页：{citation.snippet}"
            )
        lines.append("")
        lines.append("请先结合以上依据人工核对，再继续使用生成式回答。")

        return AnswerResponse(
            answer="\n".join(lines).strip(),
            citations=citations,
            meta={
                "generation_mode": "extractive_fallback",
                "grounding_status": "partial",
                "missing_information": "answer_model_unavailable",
                "used_source_count": len(citations),
                "answer_generation_enabled": self.settings.answer_generation_enabled,
                "answer_generation_configured": self.is_configured(),
                "answer_generation_skipped_reason": skipped_reason,
                "answer_generation_error": generation_error,
                "search_meta": search_meta,
            },
        )

    def _build_citations(
        self,
        sources: Sequence[SearchResultItem],
        source_numbers: Sequence[int],
        answer: str,
    ) -> list[AnswerCitation]:
        available_numbers = self._extract_citation_numbers(answer)
        if available_numbers:
            candidate_numbers = available_numbers
        else:
            candidate_numbers = [
                number
                for number in source_numbers
                if self._is_valid_source_number(number, len(sources))
            ]

        citations: list[AnswerCitation] = []
        seen: set[int] = set()
        for number in candidate_numbers:
            if number in seen or not self._is_valid_source_number(number, len(sources)):
                continue
            seen.add(number)
            item = sources[number - 1]
            citations.append(
                AnswerCitation(
                    citation_number=number,
                    chunk_id=item.chunk_id,
                    document_id=item.document_id,
                    root_chunk_id=item.root_chunk_id,
                    parent_chunk_id=item.parent_chunk_id,
                    chunk_level=item.chunk_level,
                    chunk_index=item.chunk_index,
                    page_number=item.page_number,
                    original_filename=item.original_filename,
                    snippet=item.content[: self.settings.answer_generation_max_content_chars],
                    score=item.score,
                    metadata=item.metadata,
                )
            )

        return citations

    def _chat_completion_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        payload = {
            "model": self.settings.answer_generation_model,
            "temperature": 0,
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

    def _parse_chat_completion_response(self, payload: bytes) -> dict[str, Any]:
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

    def _format_sources(self, sources: Sequence[SearchResultItem]) -> str:
        blocks: list[str] = []
        for index, item in enumerate(sources, start=1):
            snippet = item.content[: self.settings.answer_generation_max_content_chars]
            blocks.append(
                f"[{index}] 文件: {item.original_filename}\n"
                f"页码: {item.page_number}\n"
                f"chunk_id: {item.chunk_id}\n"
                f"内容: {snippet}"
            )
        return "\n\n".join(blocks)

    @staticmethod
    def _extract_citation_numbers(answer: str) -> list[int]:
        seen: set[int] = set()
        numbers: list[int] = []
        for match in re.finditer(r"\[(\d+)\]", answer or ""):
            number = int(match.group(1))
            if number in seen:
                continue
            seen.add(number)
            numbers.append(number)
        return numbers

    @staticmethod
    def _is_valid_source_number(value: Any, source_count: int) -> bool:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return False
        return 1 <= number <= source_count
