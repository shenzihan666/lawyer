from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.opponent_analysis import (
    OpponentAnalysisEventType,
    OpponentAnalysisStatus,
)
from app.schemas.opponent_analysis import (
    OpponentAnalysisAgentPayload,
    OpponentAnalysisEvidenceItem,
    OpponentAnalysisOpponentPosition,
    OpponentAnalysisResponsePlan,
    OpponentAnalysisSummary,
)
from app.services.opponent_analysis.llm import OpponentAnalysisLLMClient
from app.services.opponent_analysis.service import OpponentAnalysisService
from app.services.vectors import DocumentVectorService

logger = logging.getLogger(__name__)

WORKFLOW_PHASES = (
    "context_brief",
    "party_projection",
    "counsel_projection",
    "bench_review",
    "strategy_response",
    "revision",
    "finalize",
)

AGENT_REGISTRY: dict[str, dict[str, str]] = {
    "opponent_party": {
        "label": "对方当事人",
        "objective": "从自身利益出发，预测对方当事人在庭上最可能坚持的事实叙事、回避点与说法。",
    },
    "opponent_counsel": {
        "label": "对方律师",
        "objective": "基于对方当事人的叙事，预测对方律师可能采取的主张、抗辩、程序动作与进攻点。",
    },
    "bench_observer": {
        "label": "庭审观察员",
        "objective": "从中立视角检查双方叙事的真实性、证据强弱和法庭可采性，并提出修正要求。",
    },
    "our_strategy_advisor": {
        "label": "我方策略官",
        "objective": "基于前述预测结果，形成我方的庭审应对、证据补强与风险优先级建议。",
    },
}


class OpponentAnalysisProcessor:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.service = OpponentAnalysisService(db=db, settings=settings)
        self.vector_service = DocumentVectorService(db=db, settings=settings)
        self.llm = OpponentAnalysisLLMClient(settings)

    def run(self, run_id: str) -> None:
        run = self.service.get_run(run_id).run
        try:
            self.service.update_run_status(run_id, OpponentAnalysisStatus.running.value)
            self.service.append_event(
                run_id=run_id,
                phase="context_brief",
                round_number=0,
                from_agent=None,
                to_agent=None,
                event_type=OpponentAnalysisEventType.stage.value,
                title="开始整理共享案情与证据",
                content="先汇总案情、争点和现有文档证据，为后续四个智能体建立统一上下文。",
                structured_payload={"phase": "context_brief"},
                citations=[],
                event_status="running",
            )

            context_brief = self._build_context_brief(
                run.case_facts,
                run.top_k,
                run.scope_document_ids,
            )
            self.service.append_event(
                run_id=run_id,
                phase="context_brief",
                round_number=0,
                from_agent=None,
                to_agent=None,
                event_type=OpponentAnalysisEventType.evidence.value,
                title="共享证据包已生成",
                content="已提炼争点地图、证据包与事实缺口，后续智能体会在此基础上接力推演。",
                structured_payload=context_brief,
                citations=context_brief["evidence_cards"],
                event_status="done",
            )

            party_output = self._generate_agent_output(
                agent_key="opponent_party",
                case_facts=run.case_facts,
                phase="party_projection",
                round_number=1,
                evidence_cards=context_brief["evidence_cards"],
                context_brief=context_brief,
                upstream_payloads={},
            )
            self._append_agent_event(
                run_id=run_id,
                phase="party_projection",
                round_number=1,
                from_agent="opponent_party",
                to_agent="opponent_counsel",
                title="对方当事人初步叙事",
                payload=party_output,
                evidence_cards=context_brief["evidence_cards"],
                event_type=OpponentAnalysisEventType.agent_message.value,
            )

            counsel_output = self._generate_agent_output(
                agent_key="opponent_counsel",
                case_facts=run.case_facts,
                phase="counsel_projection",
                round_number=1,
                evidence_cards=context_brief["evidence_cards"],
                context_brief=context_brief,
                upstream_payloads={"opponent_party": party_output},
            )
            self._append_agent_event(
                run_id=run_id,
                phase="counsel_projection",
                round_number=1,
                from_agent="opponent_counsel",
                to_agent="bench_observer",
                title="对方律师策略推演",
                payload=counsel_output,
                evidence_cards=context_brief["evidence_cards"],
                event_type=OpponentAnalysisEventType.agent_message.value,
            )

            bench_output = self._generate_agent_output(
                agent_key="bench_observer",
                case_facts=run.case_facts,
                phase="bench_review",
                round_number=1,
                evidence_cards=context_brief["evidence_cards"],
                context_brief=context_brief,
                upstream_payloads={
                    "opponent_party": party_output,
                    "opponent_counsel": counsel_output,
                },
            )
            self._append_agent_event(
                run_id=run_id,
                phase="bench_review",
                round_number=1,
                from_agent="bench_observer",
                to_agent="opponent_party,opponent_counsel,our_strategy_advisor",
                title="庭审观察员校准意见",
                payload=bench_output,
                evidence_cards=context_brief["evidence_cards"],
                event_type=OpponentAnalysisEventType.agent_message.value,
            )

            strategy_output = self._generate_agent_output(
                agent_key="our_strategy_advisor",
                case_facts=run.case_facts,
                phase="strategy_response",
                round_number=1,
                evidence_cards=context_brief["evidence_cards"],
                context_brief=context_brief,
                upstream_payloads={
                    "opponent_party": party_output,
                    "opponent_counsel": counsel_output,
                    "bench_observer": bench_output,
                },
            )
            self._append_agent_event(
                run_id=run_id,
                phase="strategy_response",
                round_number=1,
                from_agent="our_strategy_advisor",
                to_agent=None,
                title="我方策略官应对建议",
                payload=strategy_output,
                evidence_cards=context_brief["evidence_cards"],
                event_type=OpponentAnalysisEventType.agent_message.value,
            )

            revised_party_output = self._generate_agent_output(
                agent_key="opponent_party",
                case_facts=run.case_facts,
                phase="revision",
                round_number=2,
                evidence_cards=context_brief["evidence_cards"],
                context_brief=context_brief,
                upstream_payloads={
                    "bench_observer": bench_output,
                    "previous_self": party_output,
                },
                revision=True,
            )
            self._append_agent_event(
                run_id=run_id,
                phase="revision",
                round_number=2,
                from_agent="opponent_party",
                to_agent="opponent_counsel",
                title="对方当事人修正叙事",
                payload=revised_party_output,
                evidence_cards=context_brief["evidence_cards"],
                event_type=OpponentAnalysisEventType.agent_revision.value,
            )

            revised_counsel_output = self._generate_agent_output(
                agent_key="opponent_counsel",
                case_facts=run.case_facts,
                phase="revision",
                round_number=2,
                evidence_cards=context_brief["evidence_cards"],
                context_brief=context_brief,
                upstream_payloads={
                    "bench_observer": bench_output,
                    "opponent_party": revised_party_output,
                    "previous_self": counsel_output,
                },
                revision=True,
            )
            self._append_agent_event(
                run_id=run_id,
                phase="revision",
                round_number=2,
                from_agent="opponent_counsel",
                to_agent="our_strategy_advisor",
                title="对方律师修正策略",
                payload=revised_counsel_output,
                evidence_cards=context_brief["evidence_cards"],
                event_type=OpponentAnalysisEventType.agent_revision.value,
            )

            final_summary = self._build_final_summary(
                case_facts=run.case_facts,
                context_brief=context_brief,
                party_output=revised_party_output,
                counsel_output=revised_counsel_output,
                strategy_output=strategy_output,
            )
            self.service.append_event(
                run_id=run_id,
                phase="finalize",
                round_number=2,
                from_agent=None,
                to_agent=None,
                event_type=OpponentAnalysisEventType.summary.value,
                title="预测总览已生成",
                content=final_summary.opponent_position.summary,
                structured_payload=final_summary.model_dump(),
                citations=[
                    item.model_dump() for item in final_summary.evidence_index[:4]
                ],
                event_status="done",
            )
            self.service.complete_run(
                run_id,
                summary=final_summary,
                risk_cards=[
                    {"title": item}
                    for item in final_summary.response_plan.priority_actions[:3]
                ],
            )
        except Exception as exc:
            logger.exception("Opponent analysis failed", extra={"run_id": run_id})
            self.service.append_event(
                run_id=run_id,
                phase="finalize",
                round_number=0,
                from_agent=None,
                to_agent=None,
                event_type=OpponentAnalysisEventType.error.value,
                title="预测任务失败",
                content=str(exc),
                structured_payload={"error": str(exc)},
                citations=[],
                event_status="error",
            )
            self.service.fail_run(run_id, str(exc))
            raise

    def _build_context_brief(
        self,
        case_facts: str,
        top_k: int,
        document_ids: Sequence[str],
    ) -> dict[str, Any]:
        search_response = self.vector_service.search_chunks(
            query=case_facts,
            top_k=max(top_k * 2, 6),
            document_ids=document_ids,
        )
        evidence_cards = [
            OpponentAnalysisEvidenceItem.model_validate(item).model_dump()
            for item in self.service.build_citations_from_sources(
                search_response.items,
                limit=max(4, min(top_k + 1, 6)),
            )
        ]
        issue_map = self._extract_key_points(case_facts, limit=3)
        if not issue_map:
            issue_map = ["围绕案件事实、责任分配和证据强弱展开庭审博弈。"]

        fact_gaps: list[str] = []
        if not evidence_cards:
            fact_gaps.append(
                "当前没有检索到可直接支撑预测的证据片段，需要补充或放宽文档范围。"
            )
        if len(case_facts.strip()) < 80:
            fact_gaps.append("案情摘要较短，时间线、金额、沟通节点等关键细节可能不足。")
        if not any(char.isdigit() for char in case_facts):
            fact_gaps.append(
                "案情中缺少日期、金额或次数等量化细节，预测置信度会受影响。"
            )
        if len(fact_gaps) < 2:
            fact_gaps.append("需重点核实双方证据形成过程与证明目的是否一致。")

        return {
            "prepared_query": case_facts.strip(),
            "issue_map": issue_map,
            "fact_gaps": fact_gaps[:3],
            "evidence_cards": evidence_cards,
            "search_meta": search_response.meta,
        }

    def _generate_agent_output(
        self,
        *,
        agent_key: str,
        case_facts: str,
        phase: str,
        round_number: int,
        evidence_cards: Sequence[dict],
        context_brief: dict[str, Any],
        upstream_payloads: dict[str, OpponentAnalysisAgentPayload],
        revision: bool = False,
    ) -> OpponentAnalysisAgentPayload:
        if self.llm.is_configured():
            try:
                return self._generate_agent_output_with_llm(
                    agent_key=agent_key,
                    case_facts=case_facts,
                    phase=phase,
                    round_number=round_number,
                    evidence_cards=evidence_cards,
                    context_brief=context_brief,
                    upstream_payloads=upstream_payloads,
                    revision=revision,
                )
            except Exception:
                logger.warning(
                    "Opponent analysis agent generation fell back to heuristic mode",
                    extra={"agent_key": agent_key, "phase": phase},
                )

        return self._generate_agent_output_with_heuristics(
            agent_key=agent_key,
            case_facts=case_facts,
            evidence_cards=evidence_cards,
            context_brief=context_brief,
            upstream_payloads=upstream_payloads,
            revision=revision,
        )

    def _generate_agent_output_with_llm(
        self,
        *,
        agent_key: str,
        case_facts: str,
        phase: str,
        round_number: int,
        evidence_cards: Sequence[dict],
        context_brief: dict[str, Any],
        upstream_payloads: dict[str, OpponentAnalysisAgentPayload],
        revision: bool,
    ) -> OpponentAnalysisAgentPayload:
        agent_meta = AGENT_REGISTRY[agent_key]
        upstream_json = {
            key: value.model_dump() for key, value in upstream_payloads.items()
        }
        system_prompt = (
            "你是法律庭审推演工作流中的一个专业智能体。"
            "你必须只基于给定案情与证据进行预测，不得把预测写成确定事实。"
            "所有结论都要使用“可能、倾向于、预计、建议”等审慎措辞。"
            "请只输出 JSON。"
        )
        user_prompt = (
            f"当前阶段: {phase}\n"
            f"回合: {round_number}\n"
            f"角色: {agent_meta['label']}\n"
            f"职责: {agent_meta['objective']}\n"
            f"是否修正轮: {json.dumps(revision, ensure_ascii=False)}\n\n"
            f"案情摘要:\n{case_facts.strip()}\n\n"
            f"共享上下文:\n{json.dumps(context_brief, ensure_ascii=False)}\n\n"
            f"上游智能体输出:\n{json.dumps(upstream_json, ensure_ascii=False)}\n\n"
            "请输出 JSON，字段固定如下：\n"
            "{"
            '"claims":["3条以内的关键预测主张"],'
            '"likely_quotes":["2到3句庭上可能说出的话"],'
            '"likely_actions":["2到4个动作或策略"],'
            '"attack_points":["2到4个可能攻击或回避的点"],'
            '"confidence":0.0,'
            '"notes":"一句总结说明",'
            '"citation_numbers":[1,2]'
            "}\n\n"
            "要求：\n"
            "1. 只能引用 evidence_cards 中出现的 citation_numbers。\n"
            "2. confidence 取值 0 到 1。\n"
            "3. revision=true 时，要显式吸收庭审观察员意见并修正原先说法。\n"
            "4. 如果证据不足，可以保守输出，但不要返回空结构。"
        )
        raw = self.llm.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
        return self._normalize_agent_payload(raw, evidence_cards, agent_key)

    def _generate_agent_output_with_heuristics(
        self,
        *,
        agent_key: str,
        case_facts: str,
        evidence_cards: Sequence[dict],
        context_brief: dict[str, Any],
        upstream_payloads: dict[str, OpponentAnalysisAgentPayload],
        revision: bool,
    ) -> OpponentAnalysisAgentPayload:
        issues = context_brief.get("issue_map", []) or self._extract_key_points(
            case_facts, limit=3
        )
        first_issue = issues[0] if issues else "案件核心争点"
        fact_gap = (context_brief.get("fact_gaps") or ["证据仍存在缺口"])[0]
        citation_numbers = [
            int(item.get("citation_number", 0))
            for item in evidence_cards[:2]
            if int(item.get("citation_number", 0)) > 0
        ]

        if agent_key == "opponent_party":
            claims = [
                f"可能会围绕“{first_issue}”构建对己有利的事实叙事。",
                "可能弱化对自身不利的履行细节或沟通节点。",
                "可能强调自己并非主动违约，而是受到对方行为或客观情况影响。",
            ]
            likely_quotes = [
                "我方一直是按当时情况正常处理，对方现在的说法并不完整。",
                "关键事实不能只看单一材料，还要结合双方当时的沟通背景。",
            ]
            likely_actions = [
                "先确认对己有利的基础事实，再对关键细节采取模糊化表达。",
                "被追问证据细节时，可能转向常理、习惯或口头沟通来解释。",
            ]
            attack_points = [
                "可能回避没有书面证据直接支撑的节点。",
                "可能淡化时间线中对己不利的先后顺序。",
            ]
            notes = "更倾向于从个人经历和结果公平性角度来包装说法。"
            confidence = 0.66 if evidence_cards else 0.42
        elif agent_key == "opponent_counsel":
            upstream_party = upstream_payloads.get("opponent_party")
            claims = [
                f"可能把“{first_issue}”包装成法律争点并主动重述证明责任分配。",
                "可能主张对方证据链条不完整，无法单独推出其核心结论。",
                "可能通过程序性措辞弱化不利事实的证明力。",
            ]
            if upstream_party and upstream_party.claims:
                claims[0] = (
                    f"可能会把当事人的叙事“{upstream_party.claims[0]}”转写为正式法庭主张。"
                )
            likely_quotes = [
                "对方的证据只能证明片段事实，尚不足以完整证明其待证事项。",
                "本案争议焦点不在情绪化叙事，而在证据是否足以形成闭合链条。",
            ]
            likely_actions = [
                "优先攻击我方关键书证与陈述之间的对应关系。",
                "必要时提出程序性异议，争取削弱对方举证节奏。",
            ]
            attack_points = [
                fact_gap,
                "我方文书、沟通记录和庭上陈述可能存在口径不一致的风险。",
            ]
            notes = "更像是在替对方叙事寻找法律包装和证据攻击路径。"
            confidence = 0.72 if evidence_cards else 0.45
        elif agent_key == "bench_observer":
            upstream_counsel = upstream_payloads.get("opponent_counsel")
            claims = [
                "法庭更可能关注时间线、证据形成过程和证明对象是否一一对应。",
                "单靠立场化叙事无法持续说服法庭，核心仍是证据闭环。",
                "若双方口径冲突，法庭会优先看客观材料而非主观解释。",
            ]
            if upstream_counsel and upstream_counsel.attack_points:
                claims[1] = (
                    f"对方律师最有可能抓住“{upstream_counsel.attack_points[0]}”持续施压。"
                )
            likely_quotes = [
                "请双方围绕关键事实节点对应具体证据，不要仅作概括性陈述。",
                "如果对该节点存在异议，请说明证据形成时间、来源和证明目的。",
            ]
            likely_actions = [
                "要求双方回到证据和时间线本身，压缩空泛评价空间。",
                "对前后矛盾的陈述进行追问，要求作出明确解释。",
            ]
            attack_points = [
                fact_gap,
                "如果材料之间缺少直接连接点，法庭采信程度会明显下降。",
            ]
            notes = "中立视角下，最容易放大的不是情绪，而是证据链断点。"
            confidence = 0.74 if evidence_cards else 0.5
        else:
            upstream_counsel = upstream_payloads.get("opponent_counsel")
            upstream_bench = upstream_payloads.get("bench_observer")
            claims = [
                "我方应先把关键事实时间线钉牢，再处理对方的解释空间。",
                "对方律师若围绕证据完整性发力，我方需提前准备对应闭环。",
                "法庭最看重的是事实与证据的一致性，而不是叙事强度。",
            ]
            if upstream_counsel and upstream_counsel.attack_points:
                claims[1] = (
                    f"我方应优先回应对方可能攻击的“{upstream_counsel.attack_points[0]}”。"
                )
            likely_quotes = [
                "我方主张并非孤立陈述，而是有对应材料和时间节点相互印证。",
                "即便对方试图弱化该证据，其形成过程和证明目的仍然清晰稳定。",
            ]
            likely_actions = [
                "按时间线整理证据目录，确保每个争点都有对应材料落点。",
                "预设对方对证据真实性、完整性和关联性的攻击，并准备简洁回应。",
                "对无法完全证明的节点提前限定主张强度，避免被反向放大。",
            ]
            attack_points = [
                "优先补强容易被对方律师抓住的断点材料。",
                "避免在庭上扩张未经证据支持的细节判断。",
            ]
            if upstream_bench and upstream_bench.attack_points:
                attack_points.insert(0, upstream_bench.attack_points[0])
            notes = "策略重点是让法庭先看到我方证据闭环，再拆解对方叙事。"
            confidence = 0.78 if evidence_cards else 0.55

        if revision:
            notes = f"已根据校准意见修正：{notes}"
            likely_actions = [
                action.replace("可能", "更可能") for action in likely_actions
            ]
            confidence = min(0.92, confidence + 0.05)

        return OpponentAnalysisAgentPayload(
            claims=claims[:3],
            likely_quotes=likely_quotes[:3],
            likely_actions=likely_actions[:4],
            attack_points=attack_points[:4],
            confidence=confidence,
            notes=notes,
            citation_numbers=citation_numbers,
        )

    def _build_final_summary(
        self,
        *,
        case_facts: str,
        context_brief: dict[str, Any],
        party_output: OpponentAnalysisAgentPayload,
        counsel_output: OpponentAnalysisAgentPayload,
        strategy_output: OpponentAnalysisAgentPayload,
    ) -> OpponentAnalysisSummary:
        if self.llm.is_configured():
            try:
                return self._build_final_summary_with_llm(
                    case_facts=case_facts,
                    context_brief=context_brief,
                    party_output=party_output,
                    counsel_output=counsel_output,
                    strategy_output=strategy_output,
                )
            except Exception:
                logger.warning("Final summary generation fell back to heuristic mode")

        return self._build_final_summary_with_heuristics(
            context_brief=context_brief,
            party_output=party_output,
            counsel_output=counsel_output,
            strategy_output=strategy_output,
        )

    def _build_final_summary_with_llm(
        self,
        *,
        case_facts: str,
        context_brief: dict[str, Any],
        party_output: OpponentAnalysisAgentPayload,
        counsel_output: OpponentAnalysisAgentPayload,
        strategy_output: OpponentAnalysisAgentPayload,
    ) -> OpponentAnalysisSummary:
        system_prompt = (
            "你是法律预测看板的汇总智能体。"
            "你必须把前面多智能体的预测整理成稳定 JSON，不得把预测写成确定事实。"
            "所有输出必须使用审慎措辞，并且只引用给定 evidence_cards 中的 citation_number。"
        )
        user_prompt = (
            f"案情摘要:\n{case_facts.strip()}\n\n"
            f"共享上下文:\n{json.dumps(context_brief, ensure_ascii=False)}\n\n"
            f"对方当事人输出:\n{json.dumps(party_output.model_dump(), ensure_ascii=False)}\n\n"
            f"对方律师输出:\n{json.dumps(counsel_output.model_dump(), ensure_ascii=False)}\n\n"
            f"我方策略官输出:\n{json.dumps(strategy_output.model_dump(), ensure_ascii=False)}\n\n"
            "请输出 JSON，结构如下：\n"
            "{"
            '"opponent_position":{"summary":"...","claims":["..."],"confidence":0.0},'
            '"lawyer_predictions":{"claims":[],"likely_quotes":[],"likely_actions":[],"attack_points":[],"confidence":0.0,"notes":"...","citation_numbers":[1,2]},'
            '"party_predictions":{"claims":[],"likely_quotes":[],"likely_actions":[],"attack_points":[],"confidence":0.0,"notes":"...","citation_numbers":[1,2]},'
            '"response_plan":{"priority_actions":[],"courtroom_responses":[],"evidence_to_prepare":[],"notes":"..."},'
            '"risk_level":"low|medium|high"'
            "}"
        )
        raw = self.llm.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
        summary = OpponentAnalysisSummary(
            opponent_position=OpponentAnalysisOpponentPosition.model_validate(
                raw.get("opponent_position", {})
            ),
            lawyer_predictions=self._normalize_agent_payload(
                raw.get("lawyer_predictions", {}),
                context_brief.get("evidence_cards", []),
                "opponent_counsel",
            ),
            party_predictions=self._normalize_agent_payload(
                raw.get("party_predictions", {}),
                context_brief.get("evidence_cards", []),
                "opponent_party",
            ),
            response_plan=OpponentAnalysisResponsePlan.model_validate(
                raw.get("response_plan", {})
            ),
            evidence_index=[],
            risk_level=self._normalize_risk_level(raw.get("risk_level")),
        )
        summary.evidence_index = self._aggregate_evidence_usage(
            context_brief.get("evidence_cards", []),
            {
                "party_predictions": summary.party_predictions,
                "lawyer_predictions": summary.lawyer_predictions,
            },
        )
        return summary

    def _build_final_summary_with_heuristics(
        self,
        *,
        context_brief: dict[str, Any],
        party_output: OpponentAnalysisAgentPayload,
        counsel_output: OpponentAnalysisAgentPayload,
        strategy_output: OpponentAnalysisAgentPayload,
    ) -> OpponentAnalysisSummary:
        evidence_index = self._aggregate_evidence_usage(
            context_brief.get("evidence_cards", []),
            {
                "party_predictions": party_output,
                "lawyer_predictions": counsel_output,
                "response_plan": strategy_output,
            },
        )
        attack_total = len(counsel_output.attack_points) + len(
            party_output.attack_points
        )
        if not evidence_index:
            risk_level = "high"
        elif attack_total >= 5:
            risk_level = "high"
        elif attack_total >= 3:
            risk_level = "medium"
        else:
            risk_level = "low"

        return OpponentAnalysisSummary(
            opponent_position=OpponentAnalysisOpponentPosition(
                summary=(
                    "对方更可能围绕已有争点组织一套对己有利的事实解释，"
                    "并由律师把它包装成围绕证据完整性与证明责任展开的法庭主张。"
                ),
                claims=[*counsel_output.claims[:2], *party_output.claims[:1]][:3],
                confidence=round(
                    max(counsel_output.confidence, party_output.confidence), 2
                ),
            ),
            lawyer_predictions=counsel_output,
            party_predictions=party_output,
            response_plan=OpponentAnalysisResponsePlan(
                priority_actions=strategy_output.likely_actions[:3],
                courtroom_responses=strategy_output.likely_quotes[:3],
                evidence_to_prepare=(
                    strategy_output.attack_points[:3]
                    + context_brief.get("fact_gaps", [])[:2]
                )[:4],
                notes=strategy_output.notes,
            ),
            evidence_index=evidence_index,
            risk_level=risk_level,
        )

    def _append_agent_event(
        self,
        *,
        run_id: str,
        phase: str,
        round_number: int,
        from_agent: str,
        to_agent: str | None,
        title: str,
        payload: OpponentAnalysisAgentPayload,
        evidence_cards: Sequence[dict],
        event_type: str,
    ) -> None:
        citations = self.service.build_citations_by_number(
            evidence_cards, payload.citation_numbers
        )
        content = "；".join(payload.claims[:2]) or payload.notes
        self.service.append_event(
            run_id=run_id,
            phase=phase,
            round_number=round_number,
            from_agent=from_agent,
            to_agent=to_agent,
            event_type=event_type,
            title=title,
            content=content,
            structured_payload=payload.model_dump(),
            citations=citations,
            event_status="done",
        )

    def _normalize_agent_payload(
        self,
        raw: dict[str, Any],
        evidence_cards: Sequence[dict],
        agent_key: str,
    ) -> OpponentAnalysisAgentPayload:
        max_citation_number = max(
            [int(item.get("citation_number", 0)) for item in evidence_cards] or [0]
        )

        def normalize_list(key: str, fallback: list[str]) -> list[str]:
            value = raw.get(key, fallback)
            if not isinstance(value, list):
                value = fallback
            items = [str(item).strip() for item in value if str(item).strip()]
            return items[:4] if items else fallback

        try:
            confidence = float(raw.get("confidence", 0.58))
        except (TypeError, ValueError):
            confidence = 0.58
        confidence = min(0.95, max(0.25, confidence))

        citation_numbers: list[int] = []
        for item in raw.get("citation_numbers", []):
            try:
                number = int(item)
            except (TypeError, ValueError):
                continue
            if 1 <= number <= max_citation_number and number not in citation_numbers:
                citation_numbers.append(number)
        if not citation_numbers and max_citation_number:
            citation_numbers = [1]

        fallback = self._generate_agent_output_with_heuristics(
            agent_key=agent_key,
            case_facts="",
            evidence_cards=evidence_cards,
            context_brief={"issue_map": [], "fact_gaps": []},
            upstream_payloads={},
            revision=False,
        )
        return OpponentAnalysisAgentPayload(
            claims=normalize_list("claims", fallback.claims)[:3],
            likely_quotes=normalize_list("likely_quotes", fallback.likely_quotes)[:3],
            likely_actions=normalize_list("likely_actions", fallback.likely_actions),
            attack_points=normalize_list("attack_points", fallback.attack_points),
            confidence=confidence,
            notes=str(raw.get("notes", fallback.notes)).strip() or fallback.notes,
            citation_numbers=citation_numbers,
        )

    def _aggregate_evidence_usage(
        self,
        evidence_cards: Sequence[dict],
        payload_map: dict[str, OpponentAnalysisAgentPayload],
    ) -> list[OpponentAnalysisEvidenceItem]:
        evidence_by_number = {
            int(
                item.get("citation_number", 0)
            ): OpponentAnalysisEvidenceItem.model_validate(item)
            for item in evidence_cards
            if int(item.get("citation_number", 0)) > 0
        }
        result_map: dict[str, OpponentAnalysisEvidenceItem] = {}
        for phase_key, payload in payload_map.items():
            for number in payload.citation_numbers:
                evidence = evidence_by_number.get(number)
                if not evidence:
                    continue
                current = result_map.setdefault(
                    evidence.chunk_id, evidence.model_copy(deep=True)
                )
                if phase_key not in current.phases:
                    current.phases.append(phase_key)
                if phase_key not in current.used_by:
                    current.used_by.append(phase_key)
        aggregated = list(result_map.values())
        aggregated.sort(key=lambda item: item.citation_number)
        return aggregated

    @staticmethod
    def _normalize_risk_level(raw: Any) -> str:
        normalized = str(raw or "").strip().lower()
        if normalized in {"low", "medium", "high"}:
            return normalized
        return "medium"

    @staticmethod
    def _extract_key_points(text: str, *, limit: int) -> list[str]:
        candidates = [
            item.strip("；;，,。!?！？ ")
            for item in re.split(r"[\n。！？!?；;]", text or "")
        ]
        points = [item for item in candidates if len(item) >= 8]
        return points[:limit]
