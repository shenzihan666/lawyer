from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Lawyer Backend"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/lawyer"
    frontend_origins: Annotated[list[str], NoDecode] = [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ]
    upload_root_path: str = "uploads"
    database_connect_timeout_seconds: int = 5
    database_startup_max_attempts: int = 3
    database_startup_retry_delay_seconds: float = 2.0
    milvus_uri: str = "http://127.0.0.1:19530"
    milvus_token: str | None = None
    milvus_database: str = "default"
    milvus_collection: str = "law_documents"
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_key_prefix: str = "lawyer"
    redis_cache_ttl_seconds: int = 300
    log_level: str = "INFO"
    log_root_path: str = "logs"
    log_retention_days: int = 30
    embedding_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("EMBEDDING_BASE_URL", "BASE_URL"),
    )
    embedding_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices("EMBEDDING_MODEL", "EMBEDDER"),
    )
    embedding_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("EMBEDDING_API_KEY", "ARK_API_KEY"),
    )
    embedding_batch_size: int = 100
    embedding_timeout_seconds: int = 30
    vector_dense_dimension: int = 3072
    vector_sparse_dimension: int = 262144
    vector_leaf_chunk_size: int = 900
    vector_leaf_chunk_overlap: int = 150
    vector_parent_group_size: int = 4
    vector_search_top_k: int = 5
    vector_auto_merge_threshold: int = 2

    @field_validator("frontend_origins", mode="before")
    @classmethod
    def split_frontend_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def backend_root(self) -> Path:
        return BACKEND_ROOT

    @property
    def data_root(self) -> Path:
        return self.backend_root / "data"

    @property
    def upload_root(self) -> Path:
        root = Path(self.upload_root_path)
        if root.is_absolute():
            return root
        return self.backend_root / root

    @property
    def logs_root(self) -> Path:
        root = Path(self.log_root_path)
        if root.is_absolute():
            return root
        return self.backend_root / root


@lru_cache
def get_settings() -> Settings:
    return Settings()
