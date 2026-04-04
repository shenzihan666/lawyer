from app.schemas.answer import AnswerCitation, AnswerResponse
from app.services.answers import DocumentAnswerService


def test_chat_answer_route(client, monkeypatch) -> None:
    def fake_answer(self, query, top_k=None, document_ids=None):
        return AnswerResponse(
            answer="依据现有材料，可以先主张返还原物。[1]",
            citations=[
                AnswerCitation(
                    citation_number=1,
                    chunk_id="chunk-1",
                    document_id="doc-1",
                    root_chunk_id="root-1",
                    parent_chunk_id="parent-1",
                    chunk_level=3,
                    chunk_index=0,
                    page_number=8,
                    original_filename="案例一.pdf",
                    snippet="返还原物请求权可适用于无权占有人。",
                    score=0.91,
                    metadata={},
                )
            ],
            meta={"generation_mode": "llm", "grounding_status": "grounded"},
        )

    monkeypatch.setattr(DocumentAnswerService, "answer", fake_answer)

    response = client.post(
        "/api/v1/chat/answer",
        json={"query": "房子被别人占着怎么要回来", "top_k": 3, "document_ids": ["doc-1"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "依据现有材料，可以先主张返还原物。[1]"
    assert payload["citations"][0]["original_filename"] == "案例一.pdf"
    assert payload["meta"]["generation_mode"] == "llm"
