from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import shutil
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import Settings


@dataclass(slots=True)
class StoredFile:
    document_id: str
    original_filename: str
    stored_filename: str
    relative_path: str
    absolute_path: Path
    file_extension: str
    mime_type: str | None
    file_size: int
    sha256_digest: str


class UploadStorage:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def save(self, upload: UploadFile) -> StoredFile:
        return self.save_upload(upload, namespace="")

    def save_upload(self, upload: UploadFile, namespace: str) -> StoredFile:
        original_name = Path(upload.filename or "document").name
        suffix = Path(original_name).suffix.lower()
        document_id = str(uuid4())
        stored_filename = f"source{suffix}"
        target_dir = self._build_target_dir(namespace, document_id)
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
            document_id=document_id,
            original_filename=original_name,
            stored_filename=stored_filename,
            absolute_path=target_path,
            mime_type=upload.content_type,
            file_size=file_size,
            sha256_digest=digest.hexdigest(),
        )

    def import_file(
        self,
        source_path: Path,
        *,
        namespace: str,
        original_filename: str | None = None,
    ) -> StoredFile:
        document_id = str(uuid4())
        suffix = source_path.suffix.lower()
        stored_filename = f"source{suffix}"
        target_dir = self._build_target_dir(namespace, document_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / stored_filename
        shutil.copy2(source_path, target_path)

        digest = sha256()
        with target_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)

        return self._to_stored_file(
            document_id=document_id,
            original_filename=original_filename or source_path.name,
            stored_filename=stored_filename,
            absolute_path=target_path,
            mime_type=None,
            file_size=target_path.stat().st_size,
            sha256_digest=digest.hexdigest(),
        )

    def build_preview_path(self, namespace: str, asset_id: str) -> Path:
        dated_dir = datetime.now().strftime("%Y/%m")
        target_dir = (
            self.settings.upload_root / "previews" / namespace / dated_dir / asset_id
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / "preview.pdf"

    def resolve_relative_path(self, relative_or_absolute: str) -> Path:
        path = Path(relative_or_absolute)
        if path.is_absolute():
            resolved = path.resolve()
        else:
            resolved = (self.settings.backend_root / path).resolve()

        allowed_roots = [
            self.settings.backend_root.resolve(),
            self.settings.upload_root.resolve(),
        ]
        if not any(
            resolved == root or root in resolved.parents for root in allowed_roots
        ):
            raise ValueError(
                f"Resolved path escapes allowed roots: {relative_or_absolute}"
            )
        return resolved

    def delete_path(self, relative_or_absolute: str) -> None:
        target = self.resolve_relative_path(relative_or_absolute)
        if target.is_file():
            target.unlink(missing_ok=True)
        elif target.is_dir():
            shutil.rmtree(target, ignore_errors=True)

    def _build_target_dir(self, namespace: str, document_id: str) -> Path:
        dated_dir = datetime.now().strftime("%Y/%m")
        base_dir = self.settings.upload_root
        if namespace:
            return base_dir / namespace / dated_dir / document_id
        return base_dir / dated_dir / document_id

    def _to_stored_file(
        self,
        *,
        document_id: str,
        original_filename: str,
        stored_filename: str,
        absolute_path: Path,
        mime_type: str | None,
        file_size: int,
        sha256_digest: str,
    ) -> StoredFile:
        relative_path: Path = absolute_path
        if absolute_path.is_relative_to(self.settings.backend_root):
            relative_path = absolute_path.relative_to(self.settings.backend_root)

        return StoredFile(
            document_id=document_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            relative_path=str(relative_path),
            absolute_path=absolute_path,
            file_extension=absolute_path.suffix.lower(),
            mime_type=mime_type,
            file_size=file_size,
            sha256_digest=sha256_digest,
        )
