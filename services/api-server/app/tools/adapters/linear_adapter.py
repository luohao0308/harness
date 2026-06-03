from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.tools.adapter_registry import AdapterRegistry, AdapterResult, timed_health_result
from app.tools.registry import RiskLevel, ToolMetadata

DEFAULT_LINEAR_API = "https://api.linear.app/graphql"
REQUEST_TIMEOUT_SECONDS = 15
MAX_TIMEOUT_SECONDS = 30
MAX_LIMIT = 50
TEXT_PREVIEW_CHARS = 2000


@dataclass(frozen=True)
class LinearAdapter:
    slug: str
    method: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk_level: RiskLevel = "low"

    server_label: str = "linear"
    requires_secret: bool = True
    module_path: str = "app.tools.adapters.linear_adapter"

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
                {"error": "missing_secret", "message": "Linear API token is required"}
            )
        if self.method == "list_issues":
            output = _list_issues(endpoint=endpoint, token=token, input_json=input_json)
        elif self.method == "get_issue":
            output = _get_issue(endpoint=endpoint, token=token, input_json=input_json)
        elif self.method == "create_issue":
            output = _create_issue(endpoint=endpoint, token=token, input_json=input_json)
        elif self.method == "create_comment":
            output = _create_comment(endpoint=endpoint, token=token, input_json=input_json)
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
                "message": "Linear API token is not configured",
                "sample": {},
            }

        def probe() -> dict[str, Any]:
            return _graphql(
                endpoint=endpoint,
                token=token,
                query="query Viewer { viewer { id name } }",
                variables={},
            )

        result = timed_health_result(
            probe,
            success_message="Linear API reachable",
            failure_prefix="Linear health check failed",
        )
        sample = result.get("sample")
        if isinstance(sample, dict) and sample.get("error"):
            result["ok"] = False
            result["message"] = str(sample.get("message") or "Linear API error")
        return result


def register_linear_adapters(registry: AdapterRegistry) -> None:
    for adapter in [
        LinearAdapter(
            slug="linear.list_issues",
            method="list_issues",
            description="List Linear issues.",
            input_schema={
                "type": "object",
                "properties": {
                    "team_key": {"type": "string"},
                    "query": {"type": "string"},
                    "state": {"type": "string"},
                    "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 50},
                },
            },
            output_schema={"type": "object", "properties": {"items": {"type": "array"}}},
        ),
        LinearAdapter(
            slug="linear.get_issue",
            method="get_issue",
            description="Get a Linear issue and comments.",
            input_schema={
                "type": "object",
                "properties": {
                    "issue_id": {"type": "string", "minLength": 1},
                    "include_comments": {"type": "boolean", "default": True},
                },
                "required": ["issue_id"],
            },
            output_schema={"type": "object", "properties": {"issue": {"type": "object"}}},
        ),
        LinearAdapter(
            slug="linear.create_issue",
            method="create_issue",
            description="Create a Linear issue.",
            risk_level="high",
            input_schema={
                "type": "object",
                "properties": {
                    "team_id": {"type": "string", "minLength": 1},
                    "title": {"type": "string", "minLength": 1, "maxLength": 256},
                    "description": {"type": "string", "maxLength": 65536},
                    "priority": {"type": "integer", "minimum": 0, "maximum": 4},
                    "idempotency_key": {"type": "string", "minLength": 1},
                },
                "required": ["team_id", "title", "idempotency_key"],
            },
            output_schema={"type": "object", "properties": {"issue": {"type": "object"}}},
        ),
        LinearAdapter(
            slug="linear.create_comment",
            method="create_comment",
            description="Create a Linear issue comment.",
            risk_level="high",
            input_schema={
                "type": "object",
                "properties": {
                    "issue_id": {"type": "string", "minLength": 1},
                    "body": {"type": "string", "minLength": 1, "maxLength": 65536},
                    "idempotency_key": {"type": "string", "minLength": 1},
                },
                "required": ["issue_id", "body", "idempotency_key"],
            },
            output_schema={"type": "object", "properties": {"comment": {"type": "object"}}},
        ),
    ]:
        registry.register(adapter)


def _endpoint_url(config_json: dict[str, Any] | None) -> str:
    config = config_json if isinstance(config_json, dict) else {}
    runtime = config.get("runtime") if isinstance(config.get("runtime"), dict) else {}
    endpoint = str(runtime.get("endpoint_url") or DEFAULT_LINEAR_API).strip()
    return endpoint or DEFAULT_LINEAR_API


def _timeout(config_json: dict[str, Any] | None) -> float:
    config = config_json if isinstance(config_json, dict) else {}
    runtime = config.get("runtime") if isinstance(config.get("runtime"), dict) else {}
    raw = runtime.get("timeout_seconds", REQUEST_TIMEOUT_SECONDS)
    try:
        return float(min(max(int(raw), 1), MAX_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        return REQUEST_TIMEOUT_SECONDS


def _graphql(
    *,
    endpoint: str,
    token: str,
    query: str,
    variables: dict[str, Any],
) -> dict[str, Any]:
    try:
        with httpx.Client(
            timeout=_timeout(None),
            headers={
                "Authorization": token,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "AgentHarness/0.1",
            },
        ) as client:
            response = client.post(endpoint, json={"query": query, "variables": variables})
    except httpx.TimeoutException:
        return {"error": "timeout", "message": "Linear API request timed out"}
    except httpx.RequestError as exc:
        return {"error": "linear_request_error", "message": str(exc)[:300]}
    if response.status_code == 429:
        return {
            "error": "rate_limited",
            "status": 429,
            "retry_after": response.headers.get("retry-after"),
            "message": "Linear API rate limited the request",
        }
    if response.status_code >= 400:
        return {
            "error": "linear_api_error",
            "status": response.status_code,
            "message": response.text[:300],
        }
    try:
        payload = response.json()
    except ValueError:
        return {
            "error": "linear_api_error",
            "status": response.status_code,
            "message": "Invalid JSON",
        }
    if isinstance(payload, dict) and payload.get("errors"):
        return {"error": "linear_api_error", "message": str(payload.get("errors"))[:300]}
    return payload if isinstance(payload, dict) else {}


def _limit(value: Any, default: int = 20) -> int:
    try:
        return max(1, min(int(value), MAX_LIMIT))
    except (TypeError, ValueError):
        return default


def _list_issues(*, endpoint: str, token: str, input_json: dict[str, Any]) -> dict[str, Any]:
    limit = _limit(input_json.get("limit"))
    filter_parts: dict[str, Any] = {}
    team_key = str(input_json.get("team_key") or "").strip()
    state = str(input_json.get("state") or "").strip()
    if team_key:
        filter_parts["team"] = {"key": {"eq": team_key}}
    if state:
        filter_parts["state"] = {"name": {"eq": state}}
    query_text = str(input_json.get("query") or "").strip()
    if query_text:
        filter_parts["title"] = {"containsIgnoreCase": query_text[:200]}
    payload = _graphql(
        endpoint=endpoint,
        token=token,
        query="""
        query Issues($first: Int!, $filter: IssueFilter) {
          issues(first: $first, filter: $filter) {
            nodes {
              id identifier title url updatedAt
              state { name }
              team { key name }
              assignee { name email }
            }
          }
        }
        """,
        variables={"first": limit, "filter": filter_parts or None},
    )
    if payload.get("error"):
        return payload
    nodes = payload.get("data", {}).get("issues", {}).get("nodes", [])
    return {
        "items": [_issue_summary(issue) for issue in nodes if isinstance(issue, dict)],
        "source": "linear-api",
        "tool": "linear.list_issues",
    }


def _get_issue(*, endpoint: str, token: str, input_json: dict[str, Any]) -> dict[str, Any]:
    issue_id = str(input_json.get("issue_id") or "").strip()
    if not issue_id:
        return {"error": "invalid_input", "message": "issue_id is required"}
    payload = _graphql(
        endpoint=endpoint,
        token=token,
        query="""
        query Issue($id: String!) {
          issue(id: $id) {
            id identifier title description url
            state { name }
            team { key name }
            assignee { name email }
            comments(first: 20) { nodes { id body createdAt user { name email } } }
          }
        }
        """,
        variables={"id": issue_id},
    )
    if payload.get("error"):
        return payload
    issue = payload.get("data", {}).get("issue")
    if not isinstance(issue, dict):
        return {"error": "not_found", "message": "Linear issue was not found"}
    comments_obj = issue.get("comments") if isinstance(issue.get("comments"), dict) else {}
    comments = comments_obj.get("nodes", []) if isinstance(comments_obj, dict) else []
    return {
        "issue": _issue_summary(issue, include_description=True),
        "comments": [
            _comment_summary(comment) for comment in comments if isinstance(comment, dict)
        ],
        "source": "linear-api",
        "tool": "linear.get_issue",
    }


def _create_issue(*, endpoint: str, token: str, input_json: dict[str, Any]) -> dict[str, Any]:
    team_id = str(input_json.get("team_id") or "").strip()
    title = str(input_json.get("title") or "").strip()
    if not team_id or not title:
        return {"error": "invalid_input", "message": "team_id and title are required"}
    issue_input: dict[str, Any] = {"teamId": team_id, "title": title[:256]}
    description = str(input_json.get("description") or "")
    if description:
        issue_input["description"] = description[:65536]
    if input_json.get("priority") is not None:
        try:
            issue_input["priority"] = max(0, min(int(input_json["priority"]), 4))
        except (TypeError, ValueError):
            return {"error": "invalid_input", "message": "priority must be an integer 0-4"}
    payload = _graphql(
        endpoint=endpoint,
        token=token,
        query="""
        mutation CreateIssue($input: IssueCreateInput!) {
          issueCreate(input: $input) {
            success
            issue { id identifier title url state { name } team { key name } }
          }
        }
        """,
        variables={"input": issue_input},
    )
    if payload.get("error"):
        return payload
    result = payload.get("data", {}).get("issueCreate", {})
    if not isinstance(result, dict) or not result.get("success"):
        return {"error": "linear_api_error", "message": "Linear issueCreate did not succeed"}
    return {
        "issue": _issue_summary(result.get("issue") or {}),
        "source": "linear-api",
        "tool": "linear.create_issue",
    }


def _create_comment(*, endpoint: str, token: str, input_json: dict[str, Any]) -> dict[str, Any]:
    issue_id = str(input_json.get("issue_id") or "").strip()
    body = str(input_json.get("body") or "").strip()
    if not issue_id or not body:
        return {"error": "invalid_input", "message": "issue_id and body are required"}
    payload = _graphql(
        endpoint=endpoint,
        token=token,
        query="""
        mutation CreateComment($input: CommentCreateInput!) {
          commentCreate(input: $input) {
            success
            comment { id body createdAt user { name email } }
          }
        }
        """,
        variables={"input": {"issueId": issue_id, "body": body[:65536]}},
    )
    if payload.get("error"):
        return payload
    result = payload.get("data", {}).get("commentCreate", {})
    if not isinstance(result, dict) or not result.get("success"):
        return {"error": "linear_api_error", "message": "Linear commentCreate did not succeed"}
    return {
        "comment": _comment_summary(result.get("comment") or {}),
        "source": "linear-api",
        "tool": "linear.create_comment",
    }


def _issue_summary(issue: dict[str, Any], *, include_description: bool = False) -> dict[str, Any]:
    state = issue.get("state") if isinstance(issue.get("state"), dict) else {}
    team = issue.get("team") if isinstance(issue.get("team"), dict) else {}
    assignee = issue.get("assignee") if isinstance(issue.get("assignee"), dict) else {}
    output = {
        "id": issue.get("id"),
        "identifier": issue.get("identifier"),
        "title": issue.get("title"),
        "url": issue.get("url"),
        "state": state.get("name"),
        "team": team.get("key") or team.get("name"),
        "assignee": assignee.get("name") or assignee.get("email"),
        "updated_at": issue.get("updatedAt"),
    }
    if include_description:
        output["description_preview"] = str(issue.get("description") or "")[:TEXT_PREVIEW_CHARS]
    return output


def _comment_summary(comment: dict[str, Any]) -> dict[str, Any]:
    user = comment.get("user") if isinstance(comment.get("user"), dict) else {}
    return {
        "id": comment.get("id"),
        "body_preview": str(comment.get("body") or "")[:TEXT_PREVIEW_CHARS],
        "created_at": comment.get("createdAt"),
        "author": user.get("name") or user.get("email"),
    }
