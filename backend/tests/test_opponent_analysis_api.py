import json
import time
from uuid import uuid4

from app.db.session import get_session_factory
from app.models import (
    DocumentAsset,
    DocumentIngestionStatus,
    DocumentVectorStatus,
)
from app.schemas.search import SearchResponse, SearchResultItem
from app.services.opponent_analysis.llm import OpponentAnalysisLLMClient
from app.services.vectors import DocumentVectorService


def _create_document_asset(
    *,
    original_filename: str,
    vector_status: str,
) -> str:
    session = get_session_factory()()
    try:
        document_id = str(uuid4())
        session.add(
            DocumentAsset(
                id=document_id,
                original_filename=original_filename,
                stored_filename=original_filename,
                storage_path=f"tests/{document_id}/{original_filename}",
                file_extension="pdf",
                mime_type="application/pdf",
                loader_name="PyPDFLoader",
                sha256=f"sha256-{document_id}",
                file_size=1024,
                page_count=2,
                raw_doc_count=2,
                preview_excerpt="preview excerpt",
                ingestion_status=DocumentIngestionStatus.ready.value,
                vector_status=vector_status,
                trace_metadata={},
            )
        )
        session.commit()
        return document_id
    finally:
        session.close()


def _build_search_response(
    *document_ids: str,
    query: str,
) -> SearchResponse:
    items = []
    for index, document_id in enumerate(document_ids, start=1):
        items.append(
            SearchResultItem(
                chunk_id=f"{document_id}:l3:{index}",
                document_id=document_id,
                root_chunk_id=f"{document_id}:l1:0",
                parent_chunk_id=f"{document_id}:l2:0",
                chunk_level=3,
                chunk_index=index,
                page_number=index,
                content=f"Evidence {index} for {query}",
                original_filename=f"scope-{index}.pdf",
                score=0.9 - index * 0.05,
                metadata={"source": "opponent-analysis-test"},
            )
        )
    return SearchResponse(items=items, meta={"retrieval_mode": "hybrid"})


def _parse_sse_payloads(body: str) -> list[dict]:
    payloads: list[dict] = []
    for block in body.split("\n\n"):
        lines = [line for line in block.splitlines() if line.startswith("data:")]
        if not lines:
            continue
        data = "\n".join(line[5:].strip() for line in lines)
        if data == "[DONE]":
            continue
        payloads.append(json.loads(data))
    return payloads


def _wait_for_terminal_run(
    client,
    run_id: str,
    *,
    timeout_seconds: float = 5.0,
) -> dict:
    deadline = time.time() + timeout_seconds
    last_payload: dict | None = None
    while time.time() < deadline:
        response = client.get(f"/api/v1/opponent-analyses/{run_id}")
        assert response.status_code == 200
        last_payload = response.json()
        if last_payload["run"]["status"] in {"completed", "failed"}:
            return last_payload
        time.sleep(0.05)

    raise AssertionError(
        f"Run {run_id} did not finish in time. "
        f"Last status: {last_payload['run']['status'] if last_payload else 'unknown'}"
    )


def test_opponent_analysis_create_list_detail_stream_and_delete(
    client,
    monkeypatch,
) -> None:
    scoped_document_id = _create_document_asset(
        original_filename="scoped.pdf",
        vector_status=DocumentVectorStatus.indexed.value,
    )
    _create_document_asset(
        original_filename="other.pdf",
        vector_status=DocumentVectorStatus.indexed.value,
    )

    def fake_search_chunks(self, query, top_k=None, document_ids=None):
        assert document_ids == [scoped_document_id]
        return _build_search_response(scoped_document_id, query=query)

    monkeypatch.setattr(DocumentVectorService, "search_chunks", fake_search_chunks)
    monkeypatch.setattr(OpponentAnalysisLLMClient, "is_configured", lambda self: False)

    create_response = client.post(
        "/api/v1/opponent-analyses",
        json={
            "case_facts": "合同履行时间、付款节点以及交付验收是否一致存在争议。",
            "top_k": 4,
            "document_ids": [scoped_document_id],
        },
    )

    assert create_response.status_code == 201
    payload = _wait_for_terminal_run(client, create_response.json()["run"]["id"])
    assert payload["run"]["status"] == "completed"
    assert payload["run"]["scope_document_ids"] == [scoped_document_id]
    assert payload["summary"]["risk_level"] in {"low", "medium", "high"}
    assert payload["summary"]["evidence_index"]
    assert {item["document_id"] for item in payload["summary"]["evidence_index"]} == {
        scoped_document_id
    }

    events = payload["events"]
    assert len(events) == 10
    assert [event["seq"] for event in events] == list(range(1, 11))

    unique_phases = list(dict.fromkeys(event["phase"] for event in events))
    assert unique_phases == [
        "context_brief",
        "party_projection",
        "counsel_projection",
        "bench_review",
        "strategy_response",
        "revision",
        "finalize",
    ]

    party_event = next(
        event for event in events if event["phase"] == "party_projection"
    )
    counsel_event = next(
        event for event in events if event["phase"] == "counsel_projection"
    )
    bench_event = next(event for event in events if event["phase"] == "bench_review")
    revision_events = [event for event in events if event["phase"] == "revision"]

    assert party_event["from_agent"] == "opponent_party"
    assert party_event["to_agent"] == "opponent_counsel"
    assert party_event["event_type"] == "agent_message"

    assert counsel_event["from_agent"] == "opponent_counsel"
    assert counsel_event["to_agent"] == "bench_observer"

    assert bench_event["from_agent"] == "bench_observer"
    assert "our_strategy_advisor" in (bench_event["to_agent"] or "")

    assert [
        (item["from_agent"], item["to_agent"], item["event_type"])
        for item in revision_events
    ] == [
        ("opponent_party", "opponent_counsel", "agent_revision"),
        ("opponent_counsel", "our_strategy_advisor", "agent_revision"),
    ]

    list_response = client.get("/api/v1/opponent-analyses")
    assert list_response.status_code == 200
    assert len(list_response.json()["items"]) == 1
    assert list_response.json()["items"][0]["id"] == payload["run"]["id"]

    detail_response = client.get(f"/api/v1/opponent-analyses/{payload['run']['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["summary"]["opponent_position"]["summary"]

    stream_response = client.get(
        f"/api/v1/opponent-analyses/{payload['run']['id']}/stream",
        params={"after_seq": 0},
    )
    assert stream_response.status_code == 200
    stream_payloads = _parse_sse_payloads(stream_response.text)
    assert stream_payloads[0]["type"] == "snapshot"
    assert stream_payloads[-1]["type"] == "done"
    streamed_events = [
        item["event"] for item in stream_payloads if item["type"] == "event"
    ]
    assert [event["seq"] for event in streamed_events] == list(range(1, 11))

    resumed_stream_response = client.get(
        f"/api/v1/opponent-analyses/{payload['run']['id']}/stream",
        params={"after_seq": 8},
    )
    resumed_payloads = _parse_sse_payloads(resumed_stream_response.text)
    resumed_events = [
        item["event"] for item in resumed_payloads if item["type"] == "event"
    ]
    assert [event["seq"] for event in resumed_events] == [9, 10]
    assert resumed_payloads[-1]["run"]["status"] == "completed"

    delete_response = client.delete(f"/api/v1/opponent-analyses/{payload['run']['id']}")
    assert delete_response.status_code == 204
    assert client.get("/api/v1/opponent-analyses").json()["items"] == []


def test_opponent_analysis_defaults_to_all_indexed_documents_when_scope_missing(
    client,
    monkeypatch,
) -> None:
    first_document_id = _create_document_asset(
        original_filename="all-a.pdf",
        vector_status=DocumentVectorStatus.indexed.value,
    )
    second_document_id = _create_document_asset(
        original_filename="all-b.pdf",
        vector_status=DocumentVectorStatus.indexed.value,
    )

    def fake_search_chunks(self, query, top_k=None, document_ids=None):
        assert document_ids == []
        return _build_search_response(
            first_document_id, second_document_id, query=query
        )

    monkeypatch.setattr(DocumentVectorService, "search_chunks", fake_search_chunks)
    monkeypatch.setattr(OpponentAnalysisLLMClient, "is_configured", lambda self: False)

    create_response = client.post(
        "/api/v1/opponent-analyses",
        json={
            "case_facts": "对方可能围绕付款安排与实际履行过程提出不同解释。",
            "top_k": 3,
        },
    )

    assert create_response.status_code == 201
    payload = _wait_for_terminal_run(client, create_response.json()["run"]["id"])
    assert payload["run"]["scope_document_ids"] == []
    assert {item["document_id"] for item in payload["summary"]["evidence_index"]} == {
        first_document_id,
        second_document_id,
    }


def test_opponent_analysis_validates_empty_case_facts_and_document_scope(
    client,
) -> None:
    not_indexed_document_id = _create_document_asset(
        original_filename="pending.pdf",
        vector_status=DocumentVectorStatus.not_requested.value,
    )

    whitespace_response = client.post(
        "/api/v1/opponent-analyses",
        json={"case_facts": "   ", "top_k": 5},
    )
    assert whitespace_response.status_code == 400
    assert whitespace_response.json()["detail"] == "case_facts must not be empty."

    missing_scope_response = client.post(
        "/api/v1/opponent-analyses",
        json={
            "case_facts": "案情摘要",
            "top_k": 5,
            "document_ids": ["missing-document-id"],
        },
    )
    assert missing_scope_response.status_code == 400
    assert "Unknown document ids" in missing_scope_response.json()["detail"]

    unindexed_scope_response = client.post(
        "/api/v1/opponent-analyses",
        json={
            "case_facts": "案情摘要",
            "top_k": 5,
            "document_ids": [not_indexed_document_id],
        },
    )
    assert unindexed_scope_response.status_code == 400
    assert "must be indexed" in unindexed_scope_response.json()["detail"]


def test_opponent_analysis_failure_writes_error_event_and_failed_status(
    client,
    monkeypatch,
) -> None:
    scoped_document_id = _create_document_asset(
        original_filename="broken.pdf",
        vector_status=DocumentVectorStatus.indexed.value,
    )

    def fake_search_chunks(self, query, top_k=None, document_ids=None):
        raise RuntimeError("vector lookup exploded")

    monkeypatch.setattr(DocumentVectorService, "search_chunks", fake_search_chunks)
    monkeypatch.setattr(OpponentAnalysisLLMClient, "is_configured", lambda self: False)

    create_response = client.post(
        "/api/v1/opponent-analyses",
        json={
            "case_facts": "对方可能会攻击交付与验收证据的对应关系。",
            "top_k": 5,
            "document_ids": [scoped_document_id],
        },
    )

    assert create_response.status_code == 201
    payload = _wait_for_terminal_run(client, create_response.json()["run"]["id"])
    assert payload["run"]["status"] == "failed"
    assert "vector lookup exploded" in (payload["run"]["failure_reason"] or "")
    assert payload["events"][-1]["event_type"] == "error"
    assert payload["events"][-1]["phase"] == "finalize"
    assert payload["events"][-1]["status"] == "error"

    stream_response = client.get(
        f"/api/v1/opponent-analyses/{payload['run']['id']}/stream",
        params={"after_seq": 0},
    )
    assert stream_response.status_code == 200
    stream_payloads = _parse_sse_payloads(stream_response.text)
    assert stream_payloads[-1]["type"] == "done"
    assert stream_payloads[-1]["run"]["status"] == "failed"
