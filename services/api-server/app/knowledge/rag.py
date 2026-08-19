"""Local retrieval and final grounding query entrypoint."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
from .cache import *
from .chunking import *
from .connectors import *
from .lifecycle import *
from .prompt_assembly import *
from .provider_routing import *
from .retrieval_events import *
from .settings import *
import app.knowledge as knowledge_api


def _chunk_embedding_vector(embedding: KnowledgeEmbedding) -> list[float]:
    if isinstance(embedding.embedding_json, list) and embedding.embedding_json:
        return [float(value) for value in embedding.embedding_json]
    if isinstance(embedding.embedding_vector, str) and embedding.embedding_vector:
        try:
            return [float(value) for value in json.loads(embedding.embedding_vector)]
        except json.JSONDecodeError:
            return []
    return []


def ground_query(
    session: Session,
    *,
    organization_id: str | None,
    agent_id: str,
    run_id: str | None,
    query: str,
) -> KnowledgeGroundingResult:
    query = _normalize_text(query).strip()
    capability = vector_capability(session, organization_id)
    research_provider = web_research_provider(session, organization_id)
    retrieval_session = RetrievalSession(
        organization_id=organization_id,
        agent_id=agent_id,
        run_id=run_id,
        query=query,
        mode="local",
        local_status="insufficient",
        vector_capability=capability,
        strategy="vector" if capability == VECTOR_CAPABILITY_AVAILABLE else "lexical",
        min_hits=DEFAULT_MIN_HITS,
        min_score=DEFAULT_MIN_SCORE,
        max_local_chunks=DEFAULT_MAX_LOCAL_CHUNKS,
        max_web_results=(
            DEFAULT_WEB_RESEARCH_MAX_RESULTS
            if research_provider != WEB_RESEARCH_PROVIDER_DISABLED
            else 0
        ),
        metadata_json={"web_research_provider": research_provider},
        created_at=utc_now(),
    )
    session.add(retrieval_session)
    session.flush()

    now = utc_now()
    chunk_rows = list(
        session.execute(
            select(KnowledgeChunk, KnowledgeEmbedding, KnowledgeDocument, KnowledgeSource)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .join(KnowledgeSource, KnowledgeChunk.source_id == KnowledgeSource.id)
            .join(KnowledgeEmbedding, KnowledgeEmbedding.chunk_id == KnowledgeChunk.id)
            .where(
                KnowledgeSource.organization_id == organization_id,
                or_(KnowledgeSource.agent_id == None, KnowledgeSource.agent_id == agent_id),  # noqa: E711
                KnowledgeSource.status == SOURCE_STATUS_ACTIVE,
                KnowledgeSource.source_type != "connector",
                or_(KnowledgeSource.expires_at == None, KnowledgeSource.expires_at > now),  # noqa: E711
                KnowledgeChunk.status == CHUNK_STATUS_ACTIVE,
                KnowledgeDocument.status == DOCUMENT_STATUS_INDEXED,
                KnowledgeDocument.superseded_at == None,  # noqa: E711
            )
            .order_by(KnowledgeChunk.created_at.desc(), KnowledgeChunk.chunk_index.asc())
            .limit(DEFAULT_MAX_RETRIEVAL_CANDIDATES)
        ).all()
    )
    connector_sources = _connector_source_rows(
        session=session,
        organization_id=organization_id,
        agent_id=agent_id,
    )
    knowledge_snapshot_hash = _knowledge_snapshot_hash(chunk_rows=chunk_rows)
    connector_snapshot_hash = _connector_snapshot_hash(connector_sources)
    rag_cache_key_hash = _rag_cache_key_hash(
        organization_id=organization_id,
        agent_id=agent_id,
        query=query,
        capability=capability,
        research_provider=research_provider,
        knowledge_snapshot_hash=_sha256(f"{knowledge_snapshot_hash}:{connector_snapshot_hash}"),
    )
    cached = _rag_cache_lookup(
        session=session,
        organization_id=organization_id,
        agent_id=agent_id,
        cache_key_hash=rag_cache_key_hash,
    )
    if cached is not None:
        cached_result = _ground_query_from_cache(
            session=session,
            cache_row=cached,
            organization_id=organization_id,
            agent_id=agent_id,
            run_id=run_id,
            query=query,
            research_provider=research_provider,
            cache_key_hash=rag_cache_key_hash,
        )
        if cached_result is not None:
            return cached_result
        cached.stale_count += 1
        cached.updated_at = utc_now()

    candidates: list[
        tuple[float, KnowledgeChunk, KnowledgeEmbedding, KnowledgeDocument, KnowledgeSource]
    ] = []
    redacted_text_by_chunk_id: dict[str, str] = {}
    redacted_candidates: list[dict] = []
    denied_candidates: list[dict] = []
    query_embedding = _fake_embedding(query)
    for chunk, embedding, document, source in chunk_rows:
        policy_decision = _policy_decision_for_text(chunk.text)
        if policy_decision == POLICY_DECISION_DENIED:
            denied_candidates.append(
                {
                    "source_kind": "knowledge_chunk",
                    "source_ref_id": chunk.id,
                    "policy_decision": POLICY_DECISION_DENIED,
                    "reason": "policy_marker_denied",
                    "reason_code": "policy_marker_denied",
                    "document_id": document.id,
                    "document_version": document.version,
                    "source_id": chunk.source_id,
                    "source_version": chunk.source_version,
                    "chunk_text_sha256": chunk.text_sha256,
                    "denied_text_sha256": chunk.text_sha256,
                }
            )
            continue
        candidate_text = chunk.text
        if policy_decision == POLICY_DECISION_REDACTED:
            candidate_text, redaction_count = _redact_policy_marked_text(chunk.text)
            redacted_text_by_chunk_id[chunk.id] = candidate_text
            redacted_candidates.append(
                {
                    "source_kind": "knowledge_chunk",
                    "source_ref_id": chunk.id,
                    "policy_decision": POLICY_DECISION_REDACTED,
                    "reason": "policy_marker_redacted",
                    "reason_code": POLICY_REDACTION_REASON,
                    "redaction_count": redaction_count,
                    "redacted_text_sha256": _sha256(candidate_text),
                    "document_id": document.id,
                    "document_version": document.version,
                    "source_id": chunk.source_id,
                    "source_version": chunk.source_version,
                    "chunk_text_sha256": chunk.text_sha256,
                }
            )
        vector = _chunk_embedding_vector(embedding)
        if capability == VECTOR_CAPABILITY_AVAILABLE and vector:
            score = _cosine_similarity(query_embedding, vector)
        else:
            score = _lexical_similarity(query, candidate_text)
        candidates.append((score, chunk, embedding, document, source))
    candidates.sort(key=lambda item: item[0], reverse=True)
    top_candidates = [
        candidate
        for candidate in candidates[: retrieval_session.max_local_chunks]
        if candidate[0] >= retrieval_session.min_score
    ]
    sufficiency_reason = "insufficient_min_hits"
    if len(top_candidates) >= retrieval_session.min_hits:
        local_status = "sufficient"
        sufficiency_reason = "min_hits_met"
    elif _is_single_cjk_strong_match(query=query, top_candidates=top_candidates):
        local_status = "sufficient"
        sufficiency_reason = "single_cjk_strong_match"
    else:
        local_status = "insufficient"
    retrieval_session.local_status = local_status
    retrieval_session.strategy = (
        "vector" if capability == VECTOR_CAPABILITY_AVAILABLE else "lexical"
    )
    hits: list[RetrievalHit] = []
    citations: list[CitationRecord] = []
    web_sources: list[WebResearchSource] = []
    web_policy_audits: list[KnowledgePolicyAudit] = []
    web_research_metadata: dict = {}
    connector_policy_audits: list[KnowledgePolicyAudit] = []
    connector_metadata: dict = {}
    selected_chunk_ids: set[str] = set()
    selected_candidates = top_candidates if local_status == "sufficient" else []
    if selected_candidates:
        for rank, (score, chunk, _embedding, document, source) in enumerate(
            selected_candidates,
            start=1,
        ):
            selected_chunk_ids.add(chunk.id)
            snippet_text = redacted_text_by_chunk_id.get(chunk.id, chunk.text)
            document_metadata = (
                document.metadata_json if isinstance(document.metadata_json, dict) else {}
            )
            hit = RetrievalHit(
                retrieval_session_id=retrieval_session.id,
                chunk_id=chunk.id,
                web_source_id=None,
                rank=rank,
                score=score,
                source_kind="knowledge_chunk",
                document_id=document.id,
                document_version=document.version,
                snippet=snippet_text[:400],
                metadata_json={
                    "source_id": chunk.source_id,
                    "source_version": chunk.source_version,
                    "source_name_snapshot": source.name,
                    **connector_source_metadata(source),
                    "chunk_version": chunk.chunk_version,
                    "document_title_snapshot": document.title,
                    "document_content_sha256": document.content_sha256,
                    "project_uri": document_metadata.get("project_uri"),
                    "project_relative_path": document_metadata.get("relative_path"),
                    "project_file_sha256": document_metadata.get("file_content_sha256"),
                    "project_index_id": document_metadata.get("project_index_id"),
                    "chunk_text_sha256": chunk.text_sha256,
                    "snippet_sha256": _sha256(snippet_text[:400]),
                    "chunk_span": {
                        "start_offset": chunk.start_offset,
                        "end_offset": chunk.end_offset,
                    },
                    **(
                        {
                            "policy_decision": POLICY_DECISION_REDACTED,
                            "reason_code": POLICY_REDACTION_REASON,
                        }
                        if chunk.id in redacted_text_by_chunk_id
                        else {}
                    ),
                },
                created_at=now,
            )
            session.add(hit)
            session.flush()
            hits.append(hit)
        for hit in hits:
            hit_metadata = hit.metadata_json if isinstance(hit.metadata_json, dict) else {}
            hit_chunk = session.get(KnowledgeChunk, hit.chunk_id) if hit.chunk_id else None
            citation = CitationRecord(
                retrieval_session_id=retrieval_session.id,
                retrieval_hit_id=hit.id,
                run_id=run_id,
                message_id=None,
                citation_key=f"[{hit.rank}]",
                source_kind=hit.source_kind,
                chunk_id=hit.chunk_id,
                web_source_id=None,
                claim_text=query,
                quoted_text=hit.snippet,
                confidence=hit.score,
                metadata_json={
                    "source_snapshot": {
                        "source_id": hit_chunk.source_id if hit_chunk else None,
                        "source_version": hit_chunk.source_version if hit_chunk else None,
                        "source_name_snapshot": hit_metadata.get("source_name_snapshot"),
                        "connector_provider": hit_metadata.get("connector_provider"),
                        "release_state": hit_metadata.get("release_state"),
                        "sync_state": hit_metadata.get("sync_state"),
                        "counts_as_usable": hit_metadata.get("counts_as_usable"),
                        "document_id": hit.document_id,
                        "document_version": hit.document_version,
                        "document_title_snapshot": hit_metadata.get("document_title_snapshot"),
                        "document_content_sha256": hit_metadata.get("document_content_sha256"),
                        "project_uri": hit_metadata.get("project_uri"),
                        "project_relative_path": hit_metadata.get("project_relative_path"),
                        "project_file_sha256": hit_metadata.get("project_file_sha256"),
                        "project_index_id": hit_metadata.get("project_index_id"),
                        "chunk_id": hit.chunk_id,
                        "chunk_version": hit_metadata.get("chunk_version"),
                        "chunk_text_sha256": hit_metadata.get("chunk_text_sha256"),
                        "chunk_span": hit_metadata.get("chunk_span"),
                        "quoted_text_sha256": _sha256(hit.snippet),
                    },
                },
                created_at=now,
            )
            session.add(citation)
            session.flush()
            citations.append(citation)

    if local_status != "sufficient":
        coze_hits, coze_citations, coze_policy_audits, coze_metadata = (
            _run_coze_connector_retrieval(
                session=session,
                retrieval_session=retrieval_session,
                connector_sources=connector_sources,
                query=query,
            )
        )
        hits.extend(coze_hits)
        citations.extend(coze_citations)
        connector_policy_audits.extend(coze_policy_audits)
        if coze_hits:
            connector_metadata = coze_metadata
            retrieval_session.mode = "connector_fallback"
        dify_hits: list[RetrievalHit] = []
        dify_citations: list[CitationRecord] = []
        dify_policy_audits: list[KnowledgePolicyAudit] = []
        dify_metadata: dict = {}
        if not coze_hits:
            dify_hits, dify_citations, dify_policy_audits, dify_metadata = (
                _run_dify_connector_retrieval(
                    session=session,
                    retrieval_session=retrieval_session,
                    connector_sources=connector_sources,
                    query=query,
                )
            )
            hits.extend(dify_hits)
            citations.extend(dify_citations)
            connector_policy_audits.extend(dify_policy_audits)
            if dify_hits:
                connector_metadata = dify_metadata
                retrieval_session.mode = "connector_fallback"
        if not connector_metadata:
            connector_metadata = (
                coze_metadata if coze_metadata.get("connector_attempt_count") else dify_metadata
            )

    connector_hits = [hit for hit in hits if hit.source_kind.endswith("_connector")]
    connector_hit_count = len(connector_hits)
    connector_grounding_provider = None
    if connector_hits:
        first_connector_metadata = (
            connector_hits[0].metadata_json
            if isinstance(connector_hits[0].metadata_json, dict)
            else {}
        )
        connector_grounding_provider = str(
            first_connector_metadata.get("connector_provider") or ""
        ).strip()
    if local_status != "sufficient" and connector_hit_count == 0:
        web_sources, web_policy_audits, web_research_metadata = _run_web_research_fallback(
            session=session,
            retrieval_session=retrieval_session,
            provider=research_provider,
            query=query,
        )
        for rank, source in enumerate(web_sources, start=1):
            source_metadata = source.metadata_json if isinstance(source.metadata_json, dict) else {}
            hit = RetrievalHit(
                retrieval_session_id=retrieval_session.id,
                chunk_id=None,
                web_source_id=source.id,
                rank=rank,
                score=float(source_metadata.get("result_score") or 1.0),
                source_kind="web_source",
                document_id=None,
                document_version=None,
                snippet=source.snippet,
                metadata_json={
                    "content_sha256": source.content_sha256,
                    "provider": source_metadata.get("provider", research_provider),
                    "source_url_sha256": source_metadata.get(
                        "source_url_sha256",
                        _sha256(source.url),
                    ),
                    "source_bound_semantics": "source_bound_not_factual_verification",
                },
                created_at=now,
            )
            session.add(hit)
            session.flush()
            hits.append(hit)
            citation = CitationRecord(
                retrieval_session_id=retrieval_session.id,
                retrieval_hit_id=hit.id,
                run_id=run_id,
                message_id=None,
                citation_key=f"[W{rank}]",
                source_kind="web_source",
                chunk_id=None,
                web_source_id=source.id,
                claim_text=query,
                quoted_text=source.snippet,
                confidence=hit.score,
                metadata_json={
                    "source_snapshot": {
                        "web_source_id": source.id,
                        "url_sha256": _sha256(source.url),
                        "title": source.title,
                        "content_sha256": source.content_sha256,
                        "quoted_text_sha256": _sha256(source.snippet),
                        "provider": source_metadata.get("provider", research_provider),
                        "source_status": source.status,
                    },
                },
                created_at=now,
            )
            session.add(citation)
            session.flush()
            citations.append(citation)
        retrieval_session.mode = "web_fallback" if web_sources else "local_insufficient"
    grounding_outcome = _grounding_outcome(
        local_status=local_status,
        web_sources=web_sources,
        connector_hit_count=connector_hit_count,
        connector_provider=connector_grounding_provider,
    )
    connector_evidence_message = connector_runtime_evidence_message(
        local_status=local_status,
        metadata=connector_metadata,
    )
    evidence_message = (
        "Local knowledge grounded the answer."
        if local_status == "sufficient"
        else (
            connector_evidence_message
            or (
                "Local knowledge is insufficient; web research grounded the answer."
                if web_sources
                else (
                    "Local knowledge is insufficient; no web research provider is configured."
                    if research_provider == WEB_RESEARCH_PROVIDER_DISABLED
                    else (
                        "Local knowledge is insufficient; web research did not provide "
                        "accepted sources."
                    )
                )
            )
        )
    )
    retrieval_session.metadata_json = {
        "web_research_provider": research_provider,
        "cache_status": "miss",
        "cache_source": CACHE_SOURCE_RAG_RETRIEVAL,
        "cache_key_hash": rag_cache_key_hash,
        "cache_reason": "rag_retrieval_computed",
        "knowledge_snapshot_hash": knowledge_snapshot_hash,
        "connector_snapshot_hash": connector_snapshot_hash,
        "hit_count": len(hits),
        "web_source_count": len(web_sources),
        "connector_hit_count": connector_hit_count,
        "top_score": hits[0].score if hits else 0.0,
        "top_candidate_score": top_candidates[0][0] if top_candidates else 0.0,
        "sufficiency_reason": sufficiency_reason,
        "local_insufficient": local_status != "sufficient",
        "local_hit_count": len(top_candidates),
        "local_best_score": top_candidates[0][0] if top_candidates else 0.0,
        "fallback_trigger_reason": (sufficiency_reason if local_status != "sufficient" else None),
        **connector_metadata,
        **web_research_metadata,
        **grounding_outcome,
    }
    session.flush()
    omitted_candidates = []
    for score, chunk, _embedding, document, _source in candidates:
        if chunk.id in selected_chunk_ids:
            continue
        if score < retrieval_session.min_score:
            reason = "score_below_threshold"
        elif local_status != "sufficient":
            reason = "insufficient_min_hits"
        else:
            reason = "outside_top_k"
        omitted_candidates.append(
            _omitted_candidate_record(
                score=score,
                chunk=chunk,
                document=document,
                reason=reason,
            )
        )
    policy_audits = _create_policy_audits(
        session=session,
        retrieval_session=retrieval_session,
        hits=hits,
        omitted_candidates=omitted_candidates,
        denied_candidates=denied_candidates,
        redacted_candidates=redacted_candidates,
    )
    policy_audits = [*connector_policy_audits, *web_policy_audits, *policy_audits]
    evidence_summary = _build_evidence_messages(
        query=query,
        hits=hits,
        citations=citations,
        web_sources=web_sources,
    )
    prompt_manifest = _create_prompt_manifest(
        session=session,
        retrieval_session=retrieval_session,
        hits=hits,
        citations=citations,
        omitted_candidates=omitted_candidates,
        evidence_summary=evidence_summary,
        grounding_outcome=grounding_outcome,
        evidence_message=evidence_message,
        metadata_overrides={
            "cache_status": "miss",
            "cache_source": CACHE_SOURCE_RAG_RETRIEVAL,
            "cache_key_hash": rag_cache_key_hash,
            "cache_reason": "rag_retrieval_computed",
            "cache_estimated_saved_tokens": max(1, len(evidence_summary) // 4),
        },
    )
    _persist_rag_cache(
        session=session,
        organization_id=organization_id,
        agent_id=agent_id,
        cache_key_hash=rag_cache_key_hash,
        retrieval_session=retrieval_session,
        hits=hits,
        citations=citations,
        omitted_candidates=omitted_candidates,
        evidence_summary=evidence_summary,
        evidence_message=evidence_message,
        grounding_outcome=grounding_outcome,
        metadata=retrieval_session.metadata_json
        if isinstance(retrieval_session.metadata_json, dict)
        else {},
    )
    if run_id:
        _record_retrieval_event(
            session=session,
            run_id=run_id,
            retrieval_session=retrieval_session,
            hits=hits,
            citations=citations,
            web_sources=web_sources,
            prompt_manifest=prompt_manifest,
            policy_audits=policy_audits,
            local_status=local_status,
        )
    session.commit()
    grounded = (
        local_status == "sufficient" or bool(web_sources) or connector_hit_count > 0
    ) and bool(citations)
    return KnowledgeGroundingResult(
        retrieval_session=retrieval_session,
        retrieval_hits=hits,
        citations=citations,
        web_sources=web_sources,
        prompt_manifest=prompt_manifest,
        policy_audits=policy_audits,
        vector_capability=capability,
        local_status=local_status,
        grounded=grounded,
        grounding_provider=str(grounding_outcome["grounding_provider"]),
        fixture_grounded=bool(grounding_outcome["fixture_grounded"]),
        verified_grounded=bool(grounding_outcome["verified_grounded"]),
        grounding_verification_reason=str(grounding_outcome["grounding_verification_reason"]),
        evidence_summary=evidence_summary,
        evidence_message=evidence_message,
    )


__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
