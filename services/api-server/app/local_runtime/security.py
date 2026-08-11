from __future__ import annotations

from urllib.parse import urlsplit

from app.core.config import get_settings


class LocalRuntimeRequestBoundaryMiddleware:
    """Reject DNS-rebinding and foreign-origin traffic in the loopback profile."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        settings = get_settings()
        if settings.runtime_profile != "local" or scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        runtime_origin = str(settings.api_base_url).rstrip("/")
        expected_host = urlsplit(runtime_origin).netloc
        origin = headers.get("origin")
        host_valid = headers.get("host") == expected_host
        allowed_origins = {runtime_origin, "harness-app://renderer"}
        origin_valid = (
            origin in allowed_origins
            if scope["type"] == "websocket"
            else origin is None or origin in allowed_origins
        )
        if host_valid and origin_valid:
            await self.app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008, "reason": "Forbidden origin"})
            return
        body = b'{"detail":"Not Found"}'
        await send(
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
