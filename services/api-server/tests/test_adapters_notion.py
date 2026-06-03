import httpx

from app.tools.adapters.notion_adapter import NotionAdapter
from app.tools.registry import ToolRegistry


class FakeNotionClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def __enter__(self) -> "FakeNotionClient":
        return self

    def __exit__(self, *args) -> None:
        return None

    def request(self, method: str, url: str, params=None, json=None) -> httpx.Response:
        self.calls.append({"method": method, "url": url, "params": params or {}, "json": json})
        return self.responses.pop(0)


def _adapter(method: str) -> NotionAdapter:
    return NotionAdapter(
        slug=f"notion.{method}",
        method=method,
        description=method,
        input_schema={},
        output_schema={},
    )


def test_notion_search_pages_parses_title(monkeypatch) -> None:
    fake = FakeNotionClient(
        [
            httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "page-1",
                            "object": "page",
                            "url": "https://notion.test/page-1",
                            "properties": {
                                "Name": {
                                    "type": "title",
                                    "title": [{"plain_text": "Launch Plan"}],
                                }
                            },
                        }
                    ]
                },
            )
        ]
    )
    monkeypatch.setattr("app.tools.adapters.notion_adapter.httpx.Client", lambda *a, **k: fake)

    result = _adapter("search_pages").execute(
        metadata=ToolRegistry.default().tools["notion.search_pages"],
        input_json={"query": "launch", "limit": 1},
        config_json={"runtime": {"endpoint_url": "https://notion.test/v1"}},
        secret_value="secret_notion",
    )

    assert fake.calls[0]["method"] == "POST"
    assert fake.calls[0]["url"] == "https://notion.test/v1/search"
    assert result.output_json["items"][0]["title"] == "Launch Plan"


def test_notion_append_block_is_high_risk_and_posts_children(monkeypatch) -> None:
    fake = FakeNotionClient(
        [
            httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "block-1",
                            "type": "paragraph",
                            "paragraph": {"rich_text": [{"plain_text": "hello"}]},
                        }
                    ]
                },
            )
        ]
    )
    monkeypatch.setattr("app.tools.adapters.notion_adapter.httpx.Client", lambda *a, **k: fake)

    result = _adapter("append_block").execute(
        metadata=ToolRegistry.default().tools["notion.append_block"],
        input_json={"parent_block_id": "page-1", "text": "hello", "idempotency_key": "n1"},
        config_json=None,
        secret_value="secret_notion",
    )

    assert ToolRegistry.default().tools["notion.append_block"].risk_level == "high"
    assert fake.calls[0]["method"] == "PATCH"
    assert fake.calls[0]["json"]["children"][0]["type"] == "paragraph"
    assert result.output_json["block"]["text_preview"] == "hello"
