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
        populate_by_name=True,
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
    query_rewrite_enabled: bool = True
    query_rewrite_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "QUERY_REWRITE_BASE_URL",
            "LLM_BASE_URL",
            "BASE_URL",
            "EMBEDDING_BASE_URL",
        ),
    )
    query_rewrite_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices("QUERY_REWRITE_MODEL", "QUERY_MODEL", "MODEL"),
    )
    query_rewrite_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "QUERY_REWRITE_API_KEY",
            "LLM_API_KEY",
            "ARK_API_KEY",
            "EMBEDDING_API_KEY",
        ),
    )
    query_rewrite_timeout_seconds: int = 30
    query_rewrite_max_context_items: int = 3
    query_rewrite_max_content_chars: int = 480
    answer_generation_enabled: bool = True
    answer_generation_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "ANSWER_GENERATION_BASE_URL",
            "ANSWER_BASE_URL",
            "CHAT_BASE_URL",
            "QUERY_REWRITE_BASE_URL",
            "LLM_BASE_URL",
            "BASE_URL",
            "EMBEDDING_BASE_URL",
        ),
    )
    answer_generation_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "ANSWER_GENERATION_MODEL",
            "ANSWER_MODEL",
            "CHAT_MODEL",
            "QUERY_REWRITE_MODEL",
            "QUERY_MODEL",
            "MODEL",
        ),
    )
    answer_generation_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "ANSWER_GENERATION_API_KEY",
            "ANSWER_API_KEY",
            "CHAT_API_KEY",
            "QUERY_REWRITE_API_KEY",
            "LLM_API_KEY",
            "ARK_API_KEY",
            "EMBEDDING_API_KEY",
        ),
    )
    answer_generation_timeout_seconds: int = 45
    answer_generation_max_context_items: int = 5
    answer_generation_max_content_chars: int = 700
    rerank_enabled: bool = True
    rerank_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RERANK_BASE_URL", "RERANK_BINDING_HOST"),
    )
    rerank_model: str | None = Field(default=None, validation_alias="RERANK_MODEL")
    rerank_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "RERANK_API_KEY",
            "ANSWER_GENERATION_API_KEY",
            "QUERY_REWRITE_API_KEY",
            "LLM_API_KEY",
            "ARK_API_KEY",
        ),
    )
    rerank_timeout_seconds: int = 20
    rerank_max_candidates: int = 12
    rerank_max_content_chars: int = 360
    rerank_llm_fallback_enabled: bool = True
    vector_dense_dimension: int = 3072
    vector_sparse_dimension: int = 262144
    vector_leaf_chunk_size: int = 900
    vector_leaf_chunk_overlap: int = 150
    vector_parent_group_size: int = 4
    vector_search_top_k: int = 5
    vector_auto_merge_threshold: int = 2
    agent_enabled: bool = Field(default=True, validation_alias="AGENT_ENABLED")

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
