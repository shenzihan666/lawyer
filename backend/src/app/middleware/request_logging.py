from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request

from app.core.logging import bind_request_context, get_logger, reset_request_context

logger = get_logger("app.http")


def add_request_logging_middleware(application: FastAPI) -> None:
    @application.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid4().hex
        tokens = bind_request_context(
            request_id=request_id,
            request_method=request.method,
            request_path=request.url.path,
        )
        request.state.request_id = request_id
        started_at = perf_counter()
        client_ip = request.client.host if request.client else None

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((perf_counter() - started_at) * 1000, 3)
            logger.exception(
                "Request failed",
                extra={
                    "event": "http_request_failed",
                    "client_ip": client_ip,
                    "query_params": dict(request.query_params),
                    "duration_ms": duration_ms,
                },
            )
            raise
        else:
            response.headers["X-Request-ID"] = request_id
            duration_ms = round((perf_counter() - started_at) * 1000, 3)
            log_method = logger.info
            if response.status_code >= 500:
                log_method = logger.error
            elif response.status_code >= 400:
                log_method = logger.warning

            log_method(
                "Request completed",
                extra={
                    "event": "http_request_completed",
                    "client_ip": client_ip,
                    "status_code": response.status_code,
                    "query_params": dict(request.query_params),
                    "duration_ms": duration_ms,
                },
            )
            return response
        finally:
            reset_request_context(tokens)
