"""Run workspace token, model-call, and tool-call response helpers."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
from ._tool_helpers import *

def _workspace_token_optimization_response(
    *,
    context_manifest: ContextAssemblyManifest | None,
    model_calls: list[ModelCall],
) -> dict:
    token_budget = (
        context_manifest.token_budget_json
        if context_manifest is not None and isinstance(context_manifest.token_budget_json, dict)
        else {}
    )
    optimized_vs_baseline = token_budget.get("optimized_vs_baseline", {})
    if not isinstance(optimized_vs_baseline, dict):
        optimized_vs_baseline = {}
    retrieval_cache = token_budget.get("retrieval_cache", {})
    if not isinstance(retrieval_cache, dict):
        retrieval_cache = {}
    context_cache = token_budget.get("context_cache", {})
    if not isinstance(context_cache, dict):
        context_cache = {}
    actual_prompt_tokens = sum(int(call.prompt_tokens or 0) for call in model_calls)
    actual_completion_tokens = sum(int(call.completion_tokens or 0) for call in model_calls)
    low_cost_routes = [
        {
            "model_call_id": call.id,
            "model_name": call.model_name,
            "reason": reason,
        }
        for call in model_calls
        for reason in [_workspace_low_cost_route_reason(call)]
        if reason is not None
    ]
    included_refs = context_manifest.included_refs_json if context_manifest is not None else []
    omitted_refs = context_manifest.omitted_refs_json if context_manifest is not None else []
    return {
        "context_manifest_id": context_manifest.id if context_manifest is not None else None,
        "mode": context_manifest.mode if context_manifest is not None else None,
        "requested_max_tokens": token_budget.get("requested_max_tokens"),
        "estimated_candidate_tokens": token_budget.get("estimated_candidate_tokens", 0),
        "estimated_included_tokens": token_budget.get("estimated_included_tokens", 0),
        "estimated_omitted_tokens": token_budget.get("estimated_omitted_tokens", 0),
        "estimated_saved_tokens": optimized_vs_baseline.get("estimated_saved_tokens", 0),
        "estimated_savings_percent": optimized_vs_baseline.get("estimated_savings_percent", 0),
        "actual_prompt_tokens": actual_prompt_tokens,
        "actual_completion_tokens": actual_completion_tokens,
        "actual_total_tokens": actual_prompt_tokens + actual_completion_tokens,
        "included_count": len(included_refs or []),
        "omitted_count": len(omitted_refs or []),
        "pruning_applied": bool(token_budget.get("pruning_applied")),
        "retrieval_cache": retrieval_cache,
        "context_cache": context_cache,
        "low_cost_routes": low_cost_routes,
        "optimizer_capability_version_ids": token_budget.get(
            "optimizer_capability_version_ids", []
        ),
        "optimizer_policy_hash": token_budget.get("optimizer_policy_hash"),
        "optimizer_decisions": token_budget.get("optimizer_decisions", []),
        "effective_strategy": token_budget.get("effective_strategy", {}),
        "optimized_vs_baseline": optimized_vs_baseline,
    }


def _workspace_low_cost_route_reason(call: ModelCall) -> str | None:
    for payload in (call.request_json, call.response_json):
        if not isinstance(payload, dict):
            continue
        reason = payload.get("low_cost_routing_reason") or payload.get("model_routing_reason")
        if reason:
            return str(reason)
        if payload.get("low_cost_route") is True:
            return "low_cost_route"
    return None


def _model_call_response(
    model_call: ModelCall,
    *,
    trace_id: str | None,
) -> ModelCallResponse:
    return ModelCallResponse(
        id=model_call.id,
        task_id=model_call.task_id,
        agent_run_id=model_call.agent_run_id,
        trace_id=trace_id,
        model_provider=model_call.model_provider,
        model_name=model_call.model_name,
        status=model_call.status,
        prompt_tokens=model_call.prompt_tokens,
        completion_tokens=model_call.completion_tokens,
        duration_ms=model_call.duration_ms,
        grounding_correlation_id=model_call.grounding_correlation_id,
        prompt_manifest_id=model_call.prompt_manifest_id,
        context_manifest_id=model_call.context_manifest_id,
        capability_snapshot_json=model_call.capability_snapshot_json,
        model_request_sha256=model_call.model_request_sha256,
        model_request_hash_schema_version=model_call.model_request_hash_schema_version,
        request_message_hashes_json=model_call.request_message_hashes_json,
        request_message_hashes_sha256=model_call.request_message_hashes_sha256,
        hash_recomputability_status=model_call.hash_recomputability_status,
        attempt_index=model_call.attempt_index,
        terminal_status=model_call.terminal_status,
        request_json=model_call.request_json,
        response_json=model_call.response_json,
        error_message=model_call.error_message,
        created_at=model_call.created_at,
    )


def _tool_call_response(
    tool_call: ToolCall,
    *,
    trace_id: str | None,
) -> ToolCallResponse:
    output = tool_call.output_json if isinstance(tool_call.output_json, dict) else {}
    return ToolCallResponse(
        id=tool_call.id,
        task_id=tool_call.task_id,
        agent_run_id=tool_call.agent_run_id,
        trace_id=trace_id,
        tool_name=tool_call.tool_name,
        status=tool_call.status,
        risk_level=tool_call.risk_level,
        capability_id=tool_call.capability_id,
        capability_version_id=tool_call.capability_version_id,
        capability_type=tool_call.capability_type,
        capability_content_sha256=tool_call.capability_content_sha256,
        capability_config_sha256=tool_call.capability_config_sha256,
        capability_schema_version=tool_call.capability_schema_version,
        capability_snapshot_json=tool_call.capability_snapshot_json,
        requires_sandbox=tool_call.requires_sandbox,
        sandbox_id=tool_call.sandbox_id,
        duration_ms=tool_call.duration_ms,
        input_json=tool_call.input_json,
        output_json=tool_call.output_json,
        output_kind=_tool_output_kind(tool_call, output),
        output_summary=_tool_output_summary(tool_call, output),
        timeout_category="tool_timeout" if tool_call.status == "TIMEOUT" else None,
        error_message=tool_call.error_message,
        created_at=tool_call.created_at,
    )


def _subagent_response(agent_run: AgentRun) -> SubagentResponse:
    return SubagentResponse(
        id=agent_run.id,
        task_id=agent_run.task_id,
        parent_agent_id=agent_run.parent_agent_id,
        agent_type=agent_run.agent_type,
        status=agent_run.status,
        specialist_id=agent_run.specialist_id,
        fanout_batch_id=_subagent_context_string(agent_run, "fanout_batch_id"),
        fanout_index=_subagent_context_int(agent_run, "fanout_index"),
        fanout_total=_subagent_context_int(agent_run, "fanout_total"),
        dynamic_fanout_origin=_subagent_context_string(agent_run, "dynamic_fanout_origin"),
        dynamic_fanout_requested_by=_subagent_context_string(
            agent_run,
            "dynamic_fanout_requested_by",
        ),
        dynamic_fanout_reason=_subagent_context_string(agent_run, "dynamic_fanout_reason"),
        context_json=agent_run.context_json,
        started_at=agent_run.started_at,
        completed_at=agent_run.completed_at,
        timeout_at=agent_run.timeout_at,
        specialist=(
            SubagentSpecialistSummary.model_validate(agent_run.specialist)
            if agent_run.specialist is not None
            else None
        ),
        output=(
            SubagentOutputResponse.model_validate(agent_run.subagent_output)
            if agent_run.subagent_output is not None
            else None
        ),
    )


def _subagent_context_string(agent_run: AgentRun, key: str) -> str | None:
    value = agent_run.context_json.get(key)
    return str(value) if value is not None else None


def _subagent_context_int(agent_run: AgentRun, key: str) -> int | None:
    value = agent_run.context_json.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
