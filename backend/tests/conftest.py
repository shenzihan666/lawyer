from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv(
        "DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'lawyer-test.db'}"
    )
    monkeypatch.setenv("UPLOAD_ROOT_PATH", str(tmp_path / "uploads"))
    monkeypatch.setenv("LOG_ROOT_PATH", str(tmp_path / "logs"))
    monkeypatch.setenv("AGENT_ENABLED", "false")

    from app.core.config import get_settings
    from app.db.session import get_engine, get_session_factory

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
