from dataclasses import dataclass
from typing import Any

from app.services.contract_review.clause_parser import ParsedClause


@dataclass(slots=True)
class AnalysisFinding:
    checklist_key: str
    title: str
    severity: str
    status: str
    issue: str
    evidence: str | None
    rewrite_suggestion: str | None
    clause_index: int | None
    metadata: dict[str, Any]


def _match_clause(clauses: list[ParsedClause], keywords: list[str]) -> tuple[int | None, ParsedClause | None]:
    best_score = 0
    best_index: int | None = None
    best_clause: ParsedClause | None = None
    for index, clause in enumerate(clauses):
        haystack = f"{clause.title}\n{clause.content}".lower()
        score = sum(keyword.lower() in haystack for keyword in keywords)
        if score > best_score:
            best_score = score
            best_index = index
            best_clause = clause
    return best_index, best_clause


def analyze_contract(
    *,
    clauses: list[ParsedClause],
    config: dict[str, Any],
    review_name: str,
    original_filename: str,
) -> tuple[list[AnalysisFinding], dict[str, int], dict[str, Any]]:
    checklist_items = config.get("checklist", [])
    findings: list[AnalysisFinding] = []
    summary = {
        "total": len(checklist_items),
        "passed": 0,
        "warnings": 0,
        "failed": 0,
        "missing": 0,
        "high_risk": 0,
        "medium_risk": 0,
        "low_risk": 0,
    }

    for item in checklist_items:
        keywords = [str(keyword) for keyword in item.get("keywords", [])]
        clause_index, clause = _match_clause(clauses, keywords)
        rewrite_hint = item.get("rewrite_hint")
        if clause is None:
            severity = str(item.get("missing_severity", "medium"))
            findings.append(
                AnalysisFinding(
                    checklist_key=str(item.get("key", "")),
                    title=str(item.get("title", "未命名检查项")),
                    severity=severity,
                    status="missing",
                    issue=f"未在合同中识别到与“{item.get('title', '该项')}”直接对应的条款。",
                    evidence=None,
                    rewrite_suggestion=str(rewrite_hint) if rewrite_hint else None,
                    clause_index=None,
                    metadata={"description": item.get("description"), "matched_keywords": []},
                )
            )
            summary["missing"] += 1
            summary[f"{severity}_risk"] += 1
            continue

        haystack = f"{clause.title}\n{clause.content}"
        triggered_flags = [
            flag for flag in item.get("red_flags", []) if str(flag).lower() in haystack.lower()
        ]
        if triggered_flags:
            severity = str(item.get("risk_severity", "medium"))
            status = "fail" if severity == "high" else "warn"
            issue = (
                f"条款中出现了需要重点核查的表述：{', '.join(triggered_flags[:3])}。"
            )
            evidence = clause.content[:280]
            rewrite_suggestion = (
                f"{rewrite_hint} 当前建议优先改写或补充风险表述。"
                if rewrite_hint
                else "建议补充更平衡的责任、期限或解释规则。"
            )
        else:
            severity = "low"
            status = "pass"
            issue = f"已识别到与“{item.get('title', '该项')}”相关的条款，可继续人工复核细节。"
            evidence = clause.content[:220]
            rewrite_suggestion = None

        findings.append(
            AnalysisFinding(
                checklist_key=str(item.get("key", "")),
                title=str(item.get("title", "未命名检查项")),
                severity=severity,
                status=status,
                issue=issue,
                evidence=evidence,
                rewrite_suggestion=rewrite_suggestion,
                clause_index=clause_index,
                metadata={
                    "description": item.get("description"),
                    "matched_keywords": keywords,
                    "triggered_red_flags": triggered_flags,
                },
            )
        )

        if status == "pass":
            summary["passed"] += 1
            summary["low_risk"] += 1
        elif status == "warn":
            summary["warnings"] += 1
            summary[f"{severity}_risk"] += 1
        else:
            summary["failed"] += 1
            summary[f"{severity}_risk"] += 1

    overview = {
        "title": config.get("report_title", "合同审查报告"),
        "review_name": review_name,
        "original_filename": original_filename,
        "contract_type": config.get("profile", "general"),
        "clause_count": len(clauses),
        "highlights": [
            f"共识别 {len(clauses)} 个条款片段",
            f"检查清单覆盖 {summary['total']} 项",
            f"高风险/中风险提示共 {summary['high_risk'] + summary['medium_risk']} 项",
        ],
    }
    return findings, summary, overview
