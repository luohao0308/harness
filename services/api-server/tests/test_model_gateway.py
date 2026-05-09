import json

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.model_gateway import (
    AnthropicCompatibleModelGateway,
    AuditedModelGateway,
    ModelCircuitBreaker,
    ModelGatewayError,
    ModelMessage,
    ModelRateLimiter,
    ModelRequest,
    ModelResponse,
    OpenAICompatibleModelGateway,
)
from app.db.models import ModelCall, SystemSetting, Task, utc_now
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.main import app
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
    assert captured["timeout"] == 7
    assert b'"model": "default"' in captured["body"]
    assert response.content == '{"summary":"ok"}'
    assert response.usage == {"prompt_tokens": 2, "completion_tokens": 4}


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
        base_url="https://api.minimaxi.com/anthropic",
        api_key="secret-key",
        timeout_seconds=9,
        max_tokens=2048,
    )
    response = gateway.complete(
        ModelRequest(
            model_provider="minimax",
            model_name="MiniMax-M2.7-highspeed",
            messages=[
                ModelMessage(role="system", content="You are concise."),
                ModelMessage(role="user", content="plan this task"),
            ],
        )
    )

    assert captured["url"] == "https://api.minimaxi.com/anthropic/v1/messages"
    assert captured["authorization"] == "Bearer secret-key"
    assert captured["timeout"] == 9
    body = json.loads(captured["body"].decode("utf-8"))
    assert body["model"] == "MiniMax-M2.7-highspeed"
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
                "default_provider": "openai-compatible",
                "default_model": "configured-model",
                "providers": [
                    {
                        "name": "openai-compatible",
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
                model_provider="openai-compatible",
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
