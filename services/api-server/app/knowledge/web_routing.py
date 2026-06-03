"""Web research provider routing helpers for grounding fallback."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
from .chunking import *
from .retrieval_events import *
from .settings import *
import app.knowledge as knowledge_api


def _web_policy_limit(snapshot: dict, key: str, default: int) -> int:
    try:
        value = int(snapshot.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _configured_web_policy_limit(
    session: Session,
    *,
    organization_id: str | None,
    key: str,
    default: int,
) -> int:
    setting = _system_setting(session, POLICY_SETTINGS_KEY, organization_id)
    web = setting.get("web_research", {}) if isinstance(setting, dict) else {}
    if not isinstance(web, dict):
        return default
    try:
        value = int(web.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _web_provider_calls_used(
    session: Session,
    *,
    run_id: str | None,
    current_retrieval_session_id: str,
) -> int:
    if not run_id:
        return 0
    return len(
        list(
            session.execute(
                select(WebResearchAttempt.id).where(
                    WebResearchAttempt.run_id == run_id,
                    WebResearchAttempt.retrieval_session_id != current_retrieval_session_id,
                )
            ).scalars()
        )
    )


def _reserve_web_provider_call(
    session: Session,
    *,
    retrieval_session: RetrievalSession,
    provider: str,
    max_calls_per_run: int,
) -> WebResearchAttempt | None:
    if not retrieval_session.run_id:
        return None
    for slot in range(1, max_calls_per_run + 1):
        attempt = WebResearchAttempt(
            run_id=retrieval_session.run_id,
            retrieval_session_id=retrieval_session.id,
            organization_id=retrieval_session.organization_id,
            agent_id=retrieval_session.agent_id,
            provider=provider,
            call_slot=slot,
            status="RESERVED",
            metadata_json={"reservation": "web_research_call"},
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        try:
            with session.begin_nested():
                session.add(attempt)
                session.flush()
            return attempt
        except IntegrityError:
            continue
    return None


def _update_web_attempt(
    attempt: WebResearchAttempt | None,
    *,
    status: str,
    metadata: dict | None = None,
) -> None:
    if attempt is None:
        return
    attempt.status = status
    attempt.updated_at = utc_now()
    attempt.metadata_json = {
        **(attempt.metadata_json if isinstance(attempt.metadata_json, dict) else {}),
        **(metadata or {}),
    }


def _provider_metadata(result: WebResearchResult, *, policy_snapshot: dict) -> dict:
    return {
        "request_id": result.provider_request_id,
        "response_time_ms": result.response_time_ms,
        "usage_credits": result.usage_credits,
        "result_rank": result.rank,
        "result_score": result.score,
        "raw_content_available": result.raw_content_available,
        "policy_snapshot": policy_snapshot,
    }


def _safe_denied_web_source_ref(result: WebResearchResult, decision) -> str:
    if decision.normalized_url_sha256:
        return f"url_sha256:{decision.normalized_url_sha256}"
    return f"url_sha256:{_sha256(result.url)}"


def _persist_web_research_results(
    *,
    session: Session,
    retrieval_session: RetrievalSession,
    provider: str,
    results: list[WebResearchResult],
    max_content_bytes: int,
) -> tuple[list[WebResearchSource], list[KnowledgePolicyAudit], int]:
    engine = PolicyEngine(session)
    sources: list[WebResearchSource] = []
    audits: list[KnowledgePolicyAudit] = []
    seen_hashes: set[str] = set()
    denied_count = 0
    for result in results:
        decision = engine.evaluate_web_research_result(
            organization_id=retrieval_session.organization_id,
            provider=provider,
            url=result.url,
            seen_url_hashes=seen_hashes,
        )
        metadata = {
            "provider": provider,
            "url_sha256": _sha256(result.url),
            "normalized_url_sha256": decision.normalized_url_sha256,
            "normalized_hostname": decision.hostname,
            "policy_id": decision.policy_id,
            "policy_snapshot": decision.snapshot or {},
        }
        if (
            not decision.allowed
            or not decision.normalized_url
            or not decision.normalized_url_sha256
        ):
            denied_count += 1
            audits.append(
                _create_web_policy_audit(
                    session=session,
                    retrieval_session=retrieval_session,
                    decision=POLICY_DECISION_DENIED,
                    reason=decision.reason,
                    source_ref_id=_safe_denied_web_source_ref(result, decision),
                    metadata=metadata,
                )
            )
            continue
        seen_hashes.add(decision.normalized_url_sha256)
        snippet = result.snippet[:max_content_bytes]
        source = WebResearchSource(
            retrieval_session_id=retrieval_session.id,
            organization_id=retrieval_session.organization_id,
            agent_id=retrieval_session.agent_id,
            run_id=retrieval_session.run_id,
            url=decision.normalized_url,
            title=result.title or decision.normalized_url,
            content_sha256=_sha256(snippet),
            snippet=snippet,
            status="READY",
            error_message=None,
            metadata_json={
                "provider": provider,
                "fixture": provider == WEB_RESEARCH_PROVIDER_FAKE,
                "source_url_sha256": decision.normalized_url_sha256,
                **_provider_metadata(result, policy_snapshot=decision.snapshot or {}),
            },
            fetched_at=utc_now(),
        )
        session.add(source)
        session.flush()
        sources.append(source)
        audits.append(
            _create_web_policy_audit(
                session=session,
                retrieval_session=retrieval_session,
                decision=POLICY_DECISION_ALLOWED,
                reason=decision.reason,
                source_ref_id=source.id,
                metadata={
                    **metadata,
                    "web_source_id": source.id,
                    "status": "READY",
                },
            )
        )
    return sources, audits, denied_count


def _run_web_research_fallback(
    *,
    session: Session,
    retrieval_session: RetrievalSession,
    provider: str,
    query: str,
) -> tuple[list[WebResearchSource], list[KnowledgePolicyAudit], dict]:
    metadata: dict = {
        "web_research_provider": provider,
        "web_query_sha256": _sha256(query),
        "web_query_preview_redacted": redacted_query_preview(query),
        "web_research_timeout_seconds": DEFAULT_WEB_RESEARCH_TIMEOUT_SECONDS,
    }
    audits: list[KnowledgePolicyAudit] = []
    if provider == WEB_RESEARCH_PROVIDER_DISABLED:
        audits.append(
            _create_web_policy_audit(
                session=session,
                retrieval_session=retrieval_session,
                decision=POLICY_DECISION_DENIED,
                reason="web research provider is disabled",
                source_ref_id=None,
                metadata={**metadata, "policy_id": "web-research-provider-enabled"},
            )
        )
        return [], audits, metadata
    if provider == WEB_RESEARCH_PROVIDER_FAKE and not fake_web_research_allowed():
        metadata.update(
            {
                "web_research_attempt": True,
                "web_research_failed": True,
                "web_research_failure_reason": "fake provider is not allowed in this environment",
                "web_research_retryable": False,
            }
        )
        audits.append(
            _create_web_policy_audit(
                session=session,
                retrieval_session=retrieval_session,
                decision=POLICY_DECISION_DENIED,
                reason=str(metadata["web_research_failure_reason"]),
                source_ref_id=None,
                metadata={**metadata, "policy_id": "web-research-fake-environment"},
            )
        )
        return [], audits, metadata

    owner_user_id = _retrieval_owner_user_id(session, retrieval_session)
    api_key_present = (
        bool(
            knowledge_api.resolve_web_research_api_key(
                provider,
                session=session,
                organization_id=retrieval_session.organization_id,
                user_id=owner_user_id,
            )
        )
        or provider == WEB_RESEARCH_PROVIDER_FAKE
    )
    calls_used = _web_provider_calls_used(
        session,
        run_id=retrieval_session.run_id,
        current_retrieval_session_id=retrieval_session.id,
    )
    requested_max_results = min(
        DEFAULT_WEB_RESEARCH_MAX_RESULTS,
        _configured_web_policy_limit(
            session,
            organization_id=retrieval_session.organization_id,
            key="max_results",
            default=DEFAULT_WEB_RESEARCH_MAX_RESULTS,
        ),
    )
    requested_timeout_seconds = min(
        DEFAULT_WEB_RESEARCH_TIMEOUT_SECONDS,
        _configured_web_policy_limit(
            session,
            organization_id=retrieval_session.organization_id,
            key="timeout_seconds",
            default=DEFAULT_WEB_RESEARCH_TIMEOUT_SECONDS,
        ),
    )
    metadata["web_research_timeout_seconds"] = requested_timeout_seconds
    engine = PolicyEngine(session)
    pre_call = engine.evaluate_web_research_pre_call(
        organization_id=retrieval_session.organization_id,
        provider=provider,
        api_key_present=api_key_present,
        query=query,
        max_results=requested_max_results,
        timeout_seconds=requested_timeout_seconds,
        calls_used=calls_used,
        query_has_secret=query_has_secret_pattern(query),
    )
    metadata["web_pre_call_policy_snapshot"] = pre_call.snapshot or {}
    audits.append(
        _create_web_policy_audit(
            session=session,
            retrieval_session=retrieval_session,
            decision=POLICY_DECISION_ALLOWED if pre_call.allowed else POLICY_DECISION_DENIED,
            reason=pre_call.reason,
            source_ref_id=None,
            metadata={
                **metadata,
                "policy_id": pre_call.policy_id,
                "api_key_present": api_key_present,
                "calls_used": calls_used,
            },
        )
    )
    if not pre_call.allowed:
        metadata.update(
            {
                "web_research_attempt": True,
                "web_research_failed": True,
                "web_research_failure_reason": pre_call.reason,
                "web_research_retryable": False,
            }
        )
        return [], audits, metadata

    max_calls_per_run = _web_policy_limit(
        pre_call.snapshot or {},
        "max_calls_per_run",
        1,
    )
    attempt = _reserve_web_provider_call(
        session,
        retrieval_session=retrieval_session,
        provider=provider,
        max_calls_per_run=max_calls_per_run,
    )
    if retrieval_session.run_id and attempt is None:
        metadata.update(
            {
                "web_research_attempt": True,
                "web_research_failed": True,
                "web_research_failure_reason": (
                    "web research call limit is exhausted for this run"
                ),
                "web_research_retryable": False,
            }
        )
        audits.append(
            _create_web_policy_audit(
                session=session,
                retrieval_session=retrieval_session,
                decision=POLICY_DECISION_DENIED,
                reason=str(metadata["web_research_failure_reason"]),
                source_ref_id=None,
                metadata={
                    **metadata,
                    "policy_id": "web-research-call-limit",
                    "calls_used": max_calls_per_run,
                },
            )
        )
        return [], audits, metadata

    adapter = knowledge_api.get_web_research_adapter(
        provider,
        session=session,
        organization_id=retrieval_session.organization_id,
        user_id=owner_user_id,
    )
    if adapter is None:
        metadata.update(
            {
                "web_research_attempt": True,
                "web_research_failed": True,
                "web_research_failure_reason": "web research provider is unsupported",
                "web_research_retryable": False,
            }
        )
        audits.append(
            _create_web_policy_audit(
                session=session,
                retrieval_session=retrieval_session,
                decision=POLICY_DECISION_DENIED,
                reason=str(metadata["web_research_failure_reason"]),
                source_ref_id=None,
                metadata={**metadata, "policy_id": "web-research-provider-supported"},
            )
        )
        _update_web_attempt(attempt, status="PROVIDER_UNSUPPORTED", metadata=metadata)
        return [], audits, metadata

    metadata["web_research_attempt"] = True
    metadata["web_provider_call_attempted"] = True
    max_results = _web_policy_limit(
        pre_call.snapshot or {},
        "max_results",
        DEFAULT_WEB_RESEARCH_MAX_RESULTS,
    )
    max_content_bytes = _web_policy_limit(
        pre_call.snapshot or {},
        "max_content_bytes",
        DEFAULT_WEB_RESEARCH_MAX_CONTENT_BYTES,
    )
    try:
        results = adapter.search(
            query=query,
            max_results=max_results,
            timeout_seconds=requested_timeout_seconds,
            include_domains=list((pre_call.snapshot or {}).get("allow_domains") or []),
            exclude_domains=list((pre_call.snapshot or {}).get("deny_domains") or []),
        )
    except WebResearchProviderError as exc:
        metadata.update(
            {
                "web_research_failed": True,
                "web_research_failure_reason": str(exc),
                "web_research_retryable": exc.retryable,
            }
        )
        audits.append(
            _create_web_policy_audit(
                session=session,
                retrieval_session=retrieval_session,
                decision=POLICY_DECISION_DENIED,
                reason=str(exc),
                source_ref_id=None,
                metadata={**metadata, "policy_id": "web-research-provider-error"},
            )
        )
        _update_web_attempt(attempt, status="PROVIDER_ERROR", metadata=metadata)
        return [], audits, metadata

    sources, post_audits, denied_count = _persist_web_research_results(
        session=session,
        retrieval_session=retrieval_session,
        provider=provider,
        results=results,
        max_content_bytes=max_content_bytes,
    )
    audits.extend(post_audits)
    metadata.update(
        {
            "web_result_count": len(results),
            "web_source_count": len(sources),
            "web_result_denied_count": denied_count,
            "web_partial_results_warning": bool(sources and denied_count),
        }
    )
    if results and not sources:
        metadata.update(
            {
                "web_research_failed": True,
                "web_research_failure_reason": "all web research results were denied by policy",
                "web_research_retryable": False,
            }
        )
        _update_web_attempt(attempt, status="ALL_RESULTS_DENIED", metadata=metadata)
    else:
        _update_web_attempt(
            attempt,
            status="SUCCEEDED" if sources else "NO_RESULTS",
            metadata=metadata,
        )
    return sources, audits, metadata


def _retrieval_owner_user_id(
    session: Session,
    retrieval_session: RetrievalSession,
) -> str | None:
    if not retrieval_session.run_id:
        return None
    task = session.get(Task, retrieval_session.run_id)
    return task.created_by if task is not None else None


__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
