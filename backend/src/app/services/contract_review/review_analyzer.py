from __future__ import annotations

import json
from typing import Any

from app.core.config import Settings
from app.services.prompts import (
    PromptSegment,
    TokenBudget,
    assemble_prompt_segments,
    build_contract_review_system_prompt,
)
from app.services.contract_review.analysis import (
    AnalysisFinding,
    build_checklist_summary,
    build_review_overview,
    normalize_severity,
    normalize_status,
)
from app.services.contract_review.clause_parser import ParsedClause
from app.services.contract_review.llm import ContractReviewLLMClient


class ContractReviewLLMAnalyzer:
    batch_size = 6
    max_clause_chars = 900

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.llm = ContractReviewLLMClient(settings)

    def analyze(
        self,
        *,
        clauses: list[ParsedClause],
        config: dict[str, Any],
        global_rule_prompt: str,
        review_name: str,
        original_filename: str,
    ) -> tuple[list[AnalysisFinding], dict[str, int], dict[str, Any]]:
        if not self.llm.is_configured():
            raise RuntimeError("合同审查模型未配置，无法执行 Excel 清单审查。")

        checklist_items = list(config.get("checklist") or [])
        findings: list[AnalysisFinding] = []
        for start in range(0, len(checklist_items), self.batch_size):
            batch = checklist_items[start : start + self.batch_size]
            raw = self.llm.chat_json(
                system_prompt=self._build_system_prompt(),
                user_prompt=self._build_user_prompt(
                    clauses=clauses,
                    config=config,
                    global_rule_prompt=global_rule_prompt,
                    checklist_batch=batch,
                    review_name=review_name,
                    original_filename=original_filename,
                ),
            )
            findings.extend(
                self._normalize_batch_response(
                    raw=raw,
                    checklist_batch=batch,
                    clauses=clauses,
                )
            )

        summary = build_checklist_summary(findings, total_items=len(checklist_items))
        overview = build_review_overview(
            config=config,
            review_name=review_name,
            original_filename=original_filename,
            clause_count=len(clauses),
            summary=summary,
        )
        return findings, summary, overview

    def _build_system_prompt(self) -> str:
        return assemble_prompt_segments(
            build_contract_review_system_prompt(),
            TokenBudget(max_input_tokens=600, reserved_output_tokens=150),
        ).text

    def _build_user_prompt(
        self,
        *,
        clauses: list[ParsedClause],
        config: dict[str, Any],
        global_rule_prompt: str,
        checklist_batch: list[dict[str, Any]],
        review_name: str,
        original_filename: str,
    ) -> str:
        applicability = config.get("applicability") or []
        prompt_parts = [
            f"审查任务名称: {review_name}",
            f"合同文件: {original_filename}",
            f"模板名称: {config.get('template_name', config.get('sheet_name', 'Excel 审查清单'))}",
            "",
            "全局规则:",
            global_rule_prompt.strip() or "（无）",
            "",
            "清单适用范围:",
            json.dumps(applicability, ensure_ascii=False),
            "",
            "当前批次清单项:",
            json.dumps(checklist_batch, ensure_ascii=False),
            "",
            "合同条款列表:",
            self._format_clauses(clauses),
            "",
            "请输出 JSON，结构如下：",
            "{",
            '  "items": [',
            "    {",
            '      "checklist_key": "item-001",',
            '      "title": "风险名称",',
            '      "severity": "low|medium|high",',
            '      "status": "pass|warn|fail|missing",',
            '      "issue": "问题说明",',
            '      "rewrite_suggestion": "修改建议或 null",',
            '      "evidence_items": [',
            "        {",
            '          "clause_path": "C001",',
            '          "clause_title": "第一条",',
            '          "excerpt": "合同摘录"',
            "        }",
            "      ]",
            "    }",
            "  ]",
            "}",
            "",
            "要求：",
            "1. items 必须覆盖当前批次中的每个 checklist_key。",
            "2. issue 必须结合该清单项的风险内容，不要泛泛而谈。",
            "3. rewrite_suggestion 可为空，但 fail/warn 时应尽量给出。",
            "4. 仅能引用给定合同条款中的 clause_path / clause_title / 摘录。",
            "5. 如果合同中找不到足够证据，请返回 status=missing 并说明原因。",
        ]
        return assemble_prompt_segments(
            [
                PromptSegment(
                    key="task",
                    version="v1",
                    content="\n".join(prompt_parts[:3]),
                ),
                PromptSegment(
                    key="global-rules",
                    version="v1",
                    content="\n".join(prompt_parts[3:8]),
                ),
                PromptSegment(
                    key="checklist",
                    version="v1",
                    content="\n".join(prompt_parts[8:12]),
                ),
                PromptSegment(
                    key="clauses",
                    version="v1",
                    content="\n".join(prompt_parts[12:15]),
                ),
                PromptSegment(
                    key="schema",
                    version="v1",
                    content="\n".join(prompt_parts[15:]),
                ),
            ],
            TokenBudget(max_input_tokens=3200, reserved_output_tokens=700),
        ).text

    def _format_clauses(self, clauses: list[ParsedClause]) -> str:
        rendered: list[str] = []
        for clause in clauses:
            content = clause.content.strip()
            if len(content) > self.max_clause_chars:
                content = f"{content[: self.max_clause_chars]}..."
            rendered.append(
                "\n".join(
                    [
                        f"[{clause.clause_path}] {clause.title}",
                        f"页码: {clause.page_start}-{clause.page_end}",
                        content,
                    ]
                )
            )
        return "\n\n".join(rendered)

    def _normalize_batch_response(
        self,
        *,
        raw: dict[str, Any],
        checklist_batch: list[dict[str, Any]],
        clauses: list[ParsedClause],
    ) -> list[AnalysisFinding]:
        raw_items = raw.get("items")
        if not isinstance(raw_items, list):
            raise RuntimeError("合同审查模型返回的 JSON 缺少 items 数组。")

        items_by_key: dict[str, dict[str, Any]] = {}
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            key = str(item.get("checklist_key", "")).strip()
            if key:
                items_by_key[key] = item

        findings: list[AnalysisFinding] = []
        for checklist_item in checklist_batch:
            checklist_key = str(checklist_item.get("key", "")).strip()
            raw_item = items_by_key.get(checklist_key)
            if raw_item is None:
                findings.append(
                    AnalysisFinding(
                        checklist_key=checklist_key,
                        title=str(checklist_item.get("title", "未命名检查项")),
                        severity="medium",
                        status="missing",
                        issue="模型未返回该清单项的审查结果，请人工复核。",
                        evidence=None,
                        rewrite_suggestion=None,
                        clause_index=None,
                        metadata={
                            "checklist_item": checklist_item,
                            "evidence_items": [],
                            "raw_model_item": None,
                        },
                    )
                )
                continue

            findings.append(
                self._normalize_item(
                    raw_item=raw_item,
                    checklist_item=checklist_item,
                    clauses=clauses,
                )
            )
        return findings

    def _normalize_item(
        self,
        *,
        raw_item: dict[str, Any],
        checklist_item: dict[str, Any],
        clauses: list[ParsedClause],
    ) -> AnalysisFinding:
        title = str(
            raw_item.get("title") or checklist_item.get("title") or "未命名检查项"
        )
        severity = normalize_severity(raw_item.get("severity"))
        status = normalize_status(raw_item.get("status"))
        issue = str(raw_item.get("issue", "")).strip() or "模型未提供问题说明。"
        rewrite_suggestion = raw_item.get("rewrite_suggestion")
        if rewrite_suggestion is not None:
            rewrite_suggestion = str(rewrite_suggestion).strip() or None

        evidence_items = self._resolve_evidence_items(
            raw_item.get("evidence_items"),
            clauses,
        )
        if status != "missing" and not evidence_items:
            status = "missing"
            issue = f"{issue} 模型未返回可定位的合同证据，结果已降级为待人工复核。"

        primary_evidence = evidence_items[0]["excerpt"] if evidence_items else None
        primary_clause_index = (
            int(evidence_items[0]["clause_index"]) if evidence_items else None
        )
        return AnalysisFinding(
            checklist_key=str(checklist_item.get("key", "")),
            title=title,
            severity=severity,
            status=status,
            issue=issue,
            evidence=primary_evidence,
            rewrite_suggestion=rewrite_suggestion,
            clause_index=primary_clause_index,
            metadata={
                "checklist_item": checklist_item,
                "evidence_items": evidence_items,
                "raw_model_item": raw_item,
            },
        )

    def _resolve_evidence_items(
        self,
        raw_items: Any,
        clauses: list[ParsedClause],
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_items, list):
            return []

        resolved: list[dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            clause_path = str(item.get("clause_path", "")).strip()
            clause_title = str(item.get("clause_title", "")).strip()
            excerpt = str(item.get("excerpt", "")).strip()
            clause = self._match_clause_reference(
                clause_path=clause_path,
                clause_title=clause_title,
                excerpt=excerpt,
                clauses=clauses,
            )
            if clause is None:
                continue
            if not excerpt:
                excerpt = clause.content[:240]
            resolved.append(
                {
                    "clause_index": clause.clause_index,
                    "clause_path": clause.clause_path,
                    "clause_title": clause.title,
                    "excerpt": excerpt,
                    "page_start": clause.page_start,
                    "page_end": clause.page_end,
                }
            )
        return resolved

    def _match_clause_reference(
        self,
        *,
        clause_path: str,
        clause_title: str,
        excerpt: str,
        clauses: list[ParsedClause],
    ) -> ParsedClause | None:
        if clause_path:
            for clause in clauses:
                if clause.clause_path == clause_path:
                    return clause
        if clause_title:
            for clause in clauses:
                if clause.title == clause_title:
                    return clause
        if excerpt:
            for clause in clauses:
                if excerpt in clause.content:
                    return clause
        return None
