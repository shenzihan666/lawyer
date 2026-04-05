from app.services.contract_review import service as contract_review_service_module
from app.services.contract_review.clause_parser import parse_clauses
from app.services.contract_review.processor import ContractReviewProcessor
from app.services.loaders import registry
from app.services.loaders.base import LoadResult, LoadedFragment


def test_clause_parser_matches_headings() -> None:
    clauses = parse_clauses(
        [
            LoadedFragment(
                fragment_index=0,
                page_number=1,
                content=(
                    "第一条 合同主体\n甲方为甲公司\n乙方为乙公司\n\n"
                    "第二条 价款与支付\n总价款为100万元，付款期限10日。"
                ),
                metadata={},
            )
        ]
    )

    assert len(clauses) == 2
    assert clauses[0].title.startswith("第一条")
    assert clauses[1].title.startswith("第二条")


def test_template_upload_duplicate_review_and_export(client, monkeypatch) -> None:
    def fake_load_document(_file_path):
        return LoadResult(
            loader_name="WordDocumentLoader",
            fragments=[
                LoadedFragment(
                    fragment_index=0,
                    page_number=1,
                    content=(
                        "第一条 合同主体\n甲方：示例公司\n乙方：测试公司\n"
                        "第二条 付款安排\n甲方有权延期付款，收到回款后支付。\n"
                        "第三条 违约责任\n任一方违约时最高不超过已付款金额。"
                    ),
                    metadata={},
                )
            ],
        )

    monkeypatch.setattr(registry, "load_document", fake_load_document)

    def run_inline(job_id: str) -> None:
        from app.core.config import get_settings
        from app.db.session import get_session_factory

        session = get_session_factory()()
        try:
            ContractReviewProcessor(session, get_settings()).run(job_id)
        finally:
            session.close()

    monkeypatch.setattr(contract_review_service_module, "submit_review_job", run_inline)

    template_upload = client.post(
        "/api/v1/contract-review/templates/upload",
        data={
            "name": "采购合同模板",
            "category": "购销合同",
            "contract_type": "sales",
            "description": "采购合同审查模板",
            "config_profile": "sales",
        },
        files={"file": ("template.docx", b"template-bytes", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    assert template_upload.status_code == 200
    template_id = template_upload.json()["items"][0]["id"]

    duplicate_upload = client.post(
        "/api/v1/contract-review/templates/upload",
        data={
            "name": "采购合同模板-重复",
            "category": "购销合同",
            "contract_type": "sales",
            "description": "重复模板",
            "config_profile": "sales",
        },
        files={"file": ("template.docx", b"template-bytes", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert duplicate_upload.status_code == 200
    assert len(duplicate_upload.json()["items"]) == 1

    review_response = client.post(
        "/api/v1/contract-review/jobs",
        data={"template_id": template_id, "review_name": "采购协议审查"},
        files={"file": ("review.docx", b"review-bytes", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    assert review_response.status_code == 200
    payload = review_response.json()
    assert payload["job"]["status"] == "completed"
    assert payload["clauses"]
    assert payload["findings"]
    assert payload["export"]["available"] is True

    export_response = client.get(
        f"/api/v1/contract-review/jobs/{payload['job']['id']}/export.docx"
    )
    assert export_response.status_code == 200
    assert (
        export_response.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    delete_response = client.delete(
        f"/api/v1/contract-review/templates/{template_id}"
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["items"] == []

    create_after_delete = client.post(
        "/api/v1/contract-review/jobs",
        data={"template_id": template_id},
        files={"file": ("review.docx", b"review-bytes", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert create_after_delete.status_code == 404


def test_review_export_conflict_before_completion(client, monkeypatch) -> None:
    monkeypatch.setattr(contract_review_service_module, "submit_review_job", lambda _job_id: None)

    template_upload = client.post(
        "/api/v1/contract-review/templates/upload",
        data={
            "name": "通用合同模板",
            "category": "通用合同",
            "contract_type": "general",
            "description": "通用审查模板",
            "config_profile": "general",
        },
        files={"file": ("template.docx", b"template-bytes", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    template_id = template_upload.json()["items"][0]["id"]

    job_response = client.post(
        "/api/v1/contract-review/jobs",
        data={"template_id": template_id, "review_name": "待处理任务"},
        files={"file": ("review.docx", b"review-bytes", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert job_response.status_code == 200
    job_id = job_response.json()["job"]["id"]
    assert job_response.json()["job"]["status"] == "queued"

    export_response = client.get(f"/api/v1/contract-review/jobs/{job_id}/export.docx")
    assert export_response.status_code == 409
