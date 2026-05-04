from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.tracing import get_current_trace_id

REDACTED_LOG_FIELDS = {
    "secret_value",
    "raw_api_key",
    "full_prompt",
    "raw_sensitive_file_content",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "created_at": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "service": getattr(record, "service", "api-server"),
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", None) or get_current_trace_id(),
            "task_id": getattr(record, "task_id", None),
            "agent_run_id": getattr(record, "agent_run_id", None),
            "event_type": getattr(record, "event_type", None),
        }
        for field in REDACTED_LOG_FIELDS:
            if hasattr(record, field):
                payload[field] = "[REDACTED]"
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_json_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)
