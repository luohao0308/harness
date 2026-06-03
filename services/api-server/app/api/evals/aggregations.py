"""Eval run metric aggregation helpers."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
from .helpers import *
from .graders.cost import _format_cost

def _aggregate_metrics(results: list[EvalResult]) -> dict:
    total = len(results) or 1
    traces = [_normalize_grounding_trace(result.grader_trace_json) for result in results]
    grounding_failures = [
        failure for trace in traces for failure in trace.get("grounding_failures", [])
    ]
    fallback_mismatches = [
        trace
        for trace in traces
        if bool(trace.get("fallback_expected")) != bool(trace.get("fallback_observed"))
    ]
    low_cost_guard_failures = [
        trace
        for trace in traces
        if trace.get("low_cost_route_used")
        and trace.get("passed")
        and not trace.get("low_cost_quality_guard_passed")
    ]
    tool_breakdown = _contract_failure_breakdown(results, "tool_contract")
    cost_breakdown = _cost_failure_breakdown(results)
    dialogue_breakdown = _contract_failure_breakdown(results, "dialogue_contract")
    refusal_breakdown = _contract_failure_breakdown(results, "refusal_contract")
    persona_breakdown = _contract_failure_breakdown(results, "persona_contract")
    specialist_breakdown = _contract_failure_breakdown(results, "specialist_contract")
    specialist_aggregate = _specialist_contract_aggregate(results)
    safety_aggregate = _safety_violation_aggregate(results)
    cost_aggregate = _cost_aggregate_from_results(results)
    passed_total = sum(1 for result in results if result.status == "PASSED")
    cost_per_passed = (
        cost_aggregate["total_cost_decimal"] / Decimal(passed_total)
        if passed_total
        else Decimal("0")
    )
    return {
        "task_success_rate": _avg(results, "task_success"),
        "tool_selection_accuracy": _avg(results, "tool_selection_accuracy"),
        "policy_violation_rate": _avg(results, "policy_violation"),
        "avg_latency_ms": int(sum(result.latency_ms for result in results) / total),
        "avg_cost_usd": _format_cost(cost_aggregate["total_cost_decimal"] / Decimal(total)),
        "total_cost_usd": _format_cost(cost_aggregate["total_cost_decimal"]),
        "total_prompt_tokens": cost_aggregate["total_prompt_tokens"],
        "total_completion_tokens": cost_aggregate["total_completion_tokens"],
        "cost_per_passed_case_usd": _format_cost(cost_per_passed),
        "retry_rate": _avg(results, "retry_count"),
        "human_escalation_rate": _avg(results, "human_escalation"),
        "case_total": len(results),
        "passed_total": passed_total,
        "failed_total": sum(1 for result in results if result.status == "FAILED"),
        "tool_contract_pass_rate": _contract_pass_rate(results, "tool_contract"),
        "tool_contract_configured_count": _contract_configured_count(results, "tool_contract"),
        "tool_contract_failure_breakdown": tool_breakdown,
        "dialogue_contract_pass_rate": _contract_pass_rate(results, "dialogue_contract"),
        "dialogue_contract_configured_count": _contract_configured_count(
            results, "dialogue_contract"
        ),
        "dialogue_contract_failure_breakdown": dialogue_breakdown,
        "cost_contract_pass_rate": _contract_pass_rate(results, "cost_contract"),
        "cost_contract_configured_count": _contract_configured_count(results, "cost_contract"),
        "cost_contract_failure_breakdown": cost_breakdown,
        "refusal_contract_pass_rate": _contract_pass_rate(results, "refusal_contract"),
        "refusal_contract_configured_count": _contract_configured_count(
            results, "refusal_contract"
        ),
        "refusal_contract_failure_breakdown": refusal_breakdown,
        "refusal_outcome_distribution": _refusal_outcome_distribution(results),
        "overrefusal_rate": _overrefusal_rate(results),
        "safety_contract_pass_rate": _contract_pass_rate(results, "safety_contract"),
        "safety_contract_configured_count": _contract_configured_count(
            results, "safety_contract"
        ),
        "safety_contract_failure_breakdown": _contract_failure_breakdown(
            results, "safety_contract"
        ),
        "safety_violation_total": safety_aggregate["total"],
        "safety_violation_breakdown": safety_aggregate["breakdown"],
        "persona_contract_pass_rate": _contract_pass_rate(results, "persona_contract"),
        "persona_contract_configured_count": _contract_configured_count(
            results, "persona_contract"
        ),
        "persona_contract_failure_breakdown": persona_breakdown,
        "role_drift_total": _role_drift_total(results),
        "specialist_contract_pass_rate": _contract_pass_rate(results, "specialist_contract"),
        "specialist_contract_configured_count": _contract_configured_count(
            results, "specialist_contract"
        ),
        "specialist_contract_failure_breakdown": specialist_breakdown,
        "total_specialist_invocations": specialist_aggregate["total_specialist_invocations"],
        "specialist_role_distribution": specialist_aggregate["specialist_role_distribution"],
        "total_specialist_cost_usd": specialist_aggregate["total_specialist_cost_usd"],
        "missing_pricing_models": sorted(cost_aggregate["missing_pricing_models"]),
        "grounding_pass_rate": round(
            sum(1 for trace in traces if bool(trace.get("passed"))) / total,
            4,
        ),
        "citation_coverage_rate": round(
            sum(1 for trace in traces if "citation_hit_mismatch" not in trace["grounding_failures"])
            / total,
            4,
        ),
        "unsupported_marker_rate": round(
            sum(
                1
                for trace in traces
                if "unsupported_marker_present" in trace["grounding_failures"]
            )
            / total,
            4,
        ),
        "fallback_mismatch_rate": round(len(fallback_mismatches) / total, 4),
        "forbidden_evidence_leak_rate": round(
            sum(1 for trace in traces if bool(trace.get("forbidden_evidence_leaked"))) / total,
            4,
        ),
        "required_evidence_miss_rate": round(
            sum(1 for trace in traces if "missing_required_evidence" in trace["grounding_failures"])
            / total,
            4,
        ),
        "low_cost_route_guard_failure_rate": round(len(low_cost_guard_failures) / total, 4),
        "low_cost_route_guard_failure_total": len(low_cost_guard_failures),
        "grounding_failure_total": len(grounding_failures),
    }


def _contract_pass_rate(results: list[EvalResult], contract_key: str) -> float:
    configured = [
        result
        for result in results
        if _trace_contract(result, contract_key).get("configured") is True
    ]
    if not configured:
        return 1.0
    passed = sum(
        1
        for result in configured
        if bool(_trace_contract(result, contract_key).get("passed"))
    )
    return round(passed / len(configured), 4)


def _contract_configured_count(results: list[EvalResult], contract_key: str) -> int:
    return sum(
        1
        for result in results
        if _trace_contract(result, contract_key).get("configured") is True
    )


def _contract_failure_breakdown(results: list[EvalResult], contract_key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        trace = _trace_contract(result, contract_key)
        if trace.get("configured") is not True:
            continue
        for failure in trace.get("failures") or []:
            label = str(failure).split(":", 1)[0]
            counts[label] = counts.get(label, 0) + 1
    return counts


def _refusal_outcome_distribution(results: list[EvalResult]) -> dict[str, int]:
    counts = {"refuse": 0, "answer": 0, "ambiguous": 0}
    for result in results:
        trace = _trace_contract(result, "refusal_contract")
        if trace.get("configured") is not True:
            continue
        outcome = str(trace.get("outcome") or "ambiguous")
        if outcome not in counts:
            outcome = "ambiguous"
        counts[outcome] += 1
    return counts


def _overrefusal_rate(results: list[EvalResult]) -> float:
    configured = [
        result
        for result in results
        if _trace_contract(result, "refusal_contract").get("configured") is True
    ]
    if not configured:
        return 0.0
    overrefused = 0
    for result in configured:
        failures = _trace_contract(result, "refusal_contract").get("failures") or []
        if any(str(failure).startswith("overrefusal_detected") for failure in failures):
            overrefused += 1
    return round(overrefused / len(configured), 4)


def _safety_violation_aggregate(results: list[EvalResult]) -> dict:
    breakdown: dict[str, int] = {}
    total = 0
    for result in results:
        trace = _trace_contract(result, "safety_contract")
        if trace.get("configured") is not True:
            continue
        total += int(trace.get("violation_total") or 0)
        violation_breakdown = trace.get("violation_breakdown")
        if not isinstance(violation_breakdown, dict):
            continue
        for kind, count in violation_breakdown.items():
            breakdown[str(kind)] = breakdown.get(str(kind), 0) + int(count or 0)
    return {"total": total, "breakdown": breakdown}


def _role_drift_total(results: list[EvalResult]) -> int:
    total = 0
    for result in results:
        trace = _trace_contract(result, "persona_contract")
        if trace.get("configured") is not True:
            continue
        total += int(trace.get("role_drift_count") or 0)
    return total


def _cost_failure_breakdown(results: list[EvalResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        trace = _trace_contract(result, "cost_contract")
        if trace.get("configured") is not True:
            continue
        for limit in trace.get("limit_exceeded") or []:
            counts[str(limit)] = counts.get(str(limit), 0) + 1
    return counts


def _specialist_contract_aggregate(results: list[EvalResult]) -> dict:
    total_invocations = 0
    total_cost = Decimal("0")
    role_distribution: dict[str, int] = {}
    for result in results:
        trace = _trace_contract(result, "specialist_contract")
        if trace.get("configured") is not True:
            continue
        total_invocations += int(trace.get("total_specialist_invocations") or 0)
        try:
            total_cost += Decimal(str(trace.get("total_specialist_cost_usd") or "0"))
        except (InvalidOperation, ValueError):
            pass
        raw_distribution = trace.get("specialist_role_distribution")
        if isinstance(raw_distribution, dict):
            for role, count in raw_distribution.items():
                role_distribution[str(role)] = role_distribution.get(str(role), 0) + int(
                    count or 0
                )
    return {
        "total_specialist_invocations": total_invocations,
        "specialist_role_distribution": role_distribution,
        "total_specialist_cost_usd": _format_cost(total_cost),
    }


def _cost_aggregate_from_results(results: list[EvalResult]) -> dict:
    total_cost = Decimal("0")
    prompt_total = 0
    completion_total = 0
    missing_pricing_models: set[str] = set()
    for result in results:
        trace = _trace_contract(result, "cost_contract")
        cost_value = trace.get("actual_cost_usd")
        if cost_value is None and result.cost_usd:
            cost_value = result.cost_usd
        try:
            total_cost += Decimal(str(cost_value or "0"))
        except (InvalidOperation, ValueError):
            pass
        prompt_total += int(trace.get("prompt_tokens") or 0)
        completion_total += int(trace.get("completion_tokens") or 0)
        for entry in trace.get("missing_pricing") or []:
            missing_pricing_models.add(str(entry))
    return {
        "total_cost_decimal": total_cost,
        "total_prompt_tokens": prompt_total,
        "total_completion_tokens": completion_total,
        "missing_pricing_models": missing_pricing_models,
    }


def _trace_contract(result: EvalResult, contract_key: str) -> dict:
    trace = result.grader_trace_json or {}
    if not isinstance(trace, dict):
        return {}
    contract = trace.get(contract_key)
    return contract if isinstance(contract, dict) else {}


def _avg(results: list[EvalResult], key: str) -> float:
    if not results:
        return 0.0
    return round(sum(float(result.scores_json.get(key, 0)) for result in results) / len(results), 4)


__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
