"""Grounding contract grader."""

# ruff: noqa: F401,F403,F405,I001,UP037
from ..common import *
from ..helpers import *

def _grade_grounding_contract(session: Session, task: Task | None, expected_json: dict) -> dict:
    contract = expected_json.get("grounding_contract")
    if not isinstance(contract, dict):
        return _grounding_trace_v1(
            grader="deterministic_trace_grader_v1",
            passed=True,
        )
    if task is None:
        return _grounding_trace_v1(
            grader="deterministic_grounding_grader_v1",
            passed=False,
            grounding_failures=["missing_task"],
        )

    requested_prompt_manifest_id = contract.get("prompt_manifest_id")
    requested_retrieval_session_id = contract.get("retrieval_session_id")
    inferred_fallback = False
    fallback_reason = None
    prompt_manifest: PromptAssemblyManifest | None = None
    if requested_prompt_manifest_id:
        prompt_manifest = session.get(PromptAssemblyManifest, str(requested_prompt_manifest_id))
        if prompt_manifest is None or prompt_manifest.run_id != task.id:
            return _grounding_trace_v1(
                grader="deterministic_grounding_grader_v1",
                passed=False,
                grounding_failures=["missing_prompt_manifest"],
                inferred_fallback=False,
                prompt_manifest_id=str(requested_prompt_manifest_id),
            )
        if requested_retrieval_session_id and prompt_manifest.retrieval_session_id != str(
            requested_retrieval_session_id
        ):
            return _grounding_trace_v1(
                grader="deterministic_grounding_grader_v1",
                passed=False,
                grounding_failures=["selector_conflict"],
                inferred_fallback=False,
                retrieval_session_id=str(requested_retrieval_session_id),
                prompt_manifest_id=prompt_manifest.id,
            )
        retrieval_session = session.get(RetrievalSession, prompt_manifest.retrieval_session_id)
    elif requested_retrieval_session_id:
        retrieval_session = session.get(RetrievalSession, str(requested_retrieval_session_id))
        if retrieval_session is not None and retrieval_session.run_id != task.id:
            retrieval_session = None
    else:
        inferred_fallback = True
        fallback_reason = "latest_run_retrieval_session"
        retrieval_session = session.execute(
            select(RetrievalSession)
            .where(RetrievalSession.run_id == task.id)
            .order_by(RetrievalSession.created_at.desc(), RetrievalSession.id.desc())
            .limit(1)
        ).scalar_one_or_none()
    failures: list[str] = []
    if retrieval_session is None:
        return _grounding_trace_v1(
            grader="deterministic_grounding_grader_v1",
            passed=False,
            grounding_failures=["missing_retrieval_session"],
            inferred_fallback=inferred_fallback,
            fallback_reason=fallback_reason,
        )

    hits = list(
        session.execute(
            select(RetrievalHit).where(RetrievalHit.retrieval_session_id == retrieval_session.id)
        ).scalars()
    )
    citations = list(
        session.execute(
            select(CitationRecord).where(
                CitationRecord.retrieval_session_id == retrieval_session.id
            )
        ).scalars()
    )
    web_sources = list(
        session.execute(
            select(WebResearchSource).where(
                WebResearchSource.retrieval_session_id == retrieval_session.id
            )
        ).scalars()
    )
    if prompt_manifest is None:
        prompt_manifest = session.execute(
            select(PromptAssemblyManifest)
            .where(PromptAssemblyManifest.retrieval_session_id == retrieval_session.id)
            .limit(1)
        ).scalar_one_or_none()
    policy_audits = list(
        session.execute(
            select(KnowledgePolicyAudit).where(
                KnowledgePolicyAudit.retrieval_session_id == retrieval_session.id
            )
        ).scalars()
    )
    model_calls = list(
        session.execute(select(ModelCall).where(ModelCall.task_id == task.id)).scalars()
    )
    outcome_source = (
        prompt_manifest.metadata_json
        if prompt_manifest is not None and isinstance(prompt_manifest.metadata_json, dict)
        else retrieval_session.metadata_json
        if isinstance(retrieval_session.metadata_json, dict)
        else {}
    )
    grounding_provider = str(outcome_source.get("grounding_provider") or "none")
    fixture_grounded = bool(outcome_source.get("fixture_grounded") or False)
    verified_grounded = bool(outcome_source.get("verified_grounded") or False)
    grounding_verification_reason = str(
        outcome_source.get("grounding_verification_reason") or "no_verified_evidence"
    )

    if contract.get("require_grounded"):
        allow_fixture_grounding = bool(contract.get("allow_fixture_grounding") or False)
        grounded = bool(citations) and (
            verified_grounded or (allow_fixture_grounding and fixture_grounded)
        )
        if not grounded or not hits:
            failures.append("missing_grounded_hits_or_citations")
        elif prompt_manifest is not None:
            included_hit_ids = set(prompt_manifest.included_retrieval_hit_ids_json)
            citation_hit_ids = {citation.retrieval_hit_id for citation in citations}
            if not citation_hit_ids <= included_hit_ids:
                failures.append("citation_hits_not_in_prompt_manifest")
    if contract.get("require_insufficient") and retrieval_session.local_status != "insufficient":
        failures.append("missing_insufficient_status")
    if contract.get("require_prompt_manifest") and prompt_manifest is None:
        failures.append("missing_prompt_manifest")
    required_decisions = set(contract.get("require_policy_decisions") or [])
    actual_decisions = {audit.decision for audit in policy_audits}
    if not required_decisions <= actual_decisions:
        failures.append("missing_policy_decisions")

    actual_hit_ids = [hit.id for hit in hits]
    actual_citation_keys = [citation.citation_key for citation in citations]
    actual_citation_hit_ids = [citation.retrieval_hit_id for citation in citations]
    expected_hit_ids = _as_string_list(contract.get("hit_ids"))
    expected_citation_keys = _as_string_list(contract.get("citation_keys"))
    expected_hit_id_set = set(expected_hit_ids)
    if expected_hit_id_set and not expected_hit_id_set <= set(actual_hit_ids):
        failures.append("missing_required_evidence")
    if expected_citation_keys and not set(expected_citation_keys) <= set(actual_citation_keys):
        failures.append("citation_hit_mismatch")
    expected_citation_hit_ids = _as_string_list(contract.get("citation_hit_ids"))
    if expected_citation_hit_ids and not set(expected_citation_hit_ids) <= set(
        actual_citation_hit_ids
    ):
        failures.append("citation_hit_mismatch")
    if expected_hit_id_set:
        required_citation_hit_ids = {
            citation.retrieval_hit_id
            for citation in citations
            if not expected_citation_keys or citation.citation_key in expected_citation_keys
        }
        if not required_citation_hit_ids or not required_citation_hit_ids <= expected_hit_id_set:
            failures.append("citation_hit_mismatch")

    evidence_inputs = _grounding_evidence_inputs(
        hits=hits,
        prompt_manifest=prompt_manifest,
        citations=citations,
        policy_audits=policy_audits,
        model_calls=model_calls,
    )
    required_evidence_snippets = _as_string_list(contract.get("required_evidence_snippets"))
    missing_required_snippets = [
        snippet
        for snippet in required_evidence_snippets
        if not _snippet_in_inputs(snippet, evidence_inputs)
    ]
    if missing_required_snippets:
        failures.append("missing_required_evidence")

    forbidden_evidence_snippets = _as_string_list(contract.get("forbidden_evidence_snippets"))
    legacy_forbidden = _normalize_text(contract.get("forbid_text") or "")
    if legacy_forbidden:
        forbidden_evidence_snippets.append(legacy_forbidden)
    forbidden_leak_sources = _matched_input_sources(forbidden_evidence_snippets, evidence_inputs)
    forbidden_evidence_leaked = bool(forbidden_leak_sources)
    if forbidden_evidence_leaked:
        failures.append("forbidden_evidence_leaked")

    unsupported_markers = _as_string_list(contract.get("unsupported_markers"))
    unsupported_marker_sources = _matched_input_sources(
        unsupported_markers,
        {
            "citations": evidence_inputs.get("citations", ""),
            "prompt_manifest": evidence_inputs.get("prompt_manifest", ""),
            "policy_audits": evidence_inputs.get("policy_audits", ""),
        },
    )
    if unsupported_marker_sources:
        failures.append("unsupported_marker_present")

    fallback_expected = bool(contract.get("fallback_expected") or False)
    fallback_observed = _fallback_observed(retrieval_session, web_sources, outcome_source)
    if fallback_expected and not fallback_observed:
        failures.append("fallback_expected_but_not_observed")
    if fallback_observed and not fallback_expected and "fallback_expected" in contract:
        failures.append("fallback_observed_but_not_expected")

    return _grounding_trace_v1(
        grader="deterministic_grounding_grader_v1",
        passed=not failures,
        grounding_failures=_dedupe(failures),
        retrieval_session_id=retrieval_session.id,
        prompt_manifest_id=prompt_manifest.id if prompt_manifest else None,
        policy_audit_ids=[audit.id for audit in policy_audits],
        hit_ids=actual_hit_ids,
        citation_keys=actual_citation_keys,
        citation_hit_ids=actual_citation_hit_ids,
        required_evidence_snippets=required_evidence_snippets,
        forbidden_evidence_snippets=forbidden_evidence_snippets,
        forbidden_evidence_leaked=forbidden_evidence_leaked,
        forbidden_leak_sources=forbidden_leak_sources,
        fallback_expected=fallback_expected,
        fallback_observed=fallback_observed,
        fallback_reason=fallback_reason,
        unsupported_markers=unsupported_markers,
        inferred_fallback=inferred_fallback,
        grounding_provider=grounding_provider,
        fixture_grounded=fixture_grounded,
        verified_grounded=verified_grounded,
        grounding_verification_reason=grounding_verification_reason,
        hit_count=len(hits),
        citation_count=len(citations),
        web_source_count=len(web_sources),
    )


__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
