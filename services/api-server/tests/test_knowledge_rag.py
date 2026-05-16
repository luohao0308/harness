import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.model_gateway import (
    AuditedModelGateway,
    ModelGatewayError,
    ModelMessage,
    ModelRequest,
    ModelResponse,
)
from app.db.models import (
    Agent,
    AgentEvent,
    CitationRecord,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeEmbedding,
    KnowledgePolicyAudit,
    ModelCall,
    PromptAssemblyManifest,
    RetrievalHit,
    Task,
    WebResearchSource,
    utc_now,
)
from app.events.event_types import EventType
from app.knowledge import (
    VECTOR_CAPABILITY_AVAILABLE,
    _is_safe_research_url,
    ground_query,
    ingest_knowledge_source,
    set_vector_capability,
    set_web_research_provider,
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
    assert model_call.request_json["model_request_sha256"] == model_call.model_request_sha256
    assert model_call.request_json["messages"][0]["content_preview"]
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


def test_org_scoped_retrieval_does_not_cross_tenant_boundary(db_session: Session) -> None:
    _ensure_agent(db_session)
    _source, _document, chunks, _embeddings = ingest_knowledge_source(
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
    hidden_chunk_ids = {chunk.id for chunk in chunks}
    evidence_payload = (
        str(result.prompt_manifest.__dict__ if result.prompt_manifest else {})
        + str([audit.safe_metadata_json for audit in result.policy_audits])
        + str([citation.metadata_json for citation in result.citations])
    )
    assert "tenant secret local fact" not in evidence_payload
    assert not any(chunk_id in evidence_payload for chunk_id in hidden_chunk_ids)


def test_web_research_url_policy_blocks_local_and_private_targets() -> None:
    assert not _is_safe_research_url("https://knowledge.local/research/q/1")
    assert not _is_safe_research_url("file:///etc/passwd")
    assert not _is_safe_research_url("http://localhost:8080")
    assert not _is_safe_research_url("http://127.0.0.1/latest")
    assert not _is_safe_research_url("http://169.254.169.254/latest/meta-data")
    assert not _is_safe_research_url("http://10.0.0.8/internal")
    assert not _is_safe_research_url("http://metadata.google.internal/computeMetadata/v1")
