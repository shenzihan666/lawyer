from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.schemas.search import SearchResponse, SearchResultItem
from app.services.answers.service import DocumentAnswerService
from app.services.vectors import DocumentVectorService


def _create_service(tmp_path, **settings_overrides) -> tuple[DocumentAnswerService, Session]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'answer-service.db'}",
        future=True,
    )
    Base.metadata.create_all(engine)
    session_local = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        class_=Session,
        expire_on_commit=False,
    )
    db = session_local()
    settings = Settings(_env_file=None, **settings_overrides)
    return DocumentAnswerService(db=db, settings=settings), db


def _search_response() -> SearchResponse:
    return SearchResponse(
        items=[
            SearchResultItem(
                chunk_id="chunk-1",
                document_id="doc-1",
                root_chunk_id="root-1",
                parent_chunk_id="parent-1",
                chunk_level=3,
                chunk_index=0,
                page_number=12,
                content="占有返还请求权要求原告证明其对涉案房屋享有合法物权。",
                original_filename="案例一.pdf",
                score=0.92,
                metadata={},
            ),
            SearchResultItem(
                chunk_id="chunk-2",
                document_id="doc-2",
                root_chunk_id="root-2",
                parent_chunk_id="parent-2",
                chunk_level=3,
                chunk_index=1,
                page_number=18,
                content="被告如主张合法占有，应对占有依据承担相应举证责任。",
                original_filename="案例二.pdf",
                score=0.89,
                metadata={},
            ),
        ],
        meta={
            "retrieval_mode": "multi_stage",
            "final_result_count": 2,
            "query_rewrite_enabled": True,
            "rewrite_needed": True,
            "relevance_grade_score": "no",
            "query_rewrite_strategy": "step_back",
            "expanded_queries": ["返还原物请求权的构成要件是什么"],
            "rerank_applied": True,
            "rerank_provider": "api",
            "rerank_candidate_count": 6,
            "auto_merge_applied": True,
            "auto_merge_replaced_chunks": 1,
            "auto_merge_steps": 1,
            "search_attempts": [
                {
                    "stage": "initial",
                    "query": "房子被别人占着怎么要回来",
                    "result_count": 2,
                    "retrieval_mode": "hybrid",
                    "candidate_k": 6,
                    "rerank_applied": True,
                    "auto_merge_applied": False,
                    "auto_merge_replaced_chunks": 0,
                },
                {
                    "stage": "step_back",
                    "query": "返还原物请求权的构成要件是什么",
                    "result_count": 2,
                    "retrieval_mode": "hybrid",
                    "candidate_k": 6,
                    "rerank_applied": True,
                    "auto_merge_applied": True,
                    "auto_merge_replaced_chunks": 1,
                },
            ],
        },
    )


def test_answer_service_generates_grounded_answer_with_citations(
    tmp_path,
    monkeypatch,
) -> None:
    service, db = _create_service(
        tmp_path,
        answer_generation_base_url="https://llm.example/v1",
        answer_generation_model="gpt-answer",
        answer_generation_api_key="secret",
    )

    monkeypatch.setattr(
        DocumentVectorService,
        "search",
        lambda *args, **kwargs: _search_response(),
    )
    monkeypatch.setattr(
        DocumentAnswerService,
        "_chat_completion_json",
        lambda self, system_prompt, user_prompt: {
            "answer": (
                "从现有材料看，如主张返还房屋，占有人需要先证明自身对房屋享有合法物权。[1]"
                "若对方抗辩其占有合法，还需要继续核查其占有依据与举证情况。[2]"
            ),
            "used_source_numbers": [1, 2],
            "grounding_status": "grounded",
            "missing_information": "",
        },
    )

    response = service.answer("房子被别人占着怎么要回来", top_k=5)

    assert response.meta["generation_mode"] == "llm"
    assert response.meta["grounding_status"] == "grounded"
    assert response.meta["used_source_count"] == 2
    assert len(response.citations) == 2
    assert response.citations[0].citation_number == 1
    assert response.citations[0].original_filename == "案例一.pdf"
    assert "[1]" in response.answer
    assert "[2]" in response.answer

    db.close()


def test_answer_service_uses_extractive_fallback_when_model_not_configured(
    tmp_path,
    monkeypatch,
) -> None:
    service, db = _create_service(tmp_path)

    monkeypatch.setattr(
        DocumentVectorService,
        "search",
        lambda *args, **kwargs: _search_response(),
    )

    response = service.answer("房子被别人占着怎么要回来", top_k=5)

    assert response.meta["generation_mode"] == "extractive_fallback"
    assert response.meta["answer_generation_skipped_reason"] == "answer_model_not_configured"
    assert response.meta["used_source_count"] == 2
    assert len(response.citations) == 2
    assert "最相关依据摘要" in response.answer
    assert "[1]" in response.answer

    db.close()


def test_answer_service_stream_emits_steps_content_and_result(
    tmp_path,
    monkeypatch,
) -> None:
    service, db = _create_service(
        tmp_path,
        answer_generation_base_url="https://llm.example/v1",
        answer_generation_model="gpt-answer",
        answer_generation_api_key="secret",
    )

    def fake_search_stream(*args, **kwargs):
        yield {
            "type": "rag_step",
            "step": {
                "key": "search-start",
                "label": "开始检索证据",
                "detail": "top_k=5",
                "status": "running",
            },
        }
        return _search_response()

    monkeypatch.setattr(
        DocumentVectorService,
        "search_stream",
        fake_search_stream,
    )
    monkeypatch.setattr(
        DocumentAnswerService,
        "_chat_completion_stream_text",
        lambda self, system_prompt, user_prompt: iter(
            ["可以先主张返还原物。[1]", "如对方抗辩合法占有，还要核验其占有依据。[2]"]
        ),
    )

    events = list(service.stream_answer("房子被别人占着怎么要回来", top_k=5))

    assert any(event["type"] == "rag_step" for event in events)
    assert any(event["type"] == "trace" for event in events)

    content = "".join(
        event["content"] for event in events if event["type"] == "content"
    )
    assert "[1]" in content
    assert "[2]" in content

    result_event = next(event for event in events if event["type"] == "result")
    assert result_event["meta"]["generation_mode"] == "llm_stream"
    assert result_event["meta"]["used_source_count"] == 2
    assert len(result_event["citations"]) == 2

    db.close()


def test_answer_service_stream_retries_non_stream_before_extractive_fallback(
    tmp_path,
    monkeypatch,
) -> None:
    service, db = _create_service(
        tmp_path,
        answer_generation_base_url="https://llm.example/v1",
        answer_generation_model="gpt-answer",
        answer_generation_api_key="secret",
    )

    def fake_search_stream(*args, **kwargs):
        yield {
            "type": "rag_step",
            "step": {
                "key": "search-start",
                "label": "开始检索证据",
                "detail": "top_k=5",
                "status": "running",
            },
        }
        return _search_response()

    monkeypatch.setattr(
        DocumentVectorService,
        "search_stream",
        fake_search_stream,
    )
    monkeypatch.setattr(
        DocumentAnswerService,
        "_chat_completion_stream_text",
        lambda self, system_prompt, user_prompt: (_ for _ in ()).throw(
            RuntimeError("stream endpoint unavailable")
        ),
    )
    monkeypatch.setattr(
        DocumentAnswerService,
        "_chat_completion_json",
        lambda self, system_prompt, user_prompt: {
            "answer": "可以先主张返还原物。[1] 如对方抗辩合法占有，还要继续核验其占有依据。[2]",
            "used_source_numbers": [1, 2],
            "grounding_status": "grounded",
            "missing_information": "",
        },
    )

    events = list(service.stream_answer("房子被别人占着怎么要回来", top_k=5))

    assert any(
        event["type"] == "rag_step" and event["step"]["key"] == "answer-retry"
        for event in events
    )
    result_event = next(event for event in events if event["type"] == "result")
    assert result_event["meta"]["generation_mode"] == "llm_retry"
    assert result_event["meta"]["used_source_count"] == 2
    assert len(result_event["citations"]) == 2

    db.close()
