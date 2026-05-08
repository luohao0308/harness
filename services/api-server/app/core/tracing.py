from __future__ import annotations

from contextvars import ContextVar
from uuid import uuid4

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings

TRACE_ID_HEADER = "x-trace-id"
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_tracing_configured = False


def get_current_trace_id() -> str | None:
    return _trace_id.get()


def configure_tracing(service_name: str = "api-server") -> None:
    global _tracing_configured
    if _tracing_configured:
        return
    _tracing_configured = True
    settings = get_settings()
    if not settings.otel_exporter_otlp_endpoint:
        return
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    except ImportError:
        return
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
        )
    )
    trace.set_tracer_provider(provider)


class OpenTelemetryTraceMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, service_name: str = "api-server") -> None:
        super().__init__(app)
        configure_tracing(service_name=service_name)
        self.tracer = trace.get_tracer(service_name)

    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get(TRACE_ID_HEADER) or str(uuid4())
        token = _trace_id.set(trace_id)
        try:
            with self.tracer.start_as_current_span(f"{request.method} {request.url.path}") as span:
                span.set_attribute("harness.trace_id", trace_id)
                span.set_attribute("http.request.method", request.method)
                span.set_attribute("url.path", request.url.path)
                response = await call_next(request)
                span.set_attribute("http.response.status_code", response.status_code)
                response.headers[TRACE_ID_HEADER] = trace_id
                return response
        finally:
            _trace_id.reset(token)
