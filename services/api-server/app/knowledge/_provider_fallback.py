"""Connector and web provider routing helpers for grounding."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
from .chunking import *
from .connectors import *
from .lifecycle import *
from .prompt_assembly import *
from .retrieval_events import *
from .web_routing import *
import app.knowledge as knowledge_api


def _dify_source_metadata(source: KnowledgeSource, settings: dict) -> dict:
    endpoint = str(settings.get("endpoint") or settings.get("uri") or "").strip()
    dataset_id = str(settings.get("dataset_id") or "").strip()
    secret_ref = str(settings.get("secret_ref") or settings.get("auth_secret_ref") or "").strip()
    secret_ref_is_raw = secret_ref_looks_like_raw_secret(secret_ref)
    return {
        "connector_provider": "dify",
        "connector_source_id": source.id,
        "connector_source_name": source.name,
        "dataset_id": dataset_id,
        "dataset_id_sha256": _sha256(dataset_id) if dataset_id else None,
        "endpoint_sha256": _sha256(endpoint) if endpoint else None,
        "endpoint_hostname": _endpoint_hostname(endpoint),
        "connector_secret_ref_present": bool(secret_ref),
        "connector_secret_ref_invalid": secret_ref_is_raw,
    }


def _dify_hit_metadata(
    *,
    source: KnowledgeSource,
    settings: dict,
    result: DifyRetrievalResult,
    snippet: str,
) -> dict:
    source_metadata = _dify_source_metadata(source, settings)
    source_metadata.pop("connector_secret_ref_present", None)
    source_metadata.pop("connector_secret_ref_invalid", None)
    return {
        **source_metadata,
        "connector_ref_valid": not secret_ref_looks_like_raw_secret(
            str(settings.get("secret_ref") or settings.get("auth_secret_ref") or "")
        ),
        "source_id": source.id,
        "source_version": source.version,
        "source_name_snapshot": source.name,
        "segment_id": result.segment_id,
        "dify_document_id": result.document_id,
        "dify_document_name": result.document_name,
        "dify_position": result.position,
        "content_sha256": result.content_sha256,
        "snippet_sha256": _sha256(snippet),
        "source_bound_semantics": "external_connector_source_bound_not_factual_verification",
    }


def _dify_document_status_metadata(status: DifyDatasetDocumentStatus) -> dict:
    metadata: dict = {}
    if status.document_count is not None:
        metadata["dify_document_count"] = status.document_count
    if status.enabled_document_count is not None:
        metadata["dify_enabled_document_count"] = status.enabled_document_count
    if status.disabled_document_count is not None:
        metadata["dify_disabled_document_count"] = status.disabled_document_count
    if status.completed_document_count is not None:
        metadata["dify_completed_document_count"] = status.completed_document_count
    return metadata


def _coze_source_metadata(source: KnowledgeSource, settings: dict) -> dict:
    endpoint = str(settings.get("endpoint") or settings.get("uri") or "").strip()
    dataset_id = str(settings.get("dataset_id") or "").strip()
    secret_ref = str(settings.get("secret_ref") or settings.get("auth_secret_ref") or "").strip()
    secret_ref_is_raw = secret_ref_looks_like_raw_secret(secret_ref)
    return {
        "connector_provider": "coze",
        "connector_source_id": source.id,
        "connector_source_name": source.name,
        "dataset_id": dataset_id,
        "dataset_id_sha256": _sha256(dataset_id) if dataset_id else None,
        "endpoint_sha256": _sha256(endpoint) if endpoint else None,
        "endpoint_hostname": _endpoint_hostname(endpoint),
        "connector_secret_ref_present": bool(secret_ref),
        "connector_secret_ref_invalid": secret_ref_is_raw,
    }


def _coze_hit_metadata(
    *,
    source: KnowledgeSource,
    settings: dict,
    result: CozeRetrievalResult,
    snippet: str,
) -> dict:
    source_metadata = _coze_source_metadata(source, settings)
    source_metadata.pop("connector_secret_ref_present", None)
    source_metadata.pop("connector_secret_ref_invalid", None)
    return {
        **source_metadata,
        "connector_ref_valid": not secret_ref_looks_like_raw_secret(
            str(settings.get("secret_ref") or settings.get("auth_secret_ref") or "")
        ),
        "source_id": source.id,
        "source_version": source.version,
        "source_name_snapshot": source.name,
        "segment_id": result.segment_id,
        "coze_document_id": result.document_id,
        "coze_document_name": result.document_name,
        "content_sha256": result.content_sha256,
        "snippet_sha256": _sha256(snippet),
        "source_bound_semantics": "external_connector_source_bound_not_factual_verification",
    }


def _eligible_connector_sources(
    *,
    session: Session,
    retrieval_session: RetrievalSession,
    connector_sources: list[KnowledgeSource],
    provider: str,
) -> tuple[list[KnowledgeSource], list[KnowledgePolicyAudit]]:
    normalized_provider = provider.strip().lower()
    audits: list[KnowledgePolicyAudit] = []
    eligible: list[KnowledgeSource] = []
    for source in connector_sources:
        settings = source.settings_json if isinstance(source.settings_json, dict) else {}
        if connector_provider_key(settings, source_type=source.source_type) != normalized_provider:
            continue
        if (
            connector_release_state(settings, source_type=source.source_type)
            != CONNECTOR_RELEASE_USABLE
        ):
            continue
        if not connector_counts_toward_complete_usable(settings, source_type=source.source_type):
            continue
        validation_status, validation_messages = connector_validation_status(source)
        if validation_status != "ready":
            source_metadata = (
                _coze_source_metadata(source, settings)
                if normalized_provider == "coze"
                else _dify_source_metadata(source, settings)
            )
            audits.append(
                _create_connector_policy_audit(
                    session=session,
                    retrieval_session=retrieval_session,
                    decision=POLICY_DECISION_DENIED,
                    reason=f"{normalized_provider} connector configuration is not ready",
                    source_ref_id=source.id,
                    source_kind=f"{normalized_provider}_connector",
                    metadata={
                        **source_metadata,
                        "status": validation_status,
                        "reason": ",".join(validation_messages),
                    },
                )
            )
            continue
        eligible.append(source)
    return eligible, audits


def _run_dify_connector_retrieval(
    *,
    session: Session,
    retrieval_session: RetrievalSession,
    connector_sources: list[KnowledgeSource],
    query: str,
) -> tuple[list[RetrievalHit], list[CitationRecord], list[KnowledgePolicyAudit], dict]:
    metadata: dict = {
        "connector_provider": "dify",
        "connector_attempt_count": 0,
        "connector_hit_count": 0,
        "connector_source_count": 0,
        "connector_source_configured": False,
    }
    hits: list[RetrievalHit] = []
    citations: list[CitationRecord] = []
    eligible_sources, audits = _eligible_connector_sources(
        session=session,
        retrieval_session=retrieval_session,
        connector_sources=connector_sources,
        provider="dify",
    )
    metadata["connector_source_count"] = len(eligible_sources)
    metadata["connector_source_configured"] = bool(eligible_sources)
    rank = 1
    for source in eligible_sources:
        settings = source.settings_json if isinstance(source.settings_json, dict) else {}
        endpoint = str(settings.get("endpoint") or settings.get("uri") or "").strip()
        secret_ref = str(
            settings.get("secret_ref") or settings.get("auth_secret_ref") or ""
        ).strip()
        dataset_id = str(settings.get("dataset_id") or "").strip()
        source_metadata = _dify_source_metadata(source, settings)
        adapter = knowledge_api.get_dify_retrieval_adapter("dify")
        if adapter is None:
            audits.append(
                _create_connector_policy_audit(
                    session=session,
                    retrieval_session=retrieval_session,
                    decision=POLICY_DECISION_DENIED,
                    reason="dify connector adapter is unavailable",
                    source_ref_id=source.id,
                    metadata=source_metadata,
                )
            )
            continue
        metadata["connector_attempt_count"] += 1
        if secret_ref_looks_like_raw_secret(secret_ref):
            audit_metadata = {
                **source_metadata,
                "connector_secret_resolved": False,
                "connector_failed": True,
                "connector_failure_reason": (
                    "dify connector secret_ref must reference a server-side secret, "
                    "not a raw secret"
                ),
                "connector_retryable": False,
            }
            audits.append(
                _create_connector_policy_audit(
                    session=session,
                    retrieval_session=retrieval_session,
                    decision=POLICY_DECISION_DENIED,
                    reason=str(audit_metadata["connector_failure_reason"]),
                    source_ref_id=source.id,
                    metadata=audit_metadata,
                )
            )
            metadata.update(audit_metadata)
            continue
        api_key = knowledge_api.resolve_connector_secret_ref(
            secret_ref,
            provider="dify",
            session=session,
            organization_id=retrieval_session.organization_id,
            user_id=source.created_by,
        )
        if not api_key:
            audit_metadata = {
                **source_metadata,
                "connector_secret_resolved": False,
                "connector_failed": True,
                "connector_failure_reason": "dify connector secret_ref could not be resolved",
                "connector_retryable": False,
            }
            audits.append(
                _create_connector_policy_audit(
                    session=session,
                    retrieval_session=retrieval_session,
                    decision=POLICY_DECISION_DENIED,
                    reason=str(audit_metadata["connector_failure_reason"]),
                    source_ref_id=source.id,
                    metadata=audit_metadata,
                )
            )
            metadata.update(audit_metadata)
            continue
        try:
            results = adapter.retrieve(
                endpoint=endpoint,
                dataset_id=dataset_id,
                api_key=api_key,
                query=query,
                max_results=DEFAULT_DIFY_MAX_RESULTS,
                timeout_seconds=DEFAULT_DIFY_TIMEOUT_SECONDS,
            )
        except DifyConnectorError as exc:
            audit_metadata = {
                **source_metadata,
                "connector_secret_resolved": True,
                "connector_failed": True,
                "connector_failure_reason": str(exc),
                "connector_retryable": exc.retryable,
            }
            audits.append(
                _create_connector_policy_audit(
                    session=session,
                    retrieval_session=retrieval_session,
                    decision=POLICY_DECISION_DENIED,
                    reason=str(exc),
                    source_ref_id=source.id,
                    metadata=audit_metadata,
                )
            )
            metadata.update(audit_metadata)
            continue
        metadata["dify_result_count"] = int(metadata.get("dify_result_count") or 0) + len(results)
        if not results and hasattr(adapter, "document_status"):
            try:
                status = adapter.document_status(
                    endpoint=endpoint,
                    dataset_id=dataset_id,
                    api_key=api_key,
                    timeout_seconds=DEFAULT_DIFY_TIMEOUT_SECONDS,
                )
            except DifyConnectorError:
                status = None
            if status is not None:
                metadata.update(_dify_document_status_metadata(status))
        for result in results:
            snippet = result.content[:400]
            metadata.update(
                {
                    "connector_secret_resolved": True,
                    "connector_failed": False,
                    "connector_source_id": source.id,
                    "connector_source_name": source.name,
                    "dataset_id": dataset_id,
                    "dataset_id_sha256": _sha256(dataset_id) if dataset_id else None,
                    "endpoint_sha256": _sha256(endpoint) if endpoint else None,
                    "endpoint_hostname": _endpoint_hostname(endpoint),
                }
            )
            hit = RetrievalHit(
                retrieval_session_id=retrieval_session.id,
                chunk_id=None,
                web_source_id=None,
                rank=rank,
                score=result.score,
                source_kind="dify_connector",
                document_id=None,
                document_version=None,
                snippet=snippet,
                metadata_json=_dify_hit_metadata(
                    source=source,
                    settings=settings,
                    result=result,
                    snippet=snippet,
                ),
                created_at=utc_now(),
            )
            session.add(hit)
            session.flush()
            hits.append(hit)
            citation = CitationRecord(
                retrieval_session_id=retrieval_session.id,
                retrieval_hit_id=hit.id,
                run_id=retrieval_session.run_id,
                message_id=None,
                citation_key=f"[D{rank}]",
                source_kind="dify_connector",
                chunk_id=None,
                web_source_id=None,
                claim_text=query,
                quoted_text=hit.snippet,
                confidence=hit.score,
                metadata_json={
                    "source_snapshot": {
                        "source_id": source.id,
                        "source_version": source.version,
                        "source_name_snapshot": source.name,
                        "connector_provider": "dify",
                        "dataset_id": dataset_id,
                        "dataset_id_sha256": _sha256(dataset_id) if dataset_id else None,
                        "endpoint_sha256": _sha256(endpoint) if endpoint else None,
                        "endpoint_hostname": _endpoint_hostname(endpoint),
                        "segment_id": result.segment_id,
                        "dify_document_id": result.document_id,
                        "dify_document_name": result.document_name,
                        "dify_position": result.position,
                        "quoted_text_sha256": _sha256(hit.snippet),
                        "source_bound_semantics": (
                            "external_connector_source_bound_not_factual_verification"
                        ),
                    },
                },
                created_at=utc_now(),
            )
            session.add(citation)
            session.flush()
            citations.append(citation)
            rank += 1
    metadata["connector_hit_count"] = len(hits)
    return hits, citations, audits, metadata


def _run_coze_connector_retrieval(
    *,
    session: Session,
    retrieval_session: RetrievalSession,
    connector_sources: list[KnowledgeSource],
    query: str,
) -> tuple[list[RetrievalHit], list[CitationRecord], list[KnowledgePolicyAudit], dict]:
    metadata: dict = {
        "connector_provider": "coze",
        "connector_attempt_count": 0,
        "connector_hit_count": 0,
        "connector_source_count": 0,
        "connector_source_configured": False,
    }
    hits: list[RetrievalHit] = []
    citations: list[CitationRecord] = []
    eligible_sources, audits = _eligible_connector_sources(
        session=session,
        retrieval_session=retrieval_session,
        connector_sources=connector_sources,
        provider="coze",
    )
    metadata["connector_source_count"] = len(eligible_sources)
    metadata["connector_source_configured"] = bool(eligible_sources)
    rank = 1
    for source in eligible_sources:
        settings = source.settings_json if isinstance(source.settings_json, dict) else {}
        endpoint = str(settings.get("endpoint") or settings.get("uri") or "").strip()
        secret_ref = str(
            settings.get("secret_ref") or settings.get("auth_secret_ref") or ""
        ).strip()
        dataset_id = str(settings.get("dataset_id") or "").strip()
        source_metadata = _coze_source_metadata(source, settings)
        adapter = knowledge_api.get_coze_retrieval_adapter("coze")
        if adapter is None:
            audits.append(
                _create_connector_policy_audit(
                    session=session,
                    retrieval_session=retrieval_session,
                    decision=POLICY_DECISION_DENIED,
                    reason="coze connector adapter is unavailable",
                    source_ref_id=source.id,
                    source_kind="coze_connector",
                    metadata=source_metadata,
                )
            )
            continue
        metadata["connector_attempt_count"] += 1
        if secret_ref_looks_like_raw_secret(secret_ref):
            audit_metadata = {
                **source_metadata,
                "connector_secret_resolved": False,
                "connector_failed": True,
                "connector_failure_reason": (
                    "coze connector secret_ref must reference a server-side secret, "
                    "not a raw secret"
                ),
                "connector_retryable": False,
            }
            audits.append(
                _create_connector_policy_audit(
                    session=session,
                    retrieval_session=retrieval_session,
                    decision=POLICY_DECISION_DENIED,
                    reason=str(audit_metadata["connector_failure_reason"]),
                    source_ref_id=source.id,
                    source_kind="coze_connector",
                    metadata=audit_metadata,
                )
            )
            metadata.update(audit_metadata)
            continue
        api_key = knowledge_api.resolve_connector_secret_ref(
            secret_ref,
            provider="coze",
            session=session,
            organization_id=retrieval_session.organization_id,
            user_id=source.created_by,
        )
        if not api_key:
            audit_metadata = {
                **source_metadata,
                "connector_secret_resolved": False,
                "connector_failed": True,
                "connector_failure_reason": "coze connector secret_ref could not be resolved",
                "connector_retryable": False,
            }
            audits.append(
                _create_connector_policy_audit(
                    session=session,
                    retrieval_session=retrieval_session,
                    decision=POLICY_DECISION_DENIED,
                    reason=str(audit_metadata["connector_failure_reason"]),
                    source_ref_id=source.id,
                    source_kind="coze_connector",
                    metadata=audit_metadata,
                )
            )
            metadata.update(audit_metadata)
            continue
        try:
            results = adapter.retrieve(
                endpoint=endpoint,
                dataset_id=dataset_id,
                api_key=api_key,
                query=query,
                max_results=DEFAULT_COZE_MAX_RESULTS,
                timeout_seconds=DEFAULT_COZE_TIMEOUT_SECONDS,
            )
        except CozeConnectorError as exc:
            audit_metadata = {
                **source_metadata,
                "connector_secret_resolved": True,
                "connector_failed": True,
                "connector_failure_reason": str(exc),
                "connector_retryable": exc.retryable,
            }
            audits.append(
                _create_connector_policy_audit(
                    session=session,
                    retrieval_session=retrieval_session,
                    decision=POLICY_DECISION_DENIED,
                    reason=str(exc),
                    source_ref_id=source.id,
                    source_kind="coze_connector",
                    metadata=audit_metadata,
                )
            )
            metadata.update(audit_metadata)
            continue
        metadata["coze_result_count"] = int(metadata.get("coze_result_count") or 0) + len(results)
        for result in results:
            snippet = result.content[:400]
            metadata.update(
                {
                    "connector_secret_resolved": True,
                    "connector_failed": False,
                    "connector_source_id": source.id,
                    "connector_source_name": source.name,
                    "dataset_id": dataset_id,
                    "dataset_id_sha256": _sha256(dataset_id) if dataset_id else None,
                    "endpoint_sha256": _sha256(endpoint) if endpoint else None,
                    "endpoint_hostname": _endpoint_hostname(endpoint),
                }
            )
            hit = RetrievalHit(
                retrieval_session_id=retrieval_session.id,
                chunk_id=None,
                web_source_id=None,
                rank=rank,
                score=result.score,
                source_kind="coze_connector",
                document_id=None,
                document_version=None,
                snippet=snippet,
                metadata_json=_coze_hit_metadata(
                    source=source,
                    settings=settings,
                    result=result,
                    snippet=snippet,
                ),
                created_at=utc_now(),
            )
            session.add(hit)
            session.flush()
            hits.append(hit)
            citation = CitationRecord(
                retrieval_session_id=retrieval_session.id,
                retrieval_hit_id=hit.id,
                run_id=retrieval_session.run_id,
                message_id=None,
                citation_key=f"[C{rank}]",
                source_kind="coze_connector",
                chunk_id=None,
                web_source_id=None,
                claim_text=query,
                quoted_text=hit.snippet,
                confidence=hit.score,
                metadata_json={
                    "source_snapshot": {
                        "source_id": source.id,
                        "source_version": source.version,
                        "source_name_snapshot": source.name,
                        "connector_provider": "coze",
                        "dataset_id": dataset_id,
                        "dataset_id_sha256": _sha256(dataset_id) if dataset_id else None,
                        "endpoint_sha256": _sha256(endpoint) if endpoint else None,
                        "endpoint_hostname": _endpoint_hostname(endpoint),
                        "segment_id": result.segment_id,
                        "coze_document_id": result.document_id,
                        "coze_document_name": result.document_name,
                        "quoted_text_sha256": _sha256(hit.snippet),
                        "source_bound_semantics": (
                            "external_connector_source_bound_not_factual_verification"
                        ),
                    },
                },
                created_at=utc_now(),
            )
            session.add(citation)
            session.flush()
            citations.append(citation)
            rank += 1
    metadata["connector_hit_count"] = len(hits)
    return hits, citations, audits, metadata


__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
