from __future__ import annotations

import logging

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import get_settings
from app.services.agent.tools import legal_knowledge_search

logger = logging.getLogger(__name__)

LEGAL_SYSTEM_PROMPT = """\
你是法律知识库问答助手。你必须严格依据给定来源作答，不能编造法条、案号、事实或结论。

当你需要检索法律知识库来回答问题时，使用 legal_knowledge_search 工具。
该工具会执行向量检索、重排序、并生成带引用编号的答案。

核心要求：
1. 只能使用知识库返回的来源编号进行引用。
2. 优先直接回答，再说明依据。
3. 如果信息不足，请明确说明信息不足。
4. 你可以连续多次调用检索工具来补充信息。
5. 对用户保持专业、严谨的法律咨询态度。
6. 使用中文回答。
"""


def create_lawyer_agent(
    checkpointer: AsyncPostgresSaver,
):
    """Create and return a compiled Deep Agent for legal Q&A."""
    from deepagents import create_deep_agent

    settings = get_settings()

    model = ChatOpenAI(
        model=settings.answer_generation_model or "gpt-4o",
        base_url=settings.answer_generation_base_url,
        api_key=settings.answer_generation_api_key or "sk-placeholder",
        temperature=0,
        streaming=True,
    )

    try:
        agent = create_deep_agent(
            model=model,
            tools=[legal_knowledge_search],
            system_prompt=LEGAL_SYSTEM_PROMPT,
            checkpointer=checkpointer,
        )
    except TypeError as exc:
        # create_deep_agent may not accept all kwargs — try minimal call
        logger.warning(
            "create_deep_agent() rejected kwargs, falling back: %s", exc,
        )
        agent = create_deep_agent(
            model=model,
            tools=[legal_knowledge_search],
            system_prompt=LEGAL_SYSTEM_PROMPT,
        )

    logger.info(
        "Lawyer agent created",
        extra={
            "event": "agent_created",
            "model": settings.answer_generation_model,
        },
    )
    return agent
