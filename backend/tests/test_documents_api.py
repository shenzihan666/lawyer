from app.services.loaders import registry
from app.services.loaders.base import LoadResult, LoadedFragment
from app.services.vectors.service import DocumentVectorService
from app.schemas.search import SearchResponse, SearchResultItem


def test_upload_list_vectorize_and_delete(client, monkeypatch) -> None:
    def fake_load_document(_file_path):
        return LoadResult(
            loader_name="PyPDFLoader",
            fragments=[
                LoadedFragment(
                    fragment_index=0,
                    page_number=1,
                    content="First page content",
                    metadata={"page": 0},
                ),
                LoadedFragment(
                    fragment_index=1,
                    page_number=2,
                    content="Second page content",
                    metadata={"page": 1},
                ),
            ],
        )

    monkeypatch.setattr(registry, "load_document", fake_load_document)

    def fake_index_documents(self, document_ids):
        documents = self._fetch_documents_for_test(document_ids)
        for document in documents:
            document.vector_status = "indexed"
        self.db.commit()
        return list(document_ids)

    def fake_delete_document_vectors(self, document_ids):
        return None

    def fetch_documents_for_test(self, document_ids):
        from sqlalchemy import select

        from app.models import DocumentAsset

        return list(
            self.db.scalars(
                select(DocumentAsset).where(DocumentAsset.id.in_(document_ids))
            )
        )

    monkeypatch.setattr(
        DocumentVectorService,
        "_fetch_documents_for_test",
        fetch_documents_for_test,
        raising=False,
    )
    monkeypatch.setattr(DocumentVectorService, "index_documents", fake_index_documents)
    monkeypatch.setattr(
        DocumentVectorService,
        "delete_document_vectors",
        fake_delete_document_vectors,
    )

    upload_response = client.post(
        "/api/v1/documents/upload",
        files=[("files", ("demo.pdf", b"fake pdf bytes", "application/pdf"))],
    )

    assert upload_response.status_code == 200
    upload_payload = upload_response.json()
    assert upload_payload["summary"]["total"] == 1
    assert upload_payload["items"][0]["loader_name"] == "PyPDFLoader"
    assert upload_payload["items"][0]["page_count"] == 2
    assert upload_payload["items"][0]["raw_doc_count"] == 2

    document_id = upload_payload["items"][0]["id"]

    list_response = client.get("/api/v1/documents")
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["id"] == document_id

    vectorize_response = client.post(
        "/api/v1/documents/vectorize",
        json={"document_ids": [document_id]},
    )
    assert vectorize_response.status_code == 200
    assert vectorize_response.json()["items"][0]["vector_status"] == "indexed"
    assert vectorize_response.json()["summary"]["vector_indexed"] == 1

    delete_response = client.post(
        "/api/v1/documents/delete",
        json={"document_ids": [document_id]},
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["summary"]["total"] == 0
    assert delete_response.json()["summary"]["deleted"] == 1


def test_search_route(client, monkeypatch) -> None:
    def fake_search(self, query, top_k=None, document_ids=None):
        return SearchResponse(
            items=[
                SearchResultItem(
                    chunk_id="doc-1:l3:0",
                    document_id="doc-1",
                    root_chunk_id="doc-1:l1:0",
                    parent_chunk_id="doc-1:l2:0",
                    chunk_level=3,
                    chunk_index=0,
                    page_number=1,
                    content=f"match for {query}",
                    original_filename="demo.pdf",
                    score=0.88,
                    metadata={"top_k": top_k, "document_ids": document_ids or []},
                )
            ],
            meta={"retrieval_mode": "hybrid"},
        )

    monkeypatch.setattr(DocumentVectorService, "search", fake_search)

    response = client.post(
        "/api/v1/search",
        json={"query": "合同违约", "top_k": 3, "document_ids": ["doc-1"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["content"] == "match for 合同违约"
    assert payload["meta"]["retrieval_mode"] == "hybrid"


def test_upload_rejects_legacy_doc_file(client) -> None:
    response = client.post(
        "/api/v1/documents/upload",
        files=[("files", ("legacy.doc", b"fake doc bytes", "application/msword"))],
    )

    assert response.status_code == 400
    assert ".docx" in response.json()["detail"]
