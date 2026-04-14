from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
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
from app.services.analytics import AnalyticsService
from app.services.opponent_analysis.llm import OpponentAnalysisLLMClient
from app.services.opponent_analysis.service import OpponentAnalysisService
from app.services.prompts import (
    PromptSegment,
    TokenBudget,
    assemble_prompt_segments,
    build_opponent_analysis_agent_system_prompt,
    build_opponent_analysis_summary_system_prompt,
)
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

MANDATORY_AGENT_ORDER = (
    "opponent_party",
    "opponent_counsel",
    "bench_observer",
    "our_strategy_advisor",
)

SCHEDULER_PRIORITY = (
    "bench_observer",
    "our_strategy_advisor",
    "opponent_counsel",
    "opponent_party",
)

MAX_DIALOGUE_TURNS = 8
MAX_AGENT_TURNS = 3

AGENT_REGISTRY: dict[str, dict[str, Any]] = {
    "opponent_party": {
        "label": "对方当事人",
        "objective": "从自身利益出发，预测对方当事人在庭上最可能坚持的事实叙事、回避点与说法。",
        "phase": "party_projection",
        "default_recipients": ["opponent_counsel", "bench_observer"],
    },
    "opponent_counsel": {
        "label": "对方律师",
        "objective": "基于对方当事人的叙事，预测对方律师可能采取的主张、抗辩、程序动作与进攻点。",
        "phase": "counsel_projection",
        "default_recipients": ["bench_observer", "our_strategy_advisor"],
    },
    "bench_observer": {
        "label": "庭审观察员",
        "objective": "从中立视角检查双方叙事的真实性、证据强弱和法庭可采性，并提出修正要求。",
        "phase": "bench_review",
        "default_recipients": [
            "opponent_party",
            "opponent_counsel",
            "our_strategy_advisor",
        ],
    },
    "our_strategy_advisor": {
        "label": "我方策略官",
        "objective": "基于前述预测结果，形成我方的庭审应对、证据补强与风险优先级建议。",
        "phase": "strategy_response",
        "default_recipients": ["bench_observer"],
    },
}

MESSAGE_TYPES = {"proposal", "challenge", "review", "strategy", "reply"}


@dataclass(slots=True)
class DialogueMessage:
    phase: str
    round_number: int
    sender: str
    recipients: list[str]
    event_type: str
    title: str
    content: str
    payload: OpponentAnalysisAgentPayload
    citations: list[dict[str, Any]]
    message_type: str
    focus: str


@dataclass(slots=True)
class AgentDecision:
    payload: OpponentAnalysisAgentPayload
    recipients: list[str]
    message_type: str
    summary: str
    focus: str


@dataclass(slots=True)
class AgentState:
    agent_key: str
    label: str
    inbox: list[DialogueMessage] = field(default_factory=list)
    memory: list[dict[str, Any]] = field(default_factory=list)
    last_payload: OpponentAnalysisAgentPayload | None = None
    turns_taken: int = 0
    has_spoken: bool = False

    def consume_inbox(self) -> list[DialogueMessage]:
        items = list(self.inbox)
        self.inbox.clear()
        for item in items:
            self.memory.append(self._to_memory_entry(item, direction="incoming"))
        self._trim_memory()
        return items

    def remember_sent(self, item: DialogueMessage) -> None:
        self.memory.append(self._to_memory_entry(item, direction="outgoing"))
        self._trim_memory()

    def _trim_memory(self) -> None:
        if len(self.memory) > 12:
            self.memory = self.memory[-12:]

    @staticmethod
    def _to_memory_entry(
        item: DialogueMessage,
        *,
        direction: str,
    ) -> dict[str, Any]:
        return {
            "direction": direction,
            "phase": item.phase,
            "round": item.round_number,
            "sender": item.sender,
            "recipients": list(item.recipients),
            "message_type": item.message_type,
            "focus": item.focus,
            "summary": item.content,
            "claims": list(item.payload.claims[:2]),
        }


class OpponentAnalysisProcessor:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.service = OpponentAnalysisService(db=db, settings=settings)
        self.vector_service = DocumentVectorService(db=db, settings=settings)
        self.llm = OpponentAnalysisLLMClient(settings)
        self.analytics = AnalyticsService(db=db, settings=settings)

    def run(self, run_id: str) -> None:
        run = self.service.get_run(run_id).run
        analytics_run = self.analytics.start_run(
            run_kind="opponent_analysis",
            resource_type="opponent_analysis_run",
            resource_id=run_id,
            metadata={"top_k": run.top_k, "document_scope": run.scope_document_ids},
        )
        try:
            self.service.update_run_status(run_id, OpponentAnalysisStatus.running.value)
            self.analytics.append_step(
                analytics_run.id,
                step_key="context_brief",
                title="Build shared context brief",
                status="running",
                payload={"phase": "context_brief"},
            )
            self.service.append_event(
                run_id=run_id,
                phase="context_brief",
                round_number=0,
                from_agent=None,
                to_agent=None,
                event_type=OpponentAnalysisEventType.stage.value,
                title="开始整理共享案情与证据",
                content="先汇总案情、争点和现有文档证据，为后续多智能体建立共享上下文。",
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
                content="已提炼争点地图、证据包与事实缺口，多智能体将基于隔离记忆和消息收件箱继续推演。",
                structured_payload=context_brief,
                citations=context_brief["evidence_cards"],
                event_status="done",
            )
            self.service.append_event(
                run_id=run_id,
                phase="context_brief",
                round_number=0,
                from_agent=None,
                to_agent=None,
                event_type=OpponentAnalysisEventType.stage.value,
                title="多智能体运行时已启动",
                content="每个角色拥有独立收件箱、独立记忆和自主收件人选择，后续事件不再按固定串行模板生成。",
                structured_payload={
                    "mode": "isolated_dialogue_runtime",
                    "agents": [
                        {
                            "agent_key": agent_key,
                            "label": meta["label"],
                            "phase": meta["phase"],
                            "default_recipients": meta["default_recipients"],
                        }
                        for agent_key, meta in AGENT_REGISTRY.items()
                    ],
                },
                citations=[],
                event_status="done",
            )
            self.analytics.append_step(
                analytics_run.id,
                step_key="context_brief",
                title="Shared context brief completed",
                status="done",
                payload={
                    "evidence_count": len(context_brief["evidence_cards"]),
                    "fact_gap_count": len(context_brief["fact_gaps"]),
                },
            )

            agent_states = self._run_dialogue_runtime(
                run_id=run_id,
                case_facts=run.case_facts,
                context_brief=context_brief,
                analytics_run_id=analytics_run.id,
            )
            party_output = self._resolve_final_agent_payload(
                agent_states,
                "opponent_party",
                run.case_facts,
                context_brief,
            )
            counsel_output = self._resolve_final_agent_payload(
                agent_states,
                "opponent_counsel",
                run.case_facts,
                context_brief,
            )
            bench_output = self._resolve_final_agent_payload(
                agent_states,
                "bench_observer",
                run.case_facts,
                context_brief,
            )
            strategy_output = self._resolve_final_agent_payload(
                agent_states,
                "our_strategy_advisor",
                run.case_facts,
                context_brief,
            )

            final_summary = self._build_final_summary(
                case_facts=run.case_facts,
                context_brief=context_brief,
                party_output=party_output,
                counsel_output=counsel_output,
                bench_output=bench_output,
                strategy_output=strategy_output,
            )
            self.service.append_event(
                run_id=run_id,
                phase="finalize",
                round_number=max(
                    [state.turns_taken for state in agent_states.values()] or [0]
                ),
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
            self.analytics.finish_run(
                analytics_run.id,
                status="completed",
                summary={
                    "risk_level": final_summary.risk_level,
                    "evidence_count": len(final_summary.evidence_index),
                },
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
            self.analytics.finish_run(
                analytics_run.id,
                status="failed",
                summary={"error": str(exc)},
            )
            raise

    def _run_dialogue_runtime(
        self,
        *,
        run_id: str,
        case_facts: str,
        context_brief: dict[str, Any],
        analytics_run_id: str,
    ) -> dict[str, AgentState]:
        states = {
            agent_key: AgentState(
                agent_key=agent_key,
                label=str(meta["label"]),
            )
            for agent_key, meta in AGENT_REGISTRY.items()
        }

        for turn_index in range(1, MAX_DIALOGUE_TURNS + 1):
            agent_key = self._pick_next_agent(states)
            if agent_key is None:
                break

            state = states[agent_key]
            incoming_messages = state.consume_inbox()
            revision = state.has_spoken
            phase = "revision" if revision else str(AGENT_REGISTRY[agent_key]["phase"])
            round_number = state.turns_taken + 1
            decision = self._generate_agent_decision(
                agent_key=agent_key,
                case_facts=case_facts,
                phase=phase,
                round_number=round_number,
                evidence_cards=context_brief["evidence_cards"],
                context_brief=context_brief,
                state=state,
                incoming_messages=incoming_messages,
                revision=revision,
            )
            recipients = self._normalize_recipients(
                decision.recipients,
                agent_key=agent_key,
                incoming_messages=incoming_messages,
                state=state,
            )
            event_type = (
                OpponentAnalysisEventType.agent_revision.value
                if revision
                else OpponentAnalysisEventType.agent_message.value
            )
            citations = self.service.build_citations_by_number(
                context_brief["evidence_cards"],
                decision.payload.citation_numbers,
            )
            title = self._build_event_title(
                agent_key=agent_key,
                incoming_messages=incoming_messages,
                revision=revision,
            )
            content = self._clip_text(
                decision.summary
                or "；".join(decision.payload.claims[:2])
                or decision.payload.notes,
                220,
            )
            message = DialogueMessage(
                phase=phase,
                round_number=round_number,
                sender=agent_key,
                recipients=recipients,
                event_type=event_type,
                title=title,
                content=content,
                payload=decision.payload,
                citations=citations,
                message_type=decision.message_type,
                focus=decision.focus,
            )

            state.turns_taken += 1
            state.has_spoken = True
            state.last_payload = decision.payload
            state.remember_sent(message)
            self._dispatch_message(states, message)
            self._append_agent_event(
                run_id=run_id,
                message=message,
                incoming_messages=incoming_messages,
                state=state,
            )
            self._record_agent_phase(
                analytics_run_id=analytics_run_id,
                step_key=f"turn_{turn_index:02d}_{agent_key}",
                phase=phase,
                agent_key=agent_key,
                payload=decision.payload,
                recipients=recipients,
                incoming_messages=incoming_messages,
            )

        return states

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

    def _generate_agent_decision(
        self,
        *,
        agent_key: str,
        case_facts: str,
        phase: str,
        round_number: int,
        evidence_cards: Sequence[dict],
        context_brief: dict[str, Any],
        state: AgentState,
        incoming_messages: Sequence[DialogueMessage],
        revision: bool,
    ) -> AgentDecision:
        if self.llm.is_configured():
            try:
                return self._generate_agent_decision_with_llm(
                    agent_key=agent_key,
                    case_facts=case_facts,
                    phase=phase,
                    round_number=round_number,
                    evidence_cards=evidence_cards,
                    context_brief=context_brief,
                    state=state,
                    incoming_messages=incoming_messages,
                    revision=revision,
                )
            except Exception:
                logger.warning(
                    "Opponent analysis agent generation fell back to heuristic mode",
                    extra={"agent_key": agent_key, "phase": phase},
                )

        return self._build_heuristic_agent_decision(
            agent_key=agent_key,
            case_facts=case_facts,
            evidence_cards=evidence_cards,
            context_brief=context_brief,
            state=state,
            incoming_messages=incoming_messages,
            revision=revision,
        )

    def _generate_agent_decision_with_llm(
        self,
        *,
        agent_key: str,
        case_facts: str,
        phase: str,
        round_number: int,
        evidence_cards: Sequence[dict],
        context_brief: dict[str, Any],
        state: AgentState,
        incoming_messages: Sequence[DialogueMessage],
        revision: bool,
    ) -> AgentDecision:
        agent_meta = AGENT_REGISTRY[agent_key]
        system_prompt = assemble_prompt_segments(
            build_opponent_analysis_agent_system_prompt(),
            TokenBudget(max_input_tokens=500, reserved_output_tokens=120),
        ).text
        user_prompt = assemble_prompt_segments(
            [
                PromptSegment(
                    key="stage",
                    version="v2",
                    content=(
                        f"当前阶段: {phase}\n"
                        f"回合: {round_number}\n"
                        f"角色: {agent_meta['label']}\n"
                        f"职责: {agent_meta['objective']}\n"
                        f"是否修正轮: {json.dumps(revision, ensure_ascii=False)}"
                    ),
                ),
                PromptSegment(
                    key="case",
                    version="v2",
                    content=f"案情摘要:\n{case_facts.strip()}",
                ),
                PromptSegment(
                    key="context",
                    version="v2",
                    content=f"共享上下文:\n{json.dumps(context_brief, ensure_ascii=False)}",
                ),
                PromptSegment(
                    key="memory",
                    version="v2",
                    content=(
                        "你的私有记忆(只允许基于自己的发送/接收记录判断):\n"
                        f"{json.dumps(state.memory[-8:], ensure_ascii=False)}"
                    ),
                ),
                PromptSegment(
                    key="inbox",
                    version="v2",
                    content=(
                        "你本轮收到的消息:\n"
                        f"{json.dumps(self._serialize_incoming_messages(incoming_messages), ensure_ascii=False)}"
                    ),
                ),
                PromptSegment(
                    key="routing",
                    version="v2",
                    content=(
                        "可选收件人仅限以下 agent_key，且不能发给自己:\n"
                        f"{json.dumps(self._allowed_recipient_keys(agent_key), ensure_ascii=False)}"
                    ),
                ),
                PromptSegment(
                    key="schema",
                    version="v2",
                    content=(
                        "请只输出 JSON，字段固定如下：\n"
                        "{"
                        '"summary":"一句概括本轮发言",'
                        '"focus":"本轮聚焦问题",'
                        '"message_type":"proposal|challenge|review|strategy|reply",'
                        '"recipients":["agent_key"],'
                        '"claims":["3条以内的关键预测主张"],'
                        '"likely_quotes":["2到3句庭上可能说出的话"],'
                        '"likely_actions":["2到4个动作或策略"],'
                        '"attack_points":["2到4个可能攻击或回避的点"],'
                        '"confidence":0.0,'
                        '"notes":"一句总结说明",'
                        '"citation_numbers":[1,2]'
                        "}\n\n"
                        "要求：\n"
                        "1. 你只能看到共享上下文、自己的私有记忆和当前收件箱，不能假设自己掌握其他 agent 的完整状态。\n"
                        "2. recipients 必须从允许列表中选择，也可以为空列表。\n"
                        "3. 所有结论都必须使用预测措辞，不能写成确定事实。\n"
                        "4. 只能引用 evidence_cards 中出现的 citation_numbers。\n"
                        "5. revision=true 时，要吸收本轮收件箱里的反馈并显式修正原判断。"
                    ),
                ),
            ],
            TokenBudget(max_input_tokens=2800, reserved_output_tokens=800),
        ).text
        raw = self.llm.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
        return self._normalize_agent_decision(
            raw=raw,
            agent_key=agent_key,
            case_facts=case_facts,
            evidence_cards=evidence_cards,
            context_brief=context_brief,
            state=state,
            incoming_messages=incoming_messages,
            revision=revision,
        )

    def _build_heuristic_agent_decision(
        self,
        *,
        agent_key: str,
        case_facts: str,
        evidence_cards: Sequence[dict],
        context_brief: dict[str, Any],
        state: AgentState,
        incoming_messages: Sequence[DialogueMessage],
        revision: bool,
    ) -> AgentDecision:
        payload = self._build_heuristic_agent_payload(
            agent_key=agent_key,
            case_facts=case_facts,
            evidence_cards=evidence_cards,
            context_brief=context_brief,
            incoming_messages=incoming_messages,
            revision=revision,
        )
        sender_labels = self._sender_labels(incoming_messages)
        if sender_labels:
            summary = f"结合{sender_labels}的最新消息，{payload.claims[0]}"
        else:
            summary = payload.claims[0] if payload.claims else payload.notes
        focus = (
            payload.attack_points[0]
            if payload.attack_points
            else payload.claims[0]
            if payload.claims
            else payload.notes
        )
        return AgentDecision(
            payload=payload,
            recipients=self._suggest_recipients(
                agent_key=agent_key,
                incoming_messages=incoming_messages,
                state=state,
            ),
            message_type=self._normalize_message_type(
                None,
                agent_key=agent_key,
                revision=revision,
            ),
            summary=self._clip_text(summary, 220),
            focus=self._clip_text(focus, 100),
        )

    def _build_heuristic_agent_payload(
        self,
        *,
        agent_key: str,
        case_facts: str,
        evidence_cards: Sequence[dict],
        context_brief: dict[str, Any],
        incoming_messages: Sequence[DialogueMessage],
        revision: bool,
    ) -> OpponentAnalysisAgentPayload:
        peer_payloads = {
            item.sender: item.payload
            for item in incoming_messages
            if item.sender in AGENT_REGISTRY
        }
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
            bench_feedback = peer_payloads.get("bench_observer")
            claims = [
                f"可能会围绕“{first_issue}”构建对己有利的事实叙事。",
                "可能弱化对自身不利的履行细节或沟通节点。",
                "可能强调自己并非主动违约，而是受到对方行为或客观情况影响。",
            ]
            if bench_feedback and bench_feedback.attack_points:
                claims[1] = (
                    f"收到观察员追问后，可能会进一步回避“{bench_feedback.attack_points[0]}”这一薄弱点。"
                )
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
            upstream_party = peer_payloads.get("opponent_party")
            bench_feedback = peer_payloads.get("bench_observer")
            claims = [
                f"可能把“{first_issue}”包装成法律争点并主动重述证明责任分配。",
                "可能主张对方证据链条不完整，无法单独推出其核心结论。",
                "可能通过程序性措辞弱化不利事实的证明力。",
            ]
            if upstream_party and upstream_party.claims:
                claims[0] = (
                    f"可能会把当事人的叙事“{upstream_party.claims[0]}”转写为正式法庭主张。"
                )
            if bench_feedback and bench_feedback.attack_points:
                claims[1] = (
                    f"在收到校准意见后，可能进一步放大“{bench_feedback.attack_points[0]}”对应的证据断点。"
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
            upstream_counsel = peer_payloads.get("opponent_counsel")
            upstream_strategy = peer_payloads.get("our_strategy_advisor")
            claims = [
                "法庭更可能关注时间线、证据形成过程和证明对象是否一一对应。",
                "单靠立场化叙事无法持续说服法庭，核心仍是证据闭环。",
                "若双方口径冲突，法庭会优先看客观材料而非主观解释。",
            ]
            if upstream_counsel and upstream_counsel.attack_points:
                claims[1] = (
                    f"对方律师最有可能抓住“{upstream_counsel.attack_points[0]}”持续施压。"
                )
            if upstream_strategy and upstream_strategy.likely_actions:
                claims[2] = (
                    f"从应对角度看，法庭会重点检验“{upstream_strategy.likely_actions[0]}”是否真的有证据支撑。"
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
            upstream_counsel = peer_payloads.get("opponent_counsel")
            upstream_bench = peer_payloads.get("bench_observer")
            claims = [
                "我方应先把关键事实时间线钉牢，再处理对方的解释空间。",
                "对方律师若围绕证据完整性发力，我方需提前准备对应闭环。",
                "法庭最看重的是事实与证据的一致性，而不是叙事强度。",
            ]
            if upstream_counsel and upstream_counsel.attack_points:
                claims[1] = (
                    f"我方应优先回应对方可能攻击的“{upstream_counsel.attack_points[0]}”。"
                )
            if upstream_bench and upstream_bench.attack_points:
                claims[2] = (
                    f"观察员已经提示“{upstream_bench.attack_points[0]}”，我方需要先补足这一法庭关注点。"
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
            notes = f"已根据本轮收件箱反馈修正：{notes}"
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
        bench_output: OpponentAnalysisAgentPayload,
        strategy_output: OpponentAnalysisAgentPayload,
    ) -> OpponentAnalysisSummary:
        if self.llm.is_configured():
            try:
                return self._build_final_summary_with_llm(
                    case_facts=case_facts,
                    context_brief=context_brief,
                    party_output=party_output,
                    counsel_output=counsel_output,
                    bench_output=bench_output,
                    strategy_output=strategy_output,
                )
            except Exception:
                logger.warning("Final summary generation fell back to heuristic mode")

        return self._build_final_summary_with_heuristics(
            context_brief=context_brief,
            party_output=party_output,
            counsel_output=counsel_output,
            bench_output=bench_output,
            strategy_output=strategy_output,
        )

    def _build_final_summary_with_llm(
        self,
        *,
        case_facts: str,
        context_brief: dict[str, Any],
        party_output: OpponentAnalysisAgentPayload,
        counsel_output: OpponentAnalysisAgentPayload,
        bench_output: OpponentAnalysisAgentPayload,
        strategy_output: OpponentAnalysisAgentPayload,
    ) -> OpponentAnalysisSummary:
        system_prompt = assemble_prompt_segments(
            build_opponent_analysis_summary_system_prompt(),
            TokenBudget(max_input_tokens=500, reserved_output_tokens=120),
        ).text
        user_prompt = assemble_prompt_segments(
            [
                PromptSegment(
                    key="case",
                    version="v2",
                    content=f"案情摘要:\n{case_facts.strip()}",
                ),
                PromptSegment(
                    key="context",
                    version="v2",
                    content=f"共享上下文:\n{json.dumps(context_brief, ensure_ascii=False)}",
                ),
                PromptSegment(
                    key="party",
                    version="v2",
                    content=f"对方当事人输出:\n{json.dumps(party_output.model_dump(), ensure_ascii=False)}",
                ),
                PromptSegment(
                    key="counsel",
                    version="v2",
                    content=f"对方律师输出:\n{json.dumps(counsel_output.model_dump(), ensure_ascii=False)}",
                ),
                PromptSegment(
                    key="bench",
                    version="v2",
                    content=f"庭审观察员输出:\n{json.dumps(bench_output.model_dump(), ensure_ascii=False)}",
                ),
                PromptSegment(
                    key="strategy",
                    version="v2",
                    content=f"我方策略官输出:\n{json.dumps(strategy_output.model_dump(), ensure_ascii=False)}",
                ),
                PromptSegment(
                    key="schema",
                    version="v2",
                    content=(
                        "请输出 JSON，结构如下：\n"
                        "{"
                        '"opponent_position":{"summary":"...","claims":["..."],"confidence":0.0},'
                        '"lawyer_predictions":{"claims":[],"likely_quotes":[],"likely_actions":[],"attack_points":[],"confidence":0.0,"notes":"...","citation_numbers":[1,2]},'
                        '"party_predictions":{"claims":[],"likely_quotes":[],"likely_actions":[],"attack_points":[],"confidence":0.0,"notes":"...","citation_numbers":[1,2]},'
                        '"response_plan":{"priority_actions":[],"courtroom_responses":[],"evidence_to_prepare":[],"notes":"..."},'
                        '"risk_level":"low|medium|high"'
                        "}"
                    ),
                ),
            ],
            TokenBudget(max_input_tokens=2800, reserved_output_tokens=800),
        ).text
        raw = self.llm.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
        summary = OpponentAnalysisSummary(
            opponent_position=OpponentAnalysisOpponentPosition.model_validate(
                raw.get("opponent_position", {})
            ),
            lawyer_predictions=self._normalize_agent_payload(
                raw=raw.get("lawyer_predictions", {}),
                evidence_cards=context_brief.get("evidence_cards", []),
                agent_key="opponent_counsel",
                case_facts=case_facts,
                context_brief=context_brief,
                incoming_messages=[],
                revision=False,
            ),
            party_predictions=self._normalize_agent_payload(
                raw=raw.get("party_predictions", {}),
                evidence_cards=context_brief.get("evidence_cards", []),
                agent_key="opponent_party",
                case_facts=case_facts,
                context_brief=context_brief,
                incoming_messages=[],
                revision=False,
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
                "bench_review": bench_output,
                "response_plan": strategy_output,
            },
        )
        return summary

    def _build_final_summary_with_heuristics(
        self,
        *,
        context_brief: dict[str, Any],
        party_output: OpponentAnalysisAgentPayload,
        counsel_output: OpponentAnalysisAgentPayload,
        bench_output: OpponentAnalysisAgentPayload,
        strategy_output: OpponentAnalysisAgentPayload,
    ) -> OpponentAnalysisSummary:
        evidence_index = self._aggregate_evidence_usage(
            context_brief.get("evidence_cards", []),
            {
                "party_predictions": party_output,
                "lawyer_predictions": counsel_output,
                "bench_review": bench_output,
                "response_plan": strategy_output,
            },
        )
        attack_total = (
            len(counsel_output.attack_points)
            + len(party_output.attack_points)
            + len(bench_output.attack_points)
        )
        if not evidence_index:
            risk_level = "high"
        elif attack_total >= 7:
            risk_level = "high"
        elif attack_total >= 4:
            risk_level = "medium"
        else:
            risk_level = "low"

        return OpponentAnalysisSummary(
            opponent_position=OpponentAnalysisOpponentPosition(
                summary=(
                    "对方更可能围绕已有争点组织对己有利的事实解释，"
                    "并由律师把它包装成围绕证据完整性与证明责任展开的法庭主张；"
                    "庭审观察视角会持续放大证据闭环中的断点。"
                ),
                claims=[
                    *counsel_output.claims[:1],
                    *party_output.claims[:1],
                    *bench_output.claims[:1],
                ][:3],
                confidence=round(
                    max(
                        counsel_output.confidence,
                        party_output.confidence,
                        bench_output.confidence,
                    ),
                    2,
                ),
            ),
            lawyer_predictions=counsel_output,
            party_predictions=party_output,
            response_plan=OpponentAnalysisResponsePlan(
                priority_actions=[
                    *strategy_output.likely_actions[:2],
                    *bench_output.likely_actions[:1],
                ][:3],
                courtroom_responses=strategy_output.likely_quotes[:3],
                evidence_to_prepare=(
                    strategy_output.attack_points[:2]
                    + bench_output.attack_points[:1]
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
        message: DialogueMessage,
        incoming_messages: Sequence[DialogueMessage],
        state: AgentState,
    ) -> None:
        structured_payload = {
            **message.payload.model_dump(),
            "dialogue_meta": {
                "message_type": message.message_type,
                "focus": message.focus,
                "incoming_from": [item.sender for item in incoming_messages],
                "incoming_titles": [item.title for item in incoming_messages],
                "recipients": message.recipients,
                "inbox_count": len(incoming_messages),
                "memory_size": len(state.memory),
                "turns_taken": state.turns_taken,
            },
        }
        self.service.append_event(
            run_id=run_id,
            phase=message.phase,
            round_number=message.round_number,
            from_agent=message.sender,
            to_agent=",".join(message.recipients) or None,
            event_type=message.event_type,
            title=message.title,
            content=message.content,
            structured_payload=structured_payload,
            citations=message.citations,
            event_status="done",
        )

    def _record_agent_phase(
        self,
        *,
        analytics_run_id: str,
        step_key: str,
        phase: str,
        agent_key: str,
        payload: OpponentAnalysisAgentPayload,
        recipients: Sequence[str],
        incoming_messages: Sequence[DialogueMessage],
    ) -> None:
        self.analytics.append_step(
            analytics_run_id,
            step_key=step_key,
            title=f"{agent_key} dialogue turn completed",
            status="done",
            payload={
                "phase": phase,
                "agent_key": agent_key,
                "claim_count": len(payload.claims),
                "citation_count": len(payload.citation_numbers),
                "confidence": payload.confidence,
                "recipient_count": len(recipients),
                "incoming_count": len(incoming_messages),
            },
        )

    def _normalize_agent_decision(
        self,
        *,
        raw: dict[str, Any],
        agent_key: str,
        case_facts: str,
        evidence_cards: Sequence[dict],
        context_brief: dict[str, Any],
        state: AgentState,
        incoming_messages: Sequence[DialogueMessage],
        revision: bool,
    ) -> AgentDecision:
        payload = self._normalize_agent_payload(
            raw=raw,
            evidence_cards=evidence_cards,
            agent_key=agent_key,
            case_facts=case_facts,
            context_brief=context_brief,
            incoming_messages=incoming_messages,
            revision=revision,
        )
        recipients = self._normalize_recipients(
            raw.get("recipients", []),
            agent_key=agent_key,
            incoming_messages=incoming_messages,
            state=state,
        )
        summary = self._clip_text(
            str(raw.get("summary", "")).strip()
            or "；".join(payload.claims[:2])
            or payload.notes,
            220,
        )
        focus = self._clip_text(
            str(raw.get("focus", "")).strip()
            or (payload.attack_points[0] if payload.attack_points else payload.notes),
            100,
        )
        return AgentDecision(
            payload=payload,
            recipients=recipients,
            message_type=self._normalize_message_type(
                raw.get("message_type"),
                agent_key=agent_key,
                revision=revision,
            ),
            summary=summary,
            focus=focus,
        )

    def _normalize_agent_payload(
        self,
        *,
        raw: dict[str, Any],
        evidence_cards: Sequence[dict],
        agent_key: str,
        case_facts: str,
        context_brief: dict[str, Any],
        incoming_messages: Sequence[DialogueMessage],
        revision: bool,
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

        fallback = self._build_heuristic_agent_payload(
            agent_key=agent_key,
            case_facts=case_facts,
            evidence_cards=evidence_cards,
            context_brief=context_brief,
            incoming_messages=incoming_messages,
            revision=revision,
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

    def _pick_next_agent(self, states: dict[str, AgentState]) -> str | None:
        for agent_key in MANDATORY_AGENT_ORDER:
            if not states[agent_key].has_spoken:
                return agent_key

        candidates: list[tuple[int, int, int, str]] = []
        for priority, agent_key in enumerate(SCHEDULER_PRIORITY):
            state = states[agent_key]
            if not state.inbox:
                continue
            if state.turns_taken >= MAX_AGENT_TURNS:
                continue
            candidates.append(
                (len(state.inbox), -priority, -state.turns_taken, agent_key)
            )
        if not candidates:
            return None
        candidates.sort(reverse=True)
        return candidates[0][3]

    def _dispatch_message(
        self,
        states: dict[str, AgentState],
        message: DialogueMessage,
    ) -> None:
        for recipient in message.recipients:
            if recipient == message.sender:
                continue
            state = states.get(recipient)
            if state is None:
                continue
            state.inbox.append(message)

    def _normalize_recipients(
        self,
        raw: object,
        *,
        agent_key: str,
        incoming_messages: Sequence[DialogueMessage],
        state: AgentState,
    ) -> list[str]:
        allowed = set(self._allowed_recipient_keys(agent_key))
        recipients: list[str] = []
        if isinstance(raw, list):
            for item in raw:
                normalized = str(item).strip()
                if normalized in allowed and normalized not in recipients:
                    recipients.append(normalized)
        if recipients:
            return recipients[:3]
        return self._suggest_recipients(
            agent_key=agent_key,
            incoming_messages=incoming_messages,
            state=state,
        )

    def _suggest_recipients(
        self,
        *,
        agent_key: str,
        incoming_messages: Sequence[DialogueMessage],
        state: AgentState,
    ) -> list[str]:
        senders = [
            item.sender
            for item in incoming_messages
            if item.sender in AGENT_REGISTRY and item.sender != agent_key
        ]
        unique_senders = list(dict.fromkeys(senders))
        defaults = [
            item
            for item in AGENT_REGISTRY[agent_key]["default_recipients"]
            if item != agent_key
        ]

        if agent_key == "our_strategy_advisor":
            if state.turns_taken == 0:
                return ["bench_observer"]
            return []

        recipients = list(unique_senders)
        for item in defaults:
            if item not in recipients:
                recipients.append(item)

        if agent_key == "bench_observer" and "our_strategy_advisor" not in recipients:
            recipients.append("our_strategy_advisor")

        return recipients[:3]

    @staticmethod
    def _normalize_message_type(
        raw: object,
        *,
        agent_key: str,
        revision: bool,
    ) -> str:
        normalized = str(raw or "").strip().lower()
        if normalized in MESSAGE_TYPES:
            return normalized
        if agent_key == "bench_observer":
            return "review"
        if agent_key == "our_strategy_advisor":
            return "strategy"
        if revision:
            return "reply"
        return "proposal"

    @staticmethod
    def _allowed_recipient_keys(agent_key: str) -> list[str]:
        return [item for item in AGENT_REGISTRY if item != agent_key]

    def _resolve_final_agent_payload(
        self,
        states: dict[str, AgentState],
        agent_key: str,
        case_facts: str,
        context_brief: dict[str, Any],
    ) -> OpponentAnalysisAgentPayload:
        state = states[agent_key]
        if state.last_payload is not None:
            return state.last_payload
        return self._build_heuristic_agent_payload(
            agent_key=agent_key,
            case_facts=case_facts,
            evidence_cards=context_brief.get("evidence_cards", []),
            context_brief=context_brief,
            incoming_messages=[],
            revision=False,
        )

    def _build_event_title(
        self,
        *,
        agent_key: str,
        incoming_messages: Sequence[DialogueMessage],
        revision: bool,
    ) -> str:
        label = str(AGENT_REGISTRY[agent_key]["label"])
        sender_labels = self._sender_labels(incoming_messages)
        if not sender_labels:
            return f"{label}发起首轮判断"
        if revision:
            return f"{label}回应{sender_labels}"
        return f"{label}接收{sender_labels}后给出判断"

    def _sender_labels(self, incoming_messages: Sequence[DialogueMessage]) -> str:
        labels: list[str] = []
        for item in incoming_messages:
            label = str(AGENT_REGISTRY.get(item.sender, {}).get("label", item.sender))
            if label and label not in labels:
                labels.append(label)
        return "、".join(labels)

    @staticmethod
    def _serialize_incoming_messages(
        incoming_messages: Sequence[DialogueMessage],
    ) -> list[dict[str, Any]]:
        return [
            {
                "phase": item.phase,
                "round": item.round_number,
                "sender": item.sender,
                "title": item.title,
                "message_type": item.message_type,
                "focus": item.focus,
                "summary": item.content,
                "claims": item.payload.claims[:2],
                "attack_points": item.payload.attack_points[:2],
            }
            for item in incoming_messages
        ]

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

    @staticmethod
    def _clip_text(value: str, limit: int) -> str:
        normalized = " ".join((value or "").split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 3].rstrip() + "..."
