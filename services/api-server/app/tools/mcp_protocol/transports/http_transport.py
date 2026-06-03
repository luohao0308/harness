from __future__ import annotations

import json
from typing import Any

import httpx

from app.tools.mcp_protocol.client import MCPProtocolError


class MCPHTTPTransport:
    def __init__(
        self,
        *,
        endpoint_url: str,
        secret_value: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.endpoint_url = endpoint_url.rstrip("/")
        self.secret_value = str(secret_value or "").strip()
        self.headers = headers or {}

    def request(self, payload: dict[str, Any], *, timeout_seconds: int) -> dict[str, Any]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            **self.headers,
        }
        if self.secret_value and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {self.secret_value}"
        try:
            response = httpx.post(
                self.endpoint_url,
                json=payload,
                headers=headers,
                timeout=max(1, min(timeout_seconds, 60)),
            )
        except httpx.TimeoutException as exc:
            raise MCPProtocolError("MCP HTTP request timed out") from exc
        except httpx.RequestError as exc:
            raise MCPProtocolError(f"MCP HTTP request failed: {exc}") from exc
        if response.status_code >= 400:
            raise MCPProtocolError(
                f"MCP HTTP request failed with HTTP {response.status_code}: {response.text[:300]}"
            )
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return _parse_sse_json(response.text)
        try:
            decoded = response.json()
        except ValueError as exc:
            raise MCPProtocolError("MCP HTTP response was not valid JSON") from exc
        if isinstance(decoded, list):
            for item in decoded:
                if isinstance(item, dict) and item.get("id") == payload.get("id"):
                    return item
            return {}
        if not isinstance(decoded, dict):
            raise MCPProtocolError("MCP HTTP response JSON must be an object")
        return decoded

    def close(self) -> None:
        return None


def _parse_sse_json(text: str) -> dict[str, Any]:
    event_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("data:"):
            value = line.split(":", 1)[1].strip()
            if value == "[DONE]":
                break
            event_lines.append(value)
    if not event_lines:
        raise MCPProtocolError("MCP SSE response did not contain data")
    raw = "\n".join(event_lines)
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MCPProtocolError("MCP SSE data was not valid JSON") from exc
    if not isinstance(decoded, dict):
        raise MCPProtocolError("MCP SSE JSON must be an object")
    return decoded
