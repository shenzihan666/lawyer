from importlib import import_module
from typing import Any

from app.core.config import Settings
from app.services.vectors.chunking import ChunkRecord


class MilvusVectorIndex:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None

    @staticmethod
    def _milvus_module() -> Any:
        try:
            return import_module("pymilvus")
        except (
            ImportError
        ) as exc:  # pragma: no cover - optional dependency until installed
            raise RuntimeError("pymilvus is not installed") from exc

    def _get_client(self):
        if self._client is None:
            milvus = self._milvus_module()
            kwargs = {"uri": self.settings.milvus_uri}
            if self.settings.milvus_token:
                kwargs["token"] = self.settings.milvus_token
            if self.settings.milvus_database:
                kwargs["db_name"] = self.settings.milvus_database
            self._client = milvus.MilvusClient(**kwargs)
        return self._client

    def ensure_collection(self) -> None:
        milvus: Any = self._milvus_module()
        data_type: Any = milvus.DataType
        client = self._get_client()
        if client.has_collection(self.settings.milvus_collection):
            return

        schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("chunk_id", data_type.VARCHAR, is_primary=True, max_length=128)
        schema.add_field("document_id", data_type.VARCHAR, max_length=64)
        schema.add_field("root_chunk_id", data_type.VARCHAR, max_length=128)
        schema.add_field("parent_chunk_id", data_type.VARCHAR, max_length=128)
        schema.add_field("chunk_level", data_type.INT64)
        schema.add_field("chunk_index", data_type.INT64)
        schema.add_field("page_number", data_type.INT64)
        schema.add_field("original_filename", data_type.VARCHAR, max_length=255)
        schema.add_field("text", data_type.VARCHAR, max_length=4096)
        schema.add_field(
            "dense_embedding",
            data_type.FLOAT_VECTOR,
            dim=self.settings.vector_dense_dimension,
        )
        schema.add_field("sparse_embedding", data_type.SPARSE_FLOAT_VECTOR)

        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="dense_embedding",
            index_type="HNSW",
            metric_type="IP",
            params={"M": 16, "efConstruction": 128},
        )
        index_params.add_index(
            field_name="sparse_embedding",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="IP",
            params={"drop_ratio_build": 0.2},
        )
        client.create_collection(
            collection_name=self.settings.milvus_collection,
            schema=schema,
            index_params=index_params,
        )

    def drop_collection(self) -> None:
        client = self._get_client()
        if client.has_collection(self.settings.milvus_collection):
            client.drop_collection(self.settings.milvus_collection)

    def delete_by_document_ids(self, document_ids: list[str]) -> None:
        if not document_ids:
            return
        quoted_ids = ", ".join(f'"{item}"' for item in document_ids)
        self._get_client().delete(
            collection_name=self.settings.milvus_collection,
            filter=f"document_id in [{quoted_ids}]",
        )

    def upsert_leaf_chunks(
        self,
        chunks: list[ChunkRecord],
        dense_embeddings: list[list[float]],
        sparse_embeddings: list[dict[int, float]],
    ) -> None:
        if not chunks:
            return

        self.ensure_collection()
        self.delete_by_document_ids(sorted({chunk.document_id for chunk in chunks}))

        payload = [
            {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "root_chunk_id": chunk.root_chunk_id,
                "parent_chunk_id": chunk.parent_chunk_id or "",
                "chunk_level": chunk.chunk_level,
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number,
                "original_filename": chunk.original_filename,
                "text": chunk.content[:4096],
                "dense_embedding": dense_embedding,
                "sparse_embedding": sparse_embedding,
            }
            for chunk, dense_embedding, sparse_embedding in zip(
                chunks,
                dense_embeddings,
                sparse_embeddings,
                strict=True,
            )
        ]
        client = self._get_client()
        client.insert(self.settings.milvus_collection, payload)
        client.flush(collection_name=self.settings.milvus_collection)

    def replace_leaf_chunks(
        self,
        chunks: list[ChunkRecord],
        dense_embeddings: list[list[float]],
        sparse_embeddings: list[dict[int, float]],
    ) -> None:
        self.drop_collection()
        if not chunks:
            return
        self.ensure_collection()
        payload = [
            {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "root_chunk_id": chunk.root_chunk_id,
                "parent_chunk_id": chunk.parent_chunk_id or "",
                "chunk_level": chunk.chunk_level,
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number,
                "original_filename": chunk.original_filename,
                "text": chunk.content[:4096],
                "dense_embedding": dense_embedding,
                "sparse_embedding": sparse_embedding,
            }
            for chunk, dense_embedding, sparse_embedding in zip(
                chunks,
                dense_embeddings,
                sparse_embeddings,
                strict=True,
            )
        ]
        client = self._get_client()
        client.insert(self.settings.milvus_collection, payload)
        client.flush(collection_name=self.settings.milvus_collection)

    def search(
        self,
        dense_embedding: list[float],
        sparse_embedding: dict[int, float],
        top_k: int,
        document_ids: list[str] | None = None,
    ) -> tuple[list[dict], str]:
        self.ensure_collection()
        filter_expr = ""
        if document_ids:
            quoted_ids = ", ".join(f'"{item}"' for item in document_ids)
            filter_expr = f"document_id in [{quoted_ids}]"

        output_fields = [
            "chunk_id",
            "document_id",
            "root_chunk_id",
            "parent_chunk_id",
            "chunk_level",
            "chunk_index",
            "page_number",
            "original_filename",
            "text",
        ]

        try:
            milvus: Any = self._milvus_module()
            dense_search = milvus.AnnSearchRequest(
                data=[dense_embedding],
                anns_field="dense_embedding",
                param={"metric_type": "IP", "params": {"ef": 64}},
                limit=max(top_k * 2, top_k),
                expr=filter_expr,
            )
            sparse_search = milvus.AnnSearchRequest(
                data=[sparse_embedding],
                anns_field="sparse_embedding",
                param={"metric_type": "IP", "params": {"drop_ratio_search": 0.2}},
                limit=max(top_k * 2, top_k),
                expr=filter_expr,
            )
            results = self._get_client().hybrid_search(
                collection_name=self.settings.milvus_collection,
                reqs=[dense_search, sparse_search],
                ranker=milvus.RRFRanker(k=60),
                limit=top_k,
                output_fields=output_fields,
            )
            return self._format_search_results(results), "hybrid"
        except Exception:
            results = self._get_client().search(
                collection_name=self.settings.milvus_collection,
                data=[dense_embedding],
                anns_field="dense_embedding",
                search_params={"metric_type": "IP", "params": {"ef": 64}},
                limit=top_k,
                output_fields=output_fields,
                filter=filter_expr,
            )
            return self._format_search_results(results), "dense_fallback"

    def _format_search_results(self, results) -> list[dict]:
        formatted: list[dict] = []
        for hits in results:
            for hit in hits:
                entity = hit.get("entity", {}) if isinstance(hit, dict) else {}
                formatted.append(
                    {
                        "chunk_id": hit.get("chunk_id") or entity.get("chunk_id"),
                        "document_id": hit.get("document_id")
                        or entity.get("document_id"),
                        "root_chunk_id": hit.get("root_chunk_id")
                        or entity.get("root_chunk_id"),
                        "parent_chunk_id": hit.get("parent_chunk_id")
                        or entity.get("parent_chunk_id")
                        or None,
                        "chunk_level": hit.get("chunk_level")
                        or entity.get("chunk_level")
                        or 3,
                        "chunk_index": hit.get("chunk_index")
                        or entity.get("chunk_index")
                        or 0,
                        "page_number": hit.get("page_number")
                        or entity.get("page_number")
                        or 0,
                        "original_filename": hit.get("original_filename")
                        or entity.get("original_filename")
                        or "",
                        "content": hit.get("text") or entity.get("text") or "",
                        "score": float(hit.get("distance", 0.0)),
                    }
                )
        return formatted
