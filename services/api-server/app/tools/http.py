from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NetworkRequest:
    method: str
    url: str
    headers: dict
    body: dict | None = None


@dataclass(frozen=True)
class NetworkResponse:
    status_code: int
    body_preview: str


class RestrictedHttpTool:
    requires_sandbox = True

    def build_sandbox_command(self, request: NetworkRequest) -> list[str]:
        method = request.method.upper()
        return [
            "python",
            "-m",
            "http.client",
            method,
            request.url,
        ]
