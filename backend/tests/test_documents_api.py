from app.services.loaders import registry
from app.services.loaders.base import LoadResult, LoadedFragment


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
    assert vectorize_response.json()["items"][0]["vector_status"] == "queued"

    delete_response = client.post(
        "/api/v1/documents/delete",
        json={"document_ids": [document_id]},
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["summary"]["total"] == 0
    assert delete_response.json()["summary"]["deleted"] == 1
