import pytest


@pytest.mark.anyio
async def test_get_checkpointer_uses_async_postgres_components(monkeypatch) -> None:
    from app.core.config import get_settings
    from app.services.agent import checkpoint as checkpoint_module

    state: dict[str, object] = {}

    class FakeAsyncConnectionPool:
        def __init__(self, *, conninfo: str, min_size: int, max_size: int, open: bool):
            state["conninfo"] = conninfo
            state["pool_open_flag"] = open
            self.closed = False

        async def open(self) -> None:
            state["pool_opened"] = True

        async def close(self) -> None:
            self.closed = True
            state["pool_closed"] = True

    class FakeAsyncPostgresSaver:
        def __init__(self, pool):
            state["pool_instance"] = pool
            self.pool = pool

        async def setup(self) -> None:
            state["setup_called"] = True

    get_settings.cache_clear()
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/lawyer",
    )
    monkeypatch.setattr(checkpoint_module, "AsyncConnectionPool", FakeAsyncConnectionPool)
    monkeypatch.setattr(checkpoint_module, "AsyncPostgresSaver", FakeAsyncPostgresSaver)
    checkpoint_module._pool = None
    checkpoint_module._checkpointer = None

    checkpointer = await checkpoint_module.get_checkpointer()

    assert isinstance(checkpointer, FakeAsyncPostgresSaver)
    assert state["conninfo"] == "postgresql://postgres:postgres@127.0.0.1:5433/lawyer"
    assert state["pool_open_flag"] is False
    assert state["pool_opened"] is True
    assert state["setup_called"] is True

    await checkpoint_module.close_checkpointer()
    assert state["pool_closed"] is True

    get_settings.cache_clear()


@pytest.mark.anyio
async def test_get_checkpointer_rejects_non_postgres_database_url(monkeypatch) -> None:
    from app.core.config import get_settings
    from app.services.agent import checkpoint as checkpoint_module

    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///tmp/test.db")
    checkpoint_module._pool = None
    checkpoint_module._checkpointer = None

    with pytest.raises(RuntimeError, match="requires a PostgreSQL DATABASE_URL"):
        await checkpoint_module.get_checkpointer()

    get_settings.cache_clear()
