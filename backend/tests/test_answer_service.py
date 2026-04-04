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
    SessionLocal = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        class_=Session,
        expire_on_commit=False,
    )
    db = SessionLocal()
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
        meta={"retrieval_mode": "multi_stage"},
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

    monkeypatch.setattr(DocumentVectorService, "search", lambda *args, **kwargs: _search_response())
    monkeypatch.setattr(
        DocumentAnswerService,
        "_chat_completion_json",
        lambda self, system_prompt, user_prompt: {
            "answer": (
                "从现有材料看，如主张返还房屋，占有人需要先证明自身对房屋享有合法物权，[1]"
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

    monkeypatch.setattr(DocumentVectorService, "search", lambda *args, **kwargs: _search_response())

    response = service.answer("房子被别人占着怎么要回来", top_k=5)

    assert response.meta["generation_mode"] == "extractive_fallback"
    assert response.meta["answer_generation_skipped_reason"] == "answer_model_not_configured"
    assert response.meta["used_source_count"] == 2
    assert len(response.citations) == 2
    assert "最相关依据摘要" in response.answer
    assert "[1]" in response.answer

    db.close()
