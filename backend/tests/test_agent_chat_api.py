from app.models.conversation import ConversationMeta


class _FakeAgent:
    async def astream_events(self, input_messages, config, version):
        assert input_messages == {
            "messages": [{"role": "user", "content": "房屋被人占有怎么办"}]
        }
        assert config["configurable"]["thread_id"]
        assert version == "v2"
        if False:
            yield None


def test_first_message_creates_conversation_with_ai_title(client, monkeypatch) -> None:
    from app.api.routes import agent_chat as agent_chat_module
    from app.services.agent import checkpoint as checkpoint_module
    from app.services.agent import factory as factory_module
    from app.db.session import get_session_factory

    async def fake_get_checkpointer():
        return object()

    async def fake_generate_title(query: str) -> str:
        assert query == "房屋被人占有怎么办"
        return "返还原物纠纷"

    monkeypatch.setattr(checkpoint_module, "get_checkpointer", fake_get_checkpointer)
    monkeypatch.setattr(
        factory_module,
        "create_lawyer_agent",
        lambda checkpointer: _FakeAgent(),
    )
    monkeypatch.setattr(agent_chat_module, "_generate_title", fake_generate_title)

    with client.stream(
        "POST",
        "/api/v1/agent/stream",
        json={"query": "房屋被人占有怎么办", "top_k": 5, "document_ids": []},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "data: [DONE]" in body
    thread_id = response.headers["x-thread-id"]

    session = get_session_factory()()
    try:
        meta = session.query(ConversationMeta).filter_by(thread_id=thread_id).first()
        assert meta is not None
        assert meta.title == "返还原物纠纷"
        assert meta.last_message_preview == "房屋被人占有怎么办"
    finally:
        session.close()
