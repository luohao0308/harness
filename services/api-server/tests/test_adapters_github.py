import httpx

from app.tools.adapters.github_adapter import GitHubAdapter
from app.tools.registry import ToolRegistry


class FakeGitHubClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def __enter__(self) -> "FakeGitHubClient":
        return self

    def __exit__(self, *args) -> None:
        return None

    def get(self, url: str, params: dict | None = None) -> httpx.Response:
        self.calls.append({"url": url, "params": params or {}})
        return self.responses.pop(0)


def _adapter(method: str) -> GitHubAdapter:
    return GitHubAdapter(
        slug=f"github.{method}",
        method=method,
        description=method,
        input_schema={},
        output_schema={},
    )


def _metadata(name: str):
    return ToolRegistry.default().tools[name]


def test_github_list_issues_parses_items_and_truncates_body(monkeypatch) -> None:
    fake = FakeGitHubClient(
        [
            httpx.Response(
                200,
                json=[
                    {
                        "number": 7,
                        "title": "Bug",
                        "state": "open",
                        "html_url": "https://github.test/acme/repo/issues/7",
                        "user": {"login": "octo"},
                        "created_at": "2026-05-28T00:00:00Z",
                        "body": "x" * 1200,
                    },
                    {"number": 8, "pull_request": {}},
                ],
            )
        ]
    )
    monkeypatch.setattr("app.tools.adapters.github_adapter._client", lambda *args, **kwargs: fake)

    result = _adapter("list_issues").execute(
        metadata=_metadata("github.list_issues"),
        input_json={"repo": "acme/repo", "limit": 5},
        config_json={"runtime": {"endpoint_url": "https://github.test"}},
        secret_value="ghp_test",
    )

    assert fake.calls[0]["url"] == "https://github.test/repos/acme/repo/issues"
    assert fake.calls[0]["params"]["per_page"] == 5
    assert result.output_json["source"] == "github-api"
    assert len(result.output_json["items"]) == 1
    assert result.output_json["items"][0]["author"] == "octo"
    assert len(result.output_json["items"][0]["body_preview"]) == 1000


def test_github_get_pull_fetches_files(monkeypatch) -> None:
    fake = FakeGitHubClient(
        [
            httpx.Response(
                200,
                json={
                    "number": 3,
                    "title": "Change",
                    "state": "open",
                    "html_url": "https://github.test/acme/repo/pull/3",
                    "base": {"ref": "main"},
                    "head": {"ref": "feature"},
                    "mergeable": True,
                    "user": {"login": "dev"},
                },
            ),
            httpx.Response(
                200,
                json=[
                    {
                        "filename": "app.py",
                        "status": "modified",
                        "additions": 2,
                        "deletions": 1,
                        "patch": "p" * 5000,
                    }
                ],
            ),
        ]
    )
    monkeypatch.setattr("app.tools.adapters.github_adapter._client", lambda *args, **kwargs: fake)

    result = _adapter("get_pull").execute(
        metadata=_metadata("github.get_pull"),
        input_json={"repo": "acme/repo", "number": 3},
        config_json=None,
        secret_value="ghp_test",
    )

    assert result.output_json["pull"]["base"] == "main"
    assert result.output_json["files"][0]["filename"] == "app.py"
    assert len(result.output_json["files"][0]["patch_preview"]) == 4000


def test_github_search_code_builds_query(monkeypatch) -> None:
    fake = FakeGitHubClient(
        [
            httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "repository": {"full_name": "acme/repo"},
                            "path": "app.py",
                            "html_url": "https://github.test/acme/repo/blob/main/app.py",
                            "name": "app.py",
                        }
                    ]
                },
            )
        ]
    )
    monkeypatch.setattr("app.tools.adapters.github_adapter._client", lambda *args, **kwargs: fake)

    result = _adapter("search_code").execute(
        metadata=_metadata("github.search_code"),
        input_json={"query": "ToolRunner", "repo": "acme/repo", "language": "python"},
        config_json=None,
        secret_value="ghp_test",
    )

    assert fake.calls[0]["params"]["q"] == "ToolRunner repo:acme/repo language:python"
    assert result.output_json["items"][0]["repo"] == "acme/repo"


def test_github_returns_structured_rate_limit(monkeypatch) -> None:
    fake = FakeGitHubClient(
        [
            httpx.Response(
                403,
                json={"message": "API rate limit exceeded"},
                headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1770000000"},
            )
        ]
    )
    monkeypatch.setattr("app.tools.adapters.github_adapter._client", lambda *args, **kwargs: fake)

    result = _adapter("list_issues").execute(
        metadata=_metadata("github.list_issues"),
        input_json={"repo": "acme/repo"},
        config_json=None,
        secret_value="ghp_test",
    )

    assert result.output_json["error"] == "rate_limited"
    assert result.output_json["reset_at"] == "1770000000"


def test_github_invalid_input_and_missing_secret_do_not_raise() -> None:
    missing_secret = _adapter("list_issues").execute(
        metadata=_metadata("github.list_issues"),
        input_json={"repo": "acme/repo"},
        config_json=None,
        secret_value=None,
    )
    invalid = _adapter("get_issue").execute(
        metadata=_metadata("github.get_issue"),
        input_json={"repo": "missing-slash", "number": 1},
        config_json=None,
        secret_value="ghp_test",
    )

    assert missing_secret.output_json["error"] == "missing_secret"
    assert invalid.output_json["error"] == "invalid_input"
