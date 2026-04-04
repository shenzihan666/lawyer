import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.services.vectors.query_rewrite import RetrievalGrade, RewritePlan
from app.services.vectors.service import DocumentVectorService, SearchAttempt


class _FakeChunkStore:
    def __init__(self) -> None:
        self._cache: dict[str, dict] = {}

    def get_cached_search(self, payload: dict):
        return self._cache.get(json.dumps(payload, sort_keys=True))

    def set_cached_search(self, payload: dict, value: dict) -> None:
        self._cache[json.dumps(payload, sort_keys=True)] = value


class _FakeQueryRewriteService:
    def __init__(
        self,
        *,
        configured: bool,
        enabled: bool,
        grade: RetrievalGrade,
        plan: RewritePlan | None = None,
    ) -> None:
        self._configured = configured
        self._enabled = enabled
        self._grade = grade
        self._plan = plan
        self.plan_calls = 0

    def is_configured(self) -> bool:
        return self._configured

    def is_enabled(self) -> bool:
        return self._enabled

    def grade_retrieval(self, query: str, docs):
        return self._grade

    def plan_rewrite(self, query: str, docs):
        self.plan_calls += 1
        if self._plan is None:
            raise AssertionError("plan_rewrite should not be called in this test")
        return self._plan


def _create_service(tmp_path) -> tuple[DocumentVectorService, Session]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'search-rewrite.db'}",
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


def test_search_runs_expanded_retrieval_when_rewrite_is_needed(
    tmp_path,
    monkeypatch,
) -> None:
    service, db = _create_service(tmp_path)
    service.query_rewrite_service = _FakeQueryRewriteService(
        configured=True,
        enabled=True,
        grade=RetrievalGrade(
            binary_score="no",
            reason="initial results miss the legal concept",
            rewrite_needed=True,
        ),
        plan=RewritePlan(
            strategy="complex",
            reason="need both abstraction and terminology expansion",
            step_back_question="物权纠纷的上位法律争点是什么？",
            step_back_query="物权纠纷 占有返还请求权 构成要件 举证责任",
            hypothetical_answer=(
                "在物权纠纷中，通常需要围绕占有返还请求权、原物返还、"
                "妨害排除、权利基础、构成要件以及举证责任来判断。"
            ),
        ),
    )

    calls: list[tuple[str, str]] = []
    attempts = {
        ("initial", "这个房子被别人占着 我怎么要回来"): SearchAttempt(
            stage="initial",
            query="这个房子被别人占着 我怎么要回来",
            items=[
                {
                    "chunk_id": "chunk-a",
                    "document_id": "doc-1",
                    "root_chunk_id": "root-1",
                    "parent_chunk_id": "parent-1",
                    "chunk_level": 3,
                    "chunk_index": 0,
                    "page_number": 1,
                    "content": "初检命中的片段 A",
                    "original_filename": "a.pdf",
                    "score": 0.55,
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
                    "content": "初检命中的片段 B",
                    "original_filename": "b.pdf",
                    "score": 0.51,
                    "metadata": {},
                },
            ],
            meta={"retrieval_mode": "hybrid", "candidate_k": 9},
        ),
        ("step_back", "物权纠纷 占有返还请求权 构成要件 举证责任"): SearchAttempt(
            stage="step_back",
            query="物权纠纷 占有返还请求权 构成要件 举证责任",
            items=[
                {
                    "chunk_id": "chunk-b",
                    "document_id": "doc-2",
                    "root_chunk_id": "root-2",
                    "parent_chunk_id": "parent-2",
                    "chunk_level": 3,
                    "chunk_index": 1,
                    "page_number": 2,
                    "content": "step-back 命中的片段 B",
                    "original_filename": "b.pdf",
                    "score": 0.72,
                    "metadata": {},
                },
                {
                    "chunk_id": "chunk-c",
                    "document_id": "doc-3",
                    "root_chunk_id": "root-3",
                    "parent_chunk_id": "parent-3",
                    "chunk_level": 3,
                    "chunk_index": 2,
                    "page_number": 3,
                    "content": "step-back 命中的片段 C",
                    "original_filename": "c.pdf",
                    "score": 0.68,
                    "metadata": {},
                },
            ],
            meta={"retrieval_mode": "hybrid", "candidate_k": 9},
        ),
        (
            "hyde",
            "在物权纠纷中，通常需要围绕占有返还请求权、原物返还、妨害排除、权利基础、构成要件以及举证责任来判断。",
        ): SearchAttempt(
            stage="hyde",
            query=(
                "在物权纠纷中，通常需要围绕占有返还请求权、原物返还、"
                "妨害排除、权利基础、构成要件以及举证责任来判断。"
            ),
            items=[
                {
                    "chunk_id": "chunk-c",
                    "document_id": "doc-3",
                    "root_chunk_id": "root-3",
                    "parent_chunk_id": "parent-3",
                    "chunk_level": 3,
                    "chunk_index": 2,
                    "page_number": 3,
                    "content": "HyDE 命中的片段 C",
                    "original_filename": "c.pdf",
                    "score": 0.81,
                    "metadata": {},
                },
                {
                    "chunk_id": "chunk-a",
                    "document_id": "doc-1",
                    "root_chunk_id": "root-1",
                    "parent_chunk_id": "parent-1",
                    "chunk_level": 3,
                    "chunk_index": 0,
                    "page_number": 1,
                    "content": "HyDE 命中的片段 A",
                    "original_filename": "a.pdf",
                    "score": 0.67,
                    "metadata": {},
                },
            ],
            meta={"retrieval_mode": "hybrid", "candidate_k": 9},
        ),
    }

    def fake_execute_search_attempt(self, stage, search_query, top_k, document_ids):
        calls.append((stage, search_query))
        return attempts[(stage, search_query)]

    monkeypatch.setattr(
        DocumentVectorService,
        "_execute_search_attempt",
        fake_execute_search_attempt,
    )

    response = service.search(
        query="这个房子被别人占着 我怎么要回来",
        top_k=3,
    )

    assert [item.chunk_id for item in response.items] == [
        "chunk-c",
        "chunk-b",
        "chunk-a",
    ]
    assert calls == [
        ("initial", "这个房子被别人占着 我怎么要回来"),
        ("step_back", "物权纠纷 占有返还请求权 构成要件 举证责任"),
        (
            "hyde",
            "在物权纠纷中，通常需要围绕占有返还请求权、原物返还、"
            "妨害排除、权利基础、构成要件以及举证责任来判断。",
        ),
    ]
    assert response.meta["retrieval_mode"] == "multi_stage"
    assert response.meta["query_rewrite_applied"] is True
    assert response.meta["query_rewrite_strategy"] == "complex"
    assert response.meta["relevance_grade_score"] == "no"
    assert response.meta["expanded_queries"] == [
        "物权纠纷 占有返还请求权 构成要件 举证责任",
        (
            "在物权纠纷中，通常需要围绕占有返还请求权、原物返还、"
            "妨害排除、权利基础、构成要件以及举证责任来判断。"
        ),
    ]
    assert response.items[0].metadata["matched_stage_count"] == 2
    assert response.items[0].metadata["matched_stages"] == ["step_back", "hyde"]

    db.close()


def test_search_keeps_initial_results_when_relevance_grade_passes(
    tmp_path,
    monkeypatch,
) -> None:
    service, db = _create_service(tmp_path)
    rewrite_service = _FakeQueryRewriteService(
        configured=True,
        enabled=True,
        grade=RetrievalGrade(
            binary_score="yes",
            reason="initial retrieval is already on topic",
            rewrite_needed=False,
        ),
    )
    service.query_rewrite_service = rewrite_service

    calls: list[tuple[str, str]] = []

    def fake_execute_search_attempt(self, stage, search_query, top_k, document_ids):
        calls.append((stage, search_query))
        return SearchAttempt(
            stage=stage,
            query=search_query,
            items=[
                {
                    "chunk_id": "chunk-a",
                    "document_id": "doc-1",
                    "root_chunk_id": "root-1",
                    "parent_chunk_id": "parent-1",
                    "chunk_level": 3,
                    "chunk_index": 0,
                    "page_number": 1,
                    "content": "初检命中的片段 A",
                    "original_filename": "a.pdf",
                    "score": 0.66,
                    "metadata": {},
                }
            ],
            meta={"retrieval_mode": "hybrid", "candidate_k": 9},
        )

    monkeypatch.setattr(
        DocumentVectorService,
        "_execute_search_attempt",
        fake_execute_search_attempt,
    )

    response = service.search(query="合同违约责任怎么认定", top_k=3)

    assert calls == [("initial", "合同违约责任怎么认定")]
    assert response.meta["retrieval_mode"] == "hybrid"
    assert response.meta["query_rewrite_applied"] is False
    assert response.meta["query_rewrite_skipped_reason"] == "relevance_grade_passed"
    assert rewrite_service.plan_calls == 0

    db.close()
