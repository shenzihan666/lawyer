from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.models import CaseSearchQueryAsset, DocumentAsset
from app.schemas.document import DocumentPreviewResponse, PreviewFragmentItem
from app.services.documents.storage import UploadStorage
from app.services.loaders import registry
from app.services.loaders.base import LoadResult


class DocumentPreviewService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.storage = UploadStorage(settings)

    def get_document_preview(self, document_id: str) -> DocumentPreviewResponse:
        document = self.db.scalar(
            select(DocumentAsset)
            .options(selectinload(DocumentAsset.fragments))
            .where(DocumentAsset.id == document_id, DocumentAsset.deleted_at.is_(None))
        )
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        preview_url, preview_status = self._ensure_preview(
            asset_id=document.id,
            source_relative_path=document.storage_path,
            source_extension=document.file_extension,
            existing_preview_path=document.trace_metadata.get("preview_storage_path")
            if isinstance(document.trace_metadata, dict)
            else None,
            preview_namespace="documents",
        )
        if isinstance(document.trace_metadata, dict):
            document.trace_metadata = {
                **document.trace_metadata,
                "preview_storage_path": preview_url["relative_path"] if preview_url else None,
            }
            self.db.commit()

        file_url = f"{self.settings.api_v1_prefix}/documents/{document.id}/file"
        preview_file_url = (
            f"{self.settings.api_v1_prefix}/documents/{document.id}/file?disposition=inline&preview=1"
            if preview_url
            else None
        )
        fragments = [
            PreviewFragmentItem(
                fragment_index=fragment.fragment_index,
                page_number=fragment.page_number,
                content=fragment.content,
                metadata=fragment.fragment_metadata,
            )
            for fragment in document.fragments
        ]
        return DocumentPreviewResponse(
            asset_type="document",
            asset_id=document.id,
            title=document.original_filename,
            original_filename=document.original_filename,
            file_extension=document.file_extension,
            mime_type=document.mime_type,
            preview_excerpt=document.preview_excerpt,
            file_url=file_url,
            preview_url=preview_file_url,
            preview_status=preview_status,
            fragments=fragments,
            meta={
                "page_count": document.page_count,
                "raw_doc_count": document.raw_doc_count,
            },
        )

    def get_case_search_asset_preview(self, asset_id: str) -> DocumentPreviewResponse:
        asset = self.db.scalar(
            select(CaseSearchQueryAsset).where(CaseSearchQueryAsset.id == asset_id)
        )
        if asset is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case search asset not found")

        preview_meta, preview_status = self._ensure_preview(
            asset_id=asset.id,
            source_relative_path=asset.storage_path,
            source_extension=asset.file_extension,
            existing_preview_path=asset.preview_storage_path,
            preview_namespace="case-search-assets",
        )
        asset.preview_storage_path = preview_meta["relative_path"] if preview_meta else asset.preview_storage_path
        asset.preview_status = preview_status
        self.db.commit()

        fragments = self._load_fragments_for_path(asset.storage_path)
        file_url = f"{self.settings.api_v1_prefix}/case-search-assets/{asset.id}/file"
        preview_file_url = (
            f"{self.settings.api_v1_prefix}/case-search-assets/{asset.id}/file?disposition=inline&preview=1"
            if preview_meta
            else None
        )
        return DocumentPreviewResponse(
            asset_type="case_search_asset",
            asset_id=asset.id,
            title=asset.original_filename,
            original_filename=asset.original_filename,
            file_extension=asset.file_extension,
            mime_type=asset.mime_type,
            preview_excerpt=asset.preview_excerpt,
            file_url=file_url,
            preview_url=preview_file_url,
            preview_status=preview_status,
            fragments=fragments,
            meta={"extraction_status": asset.extraction_status},
        )

    def resolve_document_file_path(self, document_id: str, *, preview: bool = False) -> tuple[Path, str | None, str]:
        document = self.db.scalar(
            select(DocumentAsset).where(DocumentAsset.id == document_id, DocumentAsset.deleted_at.is_(None))
        )
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        if preview:
            preview_meta, preview_status = self._ensure_preview(
                asset_id=document.id,
                source_relative_path=document.storage_path,
                source_extension=document.file_extension,
                existing_preview_path=document.trace_metadata.get("preview_storage_path")
                if isinstance(document.trace_metadata, dict)
                else None,
                preview_namespace="documents",
            )
            if preview_meta is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Preview is unavailable: {preview_status}",
                )
            return (
                self.storage.resolve_relative_path(preview_meta["relative_path"]),
                "application/pdf",
                "preview.pdf",
            )

        return (
            self.storage.resolve_relative_path(document.storage_path),
            document.mime_type,
            document.original_filename,
        )

    def resolve_case_search_asset_file_path(
        self,
        asset_id: str,
        *,
        preview: bool = False,
    ) -> tuple[Path, str | None, str]:
        asset = self.db.scalar(select(CaseSearchQueryAsset).where(CaseSearchQueryAsset.id == asset_id))
        if asset is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case search asset not found")

        if preview:
            preview_meta, preview_status = self._ensure_preview(
                asset_id=asset.id,
                source_relative_path=asset.storage_path,
                source_extension=asset.file_extension,
                existing_preview_path=asset.preview_storage_path,
                preview_namespace="case-search-assets",
            )
            asset.preview_storage_path = preview_meta["relative_path"] if preview_meta else asset.preview_storage_path
            asset.preview_status = preview_status
            self.db.commit()
            if preview_meta is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Preview is unavailable: {preview_status}",
                )
            return (
                self.storage.resolve_relative_path(preview_meta["relative_path"]),
                "application/pdf",
                "preview.pdf",
            )

        return (
            self.storage.resolve_relative_path(asset.storage_path),
            asset.mime_type,
            asset.original_filename,
        )

    def delete_preview_artifact(self, relative_path: str | None) -> None:
        if relative_path:
            self.storage.delete_path(relative_path)

    def _load_fragments_for_path(self, relative_path: str) -> list[PreviewFragmentItem]:
        absolute_path = self.storage.resolve_relative_path(relative_path)
        load_result = registry.load_document(absolute_path)
        return [
            PreviewFragmentItem(
                fragment_index=fragment.fragment_index,
                page_number=fragment.page_number,
                content=fragment.content,
                metadata=fragment.metadata,
            )
            for fragment in load_result.fragments
        ]

    def _ensure_preview(
        self,
        *,
        asset_id: str,
        source_relative_path: str,
        source_extension: str,
        existing_preview_path: str | None,
        preview_namespace: str,
    ) -> tuple[dict[str, str] | None, str]:
        source_path = self.storage.resolve_relative_path(source_relative_path)
        normalized_extension = source_extension.lower()

        if normalized_extension == ".pdf":
            return {"relative_path": source_relative_path}, "ready"

        if normalized_extension not in {".docx", ".xls", ".xlsx"}:
            return None, "unsupported"

        if existing_preview_path:
            existing_path = self.storage.resolve_relative_path(existing_preview_path)
            if existing_path.exists():
                return {"relative_path": existing_preview_path}, "ready"

        target_path = self.storage.build_preview_path(preview_namespace, asset_id)
        try:
            self._convert_office_to_pdf(source_path, target_path)
        except Exception:
            return None, "failed"

        relative_path: Path = target_path
        if target_path.is_relative_to(self.settings.backend_root):
            relative_path = target_path.relative_to(self.settings.backend_root)
        return {"relative_path": str(relative_path)}, "ready"

    def _convert_office_to_pdf(self, source_path: Path, target_path: Path) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_output = target_path.parent / (source_path.stem + ".pdf")
        if temporary_output.exists():
            temporary_output.unlink()
        if target_path.exists():
            target_path.unlink()

        command = [
            self.settings.libreoffice_bin,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(target_path.parent),
            str(source_path),
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)

        if temporary_output.exists():
            temporary_output.replace(target_path)
        if not target_path.exists():
            raise RuntimeError("Preview conversion did not generate a PDF file")

        for leftover in target_path.parent.iterdir():
            if leftover.is_file() and leftover.name != target_path.name and leftover.suffix == ".pdf":
                leftover.unlink(missing_ok=True)
