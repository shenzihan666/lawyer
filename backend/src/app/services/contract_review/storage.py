from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import shutil
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import Settings


@dataclass(slots=True)
class StoredReviewFile:
    asset_id: str
    original_filename: str
    stored_filename: str
    relative_path: str
    absolute_path: Path
    file_extension: str
    mime_type: str | None
    file_size: int
    sha256_digest: str


class ContractReviewStorage:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def save_upload(self, upload: UploadFile, namespace: str) -> StoredReviewFile:
        original_name = Path(upload.filename or "document").name
        suffix = Path(original_name).suffix.lower()
        asset_id = str(uuid4())
        stored_filename = f"source{suffix}"
        target_dir = self._build_target_dir(namespace, asset_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / stored_filename

        digest = sha256()
        file_size = 0
        with target_path.open("wb") as target:
            while chunk := upload.file.read(1024 * 1024):
                digest.update(chunk)
                file_size += len(chunk)
                target.write(chunk)
        upload.file.close()

        return self._to_stored_file(
            asset_id=asset_id,
            original_filename=original_name,
            stored_filename=stored_filename,
            absolute_path=target_path,
            mime_type=upload.content_type,
            file_size=file_size,
            sha256_digest=digest.hexdigest(),
        )

    def import_file(
        self, source_path: Path, namespace: str, original_filename: str | None = None
    ) -> StoredReviewFile:
        asset_id = str(uuid4())
        suffix = source_path.suffix.lower()
        stored_filename = f"source{suffix}"
        target_dir = self._build_target_dir(namespace, asset_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / stored_filename
        shutil.copy2(source_path, target_path)

        digest = sha256()
        with target_path.open("rb") as target:
            for chunk in iter(lambda: target.read(1024 * 1024), b""):
                digest.update(chunk)

        return self._to_stored_file(
            asset_id=asset_id,
            original_filename=original_filename or source_path.name,
            stored_filename=stored_filename,
            absolute_path=target_path,
            mime_type=None,
            file_size=target_path.stat().st_size,
            sha256_digest=digest.hexdigest(),
        )

    def build_export_path(self, review_id: str) -> Path:
        dated_dir = datetime.now().strftime("%Y/%m")
        target_dir = (
            self.settings.upload_root / "review-exports" / dated_dir / review_id
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / "report.docx"

    def resolve_relative_path(self, relative_or_absolute: str) -> Path:
        path = Path(relative_or_absolute)
        if path.is_absolute():
            return path
        return self.settings.backend_root / path

    def delete_file(self, relative_or_absolute: str) -> None:
        target = self.resolve_relative_path(relative_or_absolute)
        if target.exists():
            target.unlink()
        parent = target.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()

    def _build_target_dir(self, namespace: str, asset_id: str) -> Path:
        dated_dir = datetime.now().strftime("%Y/%m")
        return self.settings.upload_root / namespace / dated_dir / asset_id

    def _to_stored_file(
        self,
        *,
        asset_id: str,
        original_filename: str,
        stored_filename: str,
        absolute_path: Path,
        mime_type: str | None,
        file_size: int,
        sha256_digest: str,
    ) -> StoredReviewFile:
        relative_path: Path = absolute_path
        if absolute_path.is_relative_to(self.settings.backend_root):
            relative_path = absolute_path.relative_to(self.settings.backend_root)

        return StoredReviewFile(
            asset_id=asset_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            relative_path=str(relative_path),
            absolute_path=absolute_path,
            file_extension=absolute_path.suffix.lower(),
            mime_type=mime_type,
            file_size=file_size,
            sha256_digest=sha256_digest,
        )
