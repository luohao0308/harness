from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.tools.adapter_registry import AdapterRegistry, AdapterResult, timed_health_result
from app.tools.registry import RiskLevel, ToolMetadata

DEFAULT_SLACK_API = "https://slack.com/api"
REQUEST_TIMEOUT_SECONDS = 15
MAX_TIMEOUT_SECONDS = 30
MAX_LIMIT = 100
USER_CACHE_TTL_SECONDS = 300
MENTION_RE = re.compile(r"<@([A-Z0-9]+)(?:\|([^>]+))?>")
LINK_RE = re.compile(r"<(https?://[^>|]+)\|([^>]+)>")
BARE_LINK_RE = re.compile(r"<(https?://[^>]+)>")

_USER_CACHE: dict[str, tuple[float, str]] = {}


@dataclass(frozen=True)
class SlackAdapter:
    slug: str
    method: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]

    server_label: str = "slack"
    requires_secret: bool = True
    risk_level: RiskLevel = "low"
    module_path: str = "app.tools.adapters.slack_adapter"

    def execute(
        self,
        *,
        metadata: ToolMetadata,
        input_json: dict[str, Any],
        config_json: dict[str, Any] | None,
        secret_value: str | None,
        sandbox_workspace_root=None,
    ) -> AdapterResult:
        del metadata, sandbox_workspace_root
        endpoint = _endpoint_url(config_json)
        token = str(secret_value or "").strip()
        if not token:
            return AdapterResult(
                {"error": "missing_secret", "message": "Slack bot token is required"}
            )
        if self.method == "search_messages":
            output = _search_messages(
                endpoint=endpoint, token=token, input_json=input_json, config_json=config_json
            )
        elif self.method == "list_channels":
            output = _list_channels(
                endpoint=endpoint, token=token, input_json=input_json, config_json=config_json
            )
        elif self.method == "get_thread":
            output = _get_thread(
                endpoint=endpoint, token=token, input_json=input_json, config_json=config_json
            )
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
                "message": "Slack bot token is not configured",
                "sample": {},
            }

        def probe() -> dict[str, Any]:
            payload = _slack_get(
                endpoint=endpoint,
                token=token,
                method="auth.test",
                params={},
                config_json=config_json,
            )
            return payload

        result = timed_health_result(
            probe,
            success_message="Slack API reachable",
            failure_prefix="Slack health check failed",
        )
        sample = result.get("sample")
        if isinstance(sample, dict) and sample.get("error"):
            result["ok"] = False
            result["message"] = str(
                sample.get("message") or sample.get("error") or "Slack API error"
            )
        return result


def register_slack_adapters(registry: AdapterRegistry) -> None:
    for adapter in [
        SlackAdapter(
            slug="slack.search_messages",
            method="search_messages",
            description="Search Slack messages.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "channel": {"type": "string"},
                    "user": {"type": "string"},
                    "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
                    "sort": {"type": "string", "enum": ["score", "timestamp"], "default": "score"},
                },
                "required": ["query"],
            },
            output_schema={"type": "object", "properties": {"items": {"type": "array"}}},
        ),
        SlackAdapter(
            slug="slack.list_channels",
            method="list_channels",
            description="List Slack channels visible to the token.",
            input_schema={
                "type": "object",
                "properties": {
                    "types": {"type": "string", "default": "public_channel,private_channel"},
                    "limit": {"type": "integer", "default": 100, "minimum": 1, "maximum": 100},
                },
            },
            output_schema={"type": "object", "properties": {"items": {"type": "array"}}},
        ),
        SlackAdapter(
            slug="slack.get_thread",
            method="get_thread",
            description="Get a Slack thread and replies.",
            input_schema={
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "minLength": 1},
                    "thread_ts": {"type": "string", "minLength": 1},
                },
                "required": ["channel", "thread_ts"],
            },
            output_schema={"type": "object", "properties": {"replies": {"type": "array"}}},
        ),
    ]:
        registry.register(adapter)


def _endpoint_url(config_json: dict[str, Any] | None) -> str:
    config = config_json if isinstance(config_json, dict) else {}
    runtime = config.get("runtime") if isinstance(config.get("runtime"), dict) else {}
    endpoint = str(runtime.get("endpoint_url") or DEFAULT_SLACK_API).strip().rstrip("/")
    return endpoint or DEFAULT_SLACK_API


def _timeout(config_json: dict[str, Any] | None) -> float:
    config = config_json if isinstance(config_json, dict) else {}
    runtime = config.get("runtime") if isinstance(config.get("runtime"), dict) else {}
    raw = runtime.get("timeout_seconds", REQUEST_TIMEOUT_SECONDS)
    try:
        return float(min(max(int(raw), 1), MAX_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        return REQUEST_TIMEOUT_SECONDS


def _limit(value: Any, default: int = 20) -> int:
    try:
        return max(1, min(int(value), MAX_LIMIT))
    except (TypeError, ValueError):
        return default


def _slack_get(
    *,
    endpoint: str,
    token: str,
    method: str,
    params: dict[str, Any],
    config_json: dict[str, Any] | None,
) -> dict[str, Any]:
    try:
        with httpx.Client(
            timeout=_timeout(config_json),
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        ) as client:
            response = client.get(f"{endpoint}/{method}", params=params)
    except httpx.TimeoutException:
        return {"error": "timeout", "message": "Slack API request timed out"}
    except httpx.RequestError as exc:
        return {"error": "slack_request_error", "message": str(exc)[:300]}
    try:
        payload = response.json()
    except ValueError:
        return {
            "error": "slack_api_error",
            "status": response.status_code,
            "message": "Invalid JSON",
        }
    if response.status_code == 429:
        return {
            "error": "rate_limited",
            "status": 429,
            "retry_after": response.headers.get("retry-after"),
            "message": "Slack API rate limited the request",
        }
    if response.status_code >= 400:
        return {
            "error": "slack_api_error",
            "status": response.status_code,
            "message": str(payload)[:300],
        }
    if isinstance(payload, dict) and not payload.get("ok", False):
        error = str(payload.get("error") or "slack_api_error")
        return {"error": "slack_api_error", "message": error, "slack_error": error}
    return payload if isinstance(payload, dict) else {}


def _search_messages(
    *,
    endpoint: str,
    token: str,
    input_json: dict[str, Any],
    config_json: dict[str, Any] | None,
) -> dict[str, Any]:
    query = str(input_json.get("query") or "").strip()
    if not query:
        return {"error": "invalid_input", "message": "query is required"}
    channel = str(input_json.get("channel") or "").strip()
    user = str(input_json.get("user") or "").strip()
    if channel:
        query = f"{query} in:{channel}"
    if user:
        query = f"{query} from:{user}"
    limit = _limit(input_json.get("limit"))
    payload = _slack_get(
        endpoint=endpoint,
        token=token,
        method="search.messages",
        params={
            "query": query[:500],
            "count": limit,
            "sort": str(input_json.get("sort") or "score"),
        },
        config_json=config_json,
    )
    if payload.get("error"):
        return payload
    matches = (
        payload.get("messages", {}).get("matches", [])
        if isinstance(payload.get("messages"), dict)
        else []
    )
    items = []
    for match in matches if isinstance(matches, list) else []:
        if not isinstance(match, dict):
            continue
        channel_obj = match.get("channel") if isinstance(match.get("channel"), dict) else {}
        user_id = str(match.get("user") or "")
        channel_name = channel_obj.get("name") or channel_obj.get("id") or ""
        items.append(
            {
                "channel": channel_name,
                "user": _resolve_user(
                    endpoint=endpoint, token=token, user_id=user_id, config_json=config_json
                ),
                "text": _mrkdwn_to_plain(
                    str(match.get("text") or ""),
                    endpoint=endpoint,
                    token=token,
                    config_json=config_json,
                ),
                "ts": match.get("ts"),
                "permalink": match.get("permalink"),
            }
        )
    return {"items": items[:limit], "source": "slack-api", "tool": "slack.search_messages"}


def _list_channels(
    *,
    endpoint: str,
    token: str,
    input_json: dict[str, Any],
    config_json: dict[str, Any] | None,
) -> dict[str, Any]:
    limit = _limit(input_json.get("limit"), default=100)
    payload = _slack_get(
        endpoint=endpoint,
        token=token,
        method="conversations.list",
        params={
            "types": str(input_json.get("types") or "public_channel,private_channel"),
            "limit": limit,
        },
        config_json=config_json,
    )
    if payload.get("error"):
        return payload
    channels = payload.get("channels") if isinstance(payload.get("channels"), list) else []
    return {
        "items": [
            {
                "id": channel.get("id"),
                "name": channel.get("name"),
                "is_private": bool(channel.get("is_private")),
                "num_members": channel.get("num_members"),
                "topic": _plain_text_obj(channel.get("topic")),
                "purpose": _plain_text_obj(channel.get("purpose")),
            }
            for channel in channels
            if isinstance(channel, dict)
        ][:limit],
        "source": "slack-api",
        "tool": "slack.list_channels",
    }


def _get_thread(
    *,
    endpoint: str,
    token: str,
    input_json: dict[str, Any],
    config_json: dict[str, Any] | None,
) -> dict[str, Any]:
    channel = str(input_json.get("channel") or "").strip()
    thread_ts = str(input_json.get("thread_ts") or "").strip()
    if not channel or not thread_ts:
        return {"error": "invalid_input", "message": "channel and thread_ts are required"}
    payload = _slack_get(
        endpoint=endpoint,
        token=token,
        method="conversations.replies",
        params={"channel": channel, "ts": thread_ts, "limit": MAX_LIMIT},
        config_json=config_json,
    )
    if payload.get("error"):
        return payload
    raw_replies = payload.get("messages") if isinstance(payload.get("messages"), list) else []
    replies = [
        {
            "user": _resolve_user(
                endpoint=endpoint,
                token=token,
                user_id=str(item.get("user") or ""),
                config_json=config_json,
            ),
            "text": _mrkdwn_to_plain(
                str(item.get("text") or ""), endpoint=endpoint, token=token, config_json=config_json
            ),
            "ts": item.get("ts"),
        }
        for item in raw_replies
        if isinstance(item, dict)
    ]
    root = replies[0] if replies else None
    return {
        "root": root,
        "replies": replies[1:] if replies else [],
        "source": "slack-api",
        "tool": "slack.get_thread",
    }


def _plain_text_obj(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("value") or "")
    return ""


def _resolve_user(
    *,
    endpoint: str,
    token: str,
    user_id: str,
    config_json: dict[str, Any] | None,
) -> str:
    if not user_id:
        return ""
    now = time.monotonic()
    cached = _USER_CACHE.get(user_id)
    if cached and now - cached[0] < USER_CACHE_TTL_SECONDS:
        return cached[1]
    payload = _slack_get(
        endpoint=endpoint,
        token=token,
        method="users.info",
        params={"user": user_id},
        config_json=config_json,
    )
    if payload.get("error"):
        return user_id
    profile = (
        payload.get("user", {}).get("profile", {}) if isinstance(payload.get("user"), dict) else {}
    )
    display = str(
        profile.get("display_name")
        or profile.get("real_name")
        or payload.get("user", {}).get("name")
        or user_id
    )
    _USER_CACHE[user_id] = (now, display)
    return display


def _mrkdwn_to_plain(
    text: str,
    *,
    endpoint: str,
    token: str,
    config_json: dict[str, Any] | None,
) -> str:
    def mention(match: re.Match[str]) -> str:
        label = match.group(2)
        if label:
            return f"@{label}"
        user_name = _resolve_user(
            endpoint=endpoint,
            token=token,
            user_id=match.group(1),
            config_json=config_json,
        )
        return f"@{user_name}"

    value = MENTION_RE.sub(mention, text)
    value = LINK_RE.sub(lambda match: match.group(2), value)
    value = BARE_LINK_RE.sub(lambda match: match.group(1), value)
    value = (
        value.replace("<!channel>", "@channel")
        .replace("<!here>", "@here")
        .replace("<!everyone>", "@everyone")
    )
    return value[:4000]
