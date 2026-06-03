from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class SSEEvent:
    event: str
    data: dict
    raw: str


def parse_sse_frame(frame: str) -> SSEEvent | None:
    lines = [line for line in frame.splitlines() if line.strip()]
    if not lines:
        return None
    event_name = ""
    data_lines: list[str] = []
    for line in lines:
        if line.startswith("event:"):
            event_name = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").strip())
    if not event_name or not data_lines:
        return None
    payload_text = "\n".join(data_lines)
    payload = json.loads(payload_text)
    if not isinstance(payload, dict):
        payload = {"value": payload}
    return SSEEvent(event=event_name, data=payload, raw=frame)


def parse_sse_stream(text: str) -> list[SSEEvent]:
    events: list[SSEEvent] = []
    for frame in text.split("\n\n"):
        event = parse_sse_frame(frame)
        if event is not None:
            events.append(event)
    return events


class HarnessApiClient:
    def __init__(self, api_url: str, token: str = "", timeout: float = 120.0) -> None:
        self.api_url = api_url.rstrip("/")
        self.token = token.strip()
        self.timeout = timeout

    @property
    def headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _client(self, *, timeout: float | None) -> httpx.Client:
        return httpx.Client(timeout=timeout, trust_env=False)

    def health(self) -> dict:
        with self._client(timeout=self.timeout) as client:
            response = client.get(f"{self.api_url}/health", headers=self.headers)
            response.raise_for_status()
            return response.json()

    def stream_chat(self, agent_id: str, payload: dict) -> Iterator[SSEEvent]:
        url = f"{self.api_url}/api/agents/{agent_id}/runs/chat/stream"
        with self._client(timeout=None) as client:
            with client.stream("POST", url, headers=self.headers, json=payload) as response:
                response.raise_for_status()
                buffer = ""
                for chunk in response.iter_text():
                    buffer += chunk
                    while "\n\n" in buffer:
                        frame, buffer = buffer.split("\n\n", 1)
                        event = parse_sse_frame(frame)
                        if event is not None:
                            yield event
                tail = parse_sse_frame(buffer)
                if tail is not None:
                    yield tail

    def record_local_tool_event(self, run_id: str, payload: dict) -> dict:
        url = f"{self.api_url}/api/agents/runs/{run_id}/local-tool-events"
        with self._client(timeout=self.timeout) as client:
            response = client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()

    def execute_sandbox_tool(self, run_id: str, tool_name: str, input_json: dict) -> dict:
        url = f"{self.api_url}/api/tasks/{run_id}/tools/execute"
        with self._client(timeout=self.timeout) as client:
            response = client.post(
                url,
                headers=self.headers,
                json={"tool_name": tool_name, "input_json": input_json},
            )
            response.raise_for_status()
            return response.json()
