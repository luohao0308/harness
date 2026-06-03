from __future__ import annotations

from contextvars import ContextVar
from uuid import uuid4

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.security.auth import DEV_TOKEN_PRINCIPALS

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
        self.service_name = service_name

    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get(TRACE_ID_HEADER) or str(uuid4())
        token = _trace_id.set(trace_id)
        session: Session = SessionLocal()
        organization_id = _organization_id_from_request(request)
        from app.observability.tracing import traced_operation

        try:
            with traced_operation(
                session,
                f"{request.method} {request.url.path}",
                organization_id=organization_id,
                kind="server",
                attributes={
                    "http.request.method": request.method,
                    "url.path": request.url.path,
                    "service.name": self.service_name,
                    "organization_id": organization_id,
                },
                link_current_parent=False,
                best_effort=True,
            ) as attributes:
                try:
                    response = await call_next(request)
                except BaseException:
                    raise
                attributes["http.response.status_code"] = response.status_code
                response.headers[TRACE_ID_HEADER] = trace_id
                return response
        finally:
            try:
                try:
                    session.commit()
                except Exception:
                    session.rollback()
            finally:
                session.close()
                _trace_id.reset(token)

    @property
    def service_name(self) -> str:
        return getattr(self, "_service_name", "api-server")

    @service_name.setter
    def service_name(self, value: str) -> None:
        self._service_name = value


def _organization_id_from_request(request: Request) -> str | None:
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        token = request.query_params.get("access_token")
    else:
        token = auth.split(" ", 1)[1].strip()
    principal = DEV_TOKEN_PRINCIPALS.get(token or "")
    return principal.organization_id if principal is not None else None
