"""Agent Workspace context compression endpoint."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
from ._capability_helpers import *
from ._grounding_helpers import *
from ._knowledge_helpers import *
from ._plan_helpers import *
from ._session_helpers import *
from ._tool_helpers import *
from ._workspace_chat_helpers import *
from ._workspace_response_helpers import *

@router.post(
    "/{agent_id}/context/compress",
    response_model=WorkspaceContextCompressionResponse,
    summary="压缩 Workspace 对话上下文",
)
def compress_agent_workspace_context(
    agent_id: str,
    request: WorkspaceContextCompressionRequest,
    session: DbSession,
    principal: Principal,
) -> WorkspaceContextCompressionResponse:
    require_role(principal, {"admin", "engineer"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)

    now = utc_now()
    provider = _normalize_model_id(request.model_provider or "default")
    model = _normalize_model_id(request.model_name or "default")
    prior_provider = _normalize_model_id(request.compressor_provider or provider)
    prior_model = _normalize_model_id(request.compressor_model or model)
    pinned_ids = set(request.pinned_node_ids)
    eligible = [
        node
        for node in request.messages
        if node.role in {"user", "assistant", "system"}
        and node.id not in pinned_ids
        and node.content.strip()
    ]
    coverage_node_ids = [node.id for node in eligible]
    coverage_path_hash = _workspace_context_path_hash(eligible)
    pinned_path_hash = _workspace_context_path_hash(
        [
            node
            for node in request.messages
            if node.id in pinned_ids and node.role in {"user", "assistant", "system"}
        ]
    )
    estimated_original_tokens = _estimate_nodes_tokens(eligible)
    estimated_uncovered_tokens = _estimate_nodes_tokens(
        [
            node
            for node in request.messages
            if node.role in {"user", "assistant", "system"}
            and node.id not in set(coverage_node_ids)
            and node.content.strip()
        ]
    )
    cache_key_hash = _workspace_summary_cache_key_hash(
        organization_id=principal.organization_id,
        agent_id=agent_id,
        provider=provider,
        model=model,
        coverage_path_hash=coverage_path_hash,
        pinned_path_hash=pinned_path_hash,
    )

    validation_status: Literal["ok", "missing_raw_nodes", "hash_mismatch"] = "ok"
    if request.prior_coverage_node_ids:
        raw_ids = {node.id for node in request.messages}
        if any(node_id not in raw_ids for node_id in request.prior_coverage_node_ids):
            validation_status = "missing_raw_nodes"
        elif (
            request.prior_coverage_path_hash
            and request.prior_coverage_path_hash != coverage_path_hash
        ):
            validation_status = "hash_mismatch"
        elif request.summary_schema_version != SUMMARY_SCHEMA_VERSION:
            validation_status = "hash_mismatch"
        elif request.compression_prompt_version != COMPRESSION_PROMPT_VERSION:
            validation_status = "hash_mismatch"
        elif prior_provider != provider or prior_model != model:
            validation_status = "hash_mismatch"

    cached_summary = _workspace_summary_cache_lookup(
        session=session,
        organization_id=principal.organization_id,
        agent_id=agent_id,
        cache_key_hash=cache_key_hash,
        now=now,
    )
    if cached_summary is not None:
        payload = (
            cached_summary.payload_json
            if isinstance(cached_summary.payload_json, dict)
            else {}
        )
        cached_summary.hit_count += 1
        cached_summary.last_hit_at = now
        cached_summary.updated_at = now
        session.commit()
        summary = str(payload.get("summary") or "")
        return WorkspaceContextCompressionResponse(
            status="ok",
            cache_status="accepted",
            summary=summary,
            coverage_node_ids=coverage_node_ids,
            coverage_path_hash=coverage_path_hash,
            last_covered_node_id=coverage_node_ids[-1] if coverage_node_ids else None,
            summary_schema_version=SUMMARY_SCHEMA_VERSION,
            compression_prompt_version=COMPRESSION_PROMPT_VERSION,
            compressor_provider=provider,
            compressor_model=model,
            estimated_original_tokens=estimated_original_tokens,
            estimated_summary_tokens=int(payload.get("estimated_summary_tokens") or 0),
            estimated_uncovered_tokens=estimated_uncovered_tokens,
            created_at=cached_summary.created_at,
            updated_at=now,
            error=None,
        )

    if not eligible:
        return WorkspaceContextCompressionResponse(
            status="missing_raw_nodes",
            cache_status="error",
            summary="",
            coverage_node_ids=[],
            coverage_path_hash="",
            last_covered_node_id=None,
            summary_schema_version=SUMMARY_SCHEMA_VERSION,
            compression_prompt_version=COMPRESSION_PROMPT_VERSION,
            compressor_provider=provider,
            compressor_model=model,
            estimated_original_tokens=0,
            estimated_summary_tokens=0,
            estimated_uncovered_tokens=estimated_uncovered_tokens,
            created_at=now,
            updated_at=now,
            error="no eligible raw messages supplied for compression",
        )

    prompt = _workspace_compression_prompt(eligible)
    audit_task = _create_workspace_chat_run(
        agent_id=agent_id,
        goal="Compress workspace conversation context",
        session=session,
        principal=principal,
        mode="context_compression",
        model_provider=request.model_provider,
        model_name=request.model_name,
    )
    audit_task.status = "RUNNING"
    try:
        response = AuditedModelGateway(session=session, task_id=audit_task.id).complete(
            ModelRequest(
                model_provider=request.model_provider or "default",
                model_name=request.model_name or "default",
                response_format="text",
                messages=[
                    ModelMessage(
                        role="system",
                        content=(
                            "Summarize prior chat context for future assistant turns. "
                            "Preserve user goals, decisions, constraints, open questions, "
                            "named files, and important facts. Do not mention attachment "
                            "contents unless they appear in the supplied messages."
                        ),
                    ),
                    ModelMessage(role="user", content=prompt),
                ],
            )
        )
    except ModelGatewayError as exc:
        audit_task.status = "FAILED"
        audit_task.updated_at = utc_now()
        session.commit()
        return WorkspaceContextCompressionResponse(
            status="provider_error",
            cache_status="error",
            summary="",
            coverage_node_ids=coverage_node_ids,
            coverage_path_hash=coverage_path_hash,
            last_covered_node_id=coverage_node_ids[-1] if coverage_node_ids else None,
            summary_schema_version=SUMMARY_SCHEMA_VERSION,
            compression_prompt_version=COMPRESSION_PROMPT_VERSION,
            compressor_provider=provider,
            compressor_model=model,
            estimated_original_tokens=estimated_original_tokens,
            estimated_summary_tokens=0,
            estimated_uncovered_tokens=estimated_uncovered_tokens,
            created_at=now,
            updated_at=utc_now(),
            error=str(exc),
        )

    summary = response.content.strip()
    summary_tokens = max(1, len(summary) // 4) if summary else 0
    audit_task.status = "COMPLETED"
    audit_task.completed_at = utc_now()
    audit_task.updated_at = audit_task.completed_at
    session.commit()

    status: Literal["ok", "stale", "missing_raw_nodes", "hash_mismatch", "provider_error"]
    status = validation_status
    cache_status: Literal["accepted", "recomputed", "stale_rejected", "error"]
    cache_status = "recomputed" if validation_status == "ok" else "stale_rejected"
    _record_workspace_summary_cache(
        session=session,
        organization_id=principal.organization_id,
        agent_id=agent_id,
        cache_key_hash=cache_key_hash,
        summary=summary,
        coverage_node_ids=coverage_node_ids,
        coverage_path_hash=coverage_path_hash,
        pinned_path_hash=pinned_path_hash,
        provider=_normalize_model_id(response.model_provider or provider),
        model=_normalize_model_id(response.model_name or model),
        estimated_original_tokens=estimated_original_tokens,
        estimated_summary_tokens=summary_tokens,
        estimated_uncovered_tokens=estimated_uncovered_tokens,
        status=cache_status,
        now=utc_now(),
    )
    session.commit()
    return WorkspaceContextCompressionResponse(
        status=status,
        cache_status=cache_status,
        summary=summary,
        coverage_node_ids=coverage_node_ids,
        coverage_path_hash=coverage_path_hash,
        last_covered_node_id=coverage_node_ids[-1] if coverage_node_ids else None,
        summary_schema_version=SUMMARY_SCHEMA_VERSION,
        compression_prompt_version=COMPRESSION_PROMPT_VERSION,
        compressor_provider=_normalize_model_id(response.model_provider or provider),
        compressor_model=_normalize_model_id(response.model_name or model),
        estimated_original_tokens=estimated_original_tokens,
        estimated_summary_tokens=summary_tokens,
        estimated_uncovered_tokens=estimated_uncovered_tokens,
        created_at=now,
        updated_at=utc_now(),
        error=None,
    )
