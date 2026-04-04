from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Lawyer Backend"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite+pysqlite:///./data/lawyer.db"
    frontend_origins: list[str] = [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ]
    upload_root_path: str = "uploads"
    milvus_uri: str = "http://127.0.0.1:19530"
    milvus_token: str | None = None
    milvus_database: str = "default"
    milvus_collection: str = "law_documents"

    @field_validator("frontend_origins", mode="before")
    @classmethod
    def split_frontend_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def backend_root(self) -> Path:
        return Path(__file__).resolve().parents[3]

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
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
