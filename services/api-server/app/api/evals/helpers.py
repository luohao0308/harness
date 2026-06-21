"""Shared Eval API persistence, response, and grounding helper functions."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *

def _get_dataset(dataset_id: str, session: Session, organization_id: str) -> EvalDataset:
    dataset = session.execute(
        select(EvalDataset).where(
            EvalDataset.id == dataset_id,
            EvalDataset.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval Dataset 未找到")
    return dataset


def _get_task(task_id: str, session: Session, organization_id: str) -> Task:
    task = session.execute(
        select(Task).where(Task.id == task_id, Task.organization_id == organization_id)
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run 未找到")
    return task


def _dataset_response(dataset: EvalDataset, *, case_count: int) -> EvalDatasetResponse:
    return EvalDatasetResponse(
        id=dataset.id,
        organization_id=dataset.organization_id,
        name=dataset.name,
        description=dataset.description,
        status=dataset.status,
        baseline_run_id=dataset.baseline_run_id,
        created_by=dataset.created_by,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
        case_count=case_count,
    )


def _case_counts(session: Session, dataset_ids: list[str]) -> dict[str, int]:
    if not dataset_ids:
        return {}
    rows = session.execute(
        select(EvalCase.dataset_id, func.count(EvalCase.id))
        .where(EvalCase.dataset_id.in_(dataset_ids))
        .group_by(EvalCase.dataset_id)
    ).all()
    return {dataset_id: count for dataset_id, count in rows}


def _grounding_selectors_for_run(session: Session, task: Task) -> dict:
    prompt_manifest = session.execute(
        select(PromptAssemblyManifest)
        .where(PromptAssemblyManifest.run_id == task.id)
        .order_by(PromptAssemblyManifest.created_at.desc(), PromptAssemblyManifest.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    retrieval_session = None
    if prompt_manifest is not None:
        retrieval_session = session.get(RetrievalSession, prompt_manifest.retrieval_session_id)
    if retrieval_session is None:
        retrieval_session = session.execute(
            select(RetrievalSession)
            .where(RetrievalSession.run_id == task.id)
            .order_by(RetrievalSession.created_at.desc(), RetrievalSession.id.desc())
            .limit(1)
        ).scalar_one_or_none()
    if retrieval_session is None:
        return {}
    if prompt_manifest is None:
        prompt_manifest = session.execute(
            select(PromptAssemblyManifest)
            .where(PromptAssemblyManifest.retrieval_session_id == retrieval_session.id)
            .order_by(PromptAssemblyManifest.created_at.desc(), PromptAssemblyManifest.id.desc())
            .limit(1)
        ).scalar_one_or_none()

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
    policy_audits = list(
        session.execute(
            select(KnowledgePolicyAudit).where(
                KnowledgePolicyAudit.retrieval_session_id == retrieval_session.id
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
    outcome_source = (
        prompt_manifest.metadata_json
        if prompt_manifest is not None and isinstance(prompt_manifest.metadata_json, dict)
        else retrieval_session.metadata_json
        if isinstance(retrieval_session.metadata_json, dict)
        else {}
    )
    citation_keys = _dedupe([citation.citation_key for citation in citations])
    citation_hit_ids = _dedupe([citation.retrieval_hit_id for citation in citations])
    retrieval_hit_ids = _dedupe([hit.id for hit in hits])
    selectors: dict[str, object] = {
        "retrieval_session_id": retrieval_session.id,
        "hit_ids": citation_hit_ids or retrieval_hit_ids,
        "citation_keys": citation_keys,
        "citation_hit_ids": citation_hit_ids,
        "fallback_expected": _fallback_observed(retrieval_session, web_sources, outcome_source),
        "require_grounded": bool(citations),
        "require_insufficient": retrieval_session.local_status != "sufficient",
        "allow_fixture_grounding": False,
    }
    if prompt_manifest is not None:
        selectors["prompt_manifest_id"] = prompt_manifest.id
        selectors["require_prompt_manifest"] = True
    policy_decisions = _dedupe([audit.decision for audit in policy_audits])
    if policy_decisions:
        selectors["require_policy_decisions"] = policy_decisions
    return selectors


def _merge_grounding_contract_selectors(existing: dict, selectors: dict) -> dict:
    merged = {**selectors, **existing}
    for key in ("hit_ids", "citation_keys", "citation_hit_ids", "require_policy_decisions"):
        if not _as_string_list(merged.get(key)) and _as_string_list(selectors.get(key)):
            merged[key] = selectors[key]
    for key in ("retrieval_session_id", "prompt_manifest_id"):
        if not merged.get(key) and selectors.get(key):
            merged[key] = selectors[key]
    for key in (
        "fallback_expected",
        "require_grounded",
        "require_prompt_manifest",
        "require_insufficient",
        "allow_fixture_grounding",
    ):
        if key not in existing and key in selectors:
            merged[key] = selectors[key]
    return merged


def _grounding_trace_v1(
    *,
    grader: str,
    passed: bool,
    grounding_failures: list[str] | None = None,
    retrieval_session_id: str | None = None,
    prompt_manifest_id: str | None = None,
    policy_audit_ids: list[str] | None = None,
    hit_ids: list[str] | None = None,
    citation_keys: list[str] | None = None,
    citation_hit_ids: list[str] | None = None,
    required_evidence_snippets: list[str] | None = None,
    forbidden_evidence_snippets: list[str] | None = None,
    forbidden_evidence_leaked: bool = False,
    forbidden_leak_sources: list[str] | None = None,
    fallback_expected: bool = False,
    fallback_observed: bool = False,
    fallback_reason: str | None = None,
    unsupported_markers: list[str] | None = None,
    claim_checks: list[dict] | None = None,
    **extra: object,
) -> dict:
    trace = {
        "grader_trace_schema_version": GROUNDING_TRACE_SCHEMA_VERSION,
        "grader": grader,
        "passed": passed,
        "grounding_failures": _dedupe(grounding_failures or []),
        "retrieval_session_id": retrieval_session_id,
        "prompt_manifest_id": prompt_manifest_id,
        "policy_audit_ids": policy_audit_ids or [],
        "hit_ids": hit_ids or [],
        "citation_keys": citation_keys or [],
        "citation_hit_ids": citation_hit_ids or [],
        "required_evidence_snippets": required_evidence_snippets or [],
        "forbidden_evidence_snippets": forbidden_evidence_snippets or [],
        "forbidden_evidence_leaked": forbidden_evidence_leaked,
        "forbidden_leak_sources": forbidden_leak_sources or [],
        "fallback_expected": fallback_expected,
        "fallback_observed": fallback_observed,
        "fallback_reason": fallback_reason,
        "unsupported_markers": unsupported_markers or [],
        "claim_checks": claim_checks or [],
    }
    trace.update(extra)
    return _normalize_grounding_trace(trace)


def _normalize_grounding_trace(trace: dict | None) -> dict:
    raw = trace if isinstance(trace, dict) else {}
    failures = _as_string_list(raw.get("grounding_failures"))
    forbidden_leak_sources = _as_string_list(raw.get("forbidden_leak_sources"))
    forbidden_evidence_leaked = bool(raw.get("forbidden_evidence_leaked")) or bool(
        forbidden_leak_sources
    )
    fallback_expected = bool(raw.get("fallback_expected") or False)
    fallback_observed = bool(raw.get("fallback_observed") or False)
    normalized = {
        **raw,
        "grader_trace_schema_version": int(raw.get("grader_trace_schema_version") or 0),
        "grader": str(raw.get("grader") or "deterministic_trace_grader_v1"),
        "passed": bool(raw.get("passed", True)),
        "grounding_failures": failures,
        "retrieval_session_id": _nullable_str(raw.get("retrieval_session_id")),
        "prompt_manifest_id": _nullable_str(raw.get("prompt_manifest_id")),
        "policy_audit_ids": _as_string_list(raw.get("policy_audit_ids")),
        "hit_ids": _as_string_list(raw.get("hit_ids")),
        "citation_keys": _as_string_list(raw.get("citation_keys")),
        "citation_hit_ids": _as_string_list(raw.get("citation_hit_ids")),
        "required_evidence_snippets": _as_string_list(raw.get("required_evidence_snippets")),
        "forbidden_evidence_snippets": _as_string_list(raw.get("forbidden_evidence_snippets")),
        "forbidden_evidence_leaked": forbidden_evidence_leaked,
        "forbidden_leak_sources": forbidden_leak_sources,
        "fallback_expected": fallback_expected,
        "fallback_observed": fallback_observed,
        "fallback_reason": _nullable_str(raw.get("fallback_reason")),
        "unsupported_markers": _as_string_list(raw.get("unsupported_markers")),
        "claim_checks": (
            raw.get("claim_checks") if isinstance(raw.get("claim_checks"), list) else []
        ),
    }
    if forbidden_evidence_leaked and "forbidden_evidence_leaked" not in failures:
        normalized["grounding_failures"] = [*failures, "forbidden_evidence_leaked"]
        normalized["passed"] = False
    return normalized


def _grounding_evidence_inputs(
    *,
    hits: list[RetrievalHit],
    prompt_manifest: PromptAssemblyManifest | None,
    citations: list[CitationRecord],
    policy_audits: list[KnowledgePolicyAudit],
    model_calls: list[ModelCall],
) -> dict[str, str]:
    prompt_payload = ""
    if prompt_manifest is not None:
        prompt_payload = _json_text(
            {
                "included_retrieval_hit_ids": prompt_manifest.included_retrieval_hit_ids_json,
                "omitted_candidates": prompt_manifest.omitted_candidates_json,
                "source_snapshots": prompt_manifest.source_snapshots_json,
                "prompt_sections": prompt_manifest.prompt_sections_json,
                "evidence_text_sha256": prompt_manifest.evidence_text_sha256,
                "metadata": prompt_manifest.metadata_json,
            }
        )
    return {
        "retrieval_hits": _json_text(
            [
                {
                    "id": hit.id,
                    "chunk_id": hit.chunk_id,
                    "web_source_id": hit.web_source_id,
                    "source_kind": hit.source_kind,
                    "snippet": hit.snippet,
                    "metadata": hit.metadata_json,
                }
                for hit in hits
            ]
        ),
        "prompt_manifest": prompt_payload,
        "citations": _json_text(
            [
                {
                    "id": citation.id,
                    "retrieval_hit_id": citation.retrieval_hit_id,
                    "citation_key": citation.citation_key,
                    "claim_text": citation.claim_text,
                    "quoted_text": citation.quoted_text,
                    "metadata": citation.metadata_json,
                }
                for citation in citations
            ]
        ),
        "policy_audits": _json_text(
            [
                {
                    "id": audit.id,
                    "decision": audit.decision,
                    "reason": audit.reason,
                    "source_kind": audit.source_kind,
                    "source_ref_id": audit.source_ref_id,
                    "safe_metadata": audit.safe_metadata_json,
                }
                for audit in policy_audits
            ]
        ),
        "model_call_binding_metadata": _json_text(
            [
                {
                    "id": model_call.id,
                    "prompt_manifest_id": model_call.prompt_manifest_id,
                    "context_manifest_id": model_call.context_manifest_id,
                    "grounding_correlation_id": model_call.grounding_correlation_id,
                    "model_request_sha256": model_call.model_request_sha256,
                    "request_message_hashes_json": model_call.request_message_hashes_json,
                    "request_message_hashes_sha256": model_call.request_message_hashes_sha256,
                    "hash_recomputability_status": model_call.hash_recomputability_status,
                }
                for model_call in model_calls
            ]
        ),
    }


def _fallback_observed(
    retrieval_session: RetrievalSession,
    web_sources: list[WebResearchSource],
    outcome_source: dict,
) -> bool:
    if retrieval_session.mode in {"web", "web_fallback", "fallback"}:
        return True
    if web_sources:
        return True
    if bool(outcome_source.get("web_fallback_observed") or outcome_source.get("fallback_observed")):
        return True
    return str(outcome_source.get("grounding_provider") or "").endswith("_web_fixture")


def _matched_input_sources(snippets: list[str], inputs: dict[str, str]) -> list[str]:
    sources: list[str] = []
    for source, payload in inputs.items():
        if any(_contains_snippet(payload, snippet) for snippet in snippets):
            sources.append(source)
    return sources


def _snippet_in_inputs(snippet: str, inputs: dict[str, str]) -> bool:
    return any(_contains_snippet(payload, snippet) for payload in inputs.values())


def _contains_snippet(payload: object, snippet: str) -> bool:
    normalized_snippet = _normalize_text(snippet)
    if not normalized_snippet:
        return False
    return normalized_snippet in _normalize_text(payload)


def _as_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [item for item in (_normalize_text(item) for item in value) if item]
    normalized = _normalize_text(value)
    return [normalized] if normalized else []


def _normalize_text(value: object) -> str:
    return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()


def _nullable_str(value: object) -> str | None:
    normalized = _normalize_text(value or "")
    return normalized or None


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))



def _latency_ms(task: Task | None) -> int:
    if task is None or task.completed_at is None:
        return 0
    return max(0, int((task.completed_at - task.created_at).total_seconds() * 1000))


def _tool_calls(session: Session, task_id: str) -> list[ToolCall]:
    return list(session.execute(select(ToolCall).where(ToolCall.task_id == task_id)).scalars())


def _model_calls(session: Session, task_id: str) -> list[ModelCall]:
    return list(session.execute(select(ModelCall).where(ModelCall.task_id == task_id)).scalars())


def _assignments(session: Session, task_id: str) -> list[AgentAssignment]:
    return list(
        session.execute(select(AgentAssignment).where(AgentAssignment.run_id == task_id)).scalars()
    )


def _eval_run_response(eval_run: EvalRun, results: list[EvalResult]) -> EvalRunResponse:
    return EvalRunResponse(
        id=eval_run.id,
        dataset_id=eval_run.dataset_id,
        organization_id=eval_run.organization_id,
        agent_id=eval_run.agent_id,
        status=eval_run.status,
        capability_snapshot_json=eval_run.capability_snapshot_json,
        metrics_json=eval_run.metrics_json,
        created_by=eval_run.created_by,
        started_at=eval_run.started_at,
        completed_at=eval_run.completed_at,
        created_at=eval_run.created_at,
        results=[_eval_result_response(result) for result in results],
    )


def _eval_case_response(eval_case: EvalCase) -> EvalCaseResponse:
    return EvalCaseResponse(
        id=eval_case.id,
        dataset_id=eval_case.dataset_id,
        source_task_id=eval_case.source_task_id,
        input_json=_scrub_forbidden_evidence_snippets(eval_case.input_json),
        expected_json=_scrub_forbidden_evidence_snippets(eval_case.expected_json),
        capability_snapshot_json=_scrub_forbidden_evidence_snippets(
            eval_case.capability_snapshot_json
        ),
        tags_json=eval_case.tags_json,
        created_at=eval_case.created_at,
    )


def _eval_result_response(result: EvalResult) -> EvalResultResponse:
    return EvalResultResponse(
        id=result.id,
        eval_run_id=result.eval_run_id,
        eval_case_id=result.eval_case_id,
        task_id=result.task_id,
        status=result.status,
        scores_json=result.scores_json,
        grader_trace_json=_scrub_forbidden_evidence_snippets(result.grader_trace_json),
        latency_ms=result.latency_ms,
        cost_usd=result.cost_usd,
        error_message=result.error_message,
        human_verdict=result.human_verdict,
        reviewer_id=result.reviewer_id,
        reviewed_at=result.reviewed_at,
        created_at=result.created_at,
    )


def _scrub_forbidden_evidence_snippets(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _scrub_forbidden_evidence_snippets(item)
            for key, item in value.items()
            if key not in {"forbidden_evidence_snippet", "forbidden_evidence_snippets"}
        }
    if isinstance(value, list):
        return [_scrub_forbidden_evidence_snippets(item) for item in value]
    return value


def _eval_run_capability_snapshot(
    *,
    session: Session,
    organization_id: str,
    agent_id: str | None,
) -> dict:
    if agent_id is None:
        return {}
    ensure_default_agents(session, organization_id)
    _registry, snapshot = CapabilityRegistry(session, organization_id).tool_registry_for_agent(
        agent_id
    )
    return snapshot


def _audit(
    session: Session,
    *,
    principal,
    event_type: EventType,
    resource_type: str,
    resource_id: str,
    action: str,
    payload: dict,
) -> None:
    session.add(
        AdminAuditEvent(
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
            event_type=event_type.value,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            payload_json=payload,
            created_at=utc_now(),
        )
    )

__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
