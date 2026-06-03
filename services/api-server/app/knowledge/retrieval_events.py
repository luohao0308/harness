"""Retrieval event and policy audit persistence helpers."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
from .connectors import *
from .prompt_assembly import sanitize_audit_payload

def _record_retrieval_event(
    *,
    session: Session,
    run_id: str,
    retrieval_session: RetrievalSession,
    hits: list[RetrievalHit],
    citations: list[CitationRecord],
    web_sources: list[WebResearchSource],
    prompt_manifest: PromptAssemblyManifest,
    policy_audits: list[KnowledgePolicyAudit],
    local_status: str,
) -> None:
    event_store = EventStore(session)
    event_store.append(
        task_id=run_id,
        event_type=EventType.RAG_RETRIEVAL_STARTED,
        payload_json={
            "schema_version": "knowledge-grounding-v1",
            "org_id": retrieval_session.organization_id,
            "agent_id": retrieval_session.agent_id,
            "run_id": retrieval_session.run_id,
            "correlation_id": retrieval_session.id,
            "causation_id": retrieval_session.id,
            "idempotency_key": None,
            "retrieval_session_id": retrieval_session.id,
            "query": retrieval_session.query,
        },
    )
    retrieval_metadata = (
        retrieval_session.metadata_json if isinstance(retrieval_session.metadata_json, dict) else {}
    )
    web_attempt = retrieval_metadata.get("web_research_attempt")
    if web_sources or web_attempt:
        event_store.append(
            task_id=run_id,
            event_type=EventType.WEB_RESEARCH_STARTED,
            payload_json={
                "schema_version": "knowledge-grounding-v1",
                "org_id": retrieval_session.organization_id,
                "agent_id": retrieval_session.agent_id,
                "run_id": retrieval_session.run_id,
                "correlation_id": retrieval_session.id,
                "causation_id": retrieval_session.id,
                "retrieval_session_id": retrieval_session.id,
                "max_web_results": retrieval_session.max_web_results,
                "provider": retrieval_metadata.get("web_research_provider"),
            },
        )
    if hits:
        event_store.append(
            task_id=run_id,
            event_type=EventType.RAG_RETRIEVED,
            payload_json={
                "schema_version": "knowledge-grounding-v1",
                "org_id": retrieval_session.organization_id,
                "agent_id": retrieval_session.agent_id,
                "run_id": retrieval_session.run_id,
                "correlation_id": retrieval_session.id,
                "causation_id": retrieval_session.id,
                "retrieval_session_id": retrieval_session.id,
                "local_status": local_status,
                "hit_ids": [hit.id for hit in hits],
            },
        )
    event_store.append(
        task_id=run_id,
        event_type=EventType.RAG_PROMPT_ASSEMBLED,
        payload_json={
            "schema_version": "knowledge-grounding-v1",
            "org_id": retrieval_session.organization_id,
            "agent_id": retrieval_session.agent_id,
            "run_id": retrieval_session.run_id,
            "correlation_id": retrieval_session.id,
            "causation_id": retrieval_session.id,
            "retrieval_session_id": retrieval_session.id,
            "prompt_manifest_id": prompt_manifest.id,
            "included_retrieval_hit_ids": prompt_manifest.included_retrieval_hit_ids_json,
            "omitted_count": len(prompt_manifest.omitted_candidates_json),
            "evidence_text_sha256": prompt_manifest.evidence_text_sha256,
        },
    )
    for audit in policy_audits:
        event_store.append(
            task_id=run_id,
            event_type=EventType.RAG_POLICY_AUDITED,
            payload_json={
                "schema_version": "knowledge-grounding-v1",
                "org_id": retrieval_session.organization_id,
                "agent_id": retrieval_session.agent_id,
                "run_id": retrieval_session.run_id,
                "correlation_id": retrieval_session.id,
                "causation_id": retrieval_session.id,
                "retrieval_session_id": retrieval_session.id,
                "policy_audit_id": audit.id,
                "decision": audit.decision,
                "reason": audit.reason,
                "source_kind": audit.source_kind,
                "source_ref_id": audit.source_ref_id,
            },
        )
    for citation in citations:
        event_store.append(
            task_id=run_id,
            event_type=EventType.RAG_CITATION_RECORDED,
            payload_json={
                "schema_version": "knowledge-grounding-v1",
                "org_id": retrieval_session.organization_id,
                "agent_id": retrieval_session.agent_id,
                "run_id": retrieval_session.run_id,
                "correlation_id": retrieval_session.id,
                "causation_id": retrieval_session.id,
                "retrieval_session_id": retrieval_session.id,
                "citation_id": citation.id,
                "citation_key": citation.citation_key,
                "source_kind": citation.source_kind,
                "chunk_id": citation.chunk_id,
                "web_source_id": citation.web_source_id,
            },
        )
    if web_sources:
        event_store.append(
            task_id=run_id,
            event_type=EventType.WEB_RESEARCH_COMPLETED,
            payload_json={
                "schema_version": "knowledge-grounding-v1",
                "org_id": retrieval_session.organization_id,
                "agent_id": retrieval_session.agent_id,
                "run_id": retrieval_session.run_id,
                "correlation_id": retrieval_session.id,
                "causation_id": retrieval_session.id,
                "retrieval_session_id": retrieval_session.id,
                "web_source_ids": [source.id for source in web_sources],
                "provider": retrieval_metadata.get("web_research_provider"),
                "partial_denied_count": retrieval_metadata.get("web_result_denied_count", 0),
            },
        )
    elif web_attempt and retrieval_metadata.get("web_research_failed"):
        event_store.append(
            task_id=run_id,
            event_type=EventType.WEB_RESEARCH_FAILED,
            payload_json={
                "schema_version": "knowledge-grounding-v1",
                "org_id": retrieval_session.organization_id,
                "agent_id": retrieval_session.agent_id,
                "run_id": retrieval_session.run_id,
                "correlation_id": retrieval_session.id,
                "causation_id": retrieval_session.id,
                "retrieval_session_id": retrieval_session.id,
                "provider": retrieval_metadata.get("web_research_provider"),
                "reason": retrieval_metadata.get("web_research_failure_reason"),
                "retryable": bool(retrieval_metadata.get("web_research_retryable", False)),
                "timeout_seconds": retrieval_metadata.get("web_research_timeout_seconds"),
            },
        )


def _is_safe_research_url(url: str) -> bool:
    return is_safe_web_research_url(url)


def _create_web_policy_audit(
    *,
    session: Session,
    retrieval_session: RetrievalSession,
    decision: str,
    reason: str,
    source_ref_id: str | None,
    metadata: dict,
) -> KnowledgePolicyAudit:
    audit = KnowledgePolicyAudit(
        retrieval_session_id=retrieval_session.id,
        run_id=retrieval_session.run_id,
        organization_id=retrieval_session.organization_id,
        agent_id=retrieval_session.agent_id,
        decision=decision,
        reason=reason,
        source_kind="web_research",
        source_ref_id=source_ref_id,
        safe_metadata_json=sanitize_audit_payload(metadata),
        created_at=utc_now(),
    )
    session.add(audit)
    session.flush()
    return audit


def _create_connector_policy_audit(
    *,
    session: Session,
    retrieval_session: RetrievalSession,
    decision: str,
    reason: str,
    source_ref_id: str | None,
    source_kind: str = "dify_connector",
    metadata: dict,
) -> KnowledgePolicyAudit:
    audit = KnowledgePolicyAudit(
        retrieval_session_id=retrieval_session.id,
        run_id=retrieval_session.run_id,
        organization_id=retrieval_session.organization_id,
        agent_id=retrieval_session.agent_id,
        decision=decision,
        reason=reason,
        source_kind=source_kind,
        source_ref_id=source_ref_id,
        safe_metadata_json=sanitize_audit_payload(metadata),
        created_at=utc_now(),
    )
    session.add(audit)
    session.flush()
    return audit


def _endpoint_hostname(endpoint: str) -> str | None:
    try:
        parsed = urllib.parse.urlparse(endpoint)
    except ValueError:
        return None
    return parsed.hostname

__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
