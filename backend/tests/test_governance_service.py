import pytest

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models import SystemAnalyticsEvent, SystemTrajectoryRun
from app.services.governance import ToolGovernanceService


def test_governance_sanitizes_and_audits_tool_execution(client) -> None:
    session = get_session_factory()()
    captured: dict = {}
    try:
        service = ToolGovernanceService(session, get_settings())
        result = service.execute_legal_knowledge_search(
            query="  请总结合同争议点。\n\n",
            top_k=999,
            document_ids=["doc-1", "", "doc-2"],
            trace_id="req-123",
            executor=lambda payload: {
                "answer": "ok",
                "meta": {
                    "query": payload.query,
                    "top_k": payload.top_k,
                    "document_ids": payload.document_ids,
                },
                "citations": [],
                **captured.setdefault(
                    "payload",
                    {
                        "query": payload.query,
                        "top_k": payload.top_k,
                        "document_ids": payload.document_ids,
                    },
                ),
            },
        )

        assert result["answer"] == "ok"
        assert captured["payload"]["query"] == "请总结合同争议点。"
        assert captured["payload"]["top_k"] == 10
        assert captured["payload"]["document_ids"] == ["doc-1", "doc-2"]

        runs = list(
            session.query(SystemTrajectoryRun)
            .filter_by(run_kind="tool_governance")
            .all()
        )
        events = list(session.query(SystemAnalyticsEvent).all())
        assert len(runs) == 1
        assert runs[0].status == "completed"
        assert runs[0].summary_json["effective_top_k"] == 10
        assert any(item.event_name == "tool_execution_completed" for item in events)
    finally:
        session.close()


def test_governance_rejects_empty_queries_and_records_failure(client) -> None:
    session = get_session_factory()()
    try:
        service = ToolGovernanceService(session, get_settings())
        with pytest.raises(ValueError, match="must not be empty"):
            service.execute_legal_knowledge_search(
                query="   ",
                top_k=5,
                document_ids=[],
                trace_id="req-124",
                executor=lambda payload: {"answer": "should not run"},
            )

        runs = list(
            session.query(SystemTrajectoryRun)
            .filter_by(run_kind="tool_governance")
            .all()
        )
        events = list(session.query(SystemAnalyticsEvent).all())
        assert len(runs) == 1
        assert runs[0].status == "failed"
        assert any(item.event_name == "tool_execution_blocked" for item in events)
    finally:
        session.close()
