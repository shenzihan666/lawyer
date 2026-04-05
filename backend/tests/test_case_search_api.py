from pathlib import Path

import pytest

from app.core.config import Settings
from app.schemas.search import SearchResponse, SearchResultItem
from app.services.documents.storage import UploadStorage
from app.services.loaders import registry
from app.services.loaders.base import LoadResult, LoadedFragment
from app.services.vectors.service import DocumentVectorService


def _fake_load_result(loader_name: str = "PyPDFLoader") -> LoadResult:
    return LoadResult(
        loader_name=loader_name,
        fragments=[
            LoadedFragment(
                fragment_index=0,
                page_number=1,
                content="This is the first fragment about contract liability.",
                metadata={"page": 1},
            ),
            LoadedFragment(
                fragment_index=1,
                page_number=2,
                content="This is the second fragment about damages and rescission.",
                metadata={"page": 2},
            ),
        ],
    )


def test_case_search_text_mode_aggregates_history_and_delete(client, monkeypatch) -> None:
    monkeypatch.setattr(registry, "load_document", lambda _path: _fake_load_result())

    upload_response = client.post(
        "/api/v1/documents/upload",
        files=[("files", ("case-a.pdf", b"pdf-bytes", "application/pdf"))],
    )
    assert upload_response.status_code == 200
    document_id = upload_response.json()["items"][0]["id"]

    def fake_search_chunks(self, query, top_k=None, document_ids=None):
        return SearchResponse(
            items=[
                SearchResultItem(
                    chunk_id=f"{document_id}:l3:0",
                    document_id=document_id,
                    root_chunk_id=f"{document_id}:l1:0",
                    parent_chunk_id=f"{document_id}:l2:0",
                    chunk_level=3,
                    chunk_index=0,
                    page_number=1,
                    content=f"first hit for {query}",
                    original_filename="case-a.pdf",
                    score=0.91,
                    metadata={"source": "case-search"},
                ),
                SearchResultItem(
                    chunk_id=f"{document_id}:l3:1",
                    document_id=document_id,
                    root_chunk_id=f"{document_id}:l1:0",
                    parent_chunk_id=f"{document_id}:l2:0",
                    chunk_level=3,
                    chunk_index=1,
                    page_number=2,
                    content=f"second hit for {query}",
                    original_filename="case-a.pdf",
                    score=0.82,
                    metadata={"source": "case-search"},
                ),
            ],
            meta={"retrieval_mode": "hybrid"},
        )

    monkeypatch.setattr(DocumentVectorService, "search_chunks", fake_search_chunks)

    create_response = client.post(
        "/api/v1/case-searches",
        data={"query_text": "contract liability dispute", "top_k": "5"},
    )
    assert create_response.status_code == 200
    payload = create_response.json()
    assert payload["item"]["query_type"] == "text"
    assert payload["item"]["result_count"] == 1
    assert len(payload["hits"]) == 1
    assert payload["hits"][0]["matched_chunk_count"] == 2
    assert payload["hits"][0]["matched_pages"] == [1, 2]

    history_response = client.get("/api/v1/case-searches")
    assert history_response.status_code == 200
    assert len(history_response.json()["items"]) == 1

    search_id = payload["item"]["id"]
    detail_response = client.get(f"/api/v1/case-searches/{search_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["item"]["id"] == search_id

    delete_response = client.delete(f"/api/v1/case-searches/{search_id}")
    assert delete_response.status_code == 204
    assert client.get("/api/v1/case-searches").json()["items"] == []


def test_case_search_upload_mode_does_not_create_document_asset(client, monkeypatch) -> None:
    monkeypatch.setattr(
        registry,
        "load_document",
        lambda _path: _fake_load_result(loader_name="Docx2txtLoader"),
    )
    monkeypatch.setattr(
        DocumentVectorService,
        "search_chunks",
        lambda self, query, top_k=None, document_ids=None: SearchResponse(
            items=[],
            meta={"retrieval_mode": "hybrid"},
        ),
    )

    response = client.post(
        "/api/v1/case-searches",
        data={"top_k": "3"},
        files=[("file", ("query.docx", b"docx-bytes", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["item"]["query_type"] == "upload"
    assert payload["item"]["query_asset"]["original_filename"] == "query.docx"
    assert payload["hits"] == []

    documents_response = client.get("/api/v1/documents")
    assert documents_response.status_code == 200
    assert documents_response.json()["items"] == []


def test_document_preview_and_file_route_for_pdf(client, monkeypatch) -> None:
    monkeypatch.setattr(registry, "load_document", lambda _path: _fake_load_result())

    upload_response = client.post(
        "/api/v1/documents/upload",
        files=[("files", ("preview.pdf", b"pdf-preview-bytes", "application/pdf"))],
    )
    assert upload_response.status_code == 200
    document_id = upload_response.json()["items"][0]["id"]

    preview_response = client.get(f"/api/v1/documents/{document_id}/preview")
    assert preview_response.status_code == 200
    preview_payload = preview_response.json()
    assert preview_payload["preview_status"] == "ready"
    assert len(preview_payload["fragments"]) == 2
    assert preview_payload["preview_url"]

    file_response = client.get(
        f"/api/v1/documents/{document_id}/file",
        params={"disposition": "inline"},
    )
    assert file_response.status_code == 200
    assert file_response.headers["content-type"].startswith("application/pdf")


def test_document_preview_handles_office_conversion_failure(client, monkeypatch) -> None:
    monkeypatch.setattr(
        registry,
        "load_document",
        lambda _path: _fake_load_result(loader_name="Docx2txtLoader"),
    )

    from app.services.case_search.preview import DocumentPreviewService

    def fake_convert(self, source_path: Path, target_path: Path):
        raise RuntimeError("converter unavailable")

    monkeypatch.setattr(DocumentPreviewService, "_convert_office_to_pdf", fake_convert)

    upload_response = client.post(
        "/api/v1/documents/upload",
        files=[("files", ("preview.docx", b"docx-preview-bytes", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))],
    )
    assert upload_response.status_code == 200
    document_id = upload_response.json()["items"][0]["id"]

    preview_response = client.get(f"/api/v1/documents/{document_id}/preview")
    assert preview_response.status_code == 200
    preview_payload = preview_response.json()
    assert preview_payload["preview_status"] == "failed"
    assert preview_payload["preview_url"] is None


def test_upload_storage_rejects_path_escape(tmp_path) -> None:
    settings = Settings(_env_file=None, upload_root_path=str(tmp_path / "uploads"))
    storage = UploadStorage(settings)

    with pytest.raises(ValueError):
        storage.resolve_relative_path("../../outside.txt")
