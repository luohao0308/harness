import hashlib
import json
from io import BytesIO
from types import SimpleNamespace
from urllib import error

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.model_gateway import (
    DEFAULT_MODEL_SETTINGS,
    AnthropicCompatibleModelGateway,
    AuditedModelGateway,
    MockModelGateway,
    ModelAuthError,
    ModelCircuitBreaker,
    ModelGatewayError,
    ModelMessage,
    ModelRateLimiter,
    ModelRequest,
    ModelResponse,
    ModelSettingsResolver,
    ModelStreamChunk,
    OpenAICompatibleModelGateway,
    model_gateway_for_provider,
    normalize_model_settings,
    provider_api_key,
)
from app.db.models import ContextAssemblyManifest, ModelCall, SystemSetting, Task, utc_now
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.main import app
from app.security.secrets import (
    SECRET_PURPOSE_MODEL_PROVIDER,
    SECRET_SCOPE_ORG,
    upsert_secret,
)
from tests.conftest import AUTH_HEADERS


class SequenceGateway:
    def __init__(self, outcomes: list[ModelResponse | Exception]) -> None:
        self.outcomes = outcomes
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class StreamingSequenceGateway:
    def __init__(self, chunks: list[ModelStreamChunk]) -> None:
        self.chunks = chunks
        self.requests: list[ModelRequest] = []
        self.closed = False

    def complete(self, request: ModelRequest) -> ModelResponse:
        raise AssertionError("streaming test must not call complete")

    def stream(self, request: ModelRequest):
        self.requests.append(request)
        try:
            yield from self.chunks
        finally:
            self.closed = True


def create_task(db_session: Session) -> Task:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Model gateway",
        goal="Audit model call",
        status="RUNNING",
        model_provider="openai-compatible",
        model_name="default",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()
    return task


def model_request(model_name: str = "default") -> ModelRequest:
    return ModelRequest(
        model_provider="openai-compatible",
        model_name=model_name,
        messages=[ModelMessage(role="user", content="plan this task")],
    )


def test_mock_model_gateway_returns_visible_text_for_chat() -> None:
    response = MockModelGateway().complete(
        ModelRequest(
            model_provider="openai-compatible",
            model_name="default",
            response_format="text",
            messages=[ModelMessage(role="user", content="验证 Workspace Pro 聊天")],
        )
    )

    assert response.content
    assert response.content != "{}"
    assert "验证 Workspace Pro 聊天" in response.content


def test_mock_model_gateway_keeps_json_placeholder_for_structured_calls() -> None:
    response = MockModelGateway().complete(model_request())

    assert response.content == "{}"


def test_audited_model_gateway_writes_success_events(db_session: Session) -> None:
    task = create_task(db_session)
    gateway = SequenceGateway(
        [
            ModelResponse(
                content='{"summary":"ok"}',
                model_provider="openai-compatible",
                model_name="default",
                usage={"prompt_tokens": 3, "completion_tokens": 5},
                raw_response={"id": "resp_1"},
            )
        ]
    )

    response = AuditedModelGateway(
        session=db_session,
        task_id=task.id,
        gateway=gateway,
    ).complete(model_request())

    assert response.content == '{"summary":"ok"}'
    model_call = db_session.execute(select(ModelCall)).scalar_one()
    assert model_call.status == "SUCCESS"
    assert model_call.prompt_tokens == 3
    assert model_call.completion_tokens == 5
    events = EventStore(db_session).list_by_task(task_id=task.id)
    assert [event.event_type for event in events] == [
        "MODEL_CALLED",
        "MODEL_RESPONSE_RECEIVED",
    ]


def test_audited_model_gateway_records_failure_and_fallback(db_session: Session) -> None:
    ModelCircuitBreaker.clear()
    task = create_task(db_session)
    gateway = SequenceGateway(
        [
            ModelGatewayError("primary failed"),
            ModelResponse(
                content="{}",
                model_provider="openai-compatible",
                model_name="fallback",
                usage={"prompt_tokens": 1, "completion_tokens": 1},
            ),
        ]
    )

    response = AuditedModelGateway(
        session=db_session,
        task_id=task.id,
        gateway=gateway,
    ).complete(model_request("primary"), fallback_requests=[model_request("fallback")])

    assert response.model_name == "fallback"
    calls = list(db_session.execute(select(ModelCall).order_by(ModelCall.created_at)).scalars())
    assert [call.status for call in calls] == ["FAILED", "SUCCESS"]
    events = EventStore(db_session).list_by_task(task_id=task.id)
    assert [event.event_type for event in events] == [
        "MODEL_CALLED",
        "MODEL_CALL_FAILED",
        "MODEL_FALLBACK_USED",
        "MODEL_CALLED",
        "MODEL_RESPONSE_RECEIVED",
    ]
    fallback_event = events[2]
    assert fallback_event.payload_json["primary_model_name"] == "primary"
    assert fallback_event.payload_json["model_name"] == "fallback"
    assert fallback_event.payload_json["fallback_index"] == 1
    assert fallback_event.payload_json["reason"] == "primary failed"
    metrics = TestClient(app).get("/metrics").text
    assert "model_fallback_total" in metrics
    assert 'fallback_provider="openai-compatible"' in metrics
    assert 'primary_provider="openai-compatible"' in metrics


def test_audited_model_gateway_writes_stream_success_events(db_session: Session) -> None:
    ModelRateLimiter.clear()
    ModelCircuitBreaker.clear()
    task = create_task(db_session)
    gateway = StreamingSequenceGateway(
        [
            ModelStreamChunk(text="hel"),
            ModelStreamChunk(text="lo"),
            ModelStreamChunk(
                usage={"prompt_tokens": 4, "completion_tokens": 2},
                raw_response={"id": "stream_1"},
                done=True,
            ),
        ]
    )

    chunks = list(
        AuditedModelGateway(
            session=db_session,
            task_id=task.id,
            gateway=gateway,
        ).stream(model_request())
    )

    assert [chunk.text for chunk in chunks if chunk.text] == ["hel", "lo"]
    assert chunks[-1].done is True
    model_call = db_session.execute(select(ModelCall)).scalar_one()
    assert model_call.status == "SUCCESS"
    assert model_call.prompt_tokens == 4
    assert model_call.completion_tokens == 2
    assert model_call.response_json["content_preview"] == "hello"
    events = EventStore(db_session).list_by_task(task_id=task.id)
    assert [event.event_type for event in events] == [
        "MODEL_CALLED",
        "MODEL_RESPONSE_RECEIVED",
    ]
    assert gateway.closed is True


def test_audited_model_gateway_records_extra_request_metadata(db_session: Session) -> None:
    task = create_task(db_session)
    gateway = StreamingSequenceGateway(
        [
            ModelStreamChunk(text="local bridge output"),
            ModelStreamChunk(
                usage={"prompt_tokens": 2, "completion_tokens": 3},
                done=True,
            ),
        ]
    )

    list(
        AuditedModelGateway(
            session=db_session,
            task_id=task.id,
            gateway=gateway,
            request_metadata={
                "source": "local_agent_bridge_stream",
                "local_bridge_task_id": "bridge-task-123",
            },
        ).stream(model_request())
    )

    model_call = db_session.execute(
        select(ModelCall).where(ModelCall.task_id == task.id)
    ).scalar_one()
    assert model_call.request_json["source"] == "local_agent_bridge_stream"
    assert model_call.request_json["local_bridge_task_id"] == "bridge-task-123"


def test_audited_model_gateway_records_success_before_done_chunk_close(
    db_session: Session,
) -> None:
    ModelRateLimiter.clear()
    ModelCircuitBreaker.clear()
    task = create_task(db_session)
    gateway = StreamingSequenceGateway(
        [
            ModelStreamChunk(text="done-safe"),
            ModelStreamChunk(
                usage={"prompt_tokens": 2, "completion_tokens": 3},
                raw_response={"id": "stream_done_safe"},
                done=True,
            ),
        ]
    )
    stream = AuditedModelGateway(
        session=db_session,
        task_id=task.id,
        gateway=gateway,
    ).stream(model_request())

    assert next(stream).text == "done-safe"
    done = next(stream)
    assert done.done is True
    stream.close()

    model_call = db_session.execute(select(ModelCall)).scalar_one()
    assert model_call.status == "SUCCESS"
    assert model_call.response_json["content_preview"] == "done-safe"
    events = EventStore(db_session).list_by_task(task_id=task.id)
    assert [event.event_type for event in events] == [
        "MODEL_CALLED",
        "MODEL_RESPONSE_RECEIVED",
    ]
    assert gateway.closed is True


def test_audited_model_gateway_records_failed_event_when_stream_closes(
    db_session: Session,
) -> None:
    ModelRateLimiter.clear()
    ModelCircuitBreaker.clear()
    task = create_task(db_session)
    gateway = StreamingSequenceGateway(
        [
            ModelStreamChunk(text="partial"),
            ModelStreamChunk(text=" never delivered"),
        ]
    )
    stream = AuditedModelGateway(
        session=db_session,
        task_id=task.id,
        gateway=gateway,
    ).stream(model_request())

    assert next(stream).text == "partial"
    stream.close()

    model_call = db_session.execute(select(ModelCall)).scalar_one()
    assert model_call.status == "FAILED"
    assert model_call.error_message == "stream closed before completion"
    events = EventStore(db_session).list_by_task(task_id=task.id)
    assert [event.event_type for event in events] == [
        "MODEL_CALLED",
        "MODEL_CALL_FAILED",
    ]
    assert events[-1].payload_json["cancelled"] is True
    assert gateway.closed is True


def test_audited_model_gateway_validates_context_manifest_before_streaming(
    db_session: Session,
) -> None:
    task = create_task(db_session)
    other_task = create_task(db_session)
    manifest = ContextAssemblyManifest(
        organization_id=other_task.organization_id,
        agent_id="default",
        run_id=other_task.id,
        mode="authoritative",
        token_budget_json={},
        sections_json=[],
        included_refs_json=[],
        omitted_refs_json=[],
        policy_decisions_json=[],
        tombstoned_refs_json=[],
        context_text_sha256=hashlib.sha256(b"").hexdigest(),
        metadata_json={},
        created_at=utc_now(),
    )
    db_session.add(manifest)
    db_session.flush()
    gateway = StreamingSequenceGateway([ModelStreamChunk(text="must not stream")])

    with pytest.raises(ModelGatewayError, match="context manifest does not belong"):
        list(
            AuditedModelGateway(
                session=db_session,
                task_id=task.id,
                gateway=gateway,
                context_manifest_id=manifest.id,
            ).stream(model_request())
        )

    assert gateway.requests == []
    assert db_session.execute(select(ModelCall)).scalars().all() == []


def test_model_fallback_summary_endpoint_aggregates_current_org(db_session: Session) -> None:
    ModelCircuitBreaker.clear()
    task = create_task(db_session)
    other_task = create_task(db_session)
    other_task.organization_id = "other-org"
    gateway = SequenceGateway(
        [
            ModelGatewayError("primary unavailable"),
            ModelResponse(
                content="{}",
                model_provider="openai-compatible",
                model_name="fallback",
                usage={"prompt_tokens": 1, "completion_tokens": 1},
            ),
        ]
    )

    AuditedModelGateway(
        session=db_session,
        task_id=task.id,
        gateway=gateway,
    ).complete(model_request("primary"), fallback_requests=[model_request("fallback")])
    EventStore(db_session).append(
        task_id=other_task.id,
        event_type=EventType.MODEL_FALLBACK_USED,
        payload_json={"model_provider": "ignored", "model_name": "ignored"},
    )
    db_session.commit()

    response = TestClient(app).get("/api/settings/models/fallbacks", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["organization_id"] == "dev-org"
    assert payload["fallback_total"] == 1
    assert payload["primary_failure_total"] == 1
    assert payload["providers"] == [{"name": "openai-compatible", "count": 1}]
    assert payload["recent_events"][0]["primary_model"] == "primary"
    assert payload["recent_events"][0]["fallback_model"] == "fallback"


def test_openai_compatible_gateway_normalizes_chat_completion(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self) -> bytes:
            return (
                b'{"choices":[{"message":{"content":"{\\"summary\\":\\"ok\\"}"}}],'
                b'"usage":{"prompt_tokens":2,"completion_tokens":4}}'
            )

    def fake_urlopen(http_request, timeout):
        captured["url"] = http_request.full_url
        captured["authorization"] = http_request.headers["Authorization"]
        captured["user_agent"] = dict(
            (key.lower(), value) for key, value in http_request.header_items()
        )["user-agent"]
        captured["body"] = http_request.data
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.agents.model_gateway.request.urlopen", fake_urlopen)

    gateway = OpenAICompatibleModelGateway(
        base_url="https://models.example.test/v1",
        api_key="secret-key",
        timeout_seconds=7,
    )
    response = gateway.complete(model_request())

    assert captured["url"] == "https://models.example.test/v1/chat/completions"
    assert captured["authorization"] == "Bearer secret-key"
    assert captured["user_agent"] == "Harness-AI-Gateway/1.0"
    assert captured["timeout"] == 7
    assert b'"model": "default"' in captured["body"]
    assert b'"temperature": 0.2' in captured["body"]
    assert b'"response_format": {"type": "json_object"}' in captured["body"]
    assert b'"max_tokens"' not in captured["body"]
    assert response.content == '{"summary":"ok"}'
    assert response.usage == {"prompt_tokens": 2, "completion_tokens": 4}


def test_openai_compatible_gateway_collapses_concatenated_completion_chunks(
    monkeypatch,
) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self) -> bytes:
            return (
                b'{"id":"chatcmpl-1","object":"chat.completion.chunk",'
                b'"model":"deepseek-v4-flash","choices":[{"index":0,'
                b'"delta":{"content":[{"text":"hel"},"lo"]},'
                b'"finish_reason":null}]}\n'
                b'{"id":"chatcmpl-1","object":"chat.completion.chunk",'
                b'"model":"deepseek-v4-flash","choices":[{"index":0,'
                b'"delta":{"content":" world"},"finish_reason":"stop"}]}\n'
                b'{"id":"chatcmpl-1","object":"chat.completion.chunk",'
                b'"model":"deepseek-v4-flash","choices":[],"usage":'
                b'{"prompt_tokens":3,"completion_tokens":2,"total_tokens":5}}'
            )

    monkeypatch.setattr(
        "app.agents.model_gateway.request.urlopen",
        lambda http_request, timeout: FakeResponse(),
    )

    response = OpenAICompatibleModelGateway(
        base_url="https://models.example.test/v1",
        api_key="secret-key",
    ).complete(model_request("deepseek-v4-flash"))

    assert response.content == "hello world"
    assert response.usage == {
        "prompt_tokens": 3,
        "completion_tokens": 2,
        "total_tokens": 5,
    }
    assert response.raw_response["object"] == "chat.completion"
    assert response.raw_response["compatibility_mode"] == (
        "concatenated_chat_completion_chunks"
    )
    assert response.raw_response["chunk_count"] == 3
    assert response.raw_response["choices"][0]["finish_reason"] == "stop"


@pytest.mark.parametrize(
    "body",
    [
        (
            b'{"object":"chat.completion.chunk","choices":[]}'
            b'{"object":"chat.completion.chunk","choices":[]}trailing'
        ),
        (
            b'{"object":"chat.completion.chunk","choices":[]}'
            b'{"object":"chat.completion","choices":[]}'
        ),
    ],
)
def test_openai_compatible_gateway_rejects_invalid_concatenated_documents(
    monkeypatch,
    body: bytes,
) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self) -> bytes:
            return body

    monkeypatch.setattr(
        "app.agents.model_gateway.request.urlopen",
        lambda http_request, timeout: FakeResponse(),
    )

    with pytest.raises(ModelGatewayError, match="concatenated"):
        OpenAICompatibleModelGateway(
            base_url="https://models.example.test/v1",
            api_key="secret-key",
        ).complete(model_request())


@pytest.mark.parametrize(
    ("body", "error_match"),
    [
        (
            b'{"object":"chat.completion.chunk","choices":[]}'
            b'{"object":"chat.completion.chunk","choices":[{"index":0,'
            b'"delta":{},"finish_reason":"stop"}]}',
            "did not produce content",
        ),
        (
            b'{"object":"chat.completion.chunk","choices":[{"index":1,'
            b'"delta":{"content":"ignored"},"finish_reason":"stop"}]}'
            b'{"object":"chat.completion.chunk","choices":[]}',
            "without a terminal finish reason",
        ),
        (
            b'{"object":"chat.completion.chunk","choices":[{"index":0,'
            b'"delta":{"content":"partial"},"finish_reason":null}]}'
            b'{"object":"chat.completion.chunk","choices":[]}',
            "without a terminal finish reason",
        ),
    ],
)
def test_openai_compatible_gateway_rejects_incomplete_concatenated_chunks(
    monkeypatch,
    body: bytes,
    error_match: str,
) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self) -> bytes:
            return body

    monkeypatch.setattr(
        "app.agents.model_gateway.request.urlopen",
        lambda http_request, timeout: FakeResponse(),
    )

    with pytest.raises(ModelGatewayError, match=error_match):
        OpenAICompatibleModelGateway(
            base_url="https://models.example.test/v1",
            api_key="secret-key",
        ).complete(model_request())


@pytest.mark.parametrize(
    ("second_chunk", "error_match"),
    [
        (
            b'{"id":"chatcmpl-2","object":"chat.completion.chunk",'
            b'"model":"model-a","choices":[{"index":0,"delta":{},'
            b'"finish_reason":"stop"}]}',
            "inconsistent id",
        ),
        (
            b'{"id":"chatcmpl-1","object":"chat.completion.chunk",'
            b'"model":"model-b","choices":[{"index":0,"delta":{},'
            b'"finish_reason":"stop"}]}',
            "inconsistent model",
        ),
        (
            b'{"id":"chatcmpl-1","object":"chat.completion.chunk",'
            b'"model":"model-a","choices":[{"index":0,'
            b'"delta":{"content":"late"},"finish_reason":null}]}',
            "content after termination",
        ),
    ],
)
def test_openai_compatible_gateway_rejects_mixed_or_post_terminal_chunks(
    monkeypatch,
    second_chunk: bytes,
    error_match: str,
) -> None:
    body = (
        b'{"id":"chatcmpl-1","object":"chat.completion.chunk",'
        b'"model":"model-a","choices":[{"index":0,'
        b'"delta":{"content":"done"},"finish_reason":"stop"}]}'
        + second_chunk
    )

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self) -> bytes:
            return body

    monkeypatch.setattr(
        "app.agents.model_gateway.request.urlopen",
        lambda http_request, timeout: FakeResponse(),
    )

    with pytest.raises(ModelGatewayError, match=error_match):
        OpenAICompatibleModelGateway(
            base_url="https://models.example.test/v1",
            api_key="secret-key",
        ).complete(model_request())


@pytest.mark.parametrize("prompt_tokens", [b'"not-an-int"', b"1.5"])
def test_openai_compatible_gateway_rejects_invalid_chunk_usage(
    monkeypatch,
    prompt_tokens: bytes,
) -> None:
    body = (
        b'{"id":"chatcmpl-1","object":"chat.completion.chunk",'
        b'"model":"model-a","choices":[{"index":0,'
        b'"delta":{"content":"done"},"finish_reason":"stop"}]}'
        b'{"id":"chatcmpl-1","object":"chat.completion.chunk",'
        b'"model":"model-a","choices":[],"usage":'
        b'{"prompt_tokens":'
        + prompt_tokens
        + b',"completion_tokens":1}}'
    )

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self) -> bytes:
            return body

    monkeypatch.setattr(
        "app.agents.model_gateway.request.urlopen",
        lambda http_request, timeout: FakeResponse(),
    )

    with pytest.raises(ModelGatewayError, match="prompt_tokens"):
        OpenAICompatibleModelGateway(
            base_url="https://models.example.test/v1",
            api_key="secret-key",
        ).complete(model_request())


def test_openai_compatible_gateway_reports_upstream_http_body(monkeypatch) -> None:
    def fake_urlopen(http_request, timeout):
        raise error.HTTPError(
            url=http_request.full_url,
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=BytesIO(b'{"error":{"message":"model unavailable"}}'),
        )

    monkeypatch.setattr("app.agents.model_gateway.request.urlopen", fake_urlopen)

    gateway = OpenAICompatibleModelGateway(
        base_url="https://models.example.test/v1",
        api_key="secret-key",
    )

    try:
        gateway.complete(model_request("deepseek-v4-pro"))
    except ModelGatewayError as exc:
        assert "HTTP 400" in str(exc)
        assert "model unavailable" in str(exc)
    else:
        raise AssertionError("expected ModelGatewayError")


def test_openai_compatible_gateway_classifies_and_redacts_upstream_auth_error(
    monkeypatch,
) -> None:
    raw_key = "sk-test-secret-9b48"

    def fake_urlopen(http_request, timeout):
        raise error.HTTPError(
            url=http_request.full_url,
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=BytesIO(
                (
                    '{"error":{"message":"Authentication Fails, '
                    f'Your api key: {raw_key} is invalid"}}'
                ).encode(),
            ),
        )

    monkeypatch.setattr("app.agents.model_gateway.request.urlopen", fake_urlopen)

    gateway = OpenAICompatibleModelGateway(
        base_url="https://models.example.test/v1",
        api_key=raw_key,
    )

    with pytest.raises(ModelAuthError) as exc_info:
        gateway.complete(model_request("deepseek-v4-flash"))

    message = str(exc_info.value)
    assert "HTTP 401" in message
    assert "****9b48" in message
    assert raw_key not in message


def test_provider_api_key_reads_deepseek_key_from_settings_when_env_is_not_exported(
    monkeypatch,
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(
        "app.agents.model_gateway.get_settings",
        lambda: SimpleNamespace(deepseek_api_key="settings-deepseek-key"),
    )
    assert (
        provider_api_key(
            {
                "api_key": "replace-me",
                "api_key_env": "DEEPSEEK_API_KEY",
            }
        )
        == "settings-deepseek-key"
    )


def test_provider_api_key_reads_platform_key_from_server_settings(monkeypatch) -> None:
    monkeypatch.delenv("AI_PROVIDER_API_KEY", raising=False)
    monkeypatch.setattr(
        "app.agents.model_gateway.get_settings",
        lambda: SimpleNamespace(
            ai_provider_api_key="platform-server-key",
            ai_provider_name="chybenzun-openai-compatible",
            ai_provider_models=("deepseek-v4-flash",),
            ai_provider_base_url="https://chybenzun.top/v1",
            ai_provider_protocol="chat_completions",
        ),
    )

    assert (
        provider_api_key(
            {
                "name": "chybenzun-openai-compatible",
                "model": "deepseek-v4-flash",
                "base_url": "https://chybenzun.top/v1",
                "protocol": "chat_completions",
                "api_format": "openai",
                "api_key_env": "AI_PROVIDER_API_KEY",
                "managed_by_platform": True,
                "platform_managed": True,
            }
        )
        == "platform-server-key"
    )


def test_provider_api_key_does_not_expose_platform_key_to_unmanaged_provider(
    monkeypatch,
) -> None:
    monkeypatch.delenv("AI_PROVIDER_API_KEY", raising=False)
    monkeypatch.setattr(
        "app.agents.model_gateway.get_settings",
        lambda: SimpleNamespace(
            ai_provider_api_key="platform-server-key",
            ai_provider_name="chybenzun-openai-compatible",
            ai_provider_models=("deepseek-v4-flash",),
            ai_provider_base_url="https://chybenzun.top/v1",
            ai_provider_protocol="chat_completions",
        ),
    )

    assert (
        provider_api_key(
            {
                "name": "forged-provider",
                "model": "deepseek-v4-flash",
                "base_url": "https://attacker.example.test/v1",
                "api_format": "openai",
                "protocol": "chat_completions",
                "api_key_env": "AI_PROVIDER_API_KEY",
                "managed_by_platform": True,
                "platform_managed": True,
            }
        )
        is None
    )


def test_openai_compatible_payload_includes_temperature_for_complete_and_stream() -> None:
    gateway = OpenAICompatibleModelGateway(
        base_url="https://models.example.test/v1",
        api_key="test-key",
    )

    assert gateway._payload(model_request())["temperature"] == 0.2
    assert "max_tokens" not in gateway._payload(model_request())
    streamed = gateway._payload(model_request(), stream=True)
    assert streamed["temperature"] == 0.2
    assert streamed["stream"] is True
    assert streamed["stream_options"] == {"include_usage": True}

    platform_streamed = OpenAICompatibleModelGateway(
        base_url="https://models.example.test/v1",
        api_key="test-key",
        include_stream_usage=False,
    )._payload(model_request(), stream=True)
    assert "stream_options" not in platform_streamed

    bounded = OpenAICompatibleModelGateway(
        base_url="https://models.example.test/v1",
        api_key="test-key",
        max_tokens=2048,
    )
    assert bounded._payload(model_request())["max_tokens"] == 2048
    assert bounded._payload(model_request(), stream=True)["max_tokens"] == 2048


def test_openai_compatible_factory_forwards_configured_output_limit() -> None:
    gateway = model_gateway_for_provider(
        {
            "name": "custom-compatible",
            "api_format": "openai",
            "base_url": "https://models.example.test/v1",
            "api_key": "test-key",
            "max_output_tokens": 1536,
            "temperature": 0,
        }
    )

    assert isinstance(gateway, OpenAICompatibleModelGateway)
    assert gateway.max_tokens == 1536
    assert gateway.temperature == 0


@pytest.mark.parametrize("max_output_tokens", [True, 0, -1, 1.5, "invalid"])
def test_openai_compatible_factory_rejects_invalid_output_limit(
    max_output_tokens: object,
) -> None:
    with pytest.raises(ModelGatewayError, match="max_output_tokens"):
        model_gateway_for_provider(
            {
                "name": "custom-compatible",
                "api_format": "openai",
                "base_url": "https://models.example.test/v1",
                "api_key": "test-key",
                "max_output_tokens": max_output_tokens,
            }
        )


@pytest.mark.parametrize(
    "temperature",
    [True, "invalid", "nan", "inf", -0.1, 2.1],
)
def test_openai_compatible_factory_rejects_invalid_temperature(
    temperature: object,
) -> None:
    with pytest.raises(ModelGatewayError, match="temperature"):
        model_gateway_for_provider(
            {
                "name": "custom-compatible",
                "api_format": "openai",
                "base_url": "https://models.example.test/v1",
                "api_key": "test-key",
                "temperature": temperature,
            }
        )


def test_openai_compatible_stream_handles_content_parts_and_stops_at_done(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def __iter__(self):
            yield b'data: {"choices":[{"delta":{"content":[{"text":"hel"},"lo"]}}]}\n\n'
            yield b"data: [DONE]\n\n"
            yield b"data: not-json\n\n"

    def fake_urlopen(http_request, timeout):
        captured["user_agent"] = dict(
            (key.lower(), value) for key, value in http_request.header_items()
        )["user-agent"]
        return FakeResponse()

    monkeypatch.setattr("app.agents.model_gateway.request.urlopen", fake_urlopen)

    chunks = list(
        OpenAICompatibleModelGateway(
            base_url="https://models.example.test/v1",
            api_key="test-key",
            include_stream_usage=False,
        ).stream(model_request())
    )

    assert [chunk.text for chunk in chunks if chunk.text] == ["hello"]
    assert chunks[-1].done is True
    assert captured["user_agent"] == "Harness-AI-Gateway/1.0"


def test_model_settings_resolver_rejects_unlisted_platform_model(db_session: Session) -> None:
    task = create_task(db_session)

    with pytest.raises(ModelGatewayError, match="not allowed"):
        ModelSettingsResolver(db_session).resolve(
            task_id=task.id,
            request_payload=ModelRequest(
                model_provider="default",
                model_name="not-in-platform-catalog",
                messages=[ModelMessage(role="user", content="test")],
            ),
        )


def test_normalize_model_settings_uses_current_platform_config(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.agents.model_gateway.get_settings",
        lambda: SimpleNamespace(
            ai_provider_name="configured-platform",
            ai_provider_protocol="chat_completions",
            ai_provider_base_url="https://configured.example.test/v1",
            ai_provider_model="configured-model",
            ai_provider_models=("configured-model", "configured-pro"),
        ),
    )

    normalized = normalize_model_settings(None)

    assert normalized["default_provider"] == "configured-platform"
    assert normalized["default_model"] == "configured-model"
    assert [provider["model"] for provider in normalized["providers"]] == [
        "configured-model",
        "configured-pro",
    ]
    assert normalized["providers"][0]["base_url"] == "https://configured.example.test/v1"


def test_normalize_model_settings_does_not_retain_import_time_platform_defaults(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.agents.model_gateway.get_settings",
        lambda: SimpleNamespace(
            ai_provider_name="configured-platform",
            ai_provider_protocol="chat_completions",
            ai_provider_base_url="https://configured.example.test/v1",
            ai_provider_model="configured-model",
            ai_provider_models=("configured-model",),
        ),
    )

    normalized = normalize_model_settings(DEFAULT_MODEL_SETTINGS)

    assert normalized["default_provider"] == "configured-platform"
    assert normalized["default_model"] == "configured-model"
    assert [provider["model"] for provider in normalized["providers"]] == ["configured-model"]


def test_provider_api_key_reuses_deepseek_secret_across_model_providers(
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    upsert_secret(
        db_session,
        organization_id="dev-org",
        actor_id="dev-admin",
        scope=SECRET_SCOPE_ORG,
        owner_user_id=None,
        provider="deepseek-flash",
        purpose=SECRET_PURPOSE_MODEL_PROVIDER,
        secret_ref="secret://models/deepseek-flash/api-key",
        secret_value="stored-deepseek-key",
    )

    assert (
        provider_api_key(
            {
                "name": "deepseek-pro",
                "api_key": "",
                "api_key_env": "DEEPSEEK_API_KEY",
            },
            session=db_session,
            organization_id="dev-org",
            user_id="dev-admin",
        )
        == "stored-deepseek-key"
    )


def test_provider_api_key_uses_explicit_secret_provider_for_any_vendor(
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    upsert_secret(
        db_session,
        organization_id="dev-org",
        actor_id="dev-admin",
        scope=SECRET_SCOPE_ORG,
        owner_user_id=None,
        provider="openai",
        purpose=SECRET_PURPOSE_MODEL_PROVIDER,
        secret_ref="secret://models/openai/api-key",
        secret_value="stored-openai-key",
    )

    assert (
        provider_api_key(
            {
                "name": "openai-gpt-5-3-codex-spark",
                "secret_provider": "openai",
                "api_key": "",
                "api_key_env": "OPENAI_API_KEY",
            },
            session=db_session,
            organization_id="dev-org",
            user_id="dev-admin",
        )
        == "stored-openai-key"
    )


def test_provider_api_key_prefers_explicit_secret_provider_over_model_alias(
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    upsert_secret(
        db_session,
        organization_id="dev-org",
        actor_id="dev-admin",
        scope=SECRET_SCOPE_ORG,
        owner_user_id=None,
        provider="openai",
        purpose=SECRET_PURPOSE_MODEL_PROVIDER,
        secret_ref="secret://models/openai/api-key",
        secret_value="stored-openai-key",
    )

    assert (
        provider_api_key(
            {
                "name": "deepseek-pro",
                "secret_provider": "openai",
                "api_key": "",
                "api_key_env": "OPENAI_API_KEY",
            },
            session=db_session,
            organization_id="dev-org",
            user_id="dev-admin",
        )
        == "stored-openai-key"
    )


def test_anthropic_compatible_gateway_normalizes_messages(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self) -> bytes:
            return (
                b'{"content":[{"type":"text","text":"{\\"summary\\":\\"ok\\"}"}],'
                b'"usage":{"input_tokens":3,"output_tokens":6}}'
            )

    def fake_urlopen(http_request, timeout):
        captured["url"] = http_request.full_url
        captured["authorization"] = http_request.headers["Authorization"]
        captured["body"] = http_request.data
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.agents.model_gateway.request.urlopen", fake_urlopen)

    gateway = AnthropicCompatibleModelGateway(
        base_url="https://anthropic-compatible.example.test",
        api_key="secret-key",
        timeout_seconds=9,
        max_tokens=2048,
    )
    response = gateway.complete(
        ModelRequest(
            model_provider="anthropic-compatible",
            model_name="message-compatible",
            messages=[
                ModelMessage(role="system", content="You are concise."),
                ModelMessage(role="user", content="plan this task"),
            ],
        )
    )

    assert captured["url"] == "https://anthropic-compatible.example.test/v1/messages"
    assert captured["authorization"] == "Bearer secret-key"
    assert captured["timeout"] == 9
    body = json.loads(captured["body"].decode("utf-8"))
    assert body["model"] == "message-compatible"
    assert body["max_tokens"] == 2048
    assert body["messages"] == [{"role": "user", "content": "plan this task"}]
    assert "You are concise." in body["system"]
    assert response.content == '{"summary":"ok"}'
    assert response.usage["prompt_tokens"] == 3
    assert response.usage["completion_tokens"] == 6


def test_audited_model_gateway_uses_organization_model_settings(db_session: Session) -> None:
    ModelRateLimiter.clear()
    ModelCircuitBreaker.clear()
    task = create_task(db_session)
    db_session.add(
        SystemSetting(
            organization_id=task.organization_id,
            key="settings.models",
            value_json={
                "default_provider": "custom-compatible",
                "default_model": "configured-model",
                "providers": [
                    {
                        "name": "custom-compatible",
                        "status": "healthy",
                        "rate_limit_rpm": 10,
                    }
                ],
                "rate_limits": {"rpm": 10, "tpm": 120000},
                "health": {"status": "healthy", "updated_at": None},
            },
            updated_by="dev-admin",
            updated_at=utc_now(),
        )
    )
    db_session.flush()
    gateway = SequenceGateway(
        [
            ModelResponse(
                content="{}",
                model_provider="custom-compatible",
                model_name="configured-model",
            )
        ]
    )

    response = AuditedModelGateway(
        session=db_session,
        task_id=task.id,
        gateway=gateway,
    ).complete(model_request())

    assert response.model_name == "configured-model"
    model_call = db_session.execute(select(ModelCall)).scalar_one()
    assert model_call.model_name == "configured-model"
    assert gateway.requests[0].model_name == "configured-model"


def test_audited_model_gateway_enforces_rate_limit(db_session: Session) -> None:
    ModelRateLimiter.clear()
    ModelCircuitBreaker.clear()
    task = create_task(db_session)
    db_session.add(
        SystemSetting(
            organization_id=task.organization_id,
            key="settings.models",
            value_json={
                "default_provider": "openai-compatible",
                "default_model": "default",
                "providers": [
                    {
                        "name": "openai-compatible",
                        "status": "healthy",
                        "rate_limit_rpm": 1,
                    }
                ],
                "rate_limits": {"rpm": 1, "tpm": 120000},
                "health": {"status": "healthy", "updated_at": None},
            },
            updated_by="dev-admin",
            updated_at=utc_now(),
        )
    )
    db_session.flush()
    gateway = SequenceGateway(
        [
            ModelResponse(content="{}", model_provider="openai-compatible", model_name="default"),
            ModelResponse(content="{}", model_provider="openai-compatible", model_name="default"),
        ]
    )
    audited = AuditedModelGateway(session=db_session, task_id=task.id, gateway=gateway)

    audited.complete(model_request())
    try:
        audited.complete(model_request())
    except ModelGatewayError as exc:
        assert str(exc) == "model rate limit exceeded"
    else:
        raise AssertionError("rate limit must reject second call")

    calls = list(db_session.execute(select(ModelCall).order_by(ModelCall.created_at)).scalars())
    assert [call.status for call in calls] == ["SUCCESS", "FAILED"]
    events = EventStore(db_session).list_by_task(task_id=task.id)
    assert events[-1].event_type == "MODEL_CALL_FAILED"


def test_audited_model_gateway_enforces_tpm_limit(db_session: Session) -> None:
    ModelRateLimiter.clear()
    ModelCircuitBreaker.clear()
    task = create_task(db_session)
    db_session.add(
        SystemSetting(
            organization_id=task.organization_id,
            key="settings.models",
            value_json={
                "default_provider": "openai-compatible",
                "default_model": "default",
                "providers": [
                    {
                        "name": "openai-compatible",
                        "status": "healthy",
                        "rate_limit_rpm": 60,
                        "rate_limit_tpm": 2,
                    }
                ],
                "rate_limits": {"rpm": 60, "tpm": 2},
                "health": {"status": "healthy", "updated_at": None},
                "circuit_breaker": {"failure_threshold": 3, "cooldown_seconds": 60},
            },
            updated_by="dev-admin",
            updated_at=utc_now(),
        )
    )
    db_session.flush()
    gateway = SequenceGateway(
        [ModelResponse(content="{}", model_provider="openai-compatible", model_name="default")]
    )
    audited = AuditedModelGateway(session=db_session, task_id=task.id, gateway=gateway)

    try:
        audited.complete(model_request())
    except ModelGatewayError as exc:
        assert str(exc) == "model tpm limit exceeded"
    else:
        raise AssertionError("tpm limit must reject oversized prompt")

    assert gateway.requests == []
    model_call = db_session.execute(select(ModelCall)).scalar_one()
    assert model_call.status == "FAILED"
    assert model_call.error_message == "model tpm limit exceeded"


def test_audited_model_gateway_opens_provider_circuit(db_session: Session) -> None:
    ModelRateLimiter.clear()
    ModelCircuitBreaker.clear()
    task = create_task(db_session)
    db_session.add(
        SystemSetting(
            organization_id=task.organization_id,
            key="settings.models",
            value_json={
                "default_provider": "openai-compatible",
                "default_model": "default",
                "providers": [
                    {
                        "name": "openai-compatible",
                        "status": "healthy",
                        "rate_limit_rpm": 60,
                        "rate_limit_tpm": 120000,
                        "circuit_breaker": {
                            "failure_threshold": 2,
                            "cooldown_seconds": 60,
                        },
                    }
                ],
                "rate_limits": {"rpm": 60, "tpm": 120000},
                "health": {"status": "healthy", "updated_at": None},
                "circuit_breaker": {"failure_threshold": 2, "cooldown_seconds": 60},
            },
            updated_by="dev-admin",
            updated_at=utc_now(),
        )
    )
    db_session.flush()
    gateway = SequenceGateway(
        [
            ModelGatewayError("upstream failed once"),
            ModelGatewayError("upstream failed twice"),
            ModelResponse(content="{}", model_provider="openai-compatible", model_name="default"),
        ]
    )
    audited = AuditedModelGateway(session=db_session, task_id=task.id, gateway=gateway)

    for expected in ["upstream failed once", "upstream failed twice"]:
        try:
            audited.complete(model_request())
        except ModelGatewayError as exc:
            assert str(exc) == expected
        else:
            raise AssertionError("upstream failure must bubble")
    try:
        audited.complete(model_request())
    except ModelGatewayError as exc:
        assert str(exc) == "model provider circuit open"
    else:
        raise AssertionError("open circuit must reject third call")

    assert len(gateway.requests) == 2
    calls = list(db_session.execute(select(ModelCall).order_by(ModelCall.created_at)).scalars())
    assert [call.status for call in calls] == ["FAILED", "FAILED", "FAILED"]
