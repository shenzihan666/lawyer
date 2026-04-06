import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from app.core.config import Settings


@dataclass(slots=True)
class RetrievalGrade:
    binary_score: str
    reason: str
    rewrite_needed: bool


@dataclass(slots=True)
class RewritePlan:
    strategy: str
    reason: str
    step_back_question: str = ""
    step_back_query: str = ""
    hypothetical_answer: str = ""

    def expanded_queries(self) -> list[tuple[str, str]]:
        expanded: list[tuple[str, str]] = []

        if self.strategy in {"step_back", "complex"} and self.step_back_query.strip():
            expanded.append(("step_back", self.step_back_query.strip()))

        if self.strategy in {"hyde", "complex"} and self.hypothetical_answer.strip():
            expanded.append(("hyde", self.hypothetical_answer.strip()))

        return expanded


class QueryRewriteService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_enabled(self) -> bool:
        return self.settings.query_rewrite_enabled and self.is_configured()

    def is_configured(self) -> bool:
        return bool(
            self.settings.query_rewrite_base_url
            and self.settings.query_rewrite_api_key
            and self.settings.query_rewrite_model
        )

    def grade_retrieval(
        self,
        query: str,
        docs: Sequence[dict[str, Any]],
    ) -> RetrievalGrade:
        if not docs:
            return RetrievalGrade(
                binary_score="no",
                reason="no_initial_results",
                rewrite_needed=True,
            )

        response = self._chat_completion_json(
            system_prompt=(
                "你是法律知识库检索评估器。"
                "请判断当前召回片段是否已经足够相关，能支撑后续回答。"
                "只输出 JSON。"
            ),
            user_prompt=(
                "用户问题如下：\n"
                f"{query}\n\n"
                "当前召回片段如下：\n"
                f"{self._format_docs(docs)}\n\n"
                "请返回 JSON，字段如下：\n"
                "{"
                '"binary_score":"yes 或 no",'
                '"reason":"一句中文理由"'
                "}"
            ),
        )
        score = str(response.get("binary_score", "")).strip().lower()
        if score not in {"yes", "no"}:
            raise RuntimeError("Query rewrite grader returned an invalid binary_score")

        reason = str(response.get("reason", "")).strip() or "model_returned_no_reason"
        return RetrievalGrade(
            binary_score=score,
            reason=reason,
            rewrite_needed=score != "yes",
        )

    def plan_rewrite(
        self,
        query: str,
        docs: Sequence[dict[str, Any]],
    ) -> RewritePlan:
        response = self._chat_completion_json(
            system_prompt=(
                "你是中文法律检索查询改写助手。"
                "目标是提升法律文书、案例、法条片段的召回率。"
                "你可以选择 step_back、hyde 或 complex 三种策略。"
                "只输出 JSON。"
            ),
            user_prompt=(
                "用户原始问题如下：\n"
                f"{query}\n\n"
                "首轮召回摘要如下：\n"
                f"{self._format_docs(docs)}\n\n"
                "请返回 JSON，字段如下：\n"
                "{"
                '"strategy":"step_back | hyde | complex",'
                '"reason":"一句中文理由",'
                '"step_back_question":"如果选择 step_back/complex，需要给出一个更上位的法律问题，否则空字符串",'
                '"step_back_query":"如果选择 step_back/complex，需要给出适合检索的改写查询，否则空字符串",'
                '"hypothetical_answer":"如果选择 hyde/complex，需要给出 120-220 字的假设性法律分析片段，否则空字符串"'
                "}\n\n"
                "要求：\n"
                "1. step_back_query 必须保留关键争议点、法律概念、常见别称与同义表述。\n"
                "2. hypothetical_answer 不能伪造法条编号或案例编号，但要包含有助于召回的法律术语。\n"
                "3. 如果问题明显需要同时扩大概念范围和补充术语，选择 complex。"
            ),
        )

        strategy = str(response.get("strategy", "")).strip().lower()
        if strategy not in {"step_back", "hyde", "complex"}:
            raise RuntimeError("Query rewrite planner returned an invalid strategy")

        return RewritePlan(
            strategy=strategy,
            reason=str(response.get("reason", "")).strip()
            or "model_returned_no_reason",
            step_back_question=str(response.get("step_back_question", "")).strip(),
            step_back_query=str(response.get("step_back_query", "")).strip(),
            hypothetical_answer=str(response.get("hypothetical_answer", "")).strip(),
        )

    def _chat_completion_json(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("Query rewrite is not configured")

        payload = {
            "model": self.settings.query_rewrite_model,
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
                timeout=self.settings.query_rewrite_timeout_seconds,
            ) as response:
                body = response.read()
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(
                f"Query rewrite API returned HTTP {exc.code}: {detail}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(
                f"Query rewrite API request failed: {exc.reason}"
            ) from exc

        return self._parse_chat_completion_response(body)

    def _chat_completion_endpoint(self) -> str:
        base_url = self.settings.query_rewrite_base_url
        if not base_url:
            raise RuntimeError("QUERY_REWRITE_BASE_URL is required")
        return f"{base_url.rstrip('/')}/chat/completions"

    def _chat_completion_headers(self) -> dict[str, str]:
        api_key = self.settings.query_rewrite_api_key
        if not api_key:
            raise RuntimeError("QUERY_REWRITE_API_KEY is required")
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _parse_chat_completion_response(self, payload: bytes) -> dict[str, Any]:
        try:
            parsed = json.loads(payload.decode("utf-8"))
            content = parsed["choices"][0]["message"]["content"]
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise RuntimeError("Invalid query rewrite response payload") from exc

        if isinstance(content, list):
            normalized = []
            for item in content:
                if isinstance(item, dict):
                    normalized.append(str(item.get("text", "")))
                else:
                    normalized.append(str(item))
            content = "".join(normalized)

        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Query rewrite API returned empty content")

        return self._extract_json_object(content)

    @staticmethod
    def _extract_json_object(content: str) -> dict[str, Any]:
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, re.DOTALL)
        if fenced:
            content = fenced.group(1)

        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or start > end:
            raise RuntimeError("Query rewrite API did not return a JSON object")

        try:
            return json.loads(content[start : end + 1])
        except ValueError as exc:
            raise RuntimeError("Query rewrite API returned invalid JSON") from exc

    def _format_docs(self, docs: Sequence[dict[str, Any]]) -> str:
        snippets: list[str] = []
        for index, doc in enumerate(
            docs[: self.settings.query_rewrite_max_context_items],
            start=1,
        ):
            filename = str(doc.get("original_filename", "")).strip() or "unknown"
            page_number = int(doc.get("page_number") or 0)
            content = str(doc.get("content", "")).strip()
            content = content[: self.settings.query_rewrite_max_content_chars]
            snippets.append(
                f"[{index}] 文件: {filename} | 页码: {page_number} | 内容: {content}"
            )

        return "\n".join(snippets) if snippets else "无召回片段"
