import httpx

from app.tools.adapters import slack_adapter
from app.tools.adapters.slack_adapter import SlackAdapter
from app.tools.registry import ToolRegistry


class FakeSlackClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def __enter__(self) -> "FakeSlackClient":
        return self

    def __exit__(self, *args) -> None:
        return None

    def get(self, url: str, params: dict | None = None) -> httpx.Response:
        self.calls.append({"url": url, "params": params or {}})
        return self.responses.pop(0)

    def post(self, url: str, json: dict | None = None) -> httpx.Response:
        self.calls.append({"url": url, "json": json or {}})
        return self.responses.pop(0)


def _adapter(method: str) -> SlackAdapter:
    return SlackAdapter(
        slug=f"slack.{method}",
        method=method,
        description=method,
        input_schema={},
        output_schema={},
    )


def _metadata(name: str):
    return ToolRegistry.default().tools[name]


def test_slack_search_messages_simplifies_mrkdwn_and_resolves_user(monkeypatch) -> None:
    slack_adapter._USER_CACHE.clear()
    fake = FakeSlackClient(
        [
            httpx.Response(
                200,
                json={
                    "ok": True,
                    "messages": {
                        "matches": [
                            {
                                "channel": {"id": "C1", "name": "eng"},
                                "user": "U1",
                                "text": "hi <@U2|alice> <https://example.test|doc>",
                                "ts": "1.000",
                                "permalink": "https://slack.test/archives/C1/p1",
                            }
                        ]
                    },
                },
            ),
            httpx.Response(
                200,
                json={
                    "ok": True,
                    "user": {"id": "U1", "profile": {"display_name": "bob"}},
                },
            ),
        ]
    )
    monkeypatch.setattr(
        "app.tools.adapters.slack_adapter.httpx.Client", lambda *args, **kwargs: fake
    )

    result = _adapter("search_messages").execute(
        metadata=_metadata("slack.search_messages"),
        input_json={"query": "release", "channel": "eng", "limit": 2},
        config_json={"runtime": {"endpoint_url": "https://slack.test/api"}},
        secret_value="xoxb-test",
    )

    assert fake.calls[0]["url"] == "https://slack.test/api/search.messages"
    assert fake.calls[0]["params"]["query"] == "release in:eng"
    assert result.output_json["items"][0]["user"] == "bob"
    assert result.output_json["items"][0]["text"] == "hi @alice doc"


def test_slack_list_channels_parses_topic_and_purpose(monkeypatch) -> None:
    fake = FakeSlackClient(
        [
            httpx.Response(
                200,
                json={
                    "ok": True,
                    "channels": [
                        {
                            "id": "C1",
                            "name": "general",
                            "is_private": False,
                            "num_members": 5,
                            "topic": {"value": "Team updates"},
                            "purpose": {"value": "Announcements"},
                        }
                    ],
                },
            )
        ]
    )
    monkeypatch.setattr(
        "app.tools.adapters.slack_adapter.httpx.Client", lambda *args, **kwargs: fake
    )

    result = _adapter("list_channels").execute(
        metadata=_metadata("slack.list_channels"),
        input_json={"limit": 1},
        config_json=None,
        secret_value="xoxb-test",
    )

    assert result.output_json["items"][0]["name"] == "general"
    assert result.output_json["items"][0]["topic"] == "Team updates"


def test_slack_get_thread_returns_root_and_replies(monkeypatch) -> None:
    slack_adapter._USER_CACHE.clear()
    fake = FakeSlackClient(
        [
            httpx.Response(
                200,
                json={
                    "ok": True,
                    "messages": [
                        {"user": "U1", "text": "root", "ts": "1.000"},
                        {"user": "U2", "text": "reply <!channel>", "ts": "1.001"},
                    ],
                },
            ),
            httpx.Response(
                200,
                json={"ok": True, "user": {"id": "U1", "profile": {"real_name": "Root User"}}},
            ),
            httpx.Response(
                200,
                json={"ok": True, "user": {"id": "U2", "profile": {"display_name": "reply-user"}}},
            ),
        ]
    )
    monkeypatch.setattr(
        "app.tools.adapters.slack_adapter.httpx.Client", lambda *args, **kwargs: fake
    )

    result = _adapter("get_thread").execute(
        metadata=_metadata("slack.get_thread"),
        input_json={"channel": "C1", "thread_ts": "1.000"},
        config_json=None,
        secret_value="xoxb-test",
    )

    assert result.output_json["root"]["user"] == "Root User"
    assert result.output_json["replies"][0]["text"] == "reply @channel"


def test_slack_api_error_and_missing_secret_do_not_raise(monkeypatch) -> None:
    fake = FakeSlackClient([httpx.Response(200, json={"ok": False, "error": "invalid_auth"})])
    monkeypatch.setattr(
        "app.tools.adapters.slack_adapter.httpx.Client", lambda *args, **kwargs: fake
    )

    error = _adapter("list_channels").execute(
        metadata=_metadata("slack.list_channels"),
        input_json={},
        config_json=None,
        secret_value="xoxb-test",
    )
    missing = _adapter("search_messages").execute(
        metadata=_metadata("slack.search_messages"),
        input_json={"query": "release"},
        config_json=None,
        secret_value="",
    )

    assert error.output_json["error"] == "slack_api_error"
    assert error.output_json["slack_error"] == "invalid_auth"
    assert missing.output_json["error"] == "missing_secret"


def test_slack_post_message_uses_chat_post_message(monkeypatch) -> None:
    fake = FakeSlackClient(
        [
            httpx.Response(
                200,
                json={
                    "ok": True,
                    "channel": "C1",
                    "ts": "1.000",
                    "message": {"text": "hello <https://example.test|doc>", "ts": "1.000"},
                },
            )
        ]
    )
    monkeypatch.setattr(
        "app.tools.adapters.slack_adapter.httpx.Client", lambda *args, **kwargs: fake
    )

    result = _adapter("post_message").execute(
        metadata=_metadata("slack.post_message"),
        input_json={"channel": "C1", "text": "hello", "idempotency_key": "msg-1"},
        config_json={"runtime": {"endpoint_url": "https://slack.test/api"}},
        secret_value="xoxb-test",
    )

    assert fake.calls[0]["url"] == "https://slack.test/api/chat.postMessage"
    assert fake.calls[0]["json"]["channel"] == "C1"
    assert result.output_json["message"]["text"] == "hello doc"


def test_slack_write_tools_have_side_effect_metadata() -> None:
    post = ToolRegistry.default().tools["slack.post_message"]
    reaction = ToolRegistry.default().tools["slack.add_reaction"]

    assert post.risk_level == "high"
    assert reaction.risk_level == "high"
    assert post.idempotent is False
    assert reaction.idempotent is False
