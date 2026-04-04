from app.core.config import Settings
from app.services.vectors.chunking import ChunkRecord
from app.services.vectors.milvus import MilvusVectorIndex


class _FakeMilvusClient:
    def __init__(self) -> None:
        self.insert_calls: list[tuple[str, list[dict]]] = []
        self.flush_calls: list[str] = []

    def has_collection(self, name: str) -> bool:
        return True

    def delete(self, collection_name: str, filter: str) -> None:
        return

    def drop_collection(self, name: str) -> None:
        return

    def insert(self, collection_name: str, payload: list[dict]) -> None:
        self.insert_calls.append((collection_name, payload))

    def flush(self, collection_name: str) -> None:
        self.flush_calls.append(collection_name)


class _FakeMilvusIndex(MilvusVectorIndex):
    def __init__(self, settings: Settings, client: _FakeMilvusClient) -> None:
        super().__init__(settings)
        self._client = client


def test_replace_leaf_chunks_flushes_after_insert() -> None:
    settings = Settings(_env_file=None)
    client = _FakeMilvusClient()
    index = _FakeMilvusIndex(settings, client)

    chunk = ChunkRecord(
        chunk_id="doc-1:l3:0",
        document_id="doc-1",
        root_chunk_id="doc-1:l1:0",
        parent_chunk_id="doc-1:l2:0",
        chunk_level=3,
        chunk_index=0,
        page_number=1,
        content="chunk content",
        metadata={},
        original_filename="demo.pdf",
    )

    index.replace_leaf_chunks(
        chunks=[chunk],
        dense_embeddings=[[0.1, 0.2]],
        sparse_embeddings=[{1: 0.3}],
    )

    assert len(client.insert_calls) == 1
    assert client.flush_calls == [settings.milvus_collection]
