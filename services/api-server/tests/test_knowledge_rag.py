import hashlib
import json
import shutil
from datetime import timedelta

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.agents.model_gateway import (
    AuditedModelGateway,
    ModelGatewayError,
    ModelMessage,
    ModelRequest,
    ModelResponse,
)
from app.core.config import get_settings
from app.db.models import (
    AdminAuditEvent,
    Agent,
    AgentEvent,
    Base,
    CitationRecord,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeEmbedding,
    KnowledgePolicyAudit,
    KnowledgeSource,
    ModelCall,
    PromptAssemblyManifest,
    RetrievalHit,
    SystemSetting,
    Task,
    WebResearchSource,
    utc_now,
)
from app.events.event_types import EventType
from app.knowledge import (
    VECTOR_CAPABILITY_AVAILABLE,
    _is_safe_research_url,
    create_knowledge_lifecycle_audit,
    ground_query,
    ingest_knowledge_source,
    knowledge_source_lifecycle_snapshot,
    list_knowledge_sources,
    set_vector_capability,
    set_web_research_provider,
)
from app.knowledge_web import WebResearchResult
from app.main import app
from tests.conftest import AUTH_HEADERS

ADMIN_HEADERS = {"Authorization": "Bearer dev-admin-token"}
OPERATOR_HEADERS = {"Authorization": "Bearer dev-operator-token"}
OTHER_ORG_HEADERS = {"Authorization": "Bearer dev-other-org-token"}


def _run_alembic_upgrade(database_url: str, revision: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    try:
        config = Config("alembic.ini")
        config.set_main_option("script_location", "alembic")
        command.upgrade(config, revision)
    finally:
        get_settings.cache_clear()


def _ensure_agent(session: Session, agent_id: str = "default") -> Agent:
    agent = session.get(Agent, agent_id)
    if agent is not None:
        return agent
    agent = Agent(
        id=agent_id,
        organization_id=None,
        name="Default Agent",
        description="Test agent",
        role="planner",
        status="ACTIVE",
        model_provider="default",
        model_name="default",
        system_prompt="You are a test agent.",
        tools_json=[],
        routing_tags=[],
        max_parallel_assignments=1,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(agent)
    session.flush()
    return agent


def _task(session: Session, *, organization_id: str = "dev-org") -> Task:
    task = Task(
        organization_id=organization_id,
        created_by="dev-engineer",
        title="Knowledge grounding",
        goal="Ground this answer",
        status="CREATED",
        model_provider="default",
        model_name="default",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(task)
    session.flush()
    return task


def _two_chunk_content(term: str = "orion anchor") -> str:
    section = f"{term} local fact. " + ("alpha " * 120) + "\n"
    return section * 2


def _enable_web_research_policy(
    session: Session,
    *,
    organization_id: str = "dev-org",
    allow_domains: list[str] | None = None,
    max_content_bytes: int = 1200,
    max_calls_per_run: int = 1,
) -> None:
    session.add(
        SystemSetting(
            organization_id=organization_id,
            key="settings.policies",
            value_json={
                "risk_levels": [
                    {"name": "low", "requires_sandbox": False, "approval": "auto"},
                    {"name": "medium", "requires_sandbox": True, "approval": "auto"},
                    {"name": "high", "requires_sandbox": True, "approval": "admin"},
                    {"name": "critical", "requires_sandbox": True, "approval": "admin"},
                ],
                "approvals": {"manual_review": True, "deny_on_missing_policy": True},
                "sandbox": {
                    "default_network": False,
                    "default_timeout_seconds": 60,
                    "memory_mb": 1024,
                    "cpus": "1.0",
                    "workspace_quota_mb": 1024,
                    "network_allowlist": [],
                },
                "audit": {"model_calls": True, "tool_calls": True, "policy_actions": True},
                "web_research": {
                    "enabled": True,
                    "require_allowlist": True,
                    "allow_domains": (
                        allow_domains if allow_domains is not None else ["example.test"]
                    ),
                    "deny_domains": [],
                    "max_results": 2,
                    "timeout_seconds": 8,
                    "max_content_bytes": max_content_bytes,
                    "max_calls_per_run": max_calls_per_run,
                },
            },
            updated_by="dev-admin",
        )
    )
    session.flush()


def _request_hash_v2(
    *,
    model_provider: str,
    model_name: str,
    response_format: str,
    generation_parameters: dict,
    request_message_hashes: list[dict],
    request_message_hashes_sha256: str,
    retrieval_evidence_ids: list[str],
    prompt_manifest_id: str | None,
    prompt_manifest_version: str | None,
    evidence_text_sha256: str | None,
) -> str:
    canonical_payload = {
        "model_provider": model_provider,
        "model_name": model_name,
        "response_format": response_format,
        "generation_parameters": generation_parameters,
        "request_message_hashes_json": request_message_hashes,
        "request_message_hashes_sha256": request_message_hashes_sha256,
        "retrieval_evidence_ids": sorted(retrieval_evidence_ids),
        "prompt_manifest_id": prompt_manifest_id,
        "prompt_manifest_version": prompt_manifest_version,
        "evidence_text_sha256": evidence_text_sha256,
    }
    encoded = json.dumps(
        canonical_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_ingest_creates_versioned_source_document_chunks_and_embeddings(
    db_session: Session,
) -> None:
    _ensure_agent(db_session)

    source, document, chunks, embeddings = ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Runbook",
        description="Operational knowledge",
        source_type="text",
        title="Runbook v1",
        content="orion anchor local fact",
        uri="memory://runbook",
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="runbook",
    )
    db_session.flush()

    assert source.status == "ACTIVE"
    assert source.version == 1
    assert document.version == 1
    assert document.content_sha256
    assert chunks
    assert embeddings
    assert chunks[0].chunk_index == 1
    assert chunks[0].source_version == source.version
    assert chunks[0].document_version == document.version
    assert chunks[0].status == "ACTIVE"
    assert embeddings[0].provider == "deterministic"
    assert embeddings[0].model_version == "v1"
    assert embeddings[0].dimensions == 24

    source_again, document_again, chunks_again, _embeddings_again = ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Runbook",
        description="Operational knowledge",
        source_type="text",
        title="Runbook v1",
        content="orion anchor local fact",
        uri="memory://runbook",
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="runbook",
    )
    db_session.flush()

    assert source_again.id == source.id
    assert document_again.id == document.id
    assert [chunk.id for chunk in chunks_again] == [chunk.id for chunk in chunks]
    assert db_session.scalar(select(func.count()).select_from(KnowledgeDocument)) == 1
    assert db_session.scalar(select(func.count()).select_from(KnowledgeChunk)) == len(chunks)
    assert db_session.scalar(select(func.count()).select_from(KnowledgeEmbedding)) == len(chunks)


def test_knowledge_source_api_records_ingestion_audit_events(db_session: Session) -> None:
    client = TestClient(app)

    response = client.post(
        "/api/agents/default/knowledge/sources",
        headers=AUTH_HEADERS,
        json={
            "name": "Audited Knowledge",
            "description": "Audited source",
            "source_type": "markdown",
            "title": "Audit Doc",
            "content": "audited fact",
            "mime_type": "text/markdown",
            "idempotency_key": "audited-knowledge",
        },
    )

    assert response.status_code == 201
    events = list(db_session.execute(select(AgentEvent)).scalars())
    event_types = [event.event_type for event in events]
    assert EventType.KNOWLEDGE_SOURCE_CREATED in event_types
    assert EventType.KNOWLEDGE_DOCUMENT_INDEXED in event_types
    indexed = next(
        event
        for event in events
        if event.event_type == EventType.KNOWLEDGE_DOCUMENT_INDEXED
    )
    assert indexed.payload_json["schema_version"] == "knowledge-grounding-v1"
    assert indexed.payload_json["org_id"] == "dev-org"
    assert indexed.payload_json["agent_id"] == "default"
    assert indexed.payload_json["idempotency_key"] == "audited-knowledge"
    assert indexed.payload_json["chunk_count"] >= 1


def test_knowledge_source_api_rejects_oversized_inline_content() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/agents/default/knowledge/sources",
        headers=AUTH_HEADERS,
        json={
            "name": "Oversized Knowledge",
            "description": "Too large for synchronous indexing",
            "source_type": "markdown",
            "title": "Huge Doc",
            "content": "x" * 120_001,
            "mime_type": "text/markdown",
        },
    )

    assert response.status_code == 422


def test_knowledge_source_api_rejects_unsupported_mime_type() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/agents/default/knowledge/sources",
        headers=AUTH_HEADERS,
        json={
            "name": "Unsupported Knowledge",
            "description": "Only text and markdown are allowed",
            "source_type": "document",
            "title": "Unsupported",
            "content": "%PDF-1.7",
            "mime_type": "application/pdf",
        },
    )

    assert response.status_code == 422


def test_knowledge_lifecycle_migration_preserves_existing_p1_rows(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'p1-knowledge-baseline.db'}"
    _run_alembic_upgrade(database_url, "20260517_0014", monkeypatch)
    engine = create_engine(database_url)
    now = "2026-05-16 22:30:00"
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO agents (
                    id, organization_id, name, description, role, status,
                    model_provider, model_name, system_prompt, tools_json,
                    routing_tags, max_parallel_assignments, created_at, updated_at
                )
                VALUES (
                    'default', 'dev-org', 'Default Agent', 'Test agent', 'planner',
                    'ACTIVE', 'default', 'default', 'You are a test agent.',
                    '[]', '[]', 1, :now, :now
                )
                """
            ),
            {"now": now},
        )
        connection.execute(
            text(
                """
                INSERT INTO tasks (
                    id, organization_id, created_by, title, goal, status,
                    model_provider, model_name, max_runtime_seconds, max_subagents,
                    enable_sandbox, enable_network, created_at, updated_at
                )
                VALUES (
                    'task-migration', 'dev-org', 'dev-engineer', 'Migration run',
                    'Verify restored evidence', 'COMPLETED', 'default', 'default',
                    60, 1, 0, 0, :now, :now
                )
                """
            ),
            {"now": now},
        )
        connection.execute(
            text(
                """
                INSERT INTO knowledge_sources (
                    id, organization_id, agent_id, name, description, source_type,
                    status, version, settings_json, metadata_json, idempotency_key,
                    created_by, created_at, updated_at
                )
                VALUES (
                    'source-migration', 'dev-org', 'default', 'Migration Source',
                    'P1 source', 'text', 'ACTIVE', 1, '{}', '{}', 'source-key',
                    'dev-engineer', :now, :now
                )
                """
            ),
            {"now": now},
        )
        connection.execute(
            text(
                """
                INSERT INTO knowledge_documents (
                    id, source_id, organization_id, agent_id, title, uri,
                    content_sha256, mime_type, status, version,
                    supersedes_document_id, ingestion_error, metadata_json,
                    idempotency_key, created_by, created_at, updated_at, indexed_at
                )
                VALUES (
                    'document-migration', 'source-migration', 'dev-org', 'default',
                    'Migration Doc', NULL, :content_hash, 'text/markdown',
                    'INDEXED', 1, NULL, NULL, '{}', 'doc-key', 'dev-engineer',
                    :now, :now, :now
                )
                """
            ),
            {
                "content_hash": hashlib.sha256(b"migration anchor").hexdigest(),
                "now": now,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO knowledge_chunks (
                    id, document_id, source_id, organization_id, agent_id,
                    source_version, document_version, chunk_version, chunk_index,
                    text, text_sha256, start_offset, end_offset, status,
                    metadata_json, created_at
                )
                VALUES (
                    'chunk-migration', 'document-migration', 'source-migration',
                    'dev-org', 'default', 1, 1, 1, 1, 'migration anchor text',
                    :chunk_hash, 0, 21, 'ACTIVE', '{}', :now
                )
                """
            ),
            {
                "chunk_hash": hashlib.sha256(b"migration anchor text").hexdigest(),
                "now": now,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO retrieval_sessions (
                    id, organization_id, agent_id, run_id, query, mode,
                    local_status, vector_capability, strategy, min_hits, min_score,
                    max_local_chunks, max_web_results, metadata_json, created_at
                )
                VALUES (
                    'retrieval-migration', 'dev-org', 'default', 'task-migration',
                    'migration anchor', 'local', 'sufficient', 'unavailable',
                    'lexical', 1, 0.62, 6, 0, '{}', :now
                )
                """
            ),
            {"now": now},
        )
        connection.execute(
            text(
                """
                INSERT INTO retrieval_hits (
                    id, retrieval_session_id, chunk_id, web_source_id, rank,
                    score, source_kind, document_id, document_version, snippet,
                    metadata_json, created_at
                )
                VALUES (
                    'hit-migration', 'retrieval-migration', 'chunk-migration',
                    NULL, 1, 0.99, 'knowledge_chunk', 'document-migration', 1,
                    'migration anchor text', :metadata, :now
                )
                """
            ),
            {
                "metadata": json.dumps(
                    {
                        "source_snapshot": {
                            "source_id": "source-migration",
                            "document_id": "document-migration",
                            "chunk_id": "chunk-migration",
                            "text": "migration anchor text",
                        }
                    }
                ),
                "now": now,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO citation_records (
                    id, retrieval_session_id, retrieval_hit_id, run_id, message_id,
                    citation_key, source_kind, chunk_id, web_source_id, claim_text,
                    quoted_text, confidence, metadata_json, created_at
                )
                VALUES (
                    'citation-migration', 'retrieval-migration', 'hit-migration',
                    'task-migration', NULL, '1', 'knowledge_chunk',
                    'chunk-migration', NULL, NULL, 'migration anchor text',
                    0.99, :metadata, :now
                )
                """
            ),
            {"metadata": json.dumps({"source_id": "source-migration"}), "now": now},
        )
        connection.execute(
            text(
                """
                INSERT INTO prompt_assembly_manifests (
                    id, retrieval_session_id, run_id, organization_id, agent_id,
                    grounding_correlation_id, query, included_retrieval_hit_ids_json,
                    omitted_candidates_json, source_snapshots_json, token_budget_json,
                    prompt_sections_json, evidence_text_sha256, metadata_json, created_at
                )
                VALUES (
                    'manifest-migration', 'retrieval-migration', 'task-migration',
                    'dev-org', 'default', 'correlation-migration',
                    'migration anchor', '["hit-migration"]', '[]', :snapshots,
                    '{}', '[]', :evidence_hash, '{}', :now
                )
                """
            ),
            {
                "snapshots": json.dumps(
                    [
                        {
                            "source_id": "source-migration",
                            "document_id": "document-migration",
                            "chunk_id": "chunk-migration",
                            "text": "migration anchor text",
                        }
                    ]
                ),
                "evidence_hash": hashlib.sha256(b"migration anchor text").hexdigest(),
                "now": now,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO admin_audit_events (
                    id, organization_id, actor_id, event_type, resource_type,
                    resource_id, action, payload_json, created_at
                )
                VALUES (
                    'audit-migration', 'dev-org', 'dev-engineer',
                    'knowledge_source.created', 'knowledge_source',
                    'source-migration', 'created', '{}', :now
                )
                """
            ),
            {"now": now},
        )

    engine.dispose()
    _run_alembic_upgrade(database_url, "head", monkeypatch)
    upgraded_engine = create_engine(database_url)
    with upgraded_engine.connect() as connection:
        source_row = connection.execute(
            text(
                """
                SELECT status, health_status, expires_at, disabled_at, archived_at
                FROM knowledge_sources
                WHERE id = 'source-migration'
                """
            )
        ).one()
        document_row = connection.execute(
            text(
                """
                SELECT status, version, logical_document_id, superseded_at
                FROM knowledge_documents
                WHERE id = 'document-migration'
                """
            )
        ).one()
        chunk_row = connection.execute(
            text(
                """
                SELECT status, document_version
                FROM knowledge_chunks
                WHERE id = 'chunk-migration'
                """
            )
        ).one()
        evidence_counts = connection.execute(
            text(
                """
                SELECT
                    (
                        SELECT COUNT(*)
                        FROM retrieval_hits
                        WHERE id = 'hit-migration'
                    ) AS hits,
                    (
                        SELECT COUNT(*)
                        FROM citation_records
                        WHERE id = 'citation-migration'
                    ) AS citations,
                    (
                        SELECT COUNT(*)
                        FROM prompt_assembly_manifests
                        WHERE id = 'manifest-migration'
                    ) AS manifests,
                    (
                        SELECT COUNT(*)
                        FROM admin_audit_events
                        WHERE id = 'audit-migration'
                    ) AS audits
                """
            )
        ).one()
        manifest_snapshot = connection.execute(
            text(
                """
                SELECT source_snapshots_json
                FROM prompt_assembly_manifests
                WHERE id = 'manifest-migration'
                """
            )
        ).scalar_one()

    upgraded_engine.dispose()
    assert source_row == ("ACTIVE", "HEALTHY", None, None, None)
    assert document_row == ("INDEXED", 1, "document-migration", None)
    assert chunk_row == ("ACTIVE", 1)
    assert evidence_counts == (1, 1, 1, 1)
    assert "migration anchor text" in manifest_snapshot


def test_reingest_changed_content_versions_document_and_marks_old_chunks_stale(
    db_session: Session,
) -> None:
    _ensure_agent(db_session)

    _source, first_document, first_chunks, _embeddings = ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Runbook",
        description="Operational knowledge",
        source_type="text",
        title="Runbook v1",
        content="orion anchor first fact",
        uri="memory://runbook",
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="runbook",
    )
    source, second_document, second_chunks, _second_embeddings = ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Runbook",
        description="Operational knowledge",
        source_type="text",
        title="Runbook v2",
        content="orion anchor changed fact",
        uri="memory://runbook",
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="runbook",
    )
    db_session.flush()

    assert second_document.source_id == source.id
    assert second_document.version == first_document.version + 1
    assert second_document.logical_document_id == first_document.logical_document_id
    assert second_document.supersedes_document_id == first_document.id
    assert first_document.status == "SUPERSEDED"
    assert first_document.superseded_at is not None
    assert {chunk.status for chunk in first_chunks} == {"STALE"}
    assert {chunk.status for chunk in second_chunks} == {"ACTIVE"}

    result = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=None,
        query="changed fact",
    )
    stale_hit_ids = {chunk.id for chunk in first_chunks}
    assert all(hit.chunk_id not in stale_hit_ids for hit in result.retrieval_hits)


def test_document_level_versioning_does_not_supersede_sibling_documents(
    db_session: Session,
) -> None:
    _ensure_agent(db_session)

    source, first_document, first_chunks, _embeddings = ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Multi Doc Source",
        description="Multiple documents",
        source_type="text",
        title="Alpha v1",
        content="alpha beacon first fact",
        uri=None,
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="multi-doc-alpha",
    )
    _source, sibling_document, sibling_chunks, _sibling_embeddings = ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        source_id=source.id,
        name=source.name,
        description=source.description,
        source_type=source.source_type,
        title="Beta v1",
        content="beta beacon sibling fact",
        uri=None,
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="multi-doc-beta",
        create_new_logical_document=True,
    )
    _source, first_v2, first_v2_chunks, _first_v2_embeddings = ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        source_id=source.id,
        name=source.name,
        description=source.description,
        source_type=source.source_type,
        title="Alpha v2",
        content="alpha beacon changed fact",
        uri=None,
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="multi-doc-alpha-v2",
        reingest_document_id=first_document.id,
    )
    db_session.flush()

    assert first_document.status == "SUPERSEDED"
    assert {chunk.status for chunk in first_chunks} == {"STALE"}
    assert first_v2.version == 2
    assert first_v2.logical_document_id == first_document.logical_document_id
    assert {chunk.status for chunk in first_v2_chunks} == {"ACTIVE"}
    assert sibling_document.status == "INDEXED"
    assert sibling_document.logical_document_id != first_document.logical_document_id
    assert {chunk.status for chunk in sibling_chunks} == {"ACTIVE"}


def test_source_lifecycle_status_and_expiry_exclude_retrieval(
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    client = TestClient(app)

    response = client.post(
        "/api/agents/default/knowledge/sources",
        headers=AUTH_HEADERS,
        json={
            "name": "Lifecycle Runbook",
            "description": "Lifecycle source",
            "source_type": "text",
            "title": "Runbook",
            "content": _two_chunk_content("lifecycle beacon"),
            "mime_type": "text/markdown",
            "idempotency_key": "lifecycle-runbook",
        },
    )
    assert response.status_code == 201
    source_id = response.json()["id"]

    grounded = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=None,
        query="lifecycle beacon",
    )
    assert grounded.local_status == "sufficient"

    disabled = client.post(
        f"/api/agents/default/knowledge/sources/{source_id}/disable",
        headers=AUTH_HEADERS,
        json={"reason": "maintenance"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "DISABLED"
    assert disabled.json()["disabled_at"] is not None
    blocked = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=None,
        query="lifecycle beacon",
    )
    assert blocked.local_status == "insufficient"
    assert blocked.retrieval_hits == []

    enabled = client.post(
        f"/api/agents/default/knowledge/sources/{source_id}/enable",
        headers=AUTH_HEADERS,
        json={"reason": "ready"},
    )
    assert enabled.status_code == 200
    expired_at = utc_now() - timedelta(minutes=1)
    source = db_session.get(KnowledgeSource, source_id)
    assert source is not None
    source.expires_at = expired_at
    db_session.flush()

    expired = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=None,
        query="lifecycle beacon",
    )
    assert expired.local_status == "insufficient"
    assert expired.retrieval_hits == []

    source.expires_at = None
    db_session.flush()
    archived = client.post(
        f"/api/agents/default/knowledge/sources/{source_id}/archive",
        headers=AUTH_HEADERS,
        json={"reason": "retired"},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "ARCHIVED"
    assert archived.json()["archived_at"] is not None
    archived_blocked = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=None,
        query="lifecycle beacon",
    )
    assert archived_blocked.local_status == "insufficient"
    assert archived_blocked.retrieval_hits == []

    audit_actions = [
        event.action
        for event in db_session.execute(select(AdminAuditEvent)).scalars()
        if event.resource_id == source_id
    ]
    assert {"created", "disabled", "enabled", "archived"}.issubset(set(audit_actions))


def test_org_scoped_sources_require_admin_and_stay_tenant_isolated(
    db_session: Session,
) -> None:
    _ensure_agent(db_session, "default")
    _ensure_agent(db_session, "researcher")
    client = TestClient(app)

    forbidden = client.post(
        "/api/agents/default/knowledge/sources",
        headers=AUTH_HEADERS,
        json={
            "name": "Org Handbook",
            "scope": "org",
            "description": "Shared source",
            "source_type": "markdown",
            "title": "Org Handbook",
            "content": "shared beacon fact",
            "mime_type": "text/markdown",
        },
    )
    assert forbidden.status_code == 403

    created = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "Org Handbook",
            "scope": "org",
            "description": "Shared source",
            "source_type": "markdown",
            "title": "Org Handbook",
            "content": _two_chunk_content("shared beacon"),
            "mime_type": "text/markdown",
            "idempotency_key": "org-handbook",
        },
    )
    assert created.status_code == 201
    assert created.json()["scope"] == "org"
    assert created.json()["agent_id"] is None
    source_id = created.json()["id"]

    default_list = client.get(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
    )
    researcher_list = client.get(
        "/api/agents/researcher/knowledge/sources",
        headers=ADMIN_HEADERS,
    )
    foreign_list = client.get(
        "/api/agents/default/knowledge/sources",
        headers=OTHER_ORG_HEADERS,
    )
    assert source_id in {item["id"] for item in default_list.json()["items"]}
    assert source_id in {item["id"] for item in researcher_list.json()["items"]}
    assert source_id not in {item["id"] for item in foreign_list.json()["items"]}

    engineer_update = client.patch(
        f"/api/agents/default/knowledge/sources/{source_id}",
        headers=AUTH_HEADERS,
        json={"name": "Engineer rename should fail"},
    )
    engineer_disable = client.post(
        f"/api/agents/default/knowledge/sources/{source_id}/disable",
        headers=AUTH_HEADERS,
        json={"reason": "engineer should not affect org source"},
    )
    engineer_document = client.post(
        f"/api/agents/default/knowledge/sources/{source_id}/documents",
        headers=AUTH_HEADERS,
        json={
            "title": "Engineer doc should fail",
            "content": "unauthorized shared mutation",
        },
    )
    assert engineer_update.status_code == 403
    assert engineer_disable.status_code == 403
    assert engineer_document.status_code == 403

    default_grounded = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=None,
        query="shared beacon",
    )
    researcher_grounded = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="researcher",
        run_id=None,
        query="shared beacon",
    )
    foreign_grounded = ground_query(
        db_session,
        organization_id="other-org",
        agent_id="default",
        run_id=None,
        query="shared beacon",
    )
    assert default_grounded.local_status == "sufficient"
    assert researcher_grounded.local_status == "sufficient"
    assert foreign_grounded.retrieval_hits == []


def test_scope_change_updates_source_document_chunk_and_embedding_scope(
    db_session: Session,
) -> None:
    _ensure_agent(db_session, "default")
    _ensure_agent(db_session, "researcher")
    client = TestClient(app)

    created = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "Scoped Handbook",
            "description": "Scope consistency",
            "source_type": "markdown",
            "title": "Scoped Handbook",
            "content": _two_chunk_content("scope consistency beacon"),
            "mime_type": "text/markdown",
            "idempotency_key": "scope-consistency",
        },
    )
    assert created.status_code == 201
    source_id = created.json()["id"]

    changed = client.post(
        f"/api/agents/default/knowledge/sources/{source_id}/scope",
        headers=ADMIN_HEADERS,
        json={"scope": "org", "reason": "share"},
    )
    assert changed.status_code == 200
    assert changed.json()["scope"] == "org"

    source = db_session.get(KnowledgeSource, source_id)
    documents = list(
        db_session.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.source_id == source_id)
        ).scalars()
    )
    chunks = list(
        db_session.execute(
            select(KnowledgeChunk).where(KnowledgeChunk.source_id == source_id)
        ).scalars()
    )
    embeddings = list(
        db_session.execute(
            select(KnowledgeEmbedding)
            .join(KnowledgeChunk, KnowledgeEmbedding.chunk_id == KnowledgeChunk.id)
            .where(KnowledgeChunk.source_id == source_id)
        ).scalars()
    )
    assert source is not None
    assert source.agent_id is None
    assert {document.agent_id for document in documents} == {None}
    assert {chunk.agent_id for chunk in chunks} == {None}
    assert {embedding.agent_id for embedding in embeddings} == {None}
    researcher_sources = client.get(
        "/api/agents/researcher/knowledge/sources",
        headers=ADMIN_HEADERS,
    )
    assert source_id in {item["id"] for item in researcher_sources.json()["items"]}


def test_multipart_text_file_import_creates_source_and_document(
    db_session: Session,
) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)

    created = client.post(
        "/api/agents/default/knowledge/sources/import",
        headers=ADMIN_HEADERS,
        data={"name": "Uploaded Runbook", "title": "Uploaded Runbook", "scope": "agent"},
        files={"file": ("uploaded-runbook.md", b"uploaded markdown beacon", "text/markdown")},
    )

    assert created.status_code == 201
    payload = created.json()
    assert payload["name"] == "Uploaded Runbook"
    assert payload["latest_documents"][0]["title"] == "Uploaded Runbook"
    assert payload["latest_documents"][0]["mime_type"] == "text/markdown"
    assert payload["latest_documents"][0]["uri"] == "uploaded-runbook.md"


def test_multipart_import_rejects_unauthorized_actor_before_parsing(
    db_session: Session,
) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)

    response = client.post(
        "/api/agents/default/knowledge/sources/import",
        headers={
            **OPERATOR_HEADERS,
            "Content-Type": "application/octet-stream",
        },
        content=b"not multipart",
    )

    assert response.status_code == 403


def test_multipart_import_rejects_oversized_body_before_buffering(
    db_session: Session,
) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)
    boundary = "knowledge-boundary"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="too-large.md"\r\n'
        "Content-Type: text/markdown\r\n\r\n"
    ).encode() + (b"x" * 140_001) + f"\r\n--{boundary}--\r\n".encode()

    response = client.post(
        "/api/agents/default/knowledge/sources/import",
        headers={
            **ADMIN_HEADERS,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        content=body,
    )

    assert response.status_code == 413


def test_multipart_markdown_import_accepts_unstable_browser_mime(
    db_session: Session,
) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)

    created = client.post(
        "/api/agents/default/knowledge/sources/import",
        headers=ADMIN_HEADERS,
        data={"name": "Browser Markdown", "title": "Browser Markdown", "scope": "agent"},
        files={
            "file": (
                "browser-runbook.md",
                b"browser markdown mime fallback beacon",
                "application/octet-stream",
            )
        },
    )

    assert created.status_code == 201
    assert created.json()["latest_documents"][0]["mime_type"] == "text/markdown"


def test_failed_reingest_records_failed_document_and_lifecycle_event(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "Failure Contract",
            "description": "Failure visibility",
            "source_type": "markdown",
            "title": "Failure v1",
            "content": "stable failure contract beacon",
            "mime_type": "text/markdown",
        },
    )
    assert created.status_code == 201
    source_id = created.json()["id"]
    document_id = created.json()["latest_documents"][0]["id"]
    monkeypatch.setattr("app.knowledge.MAX_INGESTION_CHUNKS", 1)

    failed = client.post(
        f"/api/agents/default/knowledge/sources/{source_id}/documents/{document_id}/versions",
        headers=ADMIN_HEADERS,
        json={
            "title": "Failure v2",
            "content": "first chunk marker\n" + ("x" * 1200) + "\nsecond chunk marker",
            "mime_type": "text/markdown",
        },
    )

    assert failed.status_code == 400
    source = db_session.get(KnowledgeSource, source_id)
    documents = list(
        db_session.execute(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.source_id == source_id)
            .order_by(KnowledgeDocument.version.asc())
        ).scalars()
    )
    assert source is not None
    assert source.health_status == "ERROR"
    assert source.last_ingestion_error is not None
    assert [document.status for document in documents] == ["INDEXED", "FAILED"]
    assert documents[1].ingestion_error == source.last_ingestion_error
    assert documents[0].superseded_at is None
    audit = db_session.execute(
        select(AdminAuditEvent).where(
            AdminAuditEvent.resource_id == source_id,
            AdminAuditEvent.action == "document_reingest_failed",
        )
    ).scalar_one()
    assert audit.payload_json["after"]["error"] == source.last_ingestion_error
    assert audit.payload_json["document_id"] == documents[1].id


def test_failed_reingest_idempotency_retry_remains_failed(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ensure_agent(db_session, "default")
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/knowledge/sources",
        headers=ADMIN_HEADERS,
        json={
            "name": "Failure Retry Contract",
            "description": "Failure retry visibility",
            "source_type": "markdown",
            "title": "Failure retry v1",
            "content": "stable failure retry contract beacon",
            "mime_type": "text/markdown",
        },
    )
    assert created.status_code == 201
    source_id = created.json()["id"]
    document_id = created.json()["latest_documents"][0]["id"]
    oversized_payload = {
        "title": "Failure retry v2",
        "content": "first chunk marker\n" + ("x" * 1200) + "\nsecond chunk marker",
        "mime_type": "text/markdown",
        "idempotency_key": "failed-retry-key",
    }
    monkeypatch.setattr("app.knowledge.MAX_INGESTION_CHUNKS", 1)

    first = client.post(
        f"/api/agents/default/knowledge/sources/{source_id}/documents/{document_id}/versions",
        headers=ADMIN_HEADERS,
        json=oversized_payload,
    )
    second = client.post(
        f"/api/agents/default/knowledge/sources/{source_id}/documents/{document_id}/versions",
        headers=ADMIN_HEADERS,
        json=oversized_payload,
    )

    assert first.status_code == 400
    assert second.status_code == 400
    documents = list(
        db_session.execute(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.source_id == source_id)
            .order_by(KnowledgeDocument.version.asc())
        ).scalars()
    )
    assert [document.status for document in documents] == ["INDEXED", "FAILED", "FAILED"]
    assert all(document.indexed_at is None for document in documents[1:])
    versioned_audits = list(
        db_session.execute(
            select(AdminAuditEvent).where(
                AdminAuditEvent.resource_id == source_id,
                AdminAuditEvent.action == "document_versioned",
            )
        ).scalars()
    )
    assert versioned_audits == []


def test_knowledge_restore_smoke_preserves_current_and_historical_contracts(
    tmp_path,
) -> None:
    source_db = tmp_path / "knowledge-source.db"
    restored_db = tmp_path / "knowledge-restored.db"
    source_engine = create_engine(f"sqlite+pysqlite:///{source_db}")
    Base.metadata.create_all(bind=source_engine)
    FileSession = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=source_engine,
        expire_on_commit=False,
    )

    seed_session = FileSession()
    try:
        _ensure_agent(seed_session, "default")
        _ensure_agent(seed_session, "researcher")
        task = _task(seed_session)

        source, first_document, first_chunks, _embeddings = ingest_knowledge_source(
            seed_session,
            organization_id="dev-org",
            agent_id="default",
            name="Restore Historical",
            description="Historical restore source",
            source_type="text",
            title="Facts v1",
            content=_two_chunk_content("amber restoration point"),
            uri=None,
            mime_type="text/markdown",
            created_by="dev-engineer",
            idempotency_key="restore-historical-v1",
        )
        historical = ground_query(
            seed_session,
            organization_id="dev-org",
            agent_id="default",
            run_id=task.id,
            query="amber restoration point",
        )
        assert historical.retrieval_session is not None
        assert historical.prompt_manifest is not None
        manifest_id = historical.prompt_manifest.id
        retrieval_session_id = historical.retrieval_session.id
        historical_hit_ids = {hit.id for hit in historical.retrieval_hits}
        historical_citation_ids = {citation.id for citation in historical.citations}

        ingest_knowledge_source(
            seed_session,
            organization_id="dev-org",
            agent_id="default",
            source_id=source.id,
            name="Restore Historical",
            description="Historical restore source changed",
            source_type="text",
            title="Facts v2",
            content=_two_chunk_content("cobalt restoration point"),
            uri=None,
            mime_type="text/markdown",
            created_by="dev-engineer",
            idempotency_key="restore-historical-v2",
        )

        disabled_source, _document, _chunks, _disabled_embeddings = ingest_knowledge_source(
            seed_session,
            organization_id="dev-org",
            agent_id="default",
            name="Restore Disabled",
            description="Disabled restore source",
            source_type="text",
            title="Disabled Facts",
            content=_two_chunk_content("quartz disabled phrase"),
            uri=None,
            mime_type="text/markdown",
            created_by="dev-engineer",
            idempotency_key="restore-disabled",
        )
        before = knowledge_source_lifecycle_snapshot(disabled_source)
        disabled_source.status = "DISABLED"
        disabled_source.disabled_at = utc_now()
        disabled_source.updated_at = utc_now()
        after = knowledge_source_lifecycle_snapshot(disabled_source)
        lifecycle_event = create_knowledge_lifecycle_audit(
            seed_session,
            organization_id="dev-org",
            actor_id="dev-engineer",
            action="disabled",
            source=disabled_source,
            before=before,
            after=after,
            request_id="restore-smoke",
        )

        org_source, _org_doc, _org_chunks, _org_embeddings = ingest_knowledge_source(
            seed_session,
            organization_id="dev-org",
            agent_id=None,
            name="Restore Org Shared",
            description="Org-scoped restore source",
            source_type="text",
            title="Org Shared Facts",
            content=_two_chunk_content("shared org phrase"),
            uri=None,
            mime_type="text/markdown",
            created_by="dev-admin",
            idempotency_key="restore-org-shared",
        )
        foreign_source, _foreign_doc, _foreign_chunks, _foreign_embeddings = (
            ingest_knowledge_source(
                seed_session,
                organization_id="other-org",
                agent_id="default",
                name="Restore Foreign",
                description="Foreign restore source",
                source_type="text",
                title="Foreign Facts",
                content=_two_chunk_content("foreign tenant phrase"),
                uri=None,
                mime_type="text/markdown",
                created_by="dev-other-engineer",
                idempotency_key="restore-foreign",
            )
        )

        source_id = source.id
        first_document_id = first_document.id
        first_chunk_ids = {chunk.id for chunk in first_chunks}
        disabled_source_id = disabled_source.id
        lifecycle_event_id = lifecycle_event.id
        org_source_id = org_source.id
        foreign_source_id = foreign_source.id
        seed_session.commit()
    finally:
        seed_session.close()
        source_engine.dispose()

    shutil.copyfile(source_db, restored_db)
    restored_engine = create_engine(f"sqlite+pysqlite:///{restored_db}")
    RestoredSession = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=restored_engine,
    )
    restored_session = RestoredSession()
    try:
        current = ground_query(
            restored_session,
            organization_id="dev-org",
            agent_id="default",
            run_id=None,
            query="cobalt restoration point",
        )
        disabled = ground_query(
            restored_session,
            organization_id="dev-org",
            agent_id="default",
            run_id=None,
            query="quartz disabled phrase",
        )
        foreign = ground_query(
            restored_session,
            organization_id="dev-org",
            agent_id="default",
            run_id=None,
            query="foreign tenant phrase",
        )
        researcher_sources = list_knowledge_sources(
            restored_session,
            organization_id="dev-org",
            agent_id="researcher",
        )
        other_org_sources = list_knowledge_sources(
            restored_session,
            organization_id="other-org",
            agent_id="default",
        )
        manifest = restored_session.get(PromptAssemblyManifest, manifest_id)
        restored_hits = list(
            restored_session.execute(
                select(RetrievalHit).where(
                    RetrievalHit.retrieval_session_id == retrieval_session_id
                )
            ).scalars()
        )
        restored_citations = list(
            restored_session.execute(
                select(CitationRecord).where(
                    CitationRecord.retrieval_session_id == retrieval_session_id
                )
            ).scalars()
        )
        event = restored_session.get(AdminAuditEvent, lifecycle_event_id)

        assert current.local_status == "sufficient"
        assert {hit.document_id for hit in current.retrieval_hits} != {first_document_id}
        assert current.prompt_manifest is not None
        assert "cobalt restoration point" in str(current.prompt_manifest.source_snapshots_json)
        assert disabled.local_status == "insufficient"
        assert all(
            hit.metadata_json.get("source_snapshot", {}).get("source_id") != disabled_source_id
            for hit in disabled.retrieval_hits
        )
        assert foreign.local_status == "insufficient"
        assert foreign_source_id not in str(
            [hit.metadata_json for hit in foreign.retrieval_hits]
        )
        assert org_source_id in {item.id for item in researcher_sources}
        assert org_source_id not in {item.id for item in other_org_sources}

        assert manifest is not None
        assert manifest.retrieval_session_id == retrieval_session_id
        assert set(manifest.included_retrieval_hit_ids_json) == historical_hit_ids
        assert "amber restoration point" in str(manifest.source_snapshots_json)
        assert "cobalt restoration point" not in str(manifest.source_snapshots_json)
        assert {hit.id for hit in restored_hits} == historical_hit_ids
        assert {hit.chunk_id for hit in restored_hits}.issubset(first_chunk_ids)
        assert {citation.id for citation in restored_citations} == historical_citation_ids
        assert all(
            "amber restoration point" in (citation.quoted_text or "")
            for citation in restored_citations
        )
        assert event is not None
        assert event.action == "disabled"
        assert event.resource_id == disabled_source_id
        assert event.payload_json["schema_version"] == "knowledge-lifecycle-v1"
        assert event.payload_json["before"]["status"] == "ACTIVE"
        assert event.payload_json["after"]["status"] == "DISABLED"
        assert source_id in {item.id for item in list_knowledge_sources(
            restored_session,
            organization_id="dev-org",
            agent_id="default",
        )}
    finally:
        restored_session.close()
        restored_engine.dispose()


def test_lexical_fallback_creates_retrieval_hits_and_bound_citations(
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    task = _task(db_session)
    ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Local Facts",
        description="Local facts",
        source_type="text",
        title="Facts",
        content=_two_chunk_content(),
        uri=None,
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="facts",
    )

    result = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="orion anchor",
    )
    db_session.flush()

    assert result.retrieval_session is not None
    assert result.retrieval_session.strategy == "lexical"
    assert result.local_status == "sufficient"
    assert len([hit for hit in result.retrieval_hits if hit.source_kind == "knowledge_chunk"]) >= 2
    assert not result.web_sources
    hit_ids = {hit.id for hit in result.retrieval_hits}
    assert all(citation.chunk_id for citation in result.citations)
    assert all(citation.retrieval_hit_id in hit_ids for citation in result.citations)
    assert all(citation.metadata_json.get("source_snapshot") for citation in result.citations)
    assert db_session.scalar(select(func.count()).select_from(RetrievalHit)) >= 2
    assert db_session.scalar(select(func.count()).select_from(CitationRecord)) >= 2


def test_cjk_single_chunk_strong_match_can_ground_small_handbook(
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    task = _task(db_session)
    ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Team Handbook",
        description="Chinese handbook",
        source_type="markdown",
        title="团队手册",
        content="# 团队手册\n\n使用简洁、带引用的回答。",
        uri=None,
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="team-handbook-cjk",
    )

    result = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="看一下团队手册里写了什么",
    )
    db_session.flush()

    assert result.local_status == "sufficient"
    assert result.grounded is True
    assert len(result.retrieval_hits) == 1
    assert len(result.citations) == 1
    assert result.retrieval_session is not None
    assert result.retrieval_session.metadata_json["sufficiency_reason"] == (
        "single_cjk_strong_match"
    )
    assert result.prompt_manifest is not None
    assert result.prompt_manifest.included_retrieval_hit_ids_json == [
        result.retrieval_hits[0].id
    ]
    assert {audit.decision for audit in result.policy_audits} >= {"allowed"}


def test_single_non_cjk_hit_below_min_hits_is_not_cited(
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    task = _task(db_session)
    ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Short English Runbook",
        description="Single chunk runbook",
        source_type="text",
        title="Short English Runbook",
        content="orion anchor local fact",
        uri=None,
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="short-english-runbook",
    )

    result = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="orion anchor",
    )
    db_session.flush()

    assert result.local_status == "insufficient"
    assert result.grounded is False
    assert result.retrieval_hits == []
    assert result.citations == []
    assert result.prompt_manifest is not None
    assert result.prompt_manifest.included_retrieval_hit_ids_json == []
    assert result.prompt_manifest.omitted_candidates_json[0]["reason"] == (
        "insufficient_min_hits"
    )
    assert {audit.decision for audit in result.policy_audits} >= {"omitted"}


def test_grounding_persists_prompt_manifest_and_policy_audit(
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    task = _task(db_session)
    ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Relevant Facts",
        description="Relevant facts",
        source_type="text",
        title="Facts",
        content=_two_chunk_content(),
        uri=None,
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="relevant-facts",
    )
    ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Omitted Facts",
        description="Low-score facts",
        source_type="text",
        title="Low Score Facts",
        content="unrelated low score material " * 20,
        uri=None,
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="omitted-facts",
    )

    result = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="orion anchor",
    )
    db_session.flush()

    assert result.prompt_manifest is not None
    assert result.prompt_manifest.evidence_text_sha256
    assert result.prompt_manifest.included_retrieval_hit_ids_json == [
        hit.id for hit in result.retrieval_hits
    ]
    assert result.prompt_manifest.source_snapshots_json
    assert result.prompt_manifest.prompt_sections_json[0]["section"] == "knowledge_evidence"
    assert result.prompt_manifest.omitted_candidates_json
    assert result.grounding_provider == "local_knowledge"
    assert result.fixture_grounded is False
    assert result.verified_grounded is True
    assert result.prompt_manifest.metadata_json["verified_grounded"] is True
    assert {
        audit.decision for audit in result.policy_audits
    } >= {"allowed", "omitted"}
    assert db_session.scalar(select(func.count()).select_from(PromptAssemblyManifest)) == 1
    assert db_session.scalar(select(func.count()).select_from(KnowledgePolicyAudit)) >= 2

    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == task.id)
        ).scalars()
    ]
    assert EventType.RAG_PROMPT_ASSEMBLED in event_types
    assert EventType.RAG_POLICY_AUDITED in event_types


def test_omitted_candidates_do_not_leak_raw_text_to_manifest_or_run_detail(
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    task = _task(db_session)
    ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Selected Facts",
        description="Selected facts",
        source_type="text",
        title="Selected Facts",
        content=_two_chunk_content("visible beacon"),
        uri=None,
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="selected-facts",
    )
    forbidden_text = "forbidden omitted raw text"
    ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Forbidden Omitted Facts",
        description="Forbidden omitted facts",
        source_type="text",
        title="Forbidden Facts",
        content=(forbidden_text + " ") * 30,
        uri=None,
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="forbidden-omitted-facts",
    )

    result = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="visible beacon",
    )
    db_session.commit()
    assert result.prompt_manifest is not None
    manifest_payload = (
        str(result.prompt_manifest.omitted_candidates_json)
        + str(result.prompt_manifest.source_snapshots_json)
        + str([audit.safe_metadata_json for audit in result.policy_audits])
    )
    assert forbidden_text not in manifest_payload
    assert result.prompt_manifest.omitted_candidates_json
    assert all(
        "snapshot" not in candidate
        for candidate in result.prompt_manifest.omitted_candidates_json
    )

    response = TestClient(app).get(
        f"/api/agents/runs/{task.id}/workspace",
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert forbidden_text not in response.text


def test_denied_policy_candidates_do_not_reach_prompt_or_run_detail(
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    task = _task(db_session)
    ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Allowed Deny Control",
        description="Allowed facts",
        source_type="text",
        title="Allowed Facts",
        content=_two_chunk_content("allowed beacon"),
        uri=None,
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="allowed-deny-control",
    )
    forbidden_text = "forbidden denied raw text"
    ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Denied Facts",
        description="Denied facts",
        source_type="text",
        title="Denied Facts",
        content=(f"allowed beacon DENY: {forbidden_text}. " + ("alpha " * 80) + "\n") * 2,
        uri=None,
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="denied-facts",
    )

    result = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="allowed beacon",
    )
    db_session.commit()

    assert {audit.decision for audit in result.policy_audits} >= {"allowed", "denied"}
    payload = (
        str(result.prompt_manifest.__dict__ if result.prompt_manifest else {})
        + str([hit.snippet for hit in result.retrieval_hits])
        + str([citation.quoted_text for citation in result.citations])
        + str([audit.safe_metadata_json for audit in result.policy_audits])
    )
    assert forbidden_text not in payload

    response = TestClient(app).get(
        f"/api/agents/runs/{task.id}/workspace",
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert forbidden_text not in response.text


def test_redacted_policy_candidates_use_marker_without_raw_secret(
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    task = _task(db_session)
    secret_text = "classified.launch/api:key@example.com"
    ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Redacted Facts",
        description="Redacted facts",
        source_type="text",
        title="Redacted Facts",
        content=(f"redaction beacon REDACT: {secret_text}. " + ("alpha " * 120) + "\n") * 2,
        uri=None,
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="redacted-facts",
    )

    result = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="redaction beacon",
    )

    assert result.local_status == "sufficient"
    assert {audit.decision for audit in result.policy_audits} >= {"allowed", "redacted"}
    payload = (
        str(result.prompt_manifest.__dict__ if result.prompt_manifest else {})
        + str([hit.snippet for hit in result.retrieval_hits])
        + str([citation.quoted_text for citation in result.citations])
        + str([audit.safe_metadata_json for audit in result.policy_audits])
    )
    assert "[REDACTED:policy_marker]" in payload
    assert secret_text not in payload


def test_vector_capability_available_uses_vector_strategy(db_session: Session) -> None:
    _ensure_agent(db_session)
    set_vector_capability(
        db_session,
        organization_id="dev-org",
        status=VECTOR_CAPABILITY_AVAILABLE,
        reason="test",
    )
    ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Vector Facts",
        description="Vector facts",
        source_type="text",
        title="Facts",
        content=_two_chunk_content("vector beacon"),
        uri=None,
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="vector-facts",
    )

    result = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=None,
        query="vector beacon",
    )

    assert result.vector_capability == VECTOR_CAPABILITY_AVAILABLE
    assert result.retrieval_session is not None
    assert result.retrieval_session.strategy == "vector"


def test_insufficient_local_evidence_uses_fake_web_fallback_audit_path(
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    task = _task(db_session)
    _enable_web_research_policy(db_session)
    set_web_research_provider(
        db_session,
        organization_id="dev-org",
        provider="fake",
        updated_by="dev-engineer",
    )

    result = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="uncovered claim",
    )
    db_session.flush()

    assert result.local_status == "insufficient"
    assert result.retrieval_session is not None
    assert result.retrieval_session.mode == "web_fallback"
    assert result.retrieval_session.max_web_results == 2
    assert result.prompt_manifest is not None
    assert result.prompt_manifest.included_retrieval_hit_ids_json == [
        hit.id for hit in result.retrieval_hits
    ]
    assert result.grounding_provider == "fake_web_fixture"
    assert result.fixture_grounded is True
    assert result.verified_grounded is False
    assert result.grounding_verification_reason == "fixture_web_not_verified"
    assert result.retrieval_session.metadata_json["grounding_provider"] == (
        "fake_web_fixture"
    )
    assert result.prompt_manifest.metadata_json["fixture_grounded"] is True
    assert result.prompt_manifest.omitted_candidates_json == []
    assert result.web_sources
    assert result.citations
    assert all(citation.web_source_id for citation in result.citations)
    assert db_session.scalar(select(func.count()).select_from(WebResearchSource)) == 2
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == task.id)
        ).scalars()
    ]
    assert EventType.RAG_RETRIEVAL_STARTED in event_types
    assert EventType.WEB_RESEARCH_STARTED in event_types
    assert EventType.WEB_RESEARCH_COMPLETED in event_types
    assert EventType.RAG_CITATION_RECORDED in event_types


def test_real_web_research_success_is_source_bound_with_mock_adapter(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    task = _task(db_session)
    _enable_web_research_policy(db_session, allow_domains=["docs.example.com"])
    set_web_research_provider(
        db_session,
        organization_id="dev-org",
        provider="tavily",
        updated_by="dev-engineer",
    )
    monkeypatch.setattr("app.knowledge.resolve_web_research_api_key", lambda provider: "key")
    monkeypatch.setattr(
        "app.sandbox.policies.socket.getaddrinfo",
        lambda host, *_args, **_kwargs: [
            (None, None, None, None, ("93.184.216.34", 443))
        ],
    )

    class Adapter:
        provider = "tavily"

        def __init__(self) -> None:
            self.calls = 0

        def search(self, **kwargs):
            self.calls += 1
            assert kwargs["query"] == "uncovered real claim"
            assert kwargs["include_domains"] == ["docs.example.com"]
            return [
                WebResearchResult(
                    title="Real source",
                    url="https://docs.example.com:443/research#fragment",
                    snippet="Real provider snippet for uncovered real claim.",
                    rank=1,
                    score=0.87,
                    provider_request_id="req-123",
                    usage_credits=1.0,
                )
            ]

    adapter = Adapter()
    monkeypatch.setattr("app.knowledge.get_web_research_adapter", lambda provider: adapter)

    result = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="uncovered real claim",
    )
    db_session.flush()

    assert adapter.calls == 1
    assert result.local_status == "insufficient"
    assert result.grounding_provider == "tavily_search"
    assert result.fixture_grounded is False
    assert result.verified_grounded is True
    assert result.grounding_verification_reason == "real_source_bound"
    assert result.retrieval_session is not None
    assert result.retrieval_session.mode == "web_fallback"
    assert result.retrieval_session.metadata_json["verified_grounded_semantics"] == (
        "real_source_bound_not_factual_verification"
    )
    assert len(result.web_sources) == 1
    source = result.web_sources[0]
    assert source.url == "https://docs.example.com/research"
    assert source.metadata_json["provider"] == "tavily"
    assert source.metadata_json["request_id"] == "req-123"
    assert result.citations[0].web_source_id == source.id
    web_audits = [
        audit
        for audit in result.policy_audits
        if audit.source_kind == "web_research"
    ]
    assert web_audits[0].safe_metadata_json["web_pre_call_policy_snapshot"][
        "provider_domain_filters_advisory_only"
    ] is True
    assert any(
        audit.safe_metadata_json.get("policy_snapshot", {}).get(
            "authoritative_enforcement"
        )
        == "post_result_policy_before_persistence"
        for audit in web_audits
    )
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == task.id)
        ).scalars()
    ]
    assert EventType.WEB_RESEARCH_STARTED in event_types
    assert EventType.WEB_RESEARCH_COMPLETED in event_types
    assert EventType.WEB_RESEARCH_FAILED not in event_types


def test_missing_tavily_key_does_not_call_provider(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    task = _task(db_session)
    _enable_web_research_policy(db_session, allow_domains=["docs.example.com"])
    set_web_research_provider(
        db_session,
        organization_id="dev-org",
        provider="tavily",
        updated_by="dev-engineer",
    )
    monkeypatch.setattr("app.knowledge.resolve_web_research_api_key", lambda provider: "")

    def fail_adapter(provider):
        raise AssertionError("provider adapter must not be called")

    monkeypatch.setattr("app.knowledge.get_web_research_adapter", fail_adapter)

    result = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="uncovered key claim",
    )
    db_session.flush()

    assert result.web_sources == []
    assert result.retrieval_session is not None
    assert result.retrieval_session.mode == "local_insufficient"
    assert result.retrieval_session.metadata_json["web_research_failed"] is True
    assert result.retrieval_session.metadata_json["web_research_failure_reason"] == (
        "web research provider api key is missing"
    )
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == task.id)
        ).scalars()
    ]
    assert EventType.WEB_RESEARCH_FAILED in event_types


def test_pre_call_policy_denied_does_not_call_provider(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    task = _task(db_session)
    _enable_web_research_policy(db_session, allow_domains=[])
    set_web_research_provider(
        db_session,
        organization_id="dev-org",
        provider="tavily",
        updated_by="dev-engineer",
    )
    monkeypatch.setattr("app.knowledge.resolve_web_research_api_key", lambda provider: "key")

    def fail_adapter(provider):
        raise AssertionError("provider adapter must not be called")

    monkeypatch.setattr("app.knowledge.get_web_research_adapter", fail_adapter)

    result = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="uncovered policy claim",
    )
    db_session.flush()

    assert result.web_sources == []
    assert result.retrieval_session is not None
    assert result.retrieval_session.metadata_json["web_research_failed"] is True
    assert result.retrieval_session.metadata_json["web_research_failure_reason"] == (
        "web research domain allowlist is required"
    )


def test_denied_web_result_does_not_persist_raw_secret_url(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    task = _task(db_session)
    _enable_web_research_policy(db_session, allow_domains=["safe.example.com"])
    set_web_research_provider(
        db_session,
        organization_id="dev-org",
        provider="tavily",
        updated_by="dev-engineer",
    )
    monkeypatch.setattr("app.knowledge.resolve_web_research_api_key", lambda provider: "key")

    class Adapter:
        provider = "tavily"

        def search(self, **kwargs):
            return [
                WebResearchResult(
                    title="Denied secret URL",
                    url="https://user:pass@evil.example.com/path?token=secret",
                    snippet="Denied result",
                    rank=1,
                    score=0.4,
                )
            ]

    monkeypatch.setattr("app.knowledge.get_web_research_adapter", lambda provider: Adapter())

    result = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="denied secret url claim",
    )

    assert result.web_sources == []
    denied_audits = [
        audit
        for audit in result.policy_audits
        if audit.source_kind == "web_research" and audit.decision == "denied"
    ]
    payload = str([audit.source_ref_id for audit in denied_audits]) + str(
        [audit.safe_metadata_json for audit in denied_audits]
    )
    assert "user:pass" not in payload
    assert "token=secret" not in payload
    assert any((audit.source_ref_id or "").startswith("url_sha256:") for audit in denied_audits)


def test_fake_provider_refused_in_production_even_with_allow_env(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    task = _task(db_session)
    _enable_web_research_policy(db_session)
    set_web_research_provider(
        db_session,
        organization_id="dev-org",
        provider="fake",
        updated_by="dev-engineer",
    )
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        result = ground_query(
            db_session,
            organization_id="dev-org",
            agent_id="default",
            run_id=task.id,
            query="uncovered prod fake claim",
        )
    finally:
        get_settings.cache_clear()

    assert result.web_sources == []
    assert result.retrieval_session is not None
    assert result.retrieval_session.metadata_json["web_research_failed"] is True
    assert result.retrieval_session.metadata_json["web_research_failure_reason"] == (
        "fake provider is not allowed in this environment"
    )


def test_web_research_policy_limits_content_and_calls(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    task = _task(db_session)
    _enable_web_research_policy(
        db_session,
        allow_domains=["docs.example.com"],
        max_content_bytes=24,
        max_calls_per_run=1,
    )
    set_web_research_provider(
        db_session,
        organization_id="dev-org",
        provider="tavily",
        updated_by="dev-engineer",
    )
    monkeypatch.setattr("app.knowledge.resolve_web_research_api_key", lambda provider: "key")
    monkeypatch.setattr(
        "app.sandbox.policies.socket.getaddrinfo",
        lambda host, *_args, **_kwargs: [
            (None, None, None, None, ("93.184.216.34", 443))
        ],
    )
    calls = 0

    class Adapter:
        provider = "tavily"

        def search(self, **kwargs):
            nonlocal calls
            calls += 1
            return [
                WebResearchResult(
                    title="Limited source",
                    url="https://docs.example.com/research",
                    snippet="x" * 200,
                    rank=1,
                    score=0.7,
                )
            ]

    monkeypatch.setattr("app.knowledge.get_web_research_adapter", lambda provider: Adapter())

    first = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="first limited claim",
    )
    second = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="second limited claim",
    )

    assert calls == 1
    assert len(first.web_sources[0].snippet) == 24
    assert second.web_sources == []
    assert second.retrieval_session is not None
    assert second.retrieval_session.metadata_json["web_research_failure_reason"] == (
        "web research call limit is exhausted for this run"
    )


def test_local_sufficient_grounding_does_not_consume_web_call_budget(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    task = _task(db_session)
    _enable_web_research_policy(
        db_session,
        allow_domains=["docs.example.com"],
        max_calls_per_run=1,
    )
    set_web_research_provider(
        db_session,
        organization_id="dev-org",
        provider="tavily",
        updated_by="dev-engineer",
    )
    ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Budget Local Facts",
        description="Budget local facts",
        source_type="text",
        title="Facts",
        content=_two_chunk_content("budget beacon"),
        uri=None,
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="budget-local-facts",
    )
    monkeypatch.setattr("app.knowledge.resolve_web_research_api_key", lambda provider: "key")
    monkeypatch.setattr(
        "app.sandbox.policies.socket.getaddrinfo",
        lambda host, *_args, **_kwargs: [
            (None, None, None, None, ("93.184.216.34", 443))
        ],
    )
    calls = 0

    class Adapter:
        provider = "tavily"

        def search(self, **kwargs):
            nonlocal calls
            calls += 1
            return [
                WebResearchResult(
                    title="Budget source",
                    url="https://docs.example.com/research",
                    snippet="Budget fallback snippet",
                    rank=1,
                    score=0.7,
                )
            ]

    monkeypatch.setattr("app.knowledge.get_web_research_adapter", lambda provider: Adapter())

    local = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="budget beacon",
    )
    fallback = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="uncovered budget claim",
    )

    assert local.local_status == "sufficient"
    assert local.web_sources == []
    assert calls == 1
    assert fallback.web_sources
    assert fallback.retrieval_session is not None
    assert fallback.retrieval_session.metadata_json["web_provider_call_attempted"] is True


class _StaticGateway:
    def complete(self, request_payload: ModelRequest) -> ModelResponse:
        return ModelResponse(
            content="Grounded answer [1]",
            model_provider=request_payload.model_provider,
            model_name=request_payload.model_name,
            usage={"prompt_tokens": 12, "completion_tokens": 4},
            raw_response={},
        )


class _FailOnceGateway:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, request_payload: ModelRequest) -> ModelResponse:
        self.calls += 1
        if self.calls == 1:
            raise ModelGatewayError("rate limited")
        return ModelResponse(
            content="Fallback grounded answer [1]",
            model_provider=request_payload.model_provider,
            model_name=request_payload.model_name,
            usage={"prompt_tokens": 10, "completion_tokens": 5},
            raw_response={},
        )


def test_prompt_manifest_model_call_binding_contract(db_session: Session) -> None:
    _ensure_agent(db_session)
    task = _task(db_session)
    ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Binding Facts",
        description="Binding facts",
        source_type="text",
        title="Facts",
        content=_two_chunk_content("binding beacon"),
        uri=None,
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="binding-facts",
    )
    grounding = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="binding beacon",
    )
    assert grounding.prompt_manifest is not None
    manifest = grounding.prompt_manifest

    gateway = AuditedModelGateway(
        session=db_session,
        task_id=task.id,
        gateway=_StaticGateway(),
        grounding_correlation_id=manifest.grounding_correlation_id,
        prompt_manifest_id=manifest.id,
        prompt_manifest_version=manifest.metadata_json["prompt_manifest_version"],
        retrieval_evidence_ids=list(manifest.included_retrieval_hit_ids_json),
        evidence_text_sha256=manifest.evidence_text_sha256,
    )
    gateway.complete(
        ModelRequest(
            model_provider="default",
            model_name="default",
            response_format="text",
            messages=[
                ModelMessage(role="system", content=grounding.evidence_summary),
                ModelMessage(role="user", content="binding beacon"),
            ],
        )
    )
    db_session.flush()

    model_call = db_session.scalar(select(ModelCall).where(ModelCall.task_id == task.id))
    assert model_call is not None
    assert manifest.grounding_correlation_id == model_call.grounding_correlation_id
    assert model_call.prompt_manifest_id == manifest.id
    assert model_call.model_request_sha256
    assert model_call.model_request_hash_schema_version == 2
    assert model_call.request_message_hashes_json
    assert model_call.request_message_hashes_sha256
    assert model_call.hash_recomputability_status == "recomputable_v2"
    recomputed_message_hashes_sha256 = hashlib.sha256(
        json.dumps(
            model_call.request_message_hashes_json,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert recomputed_message_hashes_sha256 == model_call.request_message_hashes_sha256
    assert model_call.model_request_sha256 == _request_hash_v2(
        model_provider=model_call.model_provider,
        model_name=model_call.model_name,
        response_format=model_call.request_json["response_format"],
        generation_parameters=model_call.request_json["generation_parameters"],
        request_message_hashes=model_call.request_message_hashes_json,
        request_message_hashes_sha256=model_call.request_message_hashes_sha256,
        retrieval_evidence_ids=list(manifest.included_retrieval_hit_ids_json),
        prompt_manifest_id=manifest.id,
        prompt_manifest_version=manifest.metadata_json["prompt_manifest_version"],
        evidence_text_sha256=manifest.evidence_text_sha256,
    )
    assert model_call.request_json["model_request_sha256"] == model_call.model_request_sha256
    assert model_call.request_json["model_request_hash_schema_version"] == 2
    assert model_call.request_json["request_message_hashes_sha256"] == (
        model_call.request_message_hashes_sha256
    )
    assert model_call.request_json["messages"][0]["content_sha256"]
    assert model_call.request_json["messages"][0]["content_length"] > 0
    assert "content_preview" not in model_call.request_json["messages"][0]
    assert "content" not in model_call.request_json["messages"][0]
    assert model_call.attempt_index == 1
    assert model_call.terminal_status == "success"


def test_prompt_manifest_model_call_binding_rejects_stale_manifest(
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    first_task = _task(db_session)
    second_task = _task(db_session)
    ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Stale Binding Facts",
        description="Stale binding facts",
        source_type="text",
        title="Facts",
        content=_two_chunk_content("stale beacon"),
        uri=None,
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="stale-binding-facts",
    )
    grounding = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=first_task.id,
        query="stale beacon",
    )
    assert grounding.prompt_manifest is not None
    manifest = grounding.prompt_manifest
    gateway = AuditedModelGateway(
        session=db_session,
        task_id=second_task.id,
        gateway=_StaticGateway(),
        grounding_correlation_id=manifest.grounding_correlation_id,
        prompt_manifest_id=manifest.id,
        prompt_manifest_version=manifest.metadata_json["prompt_manifest_version"],
        retrieval_evidence_ids=list(manifest.included_retrieval_hit_ids_json),
        evidence_text_sha256=manifest.evidence_text_sha256,
    )

    with pytest.raises(ModelGatewayError, match="does not belong"):
        gateway.complete(
            ModelRequest(
                model_provider="default",
                model_name="default",
                response_format="text",
                messages=[
                    ModelMessage(role="system", content=grounding.evidence_summary),
                    ModelMessage(role="user", content="stale beacon"),
                ],
            )
        )
    assert db_session.scalar(select(func.count()).select_from(ModelCall)) == 0


def test_prompt_manifest_model_call_binding_requires_evidence_message(
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    task = _task(db_session)
    ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Evidence Binding Facts",
        description="Evidence binding facts",
        source_type="text",
        title="Facts",
        content=_two_chunk_content("evidence beacon"),
        uri=None,
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="evidence-binding-facts",
    )
    grounding = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="evidence beacon",
    )
    assert grounding.prompt_manifest is not None
    manifest = grounding.prompt_manifest
    gateway = AuditedModelGateway(
        session=db_session,
        task_id=task.id,
        gateway=_StaticGateway(),
        grounding_correlation_id=manifest.grounding_correlation_id,
        prompt_manifest_id=manifest.id,
        prompt_manifest_version=manifest.metadata_json["prompt_manifest_version"],
        retrieval_evidence_ids=list(manifest.included_retrieval_hit_ids_json),
        evidence_text_sha256=manifest.evidence_text_sha256,
    )

    with pytest.raises(ModelGatewayError, match="do not include prompt manifest evidence"):
        gateway.complete(
            ModelRequest(
                model_provider="default",
                model_name="default",
                response_format="text",
                messages=[
                    ModelMessage(role="system", content="No grounding evidence here."),
                    ModelMessage(role="user", content="evidence beacon"),
                ],
            )
        )
    assert db_session.scalar(select(func.count()).select_from(ModelCall)) == 0


def test_prompt_manifest_model_call_binding_records_failed_and_fallback_attempts(
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    task = _task(db_session)
    ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Retry Binding Facts",
        description="Retry binding facts",
        source_type="text",
        title="Facts",
        content=_two_chunk_content("retry beacon"),
        uri=None,
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="retry-binding-facts",
    )
    grounding = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="retry beacon",
    )
    assert grounding.prompt_manifest is not None
    manifest = grounding.prompt_manifest
    gateway = AuditedModelGateway(
        session=db_session,
        task_id=task.id,
        gateway=_FailOnceGateway(),
        grounding_correlation_id=manifest.grounding_correlation_id,
        prompt_manifest_id=manifest.id,
        prompt_manifest_version=manifest.metadata_json["prompt_manifest_version"],
        retrieval_evidence_ids=list(manifest.included_retrieval_hit_ids_json),
        evidence_text_sha256=manifest.evidence_text_sha256,
    )
    request = ModelRequest(
        model_provider="default",
        model_name="default",
        response_format="text",
        messages=[
            ModelMessage(role="system", content=grounding.evidence_summary),
            ModelMessage(role="user", content="retry beacon"),
        ],
    )
    gateway.complete(request, fallback_requests=[request])

    model_calls = list(
        db_session.execute(
            select(ModelCall).where(ModelCall.task_id == task.id).order_by(ModelCall.attempt_index)
        ).scalars()
    )
    assert [call.attempt_index for call in model_calls] == [1, 2]
    assert [call.terminal_status for call in model_calls] == ["failed", "success"]
    assert {call.prompt_manifest_id for call in model_calls} == {manifest.id}


def test_run_detail_grounding_uses_exact_selectors_and_marks_latest_fallback(
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    client = TestClient(app)
    task = _task(db_session)
    ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Selector Facts",
        description="Selector facts",
        source_type="text",
        title="Facts",
        content=_two_chunk_content("first beacon") + _two_chunk_content("second beacon"),
        uri=None,
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="selector-facts",
    )
    first = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="first beacon",
    )
    second = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="second beacon",
    )
    db_session.commit()
    assert first.prompt_manifest is not None
    assert second.prompt_manifest is not None

    latest_response = client.get(
        f"/api/agents/runs/{task.id}/workspace",
        headers=AUTH_HEADERS,
    )
    assert latest_response.status_code == 200
    latest_grounding = latest_response.json()["knowledge_grounding"]
    assert latest_grounding["inferred_fallback"] is True
    assert latest_grounding["selected_retrieval_session_id"] == second.retrieval_session.id

    exact_response = client.get(
        f"/api/agents/runs/{task.id}/workspace",
        headers=AUTH_HEADERS,
        params={"prompt_manifest_id": first.prompt_manifest.id},
    )
    assert exact_response.status_code == 200
    exact_grounding = exact_response.json()["knowledge_grounding"]
    assert exact_grounding["inferred_fallback"] is False
    assert exact_grounding["selected_prompt_manifest_id"] == first.prompt_manifest.id
    assert exact_grounding["retrieval_session"]["id"] == first.retrieval_session.id

    conflict_response = client.get(
        f"/api/agents/runs/{task.id}/workspace",
        headers=AUTH_HEADERS,
        params={
            "prompt_manifest_id": first.prompt_manifest.id,
            "retrieval_session_id": second.retrieval_session.id,
        },
    )
    assert conflict_response.status_code == 409


def test_run_detail_rejects_foreign_run_prompt_manifest_selector(
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    client = TestClient(app)
    dev_task = _task(db_session, organization_id="dev-org")
    other_task = _task(db_session, organization_id="other-org")
    ingest_knowledge_source(
        db_session,
        organization_id="other-org",
        agent_id="default",
        name="Other Selector Facts",
        description="Other selector facts",
        source_type="text",
        title="Other Facts",
        content=_two_chunk_content("other selector beacon"),
        uri=None,
        mime_type="text/markdown",
        created_by="dev-other-engineer",
        idempotency_key="other-selector-facts",
    )
    other_grounding = ground_query(
        db_session,
        organization_id="other-org",
        agent_id="default",
        run_id=other_task.id,
        query="other selector beacon",
    )
    db_session.commit()
    assert other_grounding.prompt_manifest is not None

    response = client.get(
        f"/api/agents/runs/{dev_task.id}/workspace",
        headers=AUTH_HEADERS,
        params={"prompt_manifest_id": other_grounding.prompt_manifest.id},
    )

    assert response.status_code == 404


def test_grounding_audit_survives_reingest_with_original_evidence_snapshot(
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    task = _task(db_session)
    ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Lifecycle Facts",
        description="Lifecycle facts",
        source_type="text",
        title="Facts v1",
        content=_two_chunk_content("original beacon"),
        uri=None,
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="lifecycle-facts",
    )
    result = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="original beacon",
    )
    assert result.prompt_manifest is not None
    manifest_id = result.prompt_manifest.id
    original_snapshots = list(result.prompt_manifest.source_snapshots_json)

    ingest_knowledge_source(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        name="Lifecycle Facts",
        description="Lifecycle facts changed",
        source_type="text",
        title="Facts v2",
        content=_two_chunk_content("changed beacon"),
        uri=None,
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="lifecycle-facts",
    )
    db_session.flush()
    persisted_manifest = db_session.get(PromptAssemblyManifest, manifest_id)

    assert persisted_manifest is not None
    assert persisted_manifest.source_snapshots_json == original_snapshots
    assert "original beacon" in str(persisted_manifest.source_snapshots_json)
    assert "changed beacon" not in str(persisted_manifest.source_snapshots_json)


def test_prompt_manifest_and_policy_audit_are_append_only(db_session: Session) -> None:
    _ensure_agent(db_session)
    task = _task(db_session)
    result = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="append only",
    )
    assert result.prompt_manifest is not None
    assert result.policy_audits
    audit_id = result.policy_audits[0].id
    db_session.commit()

    result.prompt_manifest.query = "mutated"
    with pytest.raises(ValueError, match="append-only"):
        db_session.flush()
    db_session.rollback()

    audit = db_session.get(KnowledgePolicyAudit, audit_id)
    assert audit is not None
    db_session.delete(audit)
    with pytest.raises(ValueError, match="append-only"):
        db_session.flush()


def test_org_scoped_retrieval_does_not_expose_foreign_tenant_signal(
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    task = _task(db_session)
    source, document, chunks, _embeddings = ingest_knowledge_source(
        db_session,
        organization_id="other-org",
        agent_id="default",
        name="Other Tenant Facts",
        description="Other org facts",
        source_type="text",
        title="Other Facts",
        content=_two_chunk_content("tenant secret"),
        uri=None,
        mime_type="text/markdown",
        created_by="dev-other-engineer",
        idempotency_key="other-facts",
    )

    result = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="tenant secret",
    )
    db_session.commit()

    assert result.local_status == "insufficient"
    assert all(hit.source_kind != "knowledge_chunk" for hit in result.retrieval_hits)
    hidden_chunk_ids = {chunk.id for chunk in chunks}
    hidden_hashes = {chunk.text_sha256 for chunk in chunks}
    evidence_payload = (
        str(result.prompt_manifest.__dict__ if result.prompt_manifest else {})
        + str([audit.safe_metadata_json for audit in result.policy_audits])
        + str([citation.metadata_json for citation in result.citations])
        + str([audit.decision for audit in result.policy_audits])
    )
    assert "tenant secret local fact" not in evidence_payload
    assert "foreign_tenant_denied" not in evidence_payload
    assert document.id not in evidence_payload
    assert source.id not in evidence_payload
    assert not any(chunk_id in evidence_payload for chunk_id in hidden_chunk_ids)
    assert not any(text_hash in evidence_payload for text_hash in hidden_hashes)

    response = TestClient(app).get(
        f"/api/agents/runs/{task.id}/workspace",
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert "tenant secret local fact" not in response.text
    assert "foreign_tenant_denied" not in response.text
    assert document.id not in response.text
    assert source.id not in response.text
    assert not any(chunk_id in response.text for chunk_id in hidden_chunk_ids)
    assert not any(text_hash in response.text for text_hash in hidden_hashes)


def test_web_research_url_policy_blocks_local_and_private_targets() -> None:
    assert not _is_safe_research_url("https://knowledge.local/research/q/1")
    assert not _is_safe_research_url("file:///etc/passwd")
    assert not _is_safe_research_url("http://localhost:8080")
    assert not _is_safe_research_url("http://127.0.0.1/latest")
    assert not _is_safe_research_url("http://2130706433/latest")
    assert not _is_safe_research_url("http://0177.0.0.1/latest")
    assert not _is_safe_research_url("http://[::1]/latest")
    assert not _is_safe_research_url("http://169.254.169.254/latest/meta-data")
    assert not _is_safe_research_url("http://10.0.0.8/internal")
    assert not _is_safe_research_url("https://user:pass@example.com/secret")
    assert not _is_safe_research_url("http://metadata.google.internal/computeMetadata/v1")
