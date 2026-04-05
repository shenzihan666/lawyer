from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.contract_review import (
    ReviewJobDetailResponse,
    ReviewJobListResponse,
    ReviewJobOperationResponse,
    ReviewTemplateListResponse,
    ReviewTemplateOperationResponse,
)
from app.services.contract_review import ContractReviewService

router = APIRouter(prefix="/contract-review", tags=["contract-review"])


def get_contract_review_service(
    db=Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ContractReviewService:
    return ContractReviewService(db=db, settings=settings)


@router.get("/templates", response_model=ReviewTemplateListResponse)
def list_templates(
    service: ContractReviewService = Depends(get_contract_review_service),
) -> ReviewTemplateListResponse:
    return service.list_templates()


@router.post("/templates/upload", response_model=ReviewTemplateOperationResponse)
def upload_template(
    file: UploadFile = File(...),
    name: str = Form(...),
    category: str = Form("通用合同"),
    contract_type: str = Form("general"),
    description: str | None = Form(None),
    config_profile: str = Form("general"),
    service: ContractReviewService = Depends(get_contract_review_service),
) -> ReviewTemplateOperationResponse:
    return service.upload_template(
        file=file,
        name=name,
        category=category,
        contract_type=contract_type,
        description=description,
        config_profile=config_profile,
    )


@router.delete("/templates/{template_id}", response_model=ReviewTemplateOperationResponse)
def delete_template(
    template_id: str,
    service: ContractReviewService = Depends(get_contract_review_service),
) -> ReviewTemplateOperationResponse:
    return service.delete_template(template_id)


@router.get("/jobs", response_model=ReviewJobListResponse)
def list_jobs(
    service: ContractReviewService = Depends(get_contract_review_service),
) -> ReviewJobListResponse:
    return service.list_jobs()


@router.post("/jobs", response_model=ReviewJobDetailResponse)
def create_job(
    file: UploadFile = File(...),
    template_id: str = Form(...),
    review_name: str | None = Form(None),
    service: ContractReviewService = Depends(get_contract_review_service),
) -> ReviewJobDetailResponse:
    return service.create_job(file=file, template_id=template_id, review_name=review_name)


@router.get("/jobs/{job_id}", response_model=ReviewJobDetailResponse)
def get_job_detail(
    job_id: str,
    service: ContractReviewService = Depends(get_contract_review_service),
) -> ReviewJobDetailResponse:
    return service.get_job_detail(job_id)


@router.delete("/jobs/{job_id}", response_model=ReviewJobOperationResponse)
def delete_job(
    job_id: str,
    service: ContractReviewService = Depends(get_contract_review_service),
) -> ReviewJobOperationResponse:
    return service.delete_job(job_id)


@router.get("/jobs/{job_id}/export.docx")
def export_job(
    job_id: str,
    service: ContractReviewService = Depends(get_contract_review_service),
) -> FileResponse:
    export_path = service.get_export_path(job_id)
    return FileResponse(
        export_path,
        filename=f"{job_id}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
