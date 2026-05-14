from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Agent,
    AgentEvent,
    CitationRecord,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeEmbedding,
    RetrievalHit,
    Task,
    utc_now,
)
from app.events.event_types import EventType
from app.knowledge import (
    VECTOR_CAPABILITY_AVAILABLE,
    _is_safe_research_url,
    ground_query,
    ingest_knowledge_source,
    set_vector_capability,
)
from app.main import app
from tests.conftest import AUTH_HEADERS


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
    assert second_document.supersedes_document_id == first_document.id
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
    assert db_session.scalar(select(func.count()).select_from(RetrievalHit)) >= 2
    assert db_session.scalar(select(func.count()).select_from(CitationRecord)) >= 2


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


def test_insufficient_local_evidence_records_no_mock_web_sources_by_default(
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    task = _task(db_session)

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
    assert result.retrieval_session.mode == "local_insufficient"
    assert result.retrieval_session.max_web_results == 0
    assert not result.web_sources
    assert not result.citations
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == task.id)
        ).scalars()
    ]
    assert EventType.RAG_RETRIEVAL_STARTED in event_types
    assert EventType.WEB_RESEARCH_STARTED not in event_types
    assert EventType.WEB_RESEARCH_COMPLETED not in event_types
    assert EventType.RAG_CITATION_RECORDED not in event_types


def test_org_scoped_retrieval_does_not_cross_tenant_boundary(db_session: Session) -> None:
    _ensure_agent(db_session)
    ingest_knowledge_source(
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
        run_id=None,
        query="tenant secret",
    )

    assert result.local_status == "insufficient"
    assert all(hit.source_kind != "knowledge_chunk" for hit in result.retrieval_hits)


def test_web_research_url_policy_blocks_local_and_private_targets() -> None:
    assert not _is_safe_research_url("https://knowledge.local/research/q/1")
    assert not _is_safe_research_url("file:///etc/passwd")
    assert not _is_safe_research_url("http://localhost:8080")
    assert not _is_safe_research_url("http://127.0.0.1/latest")
    assert not _is_safe_research_url("http://169.254.169.254/latest/meta-data")
    assert not _is_safe_research_url("http://10.0.0.8/internal")
    assert not _is_safe_research_url("http://metadata.google.internal/computeMetadata/v1")
