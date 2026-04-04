from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


class UnsupportedDocumentTypeError(ValueError):
    pass


class DocumentLoadError(RuntimeError):
    pass


@dataclass(slots=True)
class LoadedFragment:
    fragment_index: int
    page_number: int
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LoadResult:
    loader_name: str
    fragments: list[LoadedFragment]


class DocumentLoader(Protocol):
    loader_name: str
    extensions: tuple[str, ...]

    def load(self, file_path: Path) -> LoadResult: ...
