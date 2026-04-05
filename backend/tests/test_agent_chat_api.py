from app.models.conversation import ConversationMeta


QUERY = "How can I recover possession of a house?"
AI_TITLE = "Recover possession dispute"


class _FakeAgent:
    async def astream_events(self, input_messages, config, version):
        assert input_messages == {
            "messages": [{"role": "user", "content": QUERY}],
        }
        assert config["configurable"]["thread_id"]
        assert version == "v2"
        if False:
            yield None


def test_first_message_creates_conversation_and_schedules_ai_title(
    client, monkeypatch
) -> None:
    from app.api.routes import agent_chat as agent_chat_module
    from app.db.session import get_session_factory
    from app.services.agent import checkpoint as checkpoint_module
    from app.services.agent import factory as factory_module

    async def fake_get_checkpointer():
        return object()

    def fake_schedule_title_generation(thread_id: str, query: str) -> None:
        assert query == QUERY
        session = get_session_factory()()
        try:
            meta = session.query(ConversationMeta).filter_by(thread_id=thread_id).first()
            assert meta is not None
            meta.title = AI_TITLE
            session.commit()
        finally:
            session.close()

    monkeypatch.setattr(checkpoint_module, "get_checkpointer", fake_get_checkpointer)
    monkeypatch.setattr(
        factory_module,
        "create_lawyer_agent",
        lambda checkpointer: _FakeAgent(),
    )
    monkeypatch.setattr(
        agent_chat_module,
        "_schedule_title_generation",
        fake_schedule_title_generation,
    )

    with client.stream(
        "POST",
        "/api/v1/agent/stream",
        json={"query": QUERY, "top_k": 5, "document_ids": []},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "data: [DONE]" in body
    thread_id = response.headers["x-thread-id"]

    session = get_session_factory()()
    try:
        meta = session.query(ConversationMeta).filter_by(thread_id=thread_id).first()
        assert meta is not None
        assert meta.title == AI_TITLE
        assert meta.last_message_preview == QUERY
    finally:
        session.close()


def test_existing_placeholder_conversation_schedules_ai_title_on_first_message(
    client, monkeypatch
) -> None:
    from app.api.routes import agent_chat as agent_chat_module
    from app.db.session import get_session_factory
    from app.services.agent import checkpoint as checkpoint_module
    from app.services.agent import factory as factory_module

    async def fake_get_checkpointer():
        return object()

    scheduled: list[tuple[str, str]] = []

    def fake_schedule_title_generation(thread_id: str, query: str) -> None:
        scheduled.append((thread_id, query))

    session = get_session_factory()()
    try:
        meta = ConversationMeta(
            thread_id="thread-existing",
            title="新对话",
            message_count=0,
            last_message_preview=None,
        )
        session.add(meta)
        session.commit()
    finally:
        session.close()

    monkeypatch.setattr(checkpoint_module, "get_checkpointer", fake_get_checkpointer)
    monkeypatch.setattr(
        factory_module,
        "create_lawyer_agent",
        lambda checkpointer: _FakeAgent(),
    )
    monkeypatch.setattr(
        agent_chat_module,
        "_schedule_title_generation",
        fake_schedule_title_generation,
    )

    with client.stream(
        "POST",
        "/api/v1/agent/stream",
        json={"query": QUERY, "thread_id": "thread-existing", "top_k": 5, "document_ids": []},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "data: [DONE]" in body
    assert scheduled == [("thread-existing", QUERY)]


def test_translate_event_emits_result_for_dict_tool_output() -> None:
    from app.api.routes.agent_chat import _translate_event

    event = {
        "event": "on_tool_end",
        "name": "legal_knowledge_search",
        "data": {
            "output": {
                "answer": "You can request possession.[1]",
                "citations": [{"citation_number": 1, "chunk_id": "chunk-1"}],
                "meta": {"generation_mode": "llm"},
            }
        },
    }

    translated = _translate_event(event)

    assert translated is not None
    assert translated["type"] == "result"
    assert translated["citations"][0]["chunk_id"] == "chunk-1"


def test_translate_event_emits_result_for_json_string_tool_output() -> None:
    from app.api.routes.agent_chat import _translate_event

    event = {
        "event": "on_tool_end",
        "name": "legal_knowledge_search",
        "data": {
            "output": (
                '{"answer":"You can request possession.[1]",'
                '"citations":[{"citation_number":1,"chunk_id":"chunk-1"}],'
                '"meta":{"generation_mode":"llm"}}'
            )
        },
    }

    translated = _translate_event(event)

    assert translated is not None
    assert translated["type"] == "result"
    assert translated["citations"][0]["chunk_id"] == "chunk-1"
