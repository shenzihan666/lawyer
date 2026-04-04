import json
import logging

from app.core.logging import JsonFormatter


def test_json_formatter_outputs_structured_log() -> None:
    formatter = JsonFormatter(service_name="Lawyer Backend")
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=12,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    record.request_id = "req-123"
    record.request_method = "GET"
    record.request_path = "/health"
    record.event = "health_check"
    record.status_code = 200

    payload = json.loads(formatter.format(record))

    assert payload["service"] == "Lawyer Backend"
    assert payload["logger"] == "app.test"
    assert payload["message"] == "hello world"
    assert payload["request_id"] == "req-123"
    assert payload["request_method"] == "GET"
    assert payload["request_path"] == "/health"
    assert payload["event"] == "health_check"
    assert payload["status_code"] == 200
