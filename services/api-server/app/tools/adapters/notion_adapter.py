from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.tools.adapter_registry import AdapterRegistry, AdapterResult, timed_health_result
from app.tools.registry import RiskLevel, ToolMetadata

DEFAULT_NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
REQUEST_TIMEOUT_SECONDS = 15
MAX_TIMEOUT_SECONDS = 30
MAX_LIMIT = 50
TEXT_PREVIEW_CHARS = 2000


@dataclass(frozen=True)
class NotionAdapter:
    slug: str
    method: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk_level: RiskLevel = "low"

    server_label: str = "notion"
    requires_secret: bool = True
    module_path: str = "app.tools.adapters.notion_adapter"

    def execute(
        self,
        *,
        metadata: ToolMetadata,
        input_json: dict[str, Any],
        config_json: dict[str, Any] | None,
        secret_value: str | None,
        sandbox_workspace_root=None,
        sandbox_command_executor=None,
    ) -> AdapterResult:
        del metadata, sandbox_workspace_root, sandbox_command_executor
        endpoint = _endpoint_url(config_json)
        token = str(secret_value or "").strip()
        if not token:
            return AdapterResult(
                {"error": "missing_secret", "message": "Notion integration token is required"}
            )
        if self.method == "search_pages":
            output = _search_pages(endpoint=endpoint, token=token, input_json=input_json)
        elif self.method == "get_page":
            output = _get_page(endpoint=endpoint, token=token, input_json=input_json)
        elif self.method == "query_database":
            output = _query_database(endpoint=endpoint, token=token, input_json=input_json)
        elif self.method == "append_block":
            output = _append_block(endpoint=endpoint, token=token, input_json=input_json)
        else:
            output = {"error": "unsupported_method", "message": self.method}
        return AdapterResult(output)

    def health_check(
        self,
        *,
        config_json: dict[str, Any] | None,
        secret_value: str | None,
    ) -> dict[str, Any]:
        endpoint = _endpoint_url(config_json)
        token = str(secret_value or "").strip()
        if not token:
            return {
                "ok": False,
                "latency_ms": 0,
                "message": "Notion token is not configured",
                "sample": {},
            }

        def probe() -> dict[str, Any]:
            payload = _request_json(
                endpoint=endpoint,
                token=token,
                method="POST",
                path="/search",
                json_payload={"page_size": 1},
            )
            if isinstance(payload, dict) and payload.get("error"):
                return payload
            results = payload.get("results") if isinstance(payload, dict) else []
            return {"result_count": len(results) if isinstance(results, list) else 0}

        result = timed_health_result(
            probe,
            success_message="Notion API reachable",
            failure_prefix="Notion health check failed",
        )
        sample = result.get("sample")
        if isinstance(sample, dict) and sample.get("error"):
            result["ok"] = False
            result["message"] = str(sample.get("message") or "Notion API error")
        return result


def register_notion_adapters(registry: AdapterRegistry) -> None:
    for adapter in [
        NotionAdapter(
            slug="notion.search_pages",
            method="search_pages",
            description="Search Notion pages and databases.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
                },
                "required": ["query"],
            },
            output_schema={"type": "object", "properties": {"items": {"type": "array"}}},
        ),
        NotionAdapter(
            slug="notion.get_page",
            method="get_page",
            description="Get a Notion page and bounded child block preview.",
            input_schema={
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "minLength": 1},
                    "include_blocks": {"type": "boolean", "default": True},
                    "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 50},
                },
                "required": ["page_id"],
            },
            output_schema={"type": "object", "properties": {"page": {"type": "object"}}},
        ),
        NotionAdapter(
            slug="notion.query_database",
            method="query_database",
            description="Query a Notion database.",
            input_schema={
                "type": "object",
                "properties": {
                    "database_id": {"type": "string", "minLength": 1},
                    "filter": {"type": "object"},
                    "sorts": {"type": "array", "items": {"type": "object"}},
                    "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 50},
                },
                "required": ["database_id"],
            },
            output_schema={"type": "object", "properties": {"items": {"type": "array"}}},
        ),
        NotionAdapter(
            slug="notion.append_block",
            method="append_block",
            description="Append a paragraph block to a Notion page or block.",
            risk_level="high",
            input_schema={
                "type": "object",
                "properties": {
                    "parent_block_id": {"type": "string", "minLength": 1},
                    "text": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "idempotency_key": {"type": "string", "minLength": 1},
                },
                "required": ["parent_block_id", "text", "idempotency_key"],
            },
            output_schema={"type": "object", "properties": {"block": {"type": "object"}}},
        ),
    ]:
        registry.register(adapter)


def _endpoint_url(config_json: dict[str, Any] | None) -> str:
    config = config_json if isinstance(config_json, dict) else {}
    runtime = config.get("runtime") if isinstance(config.get("runtime"), dict) else {}
    endpoint = str(runtime.get("endpoint_url") or DEFAULT_NOTION_API).strip().rstrip("/")
    return endpoint or DEFAULT_NOTION_API


def _timeout(config_json: dict[str, Any] | None) -> float:
    config = config_json if isinstance(config_json, dict) else {}
    runtime = config.get("runtime") if isinstance(config.get("runtime"), dict) else {}
    raw = runtime.get("timeout_seconds", REQUEST_TIMEOUT_SECONDS)
    try:
        return float(min(max(int(raw), 1), MAX_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        return REQUEST_TIMEOUT_SECONDS


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
        "User-Agent": "AgentHarness/0.1",
    }


def _request_json(
    *,
    endpoint: str,
    token: str,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    json_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=_timeout(None), headers=_headers(token)) as client:
            response = client.request(
                method,
                f"{endpoint}{path}",
                params=params or {},
                json=json_payload,
            )
    except httpx.TimeoutException:
        return {"error": "timeout", "message": "Notion API request timed out"}
    except httpx.RequestError as exc:
        return {"error": "notion_request_error", "message": str(exc)[:300]}
    if response.status_code == 429:
        return {
            "error": "rate_limited",
            "status": 429,
            "retry_after": response.headers.get("retry-after"),
            "message": "Notion API rate limited the request",
        }
    if response.status_code >= 400:
        return _notion_error(response)
    try:
        payload = response.json()
    except ValueError:
        return {
            "error": "notion_api_error",
            "status": response.status_code,
            "message": "Invalid JSON",
        }
    return payload if isinstance(payload, dict) else {}


def _notion_error(response: httpx.Response) -> dict[str, Any]:
    message = response.text[:300]
    code = "notion_api_error"
    try:
        payload = response.json()
        if isinstance(payload, dict):
            code = str(payload.get("code") or code)
            message = str(payload.get("message") or message)[:300]
    except ValueError:
        pass
    return {
        "error": "notion_api_error",
        "code": code,
        "status": response.status_code,
        "message": message,
    }


def _limit(value: Any, default: int = 20) -> int:
    try:
        return max(1, min(int(value), MAX_LIMIT))
    except (TypeError, ValueError):
        return default


def _search_pages(*, endpoint: str, token: str, input_json: dict[str, Any]) -> dict[str, Any]:
    query = str(input_json.get("query") or "").strip()
    if not query:
        return {"error": "invalid_input", "message": "query is required"}
    limit = _limit(input_json.get("limit"), default=10)
    payload = _request_json(
        endpoint=endpoint,
        token=token,
        method="POST",
        path="/search",
        json_payload={"query": query[:200], "page_size": limit},
    )
    if payload.get("error"):
        return payload
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    return {
        "items": [_page_summary(item) for item in results if isinstance(item, dict)][:limit],
        "source": "notion-api",
        "tool": "notion.search_pages",
    }


def _get_page(*, endpoint: str, token: str, input_json: dict[str, Any]) -> dict[str, Any]:
    page_id = str(input_json.get("page_id") or "").strip()
    if not page_id:
        return {"error": "invalid_input", "message": "page_id is required"}
    page = _request_json(endpoint=endpoint, token=token, method="GET", path=f"/pages/{page_id}")
    if page.get("error"):
        return page
    blocks: list[dict[str, Any]] = []
    if bool(input_json.get("include_blocks", True)):
        block_payload = _request_json(
            endpoint=endpoint,
            token=token,
            method="GET",
            path=f"/blocks/{page_id}/children",
            params={"page_size": _limit(input_json.get("limit"))},
        )
        if block_payload.get("error"):
            return block_payload
        raw_blocks = (
            block_payload.get("results")
            if isinstance(block_payload.get("results"), list)
            else []
        )
        blocks = [_block_summary(block) for block in raw_blocks if isinstance(block, dict)]
    return {
        "page": _page_summary(page),
        "blocks": blocks,
        "source": "notion-api",
        "tool": "notion.get_page",
    }


def _query_database(*, endpoint: str, token: str, input_json: dict[str, Any]) -> dict[str, Any]:
    database_id = str(input_json.get("database_id") or "").strip()
    if not database_id:
        return {"error": "invalid_input", "message": "database_id is required"}
    body: dict[str, Any] = {"page_size": _limit(input_json.get("limit"))}
    if isinstance(input_json.get("filter"), dict):
        body["filter"] = input_json["filter"]
    if isinstance(input_json.get("sorts"), list):
        body["sorts"] = input_json["sorts"][:10]
    payload = _request_json(
        endpoint=endpoint,
        token=token,
        method="POST",
        path=f"/databases/{database_id}/query",
        json_payload=body,
    )
    if payload.get("error"):
        return payload
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    return {
        "items": [_page_summary(item) for item in results if isinstance(item, dict)],
        "source": "notion-api",
        "tool": "notion.query_database",
    }


def _append_block(*, endpoint: str, token: str, input_json: dict[str, Any]) -> dict[str, Any]:
    parent_block_id = str(input_json.get("parent_block_id") or "").strip()
    text = str(input_json.get("text") or "").strip()
    if not parent_block_id or not text:
        return {"error": "invalid_input", "message": "parent_block_id and text are required"}
    payload = _request_json(
        endpoint=endpoint,
        token=token,
        method="PATCH",
        path=f"/blocks/{parent_block_id}/children",
        json_payload={
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": text[:TEXT_PREVIEW_CHARS]},
                            }
                        ]
                    },
                }
            ]
        },
    )
    if payload.get("error"):
        return payload
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    block = _block_summary(results[0]) if results and isinstance(results[0], dict) else {}
    return {"block": block, "source": "notion-api", "tool": "notion.append_block"}


def _page_summary(page: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": page.get("id"),
        "object": page.get("object"),
        "url": page.get("url"),
        "title": _title_from_properties(page.get("properties")),
        "created_time": page.get("created_time"),
        "last_edited_time": page.get("last_edited_time"),
    }


def _block_summary(block: dict[str, Any]) -> dict[str, Any]:
    block_type = str(block.get("type") or "")
    typed = block.get(block_type) if isinstance(block.get(block_type), dict) else {}
    return {
        "id": block.get("id"),
        "type": block_type,
        "text_preview": _plain_text(typed.get("rich_text"))[:TEXT_PREVIEW_CHARS],
        "has_children": bool(block.get("has_children")),
    }


def _title_from_properties(properties: Any) -> str:
    if not isinstance(properties, dict):
        return ""
    for value in properties.values():
        if isinstance(value, dict) and value.get("type") == "title":
            return _plain_text(value.get("title"))[:TEXT_PREVIEW_CHARS]
    return ""


def _plain_text(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    parts = []
    for item in items:
        if isinstance(item, dict):
            parts.append(str(item.get("plain_text") or ""))
    return "".join(parts)
