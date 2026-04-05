def test_request_scoped_search_tool_uses_request_defaults(monkeypatch) -> None:
    from app.services.agent import factory as factory_module

    captured: dict[str, object] = {}

    class _FakeSearchTool:
        @staticmethod
        def invoke(payload):
            captured["payload"] = payload
            return {"answer": "ok", "citations": [], "meta": {}}

    monkeypatch.setattr(factory_module, "legal_knowledge_search", _FakeSearchTool())

    tool = factory_module._build_legal_search_tool(
        default_top_k=8,
        default_document_ids=["doc-1", "doc-2"],
    )

    result = tool.invoke(
        {
            "query": "合同违约责任如何认定？",
            "top_k": 3,
            "document_ids": ["doc-9"],
        }
    )

    assert result["answer"] == "ok"
    assert captured["payload"] == {
        "query": "合同违约责任如何认定？",
        "top_k": 8,
        "document_ids": ["doc-1", "doc-2"],
    }


def test_request_scoped_search_tool_allows_runtime_document_scope_when_unset(
    monkeypatch,
) -> None:
    from app.services.agent import factory as factory_module

    captured: dict[str, object] = {}

    class _FakeSearchTool:
        @staticmethod
        def invoke(payload):
            captured["payload"] = payload
            return {"answer": "ok", "citations": [], "meta": {}}

    monkeypatch.setattr(factory_module, "legal_knowledge_search", _FakeSearchTool())

    tool = factory_module._build_legal_search_tool(
        default_top_k=5,
        default_document_ids=[],
    )

    tool.invoke(
        {
            "query": "房屋返还原物请求权",
            "document_ids": ["doc-3"],
        }
    )

    assert captured["payload"] == {
        "query": "房屋返还原物请求权",
        "top_k": 5,
        "document_ids": ["doc-3"],
    }
