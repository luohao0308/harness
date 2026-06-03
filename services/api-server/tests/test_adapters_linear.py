import httpx

from app.tools.adapters.linear_adapter import LinearAdapter
from app.tools.registry import ToolRegistry


class FakeLinearClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def __enter__(self) -> "FakeLinearClient":
        return self

    def __exit__(self, *args) -> None:
        return None

    def post(self, url: str, json: dict | None = None) -> httpx.Response:
        self.calls.append({"url": url, "json": json or {}})
        return self.responses.pop(0)


def _adapter(method: str) -> LinearAdapter:
    return LinearAdapter(
        slug=f"linear.{method}",
        method=method,
        description=method,
        input_schema={},
        output_schema={},
    )


def test_linear_list_issues_parses_graphql_nodes(monkeypatch) -> None:
    fake = FakeLinearClient(
        [
            httpx.Response(
                200,
                json={
                    "data": {
                        "issues": {
                            "nodes": [
                                {
                                    "id": "issue-1",
                                    "identifier": "ENG-1",
                                    "title": "Fix bug",
                                    "url": "https://linear.test/ENG-1",
                                    "state": {"name": "Todo"},
                                    "team": {"key": "ENG"},
                                }
                            ]
                        }
                    }
                },
            )
        ]
    )
    monkeypatch.setattr("app.tools.adapters.linear_adapter.httpx.Client", lambda *a, **k: fake)

    result = _adapter("list_issues").execute(
        metadata=ToolRegistry.default().tools["linear.list_issues"],
        input_json={"team_key": "ENG", "limit": 1},
        config_json={"runtime": {"endpoint_url": "https://linear.test/graphql"}},
        secret_value="lin_api",
    )

    assert fake.calls[0]["url"] == "https://linear.test/graphql"
    assert fake.calls[0]["json"]["variables"]["filter"]["team"]["key"]["eq"] == "ENG"
    assert result.output_json["items"][0]["identifier"] == "ENG-1"


def test_linear_create_comment_is_high_risk_and_parses_response(monkeypatch) -> None:
    fake = FakeLinearClient(
        [
            httpx.Response(
                200,
                json={
                    "data": {
                        "commentCreate": {
                            "success": True,
                            "comment": {
                                "id": "comment-1",
                                "body": "Looks good",
                                "createdAt": "2026-05-29T00:00:00Z",
                                "user": {"name": "Ada"},
                            },
                        }
                    }
                },
            )
        ]
    )
    monkeypatch.setattr("app.tools.adapters.linear_adapter.httpx.Client", lambda *a, **k: fake)

    result = _adapter("create_comment").execute(
        metadata=ToolRegistry.default().tools["linear.create_comment"],
        input_json={"issue_id": "issue-1", "body": "Looks good", "idempotency_key": "lin-1"},
        config_json=None,
        secret_value="lin_api",
    )

    assert ToolRegistry.default().tools["linear.create_comment"].risk_level == "high"
    assert fake.calls[0]["json"]["variables"]["input"]["issueId"] == "issue-1"
    assert result.output_json["comment"]["author"] == "Ada"
