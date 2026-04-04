from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import DocumentAsset, DocumentChunk
from app.services.vectors.chunking import ChunkRecord
from app.services.vectors.store import DocumentChunkStore


class _DummyCache:
    def delete(self, key: str) -> None:
        return

    def get_json(self, key: str):
        return None

    def set_json(self, key: str, value, ttl: int | None = None) -> None:
        return

    def delete_pattern(self, pattern: str) -> None:
        return


def test_attach_dense_embeddings_flushes_pending_chunks(tmp_path) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'vector-store.db'}",
        future=True,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        class_=Session,
        expire_on_commit=False,
    )

    with SessionLocal() as db:
        document = DocumentAsset(
            id="doc-1",
            original_filename="demo.pdf",
            stored_filename="source.pdf",
            storage_path="uploads/demo.pdf",
            file_extension=".pdf",
            mime_type="application/pdf",
            loader_name="PyPDFLoader",
            sha256="a" * 64,
            file_size=123,
            ingestion_status="ready",
            vector_status="not_requested",
            trace_metadata={},
        )
        db.add(document)
        db.commit()

        store = DocumentChunkStore(db=db, cache=_DummyCache())
        chunk = ChunkRecord(
            chunk_id="doc-1:l3:0",
            document_id="doc-1",
            root_chunk_id="doc-1:l1:0",
            parent_chunk_id="doc-1:l2:0",
            chunk_level=3,
            chunk_index=0,
            page_number=1,
            content="chunk content",
            metadata={"source": "fragment"},
            original_filename="demo.pdf",
        )

        store.replace_document_chunks("doc-1", [chunk])
        updated_count = store.attach_dense_embeddings(
            "doc-1",
            {"doc-1:l3:0": [0.1, 0.2, 0.3]},
        )
        db.commit()

        saved_chunk = db.scalars(
            select(DocumentChunk).where(DocumentChunk.chunk_id == "doc-1:l3:0")
        ).one()

        assert updated_count == 1
        assert saved_chunk.chunk_metadata["dense_embedding"] == [0.1, 0.2, 0.3]
