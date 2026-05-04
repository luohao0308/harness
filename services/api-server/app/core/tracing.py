from __future__ import annotations

from contextvars import ContextVar
from uuid import uuid4

from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

TRACE_ID_HEADER = "x-trace-id"
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)


def get_current_trace_id() -> str | None:
    return _trace_id.get()


class OpenTelemetryTraceMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, service_name: str = "api-server") -> None:
        super().__init__(app)
        self.tracer = trace.get_tracer(service_name)

    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get(TRACE_ID_HEADER) or str(uuid4())
        token = _trace_id.set(trace_id)
        try:
            with self.tracer.start_as_current_span(f"{request.method} {request.url.path}"):
                response = await call_next(request)
                response.headers[TRACE_ID_HEADER] = trace_id
                return response
        finally:
            _trace_id.reset(token)
