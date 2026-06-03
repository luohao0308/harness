from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.tools.adapter_registry import AdapterRegistry, AdapterResult, timed_health_result
from app.tools.registry import RiskLevel, ToolMetadata

DEFAULT_GITHUB_API = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
REQUEST_TIMEOUT_SECONDS = 15
MAX_TIMEOUT_SECONDS = 30
MAX_LIST_LIMIT = 100
BODY_PREVIEW_CHARS = 1000
PATCH_PREVIEW_CHARS = 4000
SNIPPET_CHARS = 1200
REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class GitHubAdapter:
    slug: str
    method: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk_level: RiskLevel = "low"

    server_label: str = "github"
    requires_secret: bool = True
    module_path: str = "app.tools.adapters.github_adapter"

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
            return AdapterResult({"error": "missing_secret", "message": "GitHub token is required"})
        if self.method == "list_issues":
            output = _list_issues(endpoint=endpoint, token=token, input_json=input_json)
        elif self.method == "get_issue":
            output = _get_issue(endpoint=endpoint, token=token, input_json=input_json)
        elif self.method == "list_pulls":
            output = _list_pulls(endpoint=endpoint, token=token, input_json=input_json)
        elif self.method == "get_pull":
            output = _get_pull(endpoint=endpoint, token=token, input_json=input_json)
        elif self.method == "search_code":
            output = _search_code(endpoint=endpoint, token=token, input_json=input_json)
        elif self.method == "create_issue_comment":
            output = _create_issue_comment(endpoint=endpoint, token=token, input_json=input_json)
        elif self.method == "create_issue":
            output = _create_issue(endpoint=endpoint, token=token, input_json=input_json)
        elif self.method == "create_pull_review":
            output = _create_pull_review(endpoint=endpoint, token=token, input_json=input_json)
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
                "message": "GitHub token is not configured",
                "sample": {},
            }

        def probe() -> dict[str, Any]:
            with httpx.Client(timeout=_timeout(config_json), headers=_headers(token)) as client:
                response = client.get(f"{endpoint}/rate_limit")
            if response.status_code >= 400:
                return _github_error(response)
            payload = response.json()
            core = payload.get("resources", {}).get("core", {}) if isinstance(payload, dict) else {}
            return {
                "rate_remaining": core.get("remaining"),
                "rate_limit": core.get("limit"),
            }

        result = timed_health_result(
            probe,
            success_message="GitHub API reachable",
            failure_prefix="GitHub health check failed",
        )
        sample = result.get("sample")
        if isinstance(sample, dict) and sample.get("error"):
            result["ok"] = False
            result["message"] = str(sample.get("message") or "GitHub API error")
        return result


def register_github_adapters(registry: AdapterRegistry) -> None:
    for adapter in [
        GitHubAdapter(
            slug="github.list_issues",
            method="list_issues",
            description="List GitHub repository issues.",
            input_schema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "pattern": "owner/repo"},
                    "state": {
                        "type": "string",
                        "enum": ["open", "closed", "all"],
                        "default": "open",
                    },
                    "labels": {"type": "string"},
                    "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
                },
                "required": ["repo"],
            },
            output_schema={"type": "object", "properties": {"items": {"type": "array"}}},
        ),
        GitHubAdapter(
            slug="github.get_issue",
            method="get_issue",
            description="Get a GitHub issue and optional comments.",
            input_schema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "pattern": "owner/repo"},
                    "number": {"type": "integer", "minimum": 1},
                    "include_comments": {"type": "boolean", "default": False},
                },
                "required": ["repo", "number"],
            },
            output_schema={"type": "object", "properties": {"issue": {"type": "object"}}},
        ),
        GitHubAdapter(
            slug="github.list_pulls",
            method="list_pulls",
            description="List GitHub pull requests.",
            input_schema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "pattern": "owner/repo"},
                    "state": {
                        "type": "string",
                        "enum": ["open", "closed", "all"],
                        "default": "open",
                    },
                    "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
                },
                "required": ["repo"],
            },
            output_schema={"type": "object", "properties": {"items": {"type": "array"}}},
        ),
        GitHubAdapter(
            slug="github.get_pull",
            method="get_pull",
            description="Get a GitHub pull request and changed files.",
            input_schema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "pattern": "owner/repo"},
                    "number": {"type": "integer", "minimum": 1},
                },
                "required": ["repo", "number"],
            },
            output_schema={"type": "object", "properties": {"pull": {"type": "object"}}},
        ),
        GitHubAdapter(
            slug="github.search_code",
            method="search_code",
            description="Search code with GitHub Search API.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "repo": {"type": "string", "pattern": "owner/repo"},
                    "language": {"type": "string"},
                    "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
                },
                "required": ["query"],
            },
            output_schema={"type": "object", "properties": {"items": {"type": "array"}}},
        ),
        GitHubAdapter(
            slug="github.create_issue_comment",
            method="create_issue_comment",
            description="Create a comment on a GitHub issue or pull request.",
            risk_level="high",
            input_schema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "pattern": "owner/repo"},
                    "number": {"type": "integer", "minimum": 1},
                    "body": {"type": "string", "minLength": 1, "maxLength": 65536},
                    "idempotency_key": {"type": "string", "minLength": 1},
                },
                "required": ["repo", "number", "body", "idempotency_key"],
            },
            output_schema={"type": "object", "properties": {"comment": {"type": "object"}}},
        ),
        GitHubAdapter(
            slug="github.create_issue",
            method="create_issue",
            description="Create a GitHub issue.",
            risk_level="high",
            input_schema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "pattern": "owner/repo"},
                    "title": {"type": "string", "minLength": 1, "maxLength": 256},
                    "body": {"type": "string", "maxLength": 65536},
                    "labels": {"type": "array", "items": {"type": "string"}},
                    "assignees": {"type": "array", "items": {"type": "string"}},
                    "idempotency_key": {"type": "string", "minLength": 1},
                },
                "required": ["repo", "title", "idempotency_key"],
            },
            output_schema={"type": "object", "properties": {"issue": {"type": "object"}}},
        ),
        GitHubAdapter(
            slug="github.create_pull_review",
            method="create_pull_review",
            description="Create a GitHub pull request review.",
            risk_level="high",
            input_schema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "pattern": "owner/repo"},
                    "number": {"type": "integer", "minimum": 1},
                    "body": {"type": "string", "maxLength": 65536},
                    "event": {
                        "type": "string",
                        "enum": ["APPROVE", "REQUEST_CHANGES", "COMMENT"],
                    },
                    "idempotency_key": {"type": "string", "minLength": 1},
                },
                "required": ["repo", "number", "event", "idempotency_key"],
            },
            output_schema={"type": "object", "properties": {"review": {"type": "object"}}},
        ),
    ]:
        registry.register(adapter)


def _endpoint_url(config_json: dict[str, Any] | None) -> str:
    config = config_json if isinstance(config_json, dict) else {}
    runtime = config.get("runtime") if isinstance(config.get("runtime"), dict) else {}
    endpoint = str(runtime.get("endpoint_url") or DEFAULT_GITHUB_API).strip().rstrip("/")
    return endpoint or DEFAULT_GITHUB_API


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
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": "AgentHarness/0.1",
    }


def _client(endpoint: str, token: str, config_json: dict[str, Any] | None = None) -> httpx.Client:
    del endpoint
    return httpx.Client(timeout=_timeout(config_json), headers=_headers(token))


def _validate_repo(repo: Any) -> str | None:
    value = str(repo or "").strip()
    if not REPO_PATTERN.match(value):
        return None
    return value


def _limit(value: Any, default: int = 20) -> int:
    try:
        return max(1, min(int(value), MAX_LIST_LIMIT))
    except (TypeError, ValueError):
        return default


def _request_json(
    *,
    endpoint: str,
    token: str,
    path: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any] | list[Any]:
    try:
        with _client(endpoint, token) as client:
            response = client.get(f"{endpoint}{path}", params=params or {})
    except httpx.TimeoutException:
        return {"error": "timeout", "message": "GitHub API request timed out"}
    except httpx.RequestError as exc:
        return {"error": "github_request_error", "message": str(exc)[:300]}
    if response.status_code >= 400:
        return _github_error(response)
    try:
        payload = response.json()
    except ValueError:
        return {
            "error": "github_api_error",
            "status": response.status_code,
            "message": "Invalid JSON",
        }
    return payload if isinstance(payload, (dict, list)) else {}


def _request_write_json(
    *,
    endpoint: str,
    token: str,
    path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    last_error: dict[str, Any] | None = None
    for _attempt in range(3):
        try:
            with _client(endpoint, token) as client:
                response = client.post(f"{endpoint}{path}", json=payload)
        except httpx.TimeoutException:
            last_error = {"error": "timeout", "message": "GitHub API request timed out"}
            continue
        except httpx.RequestError as exc:
            last_error = {"error": "github_request_error", "message": str(exc)[:300]}
            continue
        if response.status_code >= 400:
            return _github_error(response)
        try:
            decoded = response.json()
        except ValueError:
            return {
                "error": "github_api_error",
                "status": response.status_code,
                "message": "Invalid JSON",
            }
        return decoded if isinstance(decoded, dict) else {}
    return last_error or {"error": "github_request_error", "message": "GitHub request failed"}


def _github_error(response: httpx.Response) -> dict[str, Any]:
    message = response.text[:300]
    try:
        payload = response.json()
        if isinstance(payload, dict) and payload.get("message"):
            message = str(payload["message"])[:300]
    except ValueError:
        pass
    if response.status_code in {429, 403} and response.headers.get("x-ratelimit-remaining") == "0":
        return {
            "error": "rate_limited",
            "status": response.status_code,
            "reset_at": response.headers.get("x-ratelimit-reset"),
            "message": message,
        }
    return {"error": "github_api_error", "status": response.status_code, "message": message}


def _list_issues(*, endpoint: str, token: str, input_json: dict[str, Any]) -> dict[str, Any]:
    repo = _validate_repo(input_json.get("repo"))
    if repo is None:
        return {"error": "invalid_input", "message": "repo must be in owner/repo format"}
    limit = _limit(input_json.get("limit"))
    params = {
        "state": str(input_json.get("state") or "open"),
        "per_page": limit,
    }
    labels = str(input_json.get("labels") or "").strip()
    if labels:
        params["labels"] = labels
    payload = _request_json(
        endpoint=endpoint, token=token, path=f"/repos/{repo}/issues", params=params
    )
    if isinstance(payload, dict) and payload.get("error"):
        return payload
    items = []
    for issue in payload if isinstance(payload, list) else []:
        if not isinstance(issue, dict) or "pull_request" in issue:
            continue
        items.append(_issue_summary(issue))
    return {"items": items[:limit], "source": "github-api", "tool": "github.list_issues"}


def _get_issue(*, endpoint: str, token: str, input_json: dict[str, Any]) -> dict[str, Any]:
    repo = _validate_repo(input_json.get("repo"))
    number = _positive_int(input_json.get("number"))
    if repo is None or number is None:
        return {"error": "invalid_input", "message": "repo and positive issue number are required"}
    issue = _request_json(endpoint=endpoint, token=token, path=f"/repos/{repo}/issues/{number}")
    if isinstance(issue, dict) and issue.get("error"):
        return issue
    comments: list[dict[str, Any]] = []
    if bool(input_json.get("include_comments")):
        comment_payload = _request_json(
            endpoint=endpoint,
            token=token,
            path=f"/repos/{repo}/issues/{number}/comments",
            params={"per_page": 50},
        )
        if isinstance(comment_payload, dict) and comment_payload.get("error"):
            return comment_payload
        comments = [
            {
                "author": _login(comment.get("user")),
                "body": _truncate(str(comment.get("body") or ""), BODY_PREVIEW_CHARS),
                "created_at": comment.get("created_at"),
            }
            for comment in comment_payload
            if isinstance(comment, dict)
        ]
    return {
        "issue": _issue_summary(issue if isinstance(issue, dict) else {}),
        "comments": comments,
        "source": "github-api",
        "tool": "github.get_issue",
    }


def _list_pulls(*, endpoint: str, token: str, input_json: dict[str, Any]) -> dict[str, Any]:
    repo = _validate_repo(input_json.get("repo"))
    if repo is None:
        return {"error": "invalid_input", "message": "repo must be in owner/repo format"}
    limit = _limit(input_json.get("limit"))
    payload = _request_json(
        endpoint=endpoint,
        token=token,
        path=f"/repos/{repo}/pulls",
        params={"state": str(input_json.get("state") or "open"), "per_page": limit},
    )
    if isinstance(payload, dict) and payload.get("error"):
        return payload
    return {
        "items": [_pull_summary(pull) for pull in payload if isinstance(pull, dict)][:limit],
        "source": "github-api",
        "tool": "github.list_pulls",
    }


def _get_pull(*, endpoint: str, token: str, input_json: dict[str, Any]) -> dict[str, Any]:
    repo = _validate_repo(input_json.get("repo"))
    number = _positive_int(input_json.get("number"))
    if repo is None or number is None:
        return {"error": "invalid_input", "message": "repo and positive PR number are required"}
    pull = _request_json(endpoint=endpoint, token=token, path=f"/repos/{repo}/pulls/{number}")
    if isinstance(pull, dict) and pull.get("error"):
        return pull
    files_payload = _request_json(
        endpoint=endpoint,
        token=token,
        path=f"/repos/{repo}/pulls/{number}/files",
        params={"per_page": MAX_LIST_LIMIT},
    )
    if isinstance(files_payload, dict) and files_payload.get("error"):
        return files_payload
    files = [
        {
            "filename": str(file.get("filename") or ""),
            "status": str(file.get("status") or ""),
            "additions": int(file.get("additions") or 0),
            "deletions": int(file.get("deletions") or 0),
            "patch_preview": _truncate(str(file.get("patch") or ""), PATCH_PREVIEW_CHARS),
        }
        for file in files_payload
        if isinstance(file, dict)
    ]
    return {
        "pull": _pull_summary(pull if isinstance(pull, dict) else {}),
        "files": files,
        "source": "github-api",
        "tool": "github.get_pull",
    }


def _search_code(*, endpoint: str, token: str, input_json: dict[str, Any]) -> dict[str, Any]:
    query = str(input_json.get("query") or "").strip()
    if not query:
        return {"error": "invalid_input", "message": "query is required"}
    repo = str(input_json.get("repo") or "").strip()
    if repo and not _validate_repo(repo):
        return {"error": "invalid_input", "message": "repo must be in owner/repo format"}
    language = str(input_json.get("language") or "").strip()
    if repo:
        query = f"{query} repo:{repo}"
    if language:
        query = f"{query} language:{language}"
    limit = _limit(input_json.get("limit"))
    payload = _request_json(
        endpoint=endpoint,
        token=token,
        path="/search/code",
        params={"q": query[:400], "per_page": limit},
    )
    if isinstance(payload, dict) and payload.get("error"):
        return payload
    raw_items = payload.get("items") if isinstance(payload, dict) else []
    items = []
    for item in raw_items if isinstance(raw_items, list) else []:
        if not isinstance(item, dict):
            continue
        repository = item.get("repository") if isinstance(item.get("repository"), dict) else {}
        items.append(
            {
                "repo": repository.get("full_name"),
                "path": item.get("path"),
                "html_url": item.get("html_url"),
                "snippet": _truncate(
                    str(item.get("name") or item.get("path") or ""), SNIPPET_CHARS
                ),
            }
        )
    return {"items": items, "source": "github-api", "tool": "github.search_code"}


def _create_issue_comment(
    *,
    endpoint: str,
    token: str,
    input_json: dict[str, Any],
) -> dict[str, Any]:
    repo = _validate_repo(input_json.get("repo"))
    number = _positive_int(input_json.get("number"))
    body = str(input_json.get("body") or "").strip()
    if repo is None or number is None or not body:
        return {"error": "invalid_input", "message": "repo, number, and body are required"}
    payload = _request_write_json(
        endpoint=endpoint,
        token=token,
        path=f"/repos/{repo}/issues/{number}/comments",
        payload={"body": body[:65536]},
    )
    if payload.get("error"):
        return payload
    return {
        "comment": _comment_summary(payload),
        "source": "github-api",
        "tool": "github.create_issue_comment",
    }


def _create_issue(*, endpoint: str, token: str, input_json: dict[str, Any]) -> dict[str, Any]:
    repo = _validate_repo(input_json.get("repo"))
    title = str(input_json.get("title") or "").strip()
    if repo is None or not title:
        return {"error": "invalid_input", "message": "repo and title are required"}
    payload = {"title": title[:256]}
    body = str(input_json.get("body") or "")
    if body:
        payload["body"] = body[:65536]
    labels = _string_list(input_json.get("labels"))
    assignees = _string_list(input_json.get("assignees"))
    if labels:
        payload["labels"] = labels[:20]
    if assignees:
        payload["assignees"] = assignees[:20]
    result = _request_write_json(
        endpoint=endpoint,
        token=token,
        path=f"/repos/{repo}/issues",
        payload=payload,
    )
    if result.get("error"):
        return result
    return {"issue": _issue_summary(result), "source": "github-api", "tool": "github.create_issue"}


def _create_pull_review(
    *,
    endpoint: str,
    token: str,
    input_json: dict[str, Any],
) -> dict[str, Any]:
    repo = _validate_repo(input_json.get("repo"))
    number = _positive_int(input_json.get("number"))
    event = str(input_json.get("event") or "").upper()
    if repo is None or number is None or event not in {"APPROVE", "REQUEST_CHANGES", "COMMENT"}:
        return {
            "error": "invalid_input",
            "message": "repo, number, and event APPROVE/REQUEST_CHANGES/COMMENT are required",
        }
    payload: dict[str, Any] = {"event": event}
    body = str(input_json.get("body") or "")
    if body:
        payload["body"] = body[:65536]
    result = _request_write_json(
        endpoint=endpoint,
        token=token,
        path=f"/repos/{repo}/pulls/{number}/reviews",
        payload=payload,
    )
    if result.get("error"):
        return result
    return {
        "review": {
            "id": result.get("id"),
            "state": result.get("state"),
            "body_preview": _truncate(str(result.get("body") or ""), BODY_PREVIEW_CHARS),
            "url": result.get("html_url"),
            "author": _login(result.get("user")),
        },
        "source": "github-api",
        "tool": "github.create_pull_review",
    }


def _issue_summary(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": issue.get("number"),
        "title": issue.get("title"),
        "state": issue.get("state"),
        "url": issue.get("html_url"),
        "author": _login(issue.get("user")),
        "created_at": issue.get("created_at"),
        "body_preview": _truncate(str(issue.get("body") or ""), BODY_PREVIEW_CHARS),
    }


def _pull_summary(pull: dict[str, Any]) -> dict[str, Any]:
    base = pull.get("base") if isinstance(pull.get("base"), dict) else {}
    head = pull.get("head") if isinstance(pull.get("head"), dict) else {}
    return {
        "number": pull.get("number"),
        "title": pull.get("title"),
        "state": pull.get("state"),
        "url": pull.get("html_url"),
        "base": base.get("ref"),
        "head": head.get("ref"),
        "mergeable": pull.get("mergeable"),
        "author": _login(pull.get("user")),
    }


def _comment_summary(comment: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": comment.get("id"),
        "url": comment.get("html_url"),
        "author": _login(comment.get("user")),
        "created_at": comment.get("created_at"),
        "body_preview": _truncate(str(comment.get("body") or ""), BODY_PREVIEW_CHARS),
    }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _login(user: Any) -> str:
    return str(user.get("login") or "") if isinstance(user, dict) else ""


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _truncate(value: str, limit: int) -> str:
    return value[:limit]


def encode_repo_path(repo: str) -> str:
    owner, name = repo.split("/", 1)
    return f"{quote(owner, safe='')}/{quote(name, safe='')}"
