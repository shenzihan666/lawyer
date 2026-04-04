from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import QueueHandler, QueueListener, TimedRotatingFileHandler
from pathlib import Path
from queue import Queue
from typing import Any

from app.core.config import Settings

request_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id",
    default=None,
)
request_method_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_method",
    default=None,
)
request_path_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_path",
    default=None,
)

_standard_record_keys = set(logging.makeLogRecord({}).__dict__.keys()) | {
    "message",
    "asctime",
    "request_id",
    "request_method",
    "request_path",
}
_listener: QueueListener | None = None
_queue_handler: QueueHandler | None = None
_configured_signature: tuple[str, str, int, str] | None = None


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def bind_request_context(
    *,
    request_id: str,
    request_method: str,
    request_path: str,
) -> tuple[contextvars.Token, contextvars.Token, contextvars.Token]:
    return (
        request_id_context.set(request_id),
        request_method_context.set(request_method),
        request_path_context.set(request_path),
    )


def reset_request_context(
    tokens: tuple[contextvars.Token, contextvars.Token, contextvars.Token],
) -> None:
    request_id_context.reset(tokens[0])
    request_method_context.reset(tokens[1])
    request_path_context.reset(tokens[2])


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_context.get()
        record.request_method = request_method_context.get()
        record.request_path = request_path_context.get()
        return True


class JsonFormatter(logging.Formatter):
    def __init__(self, *, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service_name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "process": record.process,
            "thread": record.thread,
        }

        if getattr(record, "request_id", None):
            payload["request_id"] = record.request_id
        if getattr(record, "request_method", None):
            payload["request_method"] = record.request_method
        if getattr(record, "request_path", None):
            payload["request_path"] = record.request_path

        for key, value in record.__dict__.items():
            if key in _standard_record_keys or key.startswith("_"):
                continue
            if value is None:
                continue
            payload[key] = self._json_value(value)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(payload, ensure_ascii=False)

    def _json_value(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(key): self._json_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._json_value(item) for item in value]
        return str(value)


def configure_logging(settings: Settings) -> None:
    global _configured_signature
    global _listener
    global _queue_handler

    signature = (
        settings.log_level.upper(),
        str(settings.logs_root),
        settings.log_retention_days,
        settings.app_name,
    )
    if _configured_signature == signature and _listener is not None:
        return

    shutdown_logging()

    settings.logs_root.mkdir(parents=True, exist_ok=True)
    formatter = JsonFormatter(service_name=settings.app_name)
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    app_handler = TimedRotatingFileHandler(
        filename=settings.logs_root / "application.log",
        when="midnight",
        interval=1,
        backupCount=settings.log_retention_days,
        encoding="utf-8",
    )
    app_handler.setLevel(level)
    app_handler.setFormatter(formatter)

    error_handler = TimedRotatingFileHandler(
        filename=settings.logs_root / "error.log",
        when="midnight",
        interval=1,
        backupCount=settings.log_retention_days,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    log_queue: Queue[logging.LogRecord] = Queue(-1)
    _queue_handler = QueueHandler(log_queue)
    _queue_handler.setLevel(level)
    _queue_handler.addFilter(RequestContextFilter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)
    root_logger.addHandler(_queue_handler)

    for logger_name in ("uvicorn", "uvicorn.error", "fastapi", "sqlalchemy"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True

    for logger_name in ("httpx", "httpcore"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.setLevel(logging.WARNING)
        logger.propagate = True

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False

    logging.captureWarnings(True)

    _listener = QueueListener(
        log_queue,
        console_handler,
        app_handler,
        error_handler,
        respect_handler_level=True,
    )
    _listener.start()
    _configured_signature = signature


def shutdown_logging() -> None:
    global _configured_signature
    global _listener
    global _queue_handler

    if _listener is not None:
        _listener.stop()
        for handler in _listener.handlers:
            handler.close()
        _listener = None

    root_logger = logging.getLogger()
    if _queue_handler is not None and _queue_handler in root_logger.handlers:
        root_logger.removeHandler(_queue_handler)
        _queue_handler.close()
        _queue_handler = None

    _configured_signature = None
