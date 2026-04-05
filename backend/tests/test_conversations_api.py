class _FakeCheckpointer:
    async def aget(self, config):
        assert config == {"configurable": {"thread_id": "thread-1"}}
        return {
            "channel_values": {
                "messages": [
                    {"role": "user", "content": "房屋被占有时怎么办？"},
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{"name": "legal_knowledge_search"}],
                    },
                    {
                        "role": "tool",
                        "name": "legal_knowledge_search",
                        "content": (
                            '{"answer":"可以先主张返还原物。[1]",'
                            '"citations":[{"citation_number":1,"chunk_id":"chunk-1",'
                            '"document_id":"doc-1","root_chunk_id":"root-1",'
                            '"parent_chunk_id":"parent-1","chunk_level":3,'
                            '"chunk_index":0,"page_number":8,'
                            '"original_filename":"案例一.pdf",'
                            '"snippet":"返还原物请求权可适用于无权占有人。",'
                            '"score":0.91,"metadata":{}}],'
                            '"meta":{"generation_mode":"llm","grounding_status":"grounded"}}'
                        ),
                    },
                ]
            }
        }


def test_conversation_history_includes_tool_result_as_assistant(
    client, monkeypatch
) -> None:
    from app.services.agent import checkpoint as checkpoint_module

    async def fake_get_checkpointer():
        return _FakeCheckpointer()

    monkeypatch.setattr(
        checkpoint_module,
        "get_checkpointer",
        fake_get_checkpointer,
    )

    response = client.get("/api/v1/conversations/thread-1/messages")

    assert response.status_code == 200
    payload = response.json()
    assert [item["role"] for item in payload["messages"]] == ["user", "assistant"]
    assert payload["messages"][1]["content"] == "可以先主张返还原物。[1]"
    assert payload["messages"][1]["citations"][0]["original_filename"] == "案例一.pdf"
    assert payload["messages"][1]["meta"]["grounding_status"] == "grounded"


def test_conversation_history_normalizes_langchain_message_roles(
    client, monkeypatch
) -> None:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    from app.services.agent import checkpoint as checkpoint_module

    class _LangChainCheckpointer:
        async def aget(self, config):
            assert config["configurable"]["thread_id"] == "thread-1"
            return {
                "channel_values": {
                    "messages": [
                        HumanMessage(content="劳动合同解除依据是什么？"),
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "legal_knowledge_search",
                                    "args": {},
                                    "id": "call-1",
                                    "type": "tool_call",
                                }
                            ],
                        ),
                        ToolMessage(
                            content='{"answer":"请先核对解除依据。","citations":[],"meta":{}}',
                            tool_call_id="call-1",
                        ),
                    ]
                }
            }

    async def fake_get_checkpointer():
        return _LangChainCheckpointer()

    monkeypatch.setattr(
        checkpoint_module,
        "get_checkpointer",
        fake_get_checkpointer,
    )

    response = client.get("/api/v1/conversations/thread-1/messages")

    assert response.status_code == 200
    payload = response.json()
    assert [item["role"] for item in payload["messages"]] == ["user", "assistant"]
    assert payload["messages"][0]["content"] == "劳动合同解除依据是什么？"
    assert payload["messages"][1]["content"] == "请先核对解除依据。"
