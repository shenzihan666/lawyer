from __future__ import annotations

import logging
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_pool: AsyncConnectionPool | None = None
_checkpointer: AsyncPostgresSaver | None = None


async def get_checkpointer() -> AsyncPostgresSaver:
    """Return a singleton async checkpointer backed by PostgreSQL.

    LangGraph streaming APIs call async checkpoint methods such as ``aget_tuple``.
    To keep behavior consistent across Windows and Linux, always use the async
    saver and rely on the app's Windows selector event-loop policy.
    """
    global _pool, _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    settings = get_settings()
    dsn = settings.database_url
    if dsn.startswith("postgresql+psycopg://"):
        dsn = dsn.replace("postgresql+psycopg://", "postgresql://", 1)

    if not dsn.startswith("postgresql://"):
        raise RuntimeError(
            "Agent checkpointer requires a PostgreSQL DATABASE_URL using the psycopg driver."
        )

    _pool = AsyncConnectionPool(
        conninfo=dsn,
        min_size=1,
        max_size=4,
        open=False,
    )
    await _pool.open()
    _checkpointer = AsyncPostgresSaver(_pool)
    await _checkpointer.setup()

    logger.info(
        "LangGraph checkpointer initialized",
        extra={"event": "checkpointer_ready"},
    )
    return _checkpointer


async def close_checkpointer() -> None:
    """Close the shared checkpointer pool when the app shuts down."""
    global _pool, _checkpointer

    if _pool is not None:
        await _pool.close()

    _pool = None
    _checkpointer = None
