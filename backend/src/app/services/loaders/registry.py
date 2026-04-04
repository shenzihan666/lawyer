from functools import lru_cache
from pathlib import Path

from app.services.loaders.base import (
    DocumentLoader,
    LoadResult,
    UnsupportedDocumentTypeError,
)
from app.services.loaders.excel import ExcelDocumentLoader
from app.services.loaders.pdf import PdfDocumentLoader
from app.services.loaders.word import WordDocumentLoader


@lru_cache
def get_loader_registry() -> dict[str, DocumentLoader]:
    loaders = (PdfDocumentLoader(), WordDocumentLoader(), ExcelDocumentLoader())
    registry: dict[str, DocumentLoader] = {}
    for loader in loaders:
        for suffix in loader.extensions:
            registry[suffix] = loader
    return registry


def get_loader_for_suffix(suffix: str) -> DocumentLoader:
    normalized = suffix.lower()
    loader = get_loader_registry().get(normalized)
    if loader is None:
        supported = ", ".join(sorted(get_loader_registry()))
        raise UnsupportedDocumentTypeError(
            f"Unsupported file type '{normalized}'. Supported types: {supported}."
        )
    return loader


def get_loader_name_for_suffix(suffix: str) -> str:
    return get_loader_for_suffix(suffix).loader_name


def load_document(file_path: Path) -> LoadResult:
    return get_loader_for_suffix(file_path.suffix).load(file_path)
