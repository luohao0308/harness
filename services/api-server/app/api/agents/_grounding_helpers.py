"""Grounding citation and Run workspace knowledge response helpers."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *

def _missing_grounding_citation_suffix(
    *,
    content: str,
    grounding: KnowledgeGroundingResult | None,
) -> str:
    if grounding is None or not grounding.citations:
        return ""
    missing_keys = [
        citation.citation_key
        for citation in grounding.citations
        if citation.citation_key not in content
    ]
    if not missing_keys:
        return ""
    return "\n\nSources: " + ", ".join(missing_keys)


def _grounding_evidence_fallback_answer(
    *,
    content: str,
    grounding: KnowledgeGroundingResult | None,
) -> str:
    if grounding is None or not grounding.grounded or not grounding.citations:
        return content
    if not _looks_like_grounding_evidence_ignored(content):
        return content
    evidence_lines: list[str] = []
    for citation in grounding.citations[:3]:
        quoted_text = (citation.quoted_text or "").strip()
        if not quoted_text:
            continue
        evidence_lines.append(f"- {quoted_text} {citation.citation_key}")
    if not evidence_lines:
        return content
    return "根据已检索到的知识库记录：\n\n" + "\n".join(evidence_lines)


def _looks_like_grounding_evidence_ignored(content: str) -> bool:
    text = unicodedata.normalize("NFKC", content).strip().lower()
    if not text:
        return False
    company_context_terms = ("公司名", "公司名称", "哪家公司", "具体公司", "具体是哪家公司")
    missing_context_terms = (
        "没有指明",
        "未指明",
        "没有提到",
        "未提到",
        "没有提供",
        "未提供",
        "补充",
        "无法给出",
        "无法确定",
        "暂时无法",
    )
    if any(term in text for term in company_context_terms) and any(
        term in text for term in missing_context_terms
    ):
        return True
    clarification_patterns = (
        "没有指明具体是哪家公司",
        "未指明具体是哪家公司",
        "没有提到具体是哪家公司",
        "未提到具体是哪家公司",
        "还没有提到具体是哪家公司",
        "补充一下公司名称",
        "请提供公司名称",
        "告诉我公司名称",
        "方便告诉我公司名称",
        "无法确定是哪家公司",
        "which company",
        "what company",
        "company name",
    )
    return any(pattern in text for pattern in clarification_patterns)


def _normalize_grounding_citations(
    *,
    content: str,
    grounding: KnowledgeGroundingResult | None,
) -> str:
    if grounding is None:
        return content
    valid_keys = {citation.citation_key for citation in grounding.citations}
    invalid_keys: set[str] = set()

    def replace_invalid(match: re.Match[str]) -> str:
        citation_key = match.group(0)
        if citation_key in valid_keys:
            return citation_key
        invalid_keys.add(citation_key)
        return "[unsupported-citation]"

    normalized = re.sub(r"\[(?:(?:web-)?\d+|W\d+)\]", replace_invalid, content)
    if not invalid_keys:
        return content
    return f"{normalized}\n\nUnsupported citations removed: {len(invalid_keys)}"


def _knowledge_source_response(
    session: Session,
    source: KnowledgeSource,
) -> KnowledgeSourceResponse:
    latest_documents = _knowledge_document_responses(session, source, limit=5)
    validation_status, validation_messages = connector_validation_status(source)
    settings_json = source.settings_json if isinstance(source.settings_json, dict) else {}
    response_settings_json = _safe_connector_settings_for_response(settings_json)
    secret_ref = str(settings_json.get("secret_ref") or settings_json.get("auth_secret_ref") or "")
    return KnowledgeSourceResponse(
        id=source.id,
        organization_id=source.organization_id,
        agent_id=source.agent_id,
        name=source.name,
        description=source.description,
        source_type=source.source_type,
        status=source.status,
        version=source.version,
        scope="org" if source.agent_id is None else "agent",
        expires_at=source.expires_at,
        disabled_at=source.disabled_at,
        archived_at=source.archived_at,
        last_indexed_at=source.last_indexed_at,
        last_ingestion_error=source.last_ingestion_error,
        health_status=source.health_status,
        connector_provider=connector_provider_key(
            settings_json,
            source_type=source.source_type,
        ),
        connector_release_state=connector_release_state(
            settings_json,
            source_type=source.source_type,
        ),
        connector_counts_toward_complete_usable=connector_counts_toward_complete_usable(
            settings_json,
            source_type=source.source_type,
        ),
        connector_validation_status=validation_status,
        connector_validation_messages=validation_messages,
        connector_secret_configured=bool(
            read_connector_secret_ref(
                session,
                organization_id=source.organization_id,
                secret_ref=secret_ref,
            )
        ),
        settings_json=response_settings_json,
        metadata_json=source.metadata_json if isinstance(source.metadata_json, dict) else {},
        idempotency_key=source.idempotency_key,
        created_by=source.created_by,
        created_at=source.created_at,
        updated_at=source.updated_at,
        latest_documents=latest_documents,
    )


def _safe_connector_settings_for_response(settings: dict) -> dict:
    safe_settings = dict(settings)
    secret_ref = str(safe_settings.get("secret_ref") or "").strip()
    if secret_ref_looks_like_raw_secret(secret_ref):
        safe_settings["secret_ref"] = "[REDACTED_RAW_SECRET_REF]"
        safe_settings["secret_ref_invalid"] = True
    return safe_settings


def _knowledge_document_responses(
    session: Session,
    source: KnowledgeSource,
    *,
    limit: int | None = None,
) -> list[KnowledgeDocumentResponse]:
    statement = (
        select(KnowledgeDocument)
        .where(KnowledgeDocument.source_id == source.id)
        .order_by(KnowledgeDocument.version.desc(), KnowledgeDocument.created_at.desc())
    )
    if limit is not None:
        statement = statement.limit(limit)
    documents = list(session.execute(statement).scalars())
    document_ids = [document.id for document in documents]
    chunk_counts = (
        dict(
            session.execute(
                select(KnowledgeChunk.document_id, func.count(KnowledgeChunk.id))
                .where(
                    KnowledgeChunk.document_id.in_(document_ids),
                    KnowledgeChunk.status == "ACTIVE",
                )
                .group_by(KnowledgeChunk.document_id)
            ).all()
        )
        if document_ids
        else {}
    )
    return [
        KnowledgeDocumentResponse.model_validate(document).model_copy(
            update={"chunk_count": int(chunk_counts.get(document.id, 0))}
        )
        for document in documents
    ]


def _knowledge_grounding_response(
    session: Session,
    *,
    run: Task,
    retrieval_session_id: str | None = None,
    prompt_manifest_id: str | None = None,
) -> KnowledgeGroundingResponse | None:
    inferred_fallback = False
    fallback_reason: str | None = None
    prompt_manifest: PromptAssemblyManifest | None = None
    if prompt_manifest_id:
        prompt_manifest = session.get(PromptAssemblyManifest, prompt_manifest_id)
        if (
            prompt_manifest is None
            or prompt_manifest.run_id != run.id
            or prompt_manifest.organization_id != run.organization_id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Prompt manifest not found",
            )
        if (
            retrieval_session_id is not None
            and prompt_manifest.retrieval_session_id != retrieval_session_id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Prompt manifest does not belong to retrieval session",
            )
        retrieval_session = session.get(RetrievalSession, prompt_manifest.retrieval_session_id)
    elif retrieval_session_id:
        retrieval_session = session.get(RetrievalSession, retrieval_session_id)
        if (
            retrieval_session is None
            or retrieval_session.run_id != run.id
            or retrieval_session.organization_id != run.organization_id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Retrieval session not found",
            )
    else:
        inferred_fallback = True
        fallback_reason = "latest_run_retrieval_session"
        retrieval_session = session.execute(
            select(RetrievalSession)
            .where(RetrievalSession.run_id == run.id)
            .order_by(RetrievalSession.created_at.desc(), RetrievalSession.id.desc())
            .limit(1)
        ).scalar_one_or_none()
    if retrieval_session is None:
        return None
    hits = list(
        session.execute(
            select(RetrievalHit)
            .where(RetrievalHit.retrieval_session_id == retrieval_session.id)
            .order_by(RetrievalHit.rank.asc(), RetrievalHit.id.asc())
        ).scalars()
    )
    citations = list(
        session.execute(
            select(CitationRecord)
            .where(CitationRecord.retrieval_session_id == retrieval_session.id)
            .order_by(CitationRecord.created_at.asc(), CitationRecord.id.asc())
        ).scalars()
    )
    web_sources = list(
        session.execute(
            select(WebResearchSource)
            .where(WebResearchSource.retrieval_session_id == retrieval_session.id)
            .order_by(WebResearchSource.fetched_at.asc(), WebResearchSource.id.asc())
        ).scalars()
    )
    if prompt_manifest is None:
        prompt_manifest = session.execute(
            select(PromptAssemblyManifest)
            .where(PromptAssemblyManifest.retrieval_session_id == retrieval_session.id)
            .order_by(PromptAssemblyManifest.created_at.desc(), PromptAssemblyManifest.id.desc())
            .limit(1)
        ).scalar_one_or_none()
    policy_audits = list(
        session.execute(
            select(KnowledgePolicyAudit)
            .where(KnowledgePolicyAudit.retrieval_session_id == retrieval_session.id)
            .order_by(KnowledgePolicyAudit.created_at.asc(), KnowledgePolicyAudit.id.asc())
        ).scalars()
    )
    evidence_summary = "Local knowledge grounded the answer."
    connector_hits = [hit for hit in hits if hit.source_kind.endswith("_connector")]
    outcome_source = (
        prompt_manifest.metadata_json
        if prompt_manifest is not None and isinstance(prompt_manifest.metadata_json, dict)
        else retrieval_session.metadata_json
        if isinstance(retrieval_session.metadata_json, dict)
        else {}
    )
    if retrieval_session.local_status != "sufficient":
        evidence_summary = str(
            outcome_source.get("evidence_message")
            or "Local knowledge is insufficient; no web research provider is configured."
        )
        if connector_hits:
            provider = str(
                (
                    connector_hits[0].metadata_json
                    if isinstance(connector_hits[0].metadata_json, dict)
                    else {}
            ).get("connector_provider")
                or "dify"
            ).strip().lower()
            label = "Coze" if provider == "coze" else "Dify"
            evidence_summary = (
                f"Local knowledge is insufficient; {label} connector grounded the answer."
            )
        elif web_sources:
            evidence_summary = (
                "Local knowledge is insufficient; controlled web research grounded the answer."
            )
    is_grounded = bool(citations) and (
        retrieval_session.local_status == "sufficient" or bool(web_sources) or bool(connector_hits)
    )
    if is_grounded and prompt_manifest is not None:
        evidence_summary = str(
            prompt_manifest.metadata_json.get("evidence_message") or evidence_summary
        )
    evidence_message = str(outcome_source.get("evidence_message") or evidence_summary)
    return KnowledgeGroundingResponse(
        retrieval_session=RetrievalSessionResponse.model_validate(retrieval_session),
        retrieval_hits=[KnowledgeRetrievalHitResponse.model_validate(hit) for hit in hits],
        citations=[KnowledgeCitationResponse.model_validate(citation) for citation in citations],
        prompt_manifest=(
            PromptAssemblyManifestResponse.model_validate(prompt_manifest)
            if prompt_manifest is not None
            else None
        ),
        policy_audits=[
            KnowledgePolicyAuditResponse.model_validate(audit) for audit in policy_audits
        ],
        web_sources=[WebResearchSourceResponse.model_validate(source) for source in web_sources],
        vector_capability=retrieval_session.vector_capability,
        local_status=retrieval_session.local_status,
        grounded=is_grounded,
        grounding_provider=str(outcome_source.get("grounding_provider") or "none"),
        fixture_grounded=bool(outcome_source.get("fixture_grounded") or False),
        verified_grounded=bool(outcome_source.get("verified_grounded") or False),
        grounding_verification_reason=str(
            outcome_source.get("grounding_verification_reason") or "no_verified_evidence"
        ),
        evidence_summary=evidence_summary,
        evidence_message=evidence_message,
        inferred_fallback=inferred_fallback,
        fallback_reason=fallback_reason,
        selected_retrieval_session_id=retrieval_session.id,
        selected_prompt_manifest_id=prompt_manifest.id if prompt_manifest else None,
    )

__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
