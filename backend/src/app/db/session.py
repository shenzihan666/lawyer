from collections.abc import Generator
from functools import lru_cache
import logging
import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_engine():
    settings = get_settings()
    settings.data_root.mkdir(parents=True, exist_ok=True)
    connect_args: dict[str, object] = {}
    if settings.database_url.startswith("postgresql"):
        connect_args["connect_timeout"] = settings.database_connect_timeout_seconds
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(
        settings.database_url,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(),
        autocommit=False,
        autoflush=False,
        class_=Session,
        expire_on_commit=False,
    )


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def wait_for_database() -> None:
    settings = get_settings()
    engine = get_engine()
    last_error: Exception | None = None

    for attempt in range(1, settings.database_startup_max_attempts + 1):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            logger.info(
                "Database connection established",
                extra={
                    "event": "database_connection_ready",
                    "attempt": attempt,
                    "database_url": settings.database_url,
                },
            )
            return
        except SQLAlchemyError as exc:
            last_error = exc
            logger.warning(
                "Database connection attempt failed",
                extra={
                    "event": "database_connection_retry",
                    "attempt": attempt,
                    "max_attempts": settings.database_startup_max_attempts,
                    "database_url": settings.database_url,
                    "retry_delay_seconds": settings.database_startup_retry_delay_seconds,
                    "error": str(exc),
                },
            )
            engine.dispose()
            if attempt < settings.database_startup_max_attempts:
                time.sleep(settings.database_startup_retry_delay_seconds)

    raise RuntimeError(
        "Database startup check failed after "
        f"{settings.database_startup_max_attempts} attempts for "
        f"{settings.database_url}. Last error: {last_error}"
    ) from last_error
