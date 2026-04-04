from dataclasses import dataclass
from itertools import islice
from typing import Any

from app.core.config import Settings
from app.models import DocumentAsset


@dataclass(slots=True)
class ChunkRecord:
    chunk_id: str
    document_id: str
    root_chunk_id: str
    parent_chunk_id: str | None
    chunk_level: int
    chunk_index: int
    page_number: int
    content: str
    metadata: dict[str, Any]
    original_filename: str


def _split_text(text: str, chunk_size: int, overlap: int) -> list[tuple[int, int, str]]:
    normalized = " ".join(text.split())
    if not normalized:
        return []

    start = 0
    parts: list[tuple[int, int, str]] = []
    step = max(chunk_size - overlap, 1)
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        parts.append((start, end, normalized[start:end]))
        if end >= len(normalized):
            break
        start += step
    return parts


def build_document_chunks(
    document: DocumentAsset, settings: Settings
) -> list[ChunkRecord]:
    root_chunk_id = f"{document.id}:l1:0"
    leaf_records: list[ChunkRecord] = []

    leaf_index = 0
    for fragment in document.fragments:
        pieces = _split_text(
            fragment.content,
            chunk_size=settings.vector_leaf_chunk_size,
            overlap=settings.vector_leaf_chunk_overlap,
        )
        for start, end, content in pieces:
            leaf_records.append(
                ChunkRecord(
                    chunk_id=f"{document.id}:l3:{leaf_index}",
                    document_id=document.id,
                    root_chunk_id=root_chunk_id,
                    parent_chunk_id=None,
                    chunk_level=3,
                    chunk_index=leaf_index,
                    page_number=fragment.page_number,
                    content=content,
                    metadata={
                        "fragment_index": fragment.fragment_index,
                        "start_char": start,
                        "end_char": end,
                        "source": "fragment",
                    },
                    original_filename=document.original_filename,
                )
            )
            leaf_index += 1

    if not leaf_records:
        return []

    parent_records: list[ChunkRecord] = []
    parent_group_size = max(settings.vector_parent_group_size, 1)
    leaf_iter = iter(leaf_records)
    parent_index = 0

    while batch := list(islice(leaf_iter, parent_group_size)):
        parent_chunk_id = f"{document.id}:l2:{parent_index}"
        for leaf in batch:
            leaf.parent_chunk_id = parent_chunk_id

        parent_records.append(
            ChunkRecord(
                chunk_id=parent_chunk_id,
                document_id=document.id,
                root_chunk_id=root_chunk_id,
                parent_chunk_id=root_chunk_id,
                chunk_level=2,
                chunk_index=parent_index,
                page_number=batch[0].page_number,
                content="\n\n".join(item.content for item in batch),
                metadata={
                    "child_chunk_ids": [item.chunk_id for item in batch],
                    "source": "parent_group",
                },
                original_filename=document.original_filename,
            )
        )
        parent_index += 1

    root_record = ChunkRecord(
        chunk_id=root_chunk_id,
        document_id=document.id,
        root_chunk_id=root_chunk_id,
        parent_chunk_id=None,
        chunk_level=1,
        chunk_index=0,
        page_number=0,
        content="\n\n".join(item.content for item in parent_records),
        metadata={
            "child_chunk_ids": [item.chunk_id for item in parent_records],
            "source": "document_root",
        },
        original_filename=document.original_filename,
    )

    return [root_record, *parent_records, *leaf_records]
