import io
import json
import urllib.error

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import SystemSetting
from app.knowledge import ground_query
from app.knowledge_connectors import (
    CONNECTOR_RELEASE_STATE_PREVIEW_NOT_COUNTED,
    CONNECTOR_RELEASE_STATE_USABLE,
)
from app.knowledge_coze import (
    CozeConnectorError,
    CozeKnowledgeBaseAdapter,
    CozeRetrievalResult,
)
from app.knowledge_dify import (
    DifyConnectorError,
    DifyDatasetDocumentStatus,
    DifyKnowledgeBaseAdapter,
    DifyRetrievalResult,
    connector_secret_setting_key,
)
from app.main import app
from tests.test_knowledge_rag import ADMIN_HEADERS, _ensure_agent, _two_chunk_content


@pytest.mark.parametrize(
    ("provider", "expected_state", "secret_ref", "source_type"),
    [
        ("dify", CONNECTOR_RELEASE_STATE_USABLE, "secret://dify", "document"),
        ("markdown_directory", CONNECTOR_RELEASE_STATE_USABLE, None, "markdown"),
        ("ragflow", CONNECTOR_RELEASE_STATE_PREVIEW_NOT_COUNTED, "secret://ragflow", "document"),
        ("coze", CONNECTOR_RELEASE_STATE_USABLE, "secret://coze", "document"),
        (
            "local_dify",
            CONNECTOR_RELEASE_STATE_PREVIEW_NOT_COUNTED,
            "secret://local-dify",
            "document",
        ),
        (
            "local_ragflow",
            CONNECTOR_RELEASE_STATE_PREVIEW_NOT_COUNTED,
            "secret://local-ragflow",
            "document",
        ),
    ],
)
def test_connector_release_state_labels_and_usable_counts(
    db_session: Session,
    provider: str,
    expected_state: str,
    secret_ref: str | None,
    source_type: str,
) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)
    reference_settings = {
        "dify": {"dataset_id": "dataset-123"},
        "coze": {"dataset_id": "dataset-123"},
        "ragflow": {"dataset_id": "dataset-123"},
    }.get(provider, {})
    payload = {
        "name": f"{provider}-source",
        "description": "Connector release-state fixture",
        "source_type": source_type,
        "title": f"{provider} docs",
        "content": _two_chunk_content(f"{provider} connector beacon"),
        "mime_type": "text/markdown",
        "connector_settings_json": {
            "provider": provider,
            **({"endpoint": f"https://{provider}.example"} if secret_ref is not None else {}),
            **({"secret_ref": secret_ref} if secret_ref is not None else {}),
            **reference_settings,
        },
    }
    created = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json=payload,
    )

    assert created.status_code == 201
    body = created.json()
    assert body["connector_provider"] == provider
    assert body["connector_release_state"] == expected_state
    assert body["connector_counts_toward_complete_usable"] == (
        expected_state == CONNECTOR_RELEASE_STATE_USABLE
    )
    assert body["connector_validation_status"] in {"ready", "configured", "preview"}
    assert body["latest_documents"][0]["chunk_count"] >= 1


def test_connector_secret_ref_is_required_and_redacted(db_session: Session) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)

    missing_secret_ref = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "secret-missing",
            "description": "Connector secret ref missing",
            "source_type": "connector",
            "title": "Secret Missing",
            "content": _two_chunk_content("secret ref gate"),
            "mime_type": "text/markdown",
            "connector_settings_json": {
                "provider": "dify",
                "endpoint": "https://dify.example",
                "dataset_id": "dataset-123",
            },
        },
    )
    assert missing_secret_ref.status_code == 400
    assert "secret_ref" in missing_secret_ref.json()["detail"]

    created = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "secret-redacted",
            "description": "Connector secret redaction",
            "source_type": "connector",
            "title": "Secret Redacted",
            "content": _two_chunk_content("secret redaction beacon"),
            "mime_type": "text/markdown",
            "connector_settings_json": {
                "provider": "dify",
                "secret_ref": "secret://dify",
                "api_key": "raw-api-key-should-not-leak",
                "endpoint": "https://dify.example",
                "dataset_id": "dataset-123",
            },
        },
    )
    assert created.status_code == 201
    settings_json = created.json()["settings_json"]
    assert settings_json["secret_ref"] == "secret://dify"
    assert settings_json["api_key"] == "[REDACTED]"

    raw_secret_ref = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "raw-secret-ref",
            "description": "Connector raw secret ref rejected",
            "source_type": "connector",
            "title": "Raw Secret Ref",
            "content": _two_chunk_content("raw secret ref gate"),
            "mime_type": "text/markdown",
            "connector_settings_json": {
                "provider": "dify",
                "secret_ref": "dataset-NAyAfpTA8FHF6fNktg2F7RnI",
                "endpoint": "https://dify.example",
                "dataset_id": "dataset-123",
            },
        },
    )
    assert raw_secret_ref.status_code == 400
    assert "server-side secret" in raw_secret_ref.json()["detail"]


def test_connector_settings_can_be_updated_without_raw_secret_leak(db_session: Session) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)

    created = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "coze-editable",
            "description": "Coze connector edit fixture",
            "source_type": "connector",
            "title": "Coze Editable",
            "content": _two_chunk_content("coze editable connector beacon"),
            "mime_type": "text/markdown",
            "connector_settings_json": {
                "provider": "coze",
                "endpoint": "https://api.coze.cn",
                "secret_ref": "secret://coze",
                "dataset_id": "space-7618108220116893732",
            },
            "connector_secret_value": "coze-api-key-value",
        },
    )
    assert created.status_code == 201
    source_id = created.json()["id"]

    updated = client.patch(
        f"/api/agents/default/knowledge/sources/{source_id}",
        headers=ADMIN_HEADERS,
        json={
            "name": "Coze 知识库",
            "description": "Coze API 接入配置",
            "connector_settings_json": {
                "provider": "coze",
                "endpoint": "https://api.coze.cn",
                "secret_ref": "secret://coze",
                "dataset_id": "7629341424630448134",
                "api_key": "raw-value-should-be-redacted",
            },
        },
    )

    assert updated.status_code == 200
    body = updated.json()
    assert body["settings_json"]["dataset_id"] == "7629341424630448134"
    assert body["settings_json"]["secret_ref"] == "secret://coze"
    assert body["settings_json"]["api_key"] == "[REDACTED]"
    assert body["connector_validation_status"] == "ready"
    assert body["connector_secret_configured"] is True


def test_connector_settings_update_rejects_raw_secret_ref(db_session: Session) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)

    created = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "dify-editable",
            "description": "Dify connector edit fixture",
            "source_type": "connector",
            "title": "Dify Editable",
            "content": _two_chunk_content("dify editable connector beacon"),
            "mime_type": "text/markdown",
            "connector_settings_json": {
                "provider": "dify",
                "endpoint": "https://api.dify.ai/v1",
                "secret_ref": "secret://dify",
                "dataset_id": "dataset-123",
            },
        },
    )
    assert created.status_code == 201

    rejected = client.patch(
        f"/api/agents/default/knowledge/sources/{created.json()['id']}",
        headers=ADMIN_HEADERS,
        json={
            "connector_settings_json": {
                "provider": "dify",
                "endpoint": "https://api.dify.ai/v1",
                "secret_ref": "dataset-NAyAfpTA8FHF6fNktg2F7RnI",
                "dataset_id": "dataset-123",
            },
        },
    )

    assert rejected.status_code == 400
    assert "server-side secret" in rejected.json()["detail"]


def test_connector_secret_value_is_stored_server_side_and_not_returned(
    db_session: Session,
) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)

    created = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "dify-secret-value",
            "description": "Connector secret value storage",
            "source_type": "connector",
            "title": "Dify Secret Value",
            "content": _two_chunk_content("secret value storage beacon"),
            "mime_type": "text/markdown",
            "connector_secret_value": "front-end-supplied-dify-key",
            "connector_settings_json": {
                "provider": "dify",
                "secret_ref": "secret://dify",
                "endpoint": "https://api.dify.ai/v1",
                "dataset_id": "dataset-123",
            },
        },
    )

    assert created.status_code == 201
    body = created.json()
    assert body["connector_secret_configured"] is True
    assert body["settings_json"]["secret_ref"] == "secret://dify"
    assert "front-end-supplied-dify-key" not in json.dumps(body)
    stored = db_session.query(SystemSetting).filter_by(
        organization_id="dev-org",
        key=connector_secret_setting_key("secret://dify"),
    ).one()
    assert stored.value_json["secret_value"] == "front-end-supplied-dify-key"

    listed = client.get("/api/agents/default/knowledge/sources", headers=ADMIN_HEADERS)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["connector_secret_configured"] is True
    assert "front-end-supplied-dify-key" not in listed.text


def test_connector_endpoint_is_required_and_cannot_include_credentials(
    db_session: Session,
) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)

    missing_endpoint = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "endpoint-missing",
            "description": "Connector endpoint missing",
            "source_type": "connector",
            "title": "Endpoint Missing",
            "content": _two_chunk_content("endpoint ref gate"),
            "mime_type": "text/markdown",
            "connector_settings_json": {
                "provider": "dify",
                "secret_ref": "secret://dify",
                "dataset_id": "dataset-123",
            },
        },
    )
    assert missing_endpoint.status_code == 400
    assert "endpoint" in missing_endpoint.json()["detail"]

    credentials_in_endpoint = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "endpoint-credentials",
            "description": "Connector endpoint credential block",
            "source_type": "connector",
            "title": "Endpoint Credentials",
            "content": _two_chunk_content("credential endpoint gate"),
            "uri": "https://user:pass@dify.example",
            "mime_type": "text/markdown",
            "connector_settings_json": {
                "provider": "dify",
                "endpoint": "https://user:pass@dify.example",
                "secret_ref": "secret://dify",
                "dataset_id": "dataset-123",
            },
        },
    )
    assert credentials_in_endpoint.status_code == 400
    assert "credentials" in credentials_in_endpoint.json()["detail"]


def test_external_api_connector_reference_id_is_required(db_session: Session) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)

    missing_reference = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "dataset-missing",
            "description": "Connector dataset ref missing",
            "source_type": "connector",
            "title": "Dataset Missing",
            "content": _two_chunk_content("dataset ref gate"),
            "mime_type": "text/markdown",
            "connector_settings_json": {
                "provider": "ragflow",
                "endpoint": "https://ragflow.example",
                "secret_ref": "secret://ragflow",
            },
        },
    )

    assert missing_reference.status_code == 400
    assert "dataset_id" in missing_reference.json()["detail"]


def test_no_web_crawler_path_is_available(db_session: Session) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)
    blocked = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "crawler-block",
            "description": "Crawler not allowed",
            "source_type": "document",
            "title": "Crawler Block",
            "content": _two_chunk_content("crawler boundary beacon"),
            "mime_type": "text/markdown",
            "connector_settings_json": {
                "provider": "web_crawler",
            },
        },
    )
    assert blocked.status_code == 400
    assert "crawler" in blocked.json()["detail"].lower()


def test_crawler_style_connector_options_are_rejected(db_session: Session) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)

    blocked = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "follow-links-block",
            "description": "Crawler flags not allowed",
            "source_type": "connector",
            "title": "Follow Links Block",
            "content": _two_chunk_content("follow links boundary beacon"),
            "mime_type": "text/markdown",
            "connector_settings_json": {
                "provider": "dify",
                "endpoint": "https://dify.example",
                "secret_ref": "secret://dify",
                "dataset_id": "dataset-123",
                "follow_links": True,
                "max_depth": 2,
            },
        },
    )

    assert blocked.status_code == 400
    assert "crawler" in blocked.json()["detail"].lower()


def test_non_runtime_connector_configuration_does_not_create_verified_grounding_evidence(
    db_session: Session,
) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "retrieval-source",
            "description": "Connector retrieval",
            "source_type": "connector",
            "title": "Retrieval Source",
            "content": _two_chunk_content("connector retrieval beacon"),
            "mime_type": "text/markdown",
            "connector_settings_json": {
                "provider": "ragflow",
                "secret_ref": "secret://ragflow",
                "endpoint": "https://ragflow.example",
                "dataset_id": "dataset-123",
            },
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["source_type"] == "connector"
    assert body["latest_documents"][0]["metadata_json"]["connector_config_only"] is True

    grounded = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=None,
        query="connector retrieval beacon",
    )
    assert grounded.local_status == "insufficient"
    assert grounded.verified_grounded is False
    assert grounded.grounding_provider == "none"
    assert not grounded.retrieval_hits


def test_dify_connector_retrieval_calls_provider_when_local_evidence_is_insufficient(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "dify-runtime-source",
            "description": "Dify runtime retrieval",
            "source_type": "connector",
            "title": "Dify Runtime Source",
            "content": _two_chunk_content("dify config only beacon"),
            "mime_type": "text/markdown",
            "connector_settings_json": {
                "provider": "dify",
                "secret_ref": "secret://dify",
                "endpoint": "https://api.dify.ai/v1",
                "dataset_id": "dataset-123",
            },
        },
    )
    assert created.status_code == 201
    assert created.json()["latest_documents"][0]["metadata_json"]["connector_config_only"] is True

    class Adapter:
        provider = "dify"

        def __init__(self) -> None:
            self.calls: list[dict] = []

        def retrieve(self, **kwargs):
            self.calls.append(kwargs)
            assert kwargs["endpoint"] == "https://api.dify.ai/v1"
            assert kwargs["dataset_id"] == "dataset-123"
            assert kwargs["api_key"] == "resolved-dify-key"
            assert kwargs["query"] == "runtime question"
            return [
                DifyRetrievalResult(
                    content="Dify returned source-bound answer content.",
                    rank=1,
                    score=0.91,
                    dataset_id="dataset-123",
                    segment_id="segment-1",
                    document_id="dify-document-1",
                    document_name="Dify Doc",
                    position=7,
                )
            ]

    adapter = Adapter()
    monkeypatch.setattr(
        "app.knowledge.resolve_connector_secret_ref",
        lambda *_args, **_kwargs: "resolved-dify-key",
    )
    monkeypatch.setattr("app.knowledge.get_dify_retrieval_adapter", lambda provider: adapter)

    grounded = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=None,
        query="runtime question",
    )

    assert len(adapter.calls) == 1
    assert grounded.local_status == "insufficient"
    assert grounded.grounded is True
    assert grounded.verified_grounded is True
    assert grounded.grounding_provider == "dify_connector"
    assert grounded.grounding_verification_reason == "connector_source_bound"
    assert grounded.retrieval_session is not None
    assert grounded.retrieval_session.mode == "connector_fallback"
    assert grounded.retrieval_session.metadata_json["connector_hit_count"] == 1
    assert grounded.retrieval_session.metadata_json["connector_secret_resolved"] is True
    assert [hit.source_kind for hit in grounded.retrieval_hits] == ["dify_connector"]
    assert grounded.retrieval_hits[0].chunk_id is None
    assert grounded.retrieval_hits[0].web_source_id is None
    assert grounded.retrieval_hits[0].metadata_json["dataset_id"] == "dataset-123"
    assert grounded.retrieval_hits[0].metadata_json["segment_id"] == "segment-1"
    assert grounded.citations[0].citation_key == "[D1]"
    assert grounded.citations[0].source_kind == "dify_connector"
    assert grounded.prompt_manifest is not None
    assert grounded.prompt_manifest.metadata_json["grounding_provider"] == "dify_connector"
    assert "Dify connector evidence" in grounded.evidence_summary
    assert "secret" not in str(grounded.prompt_manifest.source_snapshots_json).lower()


def test_coze_connector_retrieval_calls_provider_when_local_evidence_is_insufficient(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "coze-runtime-source",
            "description": "Coze runtime retrieval",
            "source_type": "connector",
            "title": "Coze Runtime Source",
            "content": _two_chunk_content("coze config only beacon"),
            "mime_type": "text/markdown",
            "connector_settings_json": {
                "provider": "coze",
                "secret_ref": "secret://coze",
                "endpoint": "https://api.coze.cn",
                "dataset_id": "dataset-123",
            },
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["connector_release_state"] == CONNECTOR_RELEASE_STATE_USABLE
    assert body["connector_counts_toward_complete_usable"] is True
    assert body["latest_documents"][0]["metadata_json"]["connector_config_only"] is True

    class Adapter:
        provider = "coze"

        def __init__(self) -> None:
            self.calls: list[dict] = []

        def retrieve(self, **kwargs):
            self.calls.append(kwargs)
            assert kwargs["endpoint"] == "https://api.coze.cn"
            assert kwargs["dataset_id"] == "dataset-123"
            assert kwargs["api_key"] == "resolved-coze-key"
            assert kwargs["query"] == "runtime question"
            return [
                CozeRetrievalResult(
                    content="Coze returned source-bound answer content.",
                    rank=1,
                    score=0.93,
                    dataset_id="dataset-123",
                    segment_id="segment-1",
                    document_id="coze-document-1",
                    document_name="Coze Doc",
                )
            ]

    adapter = Adapter()
    monkeypatch.setattr(
        "app.knowledge.resolve_connector_secret_ref",
        lambda *_args, **_kwargs: "resolved-coze-key",
    )
    monkeypatch.setattr("app.knowledge.get_coze_retrieval_adapter", lambda provider: adapter)

    grounded = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=None,
        query="runtime question",
    )

    assert len(adapter.calls) == 1
    assert grounded.local_status == "insufficient"
    assert grounded.grounded is True
    assert grounded.verified_grounded is True
    assert grounded.grounding_provider == "coze_connector"
    assert grounded.grounding_verification_reason == "connector_source_bound"
    assert grounded.retrieval_session is not None
    assert grounded.retrieval_session.mode == "connector_fallback"
    assert grounded.retrieval_session.metadata_json["connector_provider"] == "coze"
    assert grounded.retrieval_session.metadata_json["connector_hit_count"] == 1
    assert grounded.retrieval_session.metadata_json["connector_secret_resolved"] is True
    assert [hit.source_kind for hit in grounded.retrieval_hits] == ["coze_connector"]
    assert grounded.retrieval_hits[0].chunk_id is None
    assert grounded.retrieval_hits[0].web_source_id is None
    assert grounded.retrieval_hits[0].metadata_json["dataset_id"] == "dataset-123"
    assert grounded.retrieval_hits[0].metadata_json["segment_id"] == "segment-1"
    assert grounded.retrieval_hits[0].metadata_json["coze_document_id"] == "coze-document-1"
    assert grounded.citations[0].citation_key == "[C1]"
    assert grounded.citations[0].source_kind == "coze_connector"
    assert grounded.prompt_manifest is not None
    assert grounded.prompt_manifest.metadata_json["grounding_provider"] == "coze_connector"
    assert "Coze connector evidence" in grounded.evidence_summary
    assert "secret" not in str(grounded.prompt_manifest.source_snapshots_json).lower()


def test_coze_connector_missing_secret_does_not_fabricate_grounding(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "coze-missing-runtime-secret",
            "description": "Coze missing runtime secret",
            "source_type": "connector",
            "title": "Coze Missing Secret",
            "content": _two_chunk_content("coze missing secret config beacon"),
            "mime_type": "text/markdown",
            "connector_settings_json": {
                "provider": "coze",
                "secret_ref": "secret://coze",
                "endpoint": "https://api.coze.cn",
                "dataset_id": "dataset-123",
            },
        },
    )
    assert created.status_code == 201

    class Adapter:
        provider = "coze"

        def retrieve(self, **kwargs):  # pragma: no cover - should not be called
            raise AssertionError("Coze adapter must not be called without a resolved key")

    monkeypatch.setattr(
        "app.knowledge.resolve_connector_secret_ref",
        lambda *_args, **_kwargs: "",
    )
    monkeypatch.setattr("app.knowledge.get_coze_retrieval_adapter", lambda provider: Adapter())

    grounded = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=None,
        query="runtime question without key",
    )

    assert grounded.local_status == "insufficient"
    assert grounded.grounded is False
    assert grounded.verified_grounded is False
    assert grounded.grounding_provider == "none"
    assert grounded.retrieval_hits == []
    assert grounded.citations == []
    assert grounded.retrieval_session is not None
    assert grounded.retrieval_session.metadata_json["connector_provider"] == "coze"
    assert grounded.retrieval_session.metadata_json["connector_secret_resolved"] is False
    assert grounded.retrieval_session.metadata_json["connector_failed"] is True
    assert "Coze connector is configured" in grounded.evidence_message
    assert "API Key secret value" in grounded.evidence_message


def test_coze_connector_provider_error_is_visible_without_grounding(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "coze-provider-error",
            "description": "Coze provider error",
            "source_type": "connector",
            "title": "Coze Provider Error",
            "content": _two_chunk_content("coze provider error config beacon"),
            "mime_type": "text/markdown",
            "connector_settings_json": {
                "provider": "coze",
                "secret_ref": "secret://coze",
                "endpoint": "https://api.coze.cn",
                "dataset_id": "dataset-123",
            },
        },
    )
    assert created.status_code == 201

    class CozeErrorAdapter:
        provider = "coze"

        def retrieve(self, **kwargs):
            raise CozeConnectorError("coze retrieval failed with HTTP 401")

    monkeypatch.setattr(
        "app.knowledge.resolve_connector_secret_ref",
        lambda *_args, **_kwargs: "resolved-coze-key",
    )
    monkeypatch.setattr(
        "app.knowledge.get_coze_retrieval_adapter",
        lambda provider: CozeErrorAdapter(),
    )

    grounded = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=None,
        query="runtime question provider error",
    )

    assert grounded.grounded is False
    assert grounded.verified_grounded is False
    assert grounded.retrieval_session is not None
    assert grounded.retrieval_session.metadata_json["connector_provider"] == "coze"
    assert grounded.retrieval_session.metadata_json["connector_secret_resolved"] is True
    assert grounded.retrieval_session.metadata_json["connector_failed"] is True
    assert "Coze connector retrieval failed" in grounded.evidence_message
    assert "HTTP 401" in grounded.evidence_message


def test_coze_empty_results_fall_through_to_dify_connector(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)
    coze_created = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "coze-empty-runtime-source",
            "description": "Coze empty runtime retrieval",
            "source_type": "connector",
            "title": "Coze Empty Runtime Source",
            "content": _two_chunk_content("coze empty config only beacon"),
            "mime_type": "text/markdown",
            "connector_settings_json": {
                "provider": "coze",
                "secret_ref": "secret://coze",
                "endpoint": "https://api.coze.cn",
                "dataset_id": "coze-dataset-123",
            },
        },
    )
    assert coze_created.status_code == 201
    dify_created = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "dify-fallback-runtime-source",
            "description": "Dify fallback runtime retrieval",
            "source_type": "connector",
            "title": "Dify Fallback Runtime Source",
            "content": _two_chunk_content("dify fallback config only beacon"),
            "mime_type": "text/markdown",
            "connector_settings_json": {
                "provider": "dify",
                "secret_ref": "secret://dify",
                "endpoint": "https://api.dify.ai/v1",
                "dataset_id": "dify-dataset-123",
            },
        },
    )
    assert dify_created.status_code == 201

    class EmptyCozeAdapter:
        provider = "coze"

        def __init__(self) -> None:
            self.calls: list[dict] = []

        def retrieve(self, **kwargs):
            self.calls.append(kwargs)
            return []

    class DifyFallbackAdapter:
        provider = "dify"

        def __init__(self) -> None:
            self.calls: list[dict] = []

        def retrieve(self, **kwargs):
            self.calls.append(kwargs)
            return [
                DifyRetrievalResult(
                    content="Dify fallback source-bound answer content.",
                    rank=1,
                    score=0.9,
                    dataset_id="dify-dataset-123",
                    segment_id="segment-1",
                    document_id="dify-document-1",
                    document_name="Dify Fallback Doc",
                    position=1,
                )
            ]

    coze_adapter = EmptyCozeAdapter()
    dify_adapter = DifyFallbackAdapter()
    monkeypatch.setattr(
        "app.knowledge.resolve_connector_secret_ref",
        lambda *_args, **kwargs: f"resolved-{kwargs['provider']}-key",
    )
    monkeypatch.setattr("app.knowledge.get_coze_retrieval_adapter", lambda provider: coze_adapter)
    monkeypatch.setattr("app.knowledge.get_dify_retrieval_adapter", lambda provider: dify_adapter)

    grounded = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=None,
        query="公司的愿景与价值观是什么",
    )

    assert len(coze_adapter.calls) == 1
    assert len(dify_adapter.calls) == 1
    assert grounded.grounded is True
    assert grounded.grounding_provider == "dify_connector"
    assert grounded.retrieval_session is not None
    assert grounded.retrieval_session.metadata_json["connector_provider"] == "dify"
    assert grounded.retrieval_session.metadata_json["connector_hit_count"] == 1
    assert [hit.source_kind for hit in grounded.retrieval_hits] == ["dify_connector"]
    assert "Dify connector grounded the answer" in grounded.evidence_message


def test_dify_connector_runtime_uses_frontend_stored_secret(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "dify-stored-secret-runtime",
            "description": "Dify stored secret runtime retrieval",
            "source_type": "connector",
            "title": "Dify Stored Secret Runtime",
            "content": _two_chunk_content("dify stored secret config beacon"),
            "mime_type": "text/markdown",
            "connector_secret_value": "stored-dify-runtime-key",
            "connector_settings_json": {
                "provider": "dify",
                "secret_ref": "secret://dify",
                "endpoint": "https://api.dify.ai/v1",
                "dataset_id": "dataset-123",
            },
        },
    )
    assert created.status_code == 201

    class Adapter:
        provider = "dify"

        def __init__(self) -> None:
            self.calls: list[dict] = []

        def retrieve(self, **kwargs):
            self.calls.append(kwargs)
            assert kwargs["api_key"] == "stored-dify-runtime-key"
            return [
                DifyRetrievalResult(
                    content="Stored secret Dify content.",
                    rank=1,
                    score=0.9,
                    dataset_id="dataset-123",
                )
            ]

    adapter = Adapter()
    monkeypatch.setattr("app.knowledge.get_dify_retrieval_adapter", lambda provider: adapter)

    grounded = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=None,
        query="runtime question",
    )

    assert len(adapter.calls) == 1
    assert grounded.grounded is True
    assert grounded.retrieval_session is not None
    assert grounded.retrieval_session.metadata_json["connector_secret_resolved"] is True
    assert grounded.prompt_manifest is not None
    assert "stored-dify-runtime-key" not in str(grounded.prompt_manifest.source_snapshots_json)


def test_coze_connector_runtime_uses_frontend_stored_secret(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "coze-stored-secret-runtime",
            "description": "Coze stored secret runtime retrieval",
            "source_type": "connector",
            "title": "Coze Stored Secret Runtime",
            "content": _two_chunk_content("coze stored secret config beacon"),
            "mime_type": "text/markdown",
            "connector_secret_value": "stored-coze-runtime-key",
            "connector_settings_json": {
                "provider": "coze",
                "secret_ref": "secret://coze",
                "endpoint": "https://api.coze.cn",
                "dataset_id": "dataset-123",
            },
        },
    )
    assert created.status_code == 201
    assert created.json()["connector_secret_configured"] is True

    class Adapter:
        provider = "coze"

        def __init__(self) -> None:
            self.calls: list[dict] = []

        def retrieve(self, **kwargs):
            self.calls.append(kwargs)
            assert kwargs["api_key"] == "stored-coze-runtime-key"
            return [
                CozeRetrievalResult(
                    content="Stored secret Coze content.",
                    rank=1,
                    score=0.91,
                    dataset_id="dataset-123",
                )
            ]

    adapter = Adapter()
    monkeypatch.setattr("app.knowledge.get_coze_retrieval_adapter", lambda provider: adapter)

    grounded = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=None,
        query="runtime question",
    )

    assert len(adapter.calls) == 1
    assert grounded.grounded is True
    assert grounded.grounding_provider == "coze_connector"
    assert grounded.retrieval_session is not None
    assert grounded.retrieval_session.metadata_json["connector_secret_resolved"] is True
    assert grounded.prompt_manifest is not None
    assert "stored-coze-runtime-key" not in str(grounded.prompt_manifest.source_snapshots_json)


def test_dify_connector_missing_secret_does_not_fabricate_grounding(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "dify-missing-runtime-secret",
            "description": "Dify missing runtime secret",
            "source_type": "connector",
            "title": "Dify Missing Secret",
            "content": _two_chunk_content("dify missing secret config beacon"),
            "mime_type": "text/markdown",
            "connector_settings_json": {
                "provider": "dify",
                "secret_ref": "secret://dify",
                "endpoint": "https://api.dify.ai/v1",
                "dataset_id": "dataset-123",
            },
        },
    )
    assert created.status_code == 201

    class Adapter:
        provider = "dify"

        def retrieve(self, **kwargs):  # pragma: no cover - should not be called
            raise AssertionError("Dify adapter must not be called without a resolved key")

    monkeypatch.setattr(
        "app.knowledge.resolve_connector_secret_ref",
        lambda *_args, **_kwargs: "",
    )
    monkeypatch.setattr("app.knowledge.get_dify_retrieval_adapter", lambda provider: Adapter())

    grounded = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=None,
        query="runtime question without key",
    )

    assert grounded.local_status == "insufficient"
    assert grounded.grounded is False
    assert grounded.verified_grounded is False
    assert grounded.grounding_provider == "none"
    assert grounded.retrieval_hits == []
    assert grounded.citations == []
    assert grounded.retrieval_session is not None
    assert grounded.retrieval_session.metadata_json["connector_secret_resolved"] is False
    assert grounded.retrieval_session.metadata_json["connector_failed"] is True
    assert "Dify connector is configured" in grounded.evidence_message
    assert "API Key secret value" in grounded.evidence_message


def test_dify_connector_provider_error_is_visible_without_grounding(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "dify-provider-error",
            "description": "Dify provider error",
            "source_type": "connector",
            "title": "Dify Provider Error",
            "content": _two_chunk_content("dify provider error config beacon"),
            "mime_type": "text/markdown",
            "connector_settings_json": {
                "provider": "dify",
                "secret_ref": "secret://dify",
                "endpoint": "https://api.dify.ai/v1",
                "dataset_id": "dataset-123",
            },
        },
    )
    assert created.status_code == 201

    class DifyErrorAdapter:
        provider = "dify"

        def retrieve(self, **kwargs):
            from app.knowledge_dify import DifyConnectorError

            raise DifyConnectorError("dify retrieval failed with HTTP 401")

    monkeypatch.setattr(
        "app.knowledge.resolve_connector_secret_ref",
        lambda *_args, **_kwargs: "resolved-dify-key",
    )
    monkeypatch.setattr(
        "app.knowledge.get_dify_retrieval_adapter",
        lambda provider: DifyErrorAdapter(),
    )

    grounded = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=None,
        query="runtime question provider error",
    )

    assert grounded.grounded is False
    assert grounded.verified_grounded is False
    assert grounded.retrieval_session is not None
    assert grounded.retrieval_session.metadata_json["connector_secret_resolved"] is True
    assert grounded.retrieval_session.metadata_json["connector_failed"] is True
    assert "Dify connector retrieval failed" in grounded.evidence_message
    assert "HTTP 401" in grounded.evidence_message


def test_dify_adapter_posts_official_dataset_retrieve_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, *_args):
            return json.dumps(
                {
                    "records": [
                        {
                            "score": 0.88,
                            "segment": {
                                "id": "segment-1",
                                "document_id": "document-1",
                                "content": "Dify segment content",
                                "position": 3,
                                "document": {"id": "document-1", "name": "Dataset Doc"},
                            },
                        }
                    ]
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return Response()

    monkeypatch.setattr("app.knowledge_dify.urllib.request.urlopen", fake_urlopen)

    results = DifyKnowledgeBaseAdapter().retrieve(
        endpoint="https://api.dify.ai/v1",
        dataset_id="dataset-123",
        api_key="runtime-key",
        query="What is indexed?",
        max_results=2,
        timeout_seconds=5,
    )

    assert captured["url"] == "https://api.dify.ai/v1/datasets/dataset-123/retrieve"
    assert captured["timeout"] == 5
    assert captured["headers"]["Authorization"] == "Bearer runtime-key"
    assert captured["headers"]["Accept"] == "application/json"
    assert captured["headers"]["User-agent"] == "AgentHarness/0.1"
    assert captured["body"]["query"] == "What is indexed?"
    assert "retrieval_model" not in captured["body"]
    assert results == [
        DifyRetrievalResult(
            content="Dify segment content",
            rank=1,
            score=0.88,
            dataset_id="dataset-123",
            segment_id="segment-1",
            document_id="document-1",
            document_name="Dataset Doc",
            position=3,
        )
    ]


def test_dify_adapter_reports_provider_error_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_http_error(*_args):
        return urllib.error.HTTPError(
            "https://api.dify.ai/v1/datasets/dataset-123/retrieve",
            400,
            "Bad Request",
            {},
            io.BytesIO(
                json.dumps(
                    {
                        "code": "invalid_param",
                        "message": "embedding quota denied",
                    }
                ).encode("utf-8")
            ),
        )

    def fake_urlopen_with_body(_request, timeout):
        assert timeout == 5
        raise fake_http_error()

    monkeypatch.setattr("app.knowledge_dify.urllib.request.urlopen", fake_urlopen_with_body)

    with pytest.raises(DifyConnectorError) as error:
        DifyKnowledgeBaseAdapter().retrieve(
            endpoint="https://api.dify.ai/v1",
            dataset_id="dataset-123",
            api_key="runtime-key",
            query="What is indexed?",
            max_results=2,
            timeout_seconds=5,
        )

    assert "HTTP 400" in str(error.value)
    assert "invalid_param" in str(error.value)
    assert "embedding quota denied" in str(error.value)


def test_coze_adapter_uses_official_document_list_for_base_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict] = []

    class Response:
        def __init__(self, payload: dict | None = None, text: str | None = None) -> None:
            self.payload = payload
            self.text = text

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, *_args):
            if self.text is not None:
                return self.text.encode("utf-8")
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout):
        headers = dict(request.header_items())
        body = json.loads(request.data.decode("utf-8")) if request.data else None
        captured.append(
            {
                "url": request.full_url,
                "method": request.get_method(),
                "timeout": timeout,
                "headers": headers,
                "body": body,
            }
        )
        if request.full_url.endswith("/open_api/knowledge/document/list"):
            return Response(
                {
                    "code": 0,
                    "document_infos": [
                        {
                            "document_id_new": "document-1",
                            "name": "Coze Dataset Doc",
                            "preview_tos_url": "https://coze-content.example/doc.md",
                        }
                    ],
                }
            )
        return Response(
            text=(
                "# Coze Dataset Doc\n\n"
                "Coze segment content answers what is indexed.\n\n"
                "This unrelated content is intentionally long enough to force a separate "
                "chunk when the adapter splits Coze document text into bounded retrieval "
                "snippets. "
                * 12
            )
        )

    monkeypatch.setattr("app.knowledge_coze.urllib.request.urlopen", fake_urlopen)

    results = CozeKnowledgeBaseAdapter().retrieve(
        endpoint="https://api.coze.cn",
        dataset_id="7629341424630448134",
        api_key="runtime-key",
        query="What is indexed?",
        max_results=2,
        timeout_seconds=5,
    )

    assert captured[0]["url"] == "https://api.coze.cn/open_api/knowledge/document/list"
    assert captured[0]["method"] == "POST"
    assert captured[0]["timeout"] == 5
    assert captured[0]["headers"]["Authorization"] == "Bearer runtime-key"
    assert captured[0]["headers"]["Accept"] == "application/json"
    assert captured[0]["headers"]["User-agent"] == "AgentHarness/0.1"
    assert captured[0]["body"]["dataset_id"] == 7629341424630448134
    assert captured[0]["body"]["page"] == 1
    assert captured[0]["body"]["size"] == 5
    assert captured[1]["url"] == "https://coze-content.example/doc.md"
    assert results
    assert "Coze segment content answers what is indexed." in results[0].content
    assert results[0].rank == 1
    assert results[0].dataset_id == "7629341424630448134"
    assert results[0].segment_id is None
    assert results[0].document_id == "document-1"
    assert results[0].document_name == "Coze Dataset Doc"


def test_coze_document_list_rejects_weak_cjk_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        def __init__(self, payload: dict | None = None, text: str | None = None) -> None:
            self.payload = payload
            self.text = text

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, *_args):
            if self.text is not None:
                return self.text.encode("utf-8")
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout):
        assert timeout == 5
        if request.full_url.endswith("/open_api/knowledge/document/list"):
            return Response(
                {
                    "code": 0,
                    "document_infos": [
                        {
                            "document_id_new": "xiamen-science-doc",
                            "name": "厦门科技馆全馆讲解手册",
                            "preview_tos_url": "https://coze-content.example/xiamen.md",
                        }
                    ],
                }
            )
        return Response(
            text=(
                "厦门科技馆位于厦门市，是面向公众开放的综合性科普场馆。"
                "常设展览包括海洋、探索、创造、儿童科学等主题内容。"
                "讲解手册介绍参观路线、展项位置、开放时间和安全须知。"
            )
        )

    monkeypatch.setattr("app.knowledge_coze.urllib.request.urlopen", fake_urlopen)

    results = CozeKnowledgeBaseAdapter().retrieve(
        endpoint="https://api.coze.cn",
        dataset_id="7629341424630448134",
        api_key="runtime-key",
        query="公司的愿景与价值观是什么",
        max_results=2,
        timeout_seconds=5,
    )

    assert results == []


def test_coze_adapter_still_supports_explicit_custom_retrieve_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {
                    "data": {
                        "records": [
                            {
                                "score": 0.87,
                                "segment": {"id": "segment-1"},
                                "document": {"id": "document-1", "name": "Coze Dataset Doc"},
                                "content": "Coze segment content",
                            }
                        ]
                    }
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return Response()

    monkeypatch.setattr("app.knowledge_coze.urllib.request.urlopen", fake_urlopen)

    results = CozeKnowledgeBaseAdapter().retrieve(
        endpoint="https://coze-proxy.example/retrieve",
        dataset_id="dataset-123",
        api_key="runtime-key",
        query="What is indexed?",
        max_results=2,
        timeout_seconds=5,
    )

    assert captured["url"] == "https://coze-proxy.example/retrieve"
    assert captured["body"]["dataset_id"] == "dataset-123"
    assert captured["body"]["query"] == "What is indexed?"
    assert captured["body"]["top_k"] == 2
    assert captured["body"]["limit"] == 2
    assert results == [
        CozeRetrievalResult(
            content="Coze segment content",
            rank=1,
            score=0.87,
            dataset_id="dataset-123",
            segment_id="segment-1",
            document_id="document-1",
            document_name="Coze Dataset Doc",
        )
    ]


def test_coze_adapter_reports_document_list_error_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_http_error(*_args):
        return urllib.error.HTTPError(
            "https://api.coze.cn/open_api/knowledge/document/list",
            400,
            "Bad Request",
            {},
            io.BytesIO(
                json.dumps(
                    {
                        "code": "invalid_param",
                        "msg": "dataset unavailable",
                    }
                ).encode("utf-8")
            ),
        )

    def fake_urlopen_with_body(_request, timeout):
        assert timeout == 5
        raise fake_http_error()

    monkeypatch.setattr("app.knowledge_coze.urllib.request.urlopen", fake_urlopen_with_body)

    with pytest.raises(CozeConnectorError) as error:
        CozeKnowledgeBaseAdapter().retrieve(
            endpoint="https://api.coze.cn",
            dataset_id="dataset-123",
            api_key="runtime-key",
            query="What is indexed?",
            max_results=2,
            timeout_seconds=5,
        )

    assert "HTTP 400" in str(error.value)
    assert "invalid_param" in str(error.value)
    assert "dataset unavailable" in str(error.value)


def test_dify_adapter_reads_document_enabled_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {
                    "data": [
                        {"id": "doc-1", "enabled": False, "indexing_status": "completed"},
                        {"id": "doc-2", "enabled": True, "indexing_status": "completed"},
                    ]
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        return Response()

    monkeypatch.setattr("app.knowledge_dify.urllib.request.urlopen", fake_urlopen)

    status = DifyKnowledgeBaseAdapter().document_status(
        endpoint="https://api.dify.ai/v1",
        dataset_id="dataset-123",
        api_key="runtime-key",
        timeout_seconds=5,
    )

    assert captured["url"] == "https://api.dify.ai/v1/datasets/dataset-123/documents?limit=10"
    assert captured["timeout"] == 5
    assert captured["headers"]["Authorization"] == "Bearer runtime-key"
    assert status == DifyDatasetDocumentStatus(
        document_count=2,
        enabled_document_count=1,
        disabled_document_count=1,
        completed_document_count=2,
    )


def test_dify_connector_empty_results_report_disabled_documents(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "dify-disabled-documents",
            "description": "Dify empty due to disabled docs",
            "source_type": "connector",
            "title": "Dify Disabled Documents",
            "content": _two_chunk_content("dify disabled documents config beacon"),
            "mime_type": "text/markdown",
            "connector_settings_json": {
                "provider": "dify",
                "secret_ref": "secret://dify",
                "endpoint": "https://api.dify.ai/v1",
                "dataset_id": "dataset-123",
            },
        },
    )
    assert created.status_code == 201

    class EmptyDifyAdapter:
        provider = "dify"

        def retrieve(self, **_kwargs):
            return []

        def document_status(self, **_kwargs):
            return DifyDatasetDocumentStatus(
                document_count=4,
                enabled_document_count=0,
                disabled_document_count=4,
                completed_document_count=4,
            )

    monkeypatch.setattr(
        "app.knowledge.resolve_connector_secret_ref",
        lambda *_args, **_kwargs: "resolved-dify-key",
    )
    monkeypatch.setattr(
        "app.knowledge.get_dify_retrieval_adapter",
        lambda provider: EmptyDifyAdapter(),
    )

    grounded = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=None,
        query="runtime question with disabled dify documents",
    )

    assert grounded.grounded is False
    assert grounded.retrieval_session is not None
    assert grounded.retrieval_session.metadata_json["dify_document_count"] == 4
    assert grounded.retrieval_session.metadata_json["dify_enabled_document_count"] == 0
    assert grounded.retrieval_session.metadata_json["dify_disabled_document_count"] == 4
    assert "Dify connector returned no accepted results" in grounded.evidence_message
    assert "all 4 indexed Dify documents are disabled" in grounded.evidence_message


def test_connector_source_type_accepts_dify_preset_contract(db_session: Session) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)

    created = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "dify-api-source",
            "description": "Built-in Dify connector preset",
            "source_type": "connector",
            "title": "Dify API Connector",
            "content": _two_chunk_content("dify external api connector beacon"),
            "uri": "https://api.dify.ai/v1",
            "mime_type": "text/markdown",
            "connector_settings_json": {
                "provider": "dify",
                "endpoint": "https://api.dify.ai/v1",
                "secret_ref": "secret://dify",
                "dataset_id": "dataset-123",
            },
        },
    )

    assert created.status_code == 201
    body = created.json()
    assert body["source_type"] == "connector"
    assert body["connector_provider"] == "dify"
    assert body["connector_release_state"] == CONNECTOR_RELEASE_STATE_USABLE
    assert body["connector_counts_toward_complete_usable"] is True
    assert body["settings_json"]["connector_provider"] == "dify"
    assert body["settings_json"]["secret_ref"] == "secret://dify"
    assert body["settings_json"]["endpoint"] == "https://api.dify.ai/v1"
    assert body["connector_validation_status"] == "ready"
