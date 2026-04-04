from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.services.vectors.service import DocumentVectorService


class _FakeChunkStore:
    def get_bm25_stats(self):
        return {"vocab": {}, "doc_freq": {}, "total_docs": 1, "avg_doc_len": 1.0}


def _create_service(tmp_path) -> tuple[DocumentVectorService, Session]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'search-rerank.db'}",
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
    service = DocumentVectorService(db=db, settings=Settings(_env_file=None))
    service.chunk_store = _FakeChunkStore()
    return service, db


def test_execute_search_attempt_applies_rerank_before_returning_results(
    tmp_path,
    monkeypatch,
) -> None:
    service, db = _create_service(tmp_path)

    monkeypatch.setattr(
        service.dense_embedding_service,
        "embed_text",
        lambda query: [0.1, 0.2],
    )
    monkeypatch.setattr(
        service.sparse_embedding_service,
        "sparse_embed_text",
        lambda query, corpus_stats: {1: 0.3},
    )
    monkeypatch.setattr(
        service.milvus,
        "search",
        lambda dense_embedding, sparse_embedding, top_k, document_ids: (
            [
                {
                    "chunk_id": "chunk-a",
                    "document_id": "doc-1",
                    "root_chunk_id": "root-1",
                    "parent_chunk_id": "parent-1",
                    "chunk_level": 3,
                    "chunk_index": 0,
                    "page_number": 1,
                    "content": "candidate a",
                    "original_filename": "a.pdf",
                    "score": 0.51,
                    "metadata": {},
                },
                {
                    "chunk_id": "chunk-b",
                    "document_id": "doc-2",
                    "root_chunk_id": "root-2",
                    "parent_chunk_id": "parent-2",
                    "chunk_level": 3,
                    "chunk_index": 1,
                    "page_number": 2,
                    "content": "candidate b",
                    "original_filename": "b.pdf",
                    "score": 0.49,
                    "metadata": {},
                },
            ],
            "hybrid",
        ),
    )
    monkeypatch.setattr(
        service.rerank_service,
        "rerank",
        lambda query, docs, top_k: (
            [
                {
                    **docs[1],
                    "score": 0.97,
                    "metadata": {"rerank_score": 0.97, "retrieval_score": 0.49},
                },
                {
                    **docs[0],
                    "score": 0.82,
                    "metadata": {"rerank_score": 0.82, "retrieval_score": 0.51},
                },
            ],
            {
                "rerank_enabled": True,
                "rerank_configured": True,
                "rerank_applied": True,
                "rerank_provider": "api",
                "rerank_model": "rerank-v1",
                "rerank_endpoint": "https://rerank.example/v1/rerank",
                "rerank_error": None,
                "rerank_skipped_reason": None,
                "rerank_candidate_count": 2,
                "rerank_truncated_candidate_count": 2,
                "rerank_top_n": top_k,
            },
        ),
    )

    attempt = service._execute_search_attempt(
        stage="initial",
        search_query="contract breach",
        top_k=2,
        document_ids=[],
    )

    assert [item["chunk_id"] for item in attempt.items] == ["chunk-b", "chunk-a"]
    assert attempt.meta["rerank_applied"] is True
    assert attempt.meta["rerank_provider"] == "api"
    assert attempt.items[0]["metadata"]["rerank_score"] == 0.97

    db.close()
