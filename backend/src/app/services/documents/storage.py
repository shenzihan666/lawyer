from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
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
        original_name = Path(upload.filename or "document").name
        suffix = Path(original_name).suffix.lower()
        document_id = str(uuid4())
        stored_filename = f"source{suffix}"
        dated_dir = datetime.now().strftime("%Y/%m")
        target_dir = self.settings.upload_root / dated_dir / document_id
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

        relative_path = target_path
        if target_path.is_relative_to(self.settings.backend_root):
            relative_path = target_path.relative_to(self.settings.backend_root)

        return StoredFile(
            document_id=document_id,
            original_filename=original_name,
            stored_filename=stored_filename,
            relative_path=str(relative_path),
            absolute_path=target_path,
            file_extension=suffix,
            mime_type=upload.content_type,
            file_size=file_size,
            sha256_digest=digest.hexdigest(),
        )
