import asyncio
import os
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger, shutdown_logging
from app.db.base import Base
from app.db.session import get_engine, wait_for_database
from app.middleware import add_request_logging_middleware


# Configure event loop for Windows compatibility
if sys.platform == "win32":
    # On Windows, default to SelectorEventLoop for psycopg compatibility
    # ProactorEventLoop (default on Windows) doesn't work with psycopg async connections
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)
    logger = get_logger("app.lifecycle")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        settings.data_root.mkdir(parents=True, exist_ok=True)
        settings.upload_root.mkdir(parents=True, exist_ok=True)
        settings.logs_root.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Application startup",
            extra={
                "event": "application_startup",
                "data_root": settings.data_root,
                "upload_root": settings.upload_root,
                "logs_root": settings.logs_root,
            },
        )
        logger.info(
            "Checking database availability",
            extra={
                "event": "database_startup_check",
                "database_url": settings.database_url,
                "connect_timeout_seconds": settings.database_connect_timeout_seconds,
                "max_attempts": settings.database_startup_max_attempts,
            },
        )
        wait_for_database()
        Base.metadata.create_all(bind=get_engine())
        logger.info("Database schema ready", extra={"event": "database_schema_ready"})

        # Initialize LangGraph checkpointer for agent conversations
        if settings.agent_enabled:
            try:
                from app.services.agent.checkpoint import get_checkpointer
                await get_checkpointer()
                logger.info("Agent checkpointer ready", extra={"event": "agent_ready"})
            except Exception as exc:
                logger.warning(
                    "Agent checkpointer init failed, agent features disabled",
                    extra={"event": "agent_init_failed", "error": str(exc)},
                )

        try:
            yield
        finally:
            if settings.agent_enabled:
                try:
                    from app.services.agent.checkpoint import close_checkpointer

                    await close_checkpointer()
                except Exception as exc:
                    logger.warning(
                        "Agent checkpointer shutdown failed",
                        extra={"event": "agent_shutdown_failed", "error": str(exc)},
                    )
            logger.info("Application shutdown", extra={"event": "application_shutdown"})
            shutdown_logging()

    application = FastAPI(title=settings.app_name, lifespan=lifespan)
    add_request_logging_middleware(application)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.frontend_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    application.include_router(api_router, prefix=settings.api_v1_prefix)
    return application


app = create_app()


def main() -> None:
    # Set event loop policy for Windows before uvicorn starts
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    settings = get_settings()
    configure_logging(settings)
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("UVICORN_RELOAD", "false").lower() == "true",
        access_log=False,
        log_config=None,
    )
