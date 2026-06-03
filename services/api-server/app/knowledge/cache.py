"""RAG cache serialization and hydration helpers."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
from .chunking import *
from .prompt_assembly import *
from .retrieval_events import *

def _knowledge_snapshot_hash(
    *,
    chunk_rows: list[tuple[KnowledgeChunk, KnowledgeEmbedding, KnowledgeDocument, KnowledgeSource]],
) -> str:
    payload = [
        {
            "chunk_id": chunk.id,
            "chunk_status": chunk.status,
            "chunk_version": chunk.chunk_version,
            "chunk_text_sha256": chunk.text_sha256,
            "document_id": document.id,
            "document_version": document.version,
            "document_status": document.status,
            "document_content_sha256": document.content_sha256,
            "source_id": source.id,
            "source_version": source.version,
            "source_status": source.status,
            "source_agent_id": source.agent_id,
        }
        for chunk, _embedding, document, source in chunk_rows
    ]
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256(raw)


def _rag_cache_key_hash(
    *,
    organization_id: str | None,
    agent_id: str,
    query: str,
    capability: str,
    research_provider: str,
    knowledge_snapshot_hash: str,
) -> str:
    payload = {
        "schema_version": CONTEXT_CACHE_SCHEMA_VERSION,
        "cache_source": CACHE_SOURCE_RAG_RETRIEVAL,
        "organization_id": organization_id,
        "agent_id": agent_id,
        "query": query,
        "strategy": "vector" if capability == VECTOR_CAPABILITY_AVAILABLE else "lexical",
        "vector_capability": capability,
        "min_hits": DEFAULT_MIN_HITS,
        "min_score": DEFAULT_MIN_SCORE,
        "max_local_chunks": DEFAULT_MAX_LOCAL_CHUNKS,
        "max_web_results": (
            DEFAULT_WEB_RESEARCH_MAX_RESULTS
            if research_provider != WEB_RESEARCH_PROVIDER_DISABLED
            else 0
        ),
        "knowledge_snapshot_hash": knowledge_snapshot_hash,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256(raw)


def _rag_cache_lookup(
    *,
    session: Session,
    organization_id: str | None,
    agent_id: str,
    cache_key_hash: str,
) -> WorkspaceContextCache | None:
    now = utc_now()
    return session.execute(
        select(WorkspaceContextCache).where(
            WorkspaceContextCache.organization_id == organization_id,
            WorkspaceContextCache.agent_id == agent_id,
            WorkspaceContextCache.cache_source == CACHE_SOURCE_RAG_RETRIEVAL,
            WorkspaceContextCache.cache_key_hash == cache_key_hash,
            WorkspaceContextCache.status == "active",
            or_(
                WorkspaceContextCache.expires_at.is_(None),
                WorkspaceContextCache.expires_at > now,
            ),
        )
    ).scalar_one_or_none()


def _persist_rag_cache(
    *,
    session: Session,
    organization_id: str | None,
    agent_id: str,
    cache_key_hash: str,
    retrieval_session: RetrievalSession,
    hits: list[RetrievalHit],
    citations: list[CitationRecord],
    omitted_candidates: list[dict],
    evidence_summary: str,
    evidence_message: str,
    grounding_outcome: dict,
    metadata: dict,
) -> None:
    if retrieval_session.mode != "local" or retrieval_session.local_status != "sufficient":
        return
    now = utc_now()
    payload = {
        "retrieval_session": {
            "mode": retrieval_session.mode,
            "local_status": retrieval_session.local_status,
            "vector_capability": retrieval_session.vector_capability,
            "strategy": retrieval_session.strategy,
            "min_hits": retrieval_session.min_hits,
            "min_score": retrieval_session.min_score,
            "max_local_chunks": retrieval_session.max_local_chunks,
            "max_web_results": retrieval_session.max_web_results,
            "metadata_json": retrieval_session.metadata_json,
        },
        "hits": [
            {
                "chunk_id": hit.chunk_id,
                "rank": hit.rank,
                "score": hit.score,
                "source_kind": hit.source_kind,
                "document_id": hit.document_id,
                "document_version": hit.document_version,
                "snippet": hit.snippet,
                "metadata_json": hit.metadata_json,
            }
            for hit in hits
            if hit.source_kind == "knowledge_chunk"
        ],
        "citations": [
            {
                "citation_key": citation.citation_key,
                "source_kind": citation.source_kind,
                "chunk_id": citation.chunk_id,
                "claim_text": citation.claim_text,
                "quoted_text": citation.quoted_text,
                "confidence": citation.confidence,
                "metadata_json": citation.metadata_json,
            }
            for citation in citations
            if citation.source_kind == "knowledge_chunk"
        ],
        "omitted_candidates": omitted_candidates,
        "evidence_summary": evidence_summary,
        "evidence_message": evidence_message,
        "grounding_outcome": grounding_outcome,
        "cache_metadata": metadata,
        "estimated_saved_tokens": max(1, len(evidence_summary) // 4),
    }
    row = session.execute(
        select(WorkspaceContextCache).where(
            WorkspaceContextCache.organization_id == organization_id,
            WorkspaceContextCache.cache_source == CACHE_SOURCE_RAG_RETRIEVAL,
            WorkspaceContextCache.cache_key_hash == cache_key_hash,
        )
    ).scalar_one_or_none()
    if row is None:
        session.add(
            WorkspaceContextCache(
                organization_id=organization_id,
                agent_id=agent_id,
                cache_source=CACHE_SOURCE_RAG_RETRIEVAL,
                cache_key_hash=cache_key_hash,
                schema_version=CONTEXT_CACHE_SCHEMA_VERSION,
                status="active",
                payload_json=payload,
                metadata_json={"reason": "rag_retrieval_computed"},
                hit_count=0,
                miss_count=1,
                stale_count=0,
                estimated_saved_tokens=int(payload["estimated_saved_tokens"]),
                created_at=now,
                updated_at=now,
            )
        )
    else:
        row.payload_json = payload
        row.metadata_json = {"reason": "rag_retrieval_computed"}
        row.estimated_saved_tokens = int(payload["estimated_saved_tokens"])
        row.miss_count += 1
        row.updated_at = now
    session.flush()


def _ground_query_from_cache(
    *,
    session: Session,
    cache_row: WorkspaceContextCache,
    organization_id: str | None,
    agent_id: str,
    run_id: str | None,
    query: str,
    research_provider: str,
    cache_key_hash: str,
) -> KnowledgeGroundingResult | None:
    payload = cache_row.payload_json if isinstance(cache_row.payload_json, dict) else {}
    cached_hits = payload.get("hits")
    if not isinstance(cached_hits, list) or not cached_hits:
        return None
    now = utc_now()
    session_payload = payload.get("retrieval_session")
    if not isinstance(session_payload, dict):
        return None
    metadata = dict(session_payload.get("metadata_json") or {})
    metadata.update(
        {
            "cache_status": "hit",
            "cache_source": CACHE_SOURCE_RAG_RETRIEVAL,
            "cache_key_hash": cache_key_hash,
            "cache_reason": "rag_retrieval_reused",
            "cache_estimated_saved_tokens": int(payload.get("estimated_saved_tokens") or 0),
        }
    )
    retrieval_session = RetrievalSession(
        organization_id=organization_id,
        agent_id=agent_id,
        run_id=run_id,
        query=query,
        mode=str(session_payload.get("mode") or "local"),
        local_status=str(session_payload.get("local_status") or "sufficient"),
        vector_capability=str(
            session_payload.get("vector_capability") or VECTOR_CAPABILITY_UNAVAILABLE
        ),
        strategy=str(session_payload.get("strategy") or "lexical"),
        min_hits=int(session_payload.get("min_hits") or DEFAULT_MIN_HITS),
        min_score=float(session_payload.get("min_score") or DEFAULT_MIN_SCORE),
        max_local_chunks=int(session_payload.get("max_local_chunks") or DEFAULT_MAX_LOCAL_CHUNKS),
        max_web_results=int(session_payload.get("max_web_results") or 0),
        metadata_json=metadata,
        created_at=now,
    )
    session.add(retrieval_session)
    session.flush()

    hits: list[RetrievalHit] = []
    old_to_new_hit_id: dict[str, str] = {}
    for raw_hit in cached_hits:
        if not isinstance(raw_hit, dict):
            continue
        hit = RetrievalHit(
            retrieval_session_id=retrieval_session.id,
            chunk_id=raw_hit.get("chunk_id"),
            web_source_id=None,
            rank=int(raw_hit.get("rank") or len(hits) + 1),
            score=float(raw_hit.get("score") or 0),
            source_kind=str(raw_hit.get("source_kind") or "knowledge_chunk"),
            document_id=raw_hit.get("document_id"),
            document_version=raw_hit.get("document_version"),
            snippet=str(raw_hit.get("snippet") or ""),
            metadata_json={
                **(
                    raw_hit.get("metadata_json")
                    if isinstance(raw_hit.get("metadata_json"), dict)
                    else {}
                ),
                "cache_status": "hit",
                "cache_source": CACHE_SOURCE_RAG_RETRIEVAL,
                "cache_key_hash": cache_key_hash,
            },
            created_at=now,
        )
        session.add(hit)
        session.flush()
        if raw_hit.get("retrieval_hit_id"):
            old_to_new_hit_id[str(raw_hit["retrieval_hit_id"])] = hit.id
        hits.append(hit)

    citations: list[CitationRecord] = []
    for raw_citation in payload.get("citations") or []:
        if not isinstance(raw_citation, dict):
            continue
        matching_hit = next(
            (hit for hit in hits if hit.chunk_id == raw_citation.get("chunk_id")),
            hits[0] if hits else None,
        )
        if matching_hit is None:
            continue
        citation = CitationRecord(
            retrieval_session_id=retrieval_session.id,
            retrieval_hit_id=matching_hit.id,
            run_id=run_id,
            message_id=None,
            citation_key=str(raw_citation.get("citation_key") or f"[{matching_hit.rank}]"),
            source_kind=str(raw_citation.get("source_kind") or matching_hit.source_kind),
            chunk_id=matching_hit.chunk_id,
            web_source_id=None,
            claim_text=str(raw_citation.get("claim_text") or query),
            quoted_text=str(raw_citation.get("quoted_text") or matching_hit.snippet),
            confidence=float(raw_citation.get("confidence") or matching_hit.score),
            metadata_json=raw_citation.get("metadata_json")
            if isinstance(raw_citation.get("metadata_json"), dict)
            else {},
            created_at=now,
        )
        session.add(citation)
        session.flush()
        citations.append(citation)

    grounding_outcome = payload.get("grounding_outcome")
    if not isinstance(grounding_outcome, dict):
        grounding_outcome = _grounding_outcome(
            local_status=retrieval_session.local_status,
            web_sources=[],
        )
    evidence_summary = str(payload.get("evidence_summary") or "")
    evidence_message = str(
        payload.get("evidence_message") or "Local knowledge grounded the answer."
    )
    omitted_candidates = (
        payload.get("omitted_candidates")
        if isinstance(payload.get("omitted_candidates"), list)
        else []
    )
    policy_audits = _create_policy_audits(
        session=session,
        retrieval_session=retrieval_session,
        hits=hits,
        omitted_candidates=omitted_candidates,
        denied_candidates=[],
        redacted_candidates=[],
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
            "cache_status": "hit",
            "cache_source": CACHE_SOURCE_RAG_RETRIEVAL,
            "cache_key_hash": cache_key_hash,
            "cache_reason": "rag_retrieval_reused",
            "cache_estimated_saved_tokens": int(payload.get("estimated_saved_tokens") or 0),
        },
    )
    if run_id:
        _record_retrieval_event(
            session=session,
            run_id=run_id,
            retrieval_session=retrieval_session,
            hits=hits,
            citations=citations,
            web_sources=[],
            prompt_manifest=prompt_manifest,
            policy_audits=policy_audits,
            local_status=retrieval_session.local_status,
        )
    cache_row.hit_count += 1
    cache_row.last_hit_at = now
    cache_row.updated_at = now
    session.commit()
    grounded = retrieval_session.local_status == "sufficient" and bool(citations)
    return KnowledgeGroundingResult(
        retrieval_session=retrieval_session,
        retrieval_hits=hits,
        citations=citations,
        web_sources=[],
        prompt_manifest=prompt_manifest,
        policy_audits=policy_audits,
        vector_capability=retrieval_session.vector_capability,
        local_status=retrieval_session.local_status,
        grounded=grounded,
        grounding_provider=str(grounding_outcome["grounding_provider"]),
        fixture_grounded=bool(grounding_outcome["fixture_grounded"]),
        verified_grounded=bool(grounding_outcome["verified_grounded"]),
        grounding_verification_reason=str(grounding_outcome["grounding_verification_reason"]),
        evidence_summary=evidence_summary,
        evidence_message=evidence_message,
    )

__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
