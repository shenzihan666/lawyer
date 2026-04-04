from app.core.config import Settings
from app.services.vectors.rerank import DocumentRerankService


def _candidate_docs() -> list[dict]:
    return [
        {
            "chunk_id": "chunk-1",
            "document_id": "doc-1",
            "root_chunk_id": "root-1",
            "parent_chunk_id": "parent-1",
            "chunk_level": 3,
            "chunk_index": 0,
            "page_number": 2,
            "content": "合同成立后，一方迟延履行时应区分违约责任和抗辩事由。",
            "original_filename": "a.pdf",
            "score": 0.51,
            "metadata": {},
        },
        {
            "chunk_id": "chunk-2",
            "document_id": "doc-2",
            "root_chunk_id": "root-2",
            "parent_chunk_id": "parent-2",
            "chunk_level": 3,
            "chunk_index": 1,
            "page_number": 4,
            "content": "违约责任通常包括继续履行、赔偿损失、违约金等承担方式。",
            "original_filename": "b.pdf",
            "score": 0.49,
            "metadata": {},
        },
        {
            "chunk_id": "chunk-3",
            "document_id": "doc-3",
            "root_chunk_id": "root-3",
            "parent_chunk_id": "parent-3",
            "chunk_level": 3,
            "chunk_index": 2,
            "page_number": 5,
            "content": "该片段与合同违约关系较弱，更偏向一般民事程序问题。",
            "original_filename": "c.pdf",
            "score": 0.47,
            "metadata": {},
        },
    ]


def test_rerank_service_uses_dedicated_api_when_configured(monkeypatch) -> None:
    service = DocumentRerankService(
        Settings(
            _env_file=None,
            rerank_base_url="https://rerank.example",
            rerank_model="rerank-v1",
            rerank_api_key="secret",
        )
    )

    monkeypatch.setattr(
        DocumentRerankService,
        "_post_json",
        staticmethod(
            lambda url, payload, api_key, timeout_seconds: {
                "results": [
                    {"index": 1, "relevance_score": 0.97},
                    {"index": 0, "relevance_score": 0.83},
                ]
            }
        ),
    )

    reranked, meta = service.rerank(
        query="合同违约责任怎么认定",
        docs=_candidate_docs(),
        top_k=2,
    )

    assert [item["chunk_id"] for item in reranked] == ["chunk-2", "chunk-1"]
    assert meta["rerank_applied"] is True
    assert meta["rerank_provider"] == "api"
    assert reranked[0]["metadata"]["rerank_score"] == 0.97
    assert reranked[0]["metadata"]["retrieval_score"] == 0.49


def test_rerank_service_falls_back_to_llm_when_api_not_configured(
    monkeypatch,
) -> None:
    service = DocumentRerankService(
        Settings(
            _env_file=None,
            answer_generation_base_url="https://llm.example/v1",
            answer_generation_model="gpt-answer",
            answer_generation_api_key="secret",
        )
    )

    monkeypatch.setattr(
        DocumentRerankService,
        "_chat_completion_json",
        lambda self, system_prompt, user_prompt: {"ranking": [2, 1, 3]},
    )

    reranked, meta = service.rerank(
        query="合同违约责任怎么认定",
        docs=_candidate_docs(),
        top_k=2,
    )

    assert [item["chunk_id"] for item in reranked] == ["chunk-2", "chunk-1"]
    assert meta["rerank_applied"] is True
    assert meta["rerank_provider"] == "llm"
    assert reranked[0]["metadata"]["rerank_provider"] == "llm"
