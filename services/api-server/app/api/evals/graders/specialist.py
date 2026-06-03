"""Specialist contract grader."""

# ruff: noqa: F401,F403,F405,I001,UP037
from ..common import *
from ..helpers import *
from .cost import _format_cost
from .helpers import *

def _grade_specialist_contract(
    session: Session,
    task: Task | None,
    expected_json: dict,
) -> dict:
    contract = expected_json.get("specialist_contract")
    if not isinstance(contract, dict):
        return {
            "configured": False,
            "passed": True,
            "failures": [],
            "outputs_by_specialist": {},
            "fanout_batches": [],
        }
    if task is None:
        return {
            "configured": True,
            "passed": False,
            "failures": ["missing_task"],
            "outputs_by_specialist": {},
            "fanout_batches": [],
        }
    rows = list(
        session.execute(
            select(SubagentOutput, AgentRun, SubagentSpecialist)
            .join(AgentRun, AgentRun.id == SubagentOutput.agent_run_id)
            .outerjoin(SubagentSpecialist, SubagentSpecialist.id == SubagentOutput.specialist_id)
            .where(SubagentOutput.task_id == task.id)
            .order_by(SubagentOutput.written_at.asc(), SubagentOutput.id.asc())
        ).all()
    )
    outputs_by_slug: dict[str, list[SubagentOutput]] = {}
    output_records: list[dict] = []
    total_cost = Decimal("0")
    total_runtime_ms = 0
    role_distribution: dict[str, int] = {}
    for output, run, specialist in rows:
        slug = (
            specialist.slug
            if specialist is not None
            else str(run.context_json.get("specialist_slug") or output.specialist_id or "unknown")
        )
        role = (
            specialist.role
            if specialist is not None
            else str(run.context_json.get("specialist_role") or "specialist")
        )
        outputs_by_slug.setdefault(slug, []).append(output)
        role_distribution[role] = role_distribution.get(role, 0) + 1
        budget = (
            output.budget_consumed_json
            if isinstance(output.budget_consumed_json, dict)
            else {}
        )
        try:
            total_cost += Decimal(str(budget.get("cost_usd") or "0"))
        except (InvalidOperation, ValueError):
            pass
        runtime_ms = _specialist_runtime_ms(run, budget)
        total_runtime_ms += runtime_ms
        output_records.append(
            {
                "output_id": output.id,
                "agent_run_id": run.id,
                "specialist_slug": slug,
                "specialist_role": role,
                "status": run.status,
                "fanout_batch_id": run.context_json.get("fanout_batch_id"),
                "fanout_index": run.context_json.get("fanout_index"),
                "fanout_total": run.context_json.get("fanout_total"),
                "runtime_ms": runtime_ms,
                "cost_usd": str(budget.get("cost_usd") or "0"),
            }
        )
    failures: list[str] = []
    for slug in _as_string_list(contract.get("expected_specialists")):
        if not outputs_by_slug.get(slug):
            failures.append(f"missing_specialist:{slug}")
    for slug in _as_string_list(contract.get("forbidden_specialists")):
        if outputs_by_slug.get(slug):
            failures.append(f"forbidden_specialist:{slug}")
    min_outputs = contract.get("min_outputs_per_specialist")
    if isinstance(min_outputs, dict):
        for slug, raw_min in min_outputs.items():
            if not isinstance(raw_min, int):
                continue
            actual = len(outputs_by_slug.get(str(slug), []))
            if actual < raw_min:
                failures.append(f"min_outputs_not_met:{slug}:{actual}<{raw_min}")
    max_outputs = contract.get("max_outputs_per_specialist")
    if isinstance(max_outputs, dict):
        for slug, raw_max in max_outputs.items():
            if not isinstance(raw_max, int):
                continue
            actual = len(outputs_by_slug.get(str(slug), []))
            if actual > raw_max:
                failures.append(f"max_outputs_exceeded:{slug}:{actual}>{raw_max}")
    output_assertions = contract.get("output_assertions")
    if isinstance(output_assertions, dict):
        for slug, assertions in output_assertions.items():
            slug_outputs = outputs_by_slug.get(str(slug), [])
            if not isinstance(assertions, list):
                continue
            for assertion in assertions:
                if not isinstance(assertion, dict):
                    continue
                failures.extend(
                    _specialist_output_assertion_failures(
                        slug=str(slug),
                        outputs=slug_outputs,
                        assertion=assertion,
                    )
                )
    budget_assertions = contract.get("budget_assertions")
    if isinstance(budget_assertions, dict):
        max_cost = budget_assertions.get("max_total_specialist_cost_usd")
        if max_cost is not None:
            try:
                max_cost_decimal = Decimal(str(max_cost))
                if total_cost > max_cost_decimal:
                    failures.append(
                        f"specialist_cost_exceeded:{_format_cost(total_cost)}>{max_cost_decimal}"
                    )
            except (InvalidOperation, ValueError):
                failures.append("invalid_max_total_specialist_cost_usd")
        max_runtime = budget_assertions.get("max_total_specialist_runtime_ms")
        if isinstance(max_runtime, int) and total_runtime_ms > max_runtime:
            failures.append(f"specialist_runtime_exceeded:{total_runtime_ms}>{max_runtime}")
    fanout_batches = _specialist_fanout_batches(rows)
    fanout_assertions = contract.get("fanout_assertions")
    if isinstance(fanout_assertions, dict):
        expected_count = fanout_assertions.get("expected_batch_count")
        if isinstance(expected_count, int) and len(fanout_batches) != expected_count:
            failures.append(f"fanout_batch_count:{len(fanout_batches)}!={expected_count}")
        min_batch_size = fanout_assertions.get("min_batch_size")
        if isinstance(min_batch_size, int):
            for batch in fanout_batches:
                if int(batch["size"]) < min_batch_size:
                    failures.append(
                        f"fanout_batch_too_small:{batch['fanout_batch_id']}:{batch['size']}<{min_batch_size}"
                    )
    outputs_by_specialist = {
        slug: len(outputs) for slug, outputs in sorted(outputs_by_slug.items())
    }
    return {
        "configured": True,
        "passed": not failures,
        "failures": failures,
        "outputs_by_specialist": outputs_by_specialist,
        "output_records": output_records,
        "total_specialist_invocations": len(rows),
        "total_specialist_cost_usd": _format_cost(total_cost),
        "total_specialist_runtime_ms": total_runtime_ms,
        "specialist_role_distribution": role_distribution,
        "fanout_batches": fanout_batches,
    }


def _specialist_output_assertion_failures(
    *,
    slug: str,
    outputs: list[SubagentOutput],
    assertion: dict,
) -> list[str]:
    field = assertion.get("field")
    if not isinstance(field, str) or not field:
        return [f"output_assertion_failed:{slug}.invalid_field"]
    values = [_nested_field(output.output_json, field) for output in outputs]
    if not values:
        return [f"output_assertion_failed:{slug}.{field}.missing_output"]
    failures: list[str] = []
    min_length = assertion.get("min_length")
    if isinstance(min_length, int):
        if not any(_value_length(value) >= min_length for value in values):
            actual = max((_value_length(value) for value in values), default=0)
            failures.append(
                f"output_assertion_failed:{slug}.{field}.min_length:{actual}<{min_length}"
            )
    max_length = assertion.get("max_length")
    if isinstance(max_length, int):
        if any(_value_length(value) > max_length for value in values):
            actual = max(_value_length(value) for value in values)
            failures.append(
                f"output_assertion_failed:{slug}.{field}.max_length:{actual}>{max_length}"
            )
    contains = _as_string_list(assertion.get("contains"))
    if contains:
        text_values = [_json_text(value) for value in values]
        for marker in contains:
            if not any(marker in text for text in text_values):
                failures.append(
                    f"output_assertion_failed:{slug}.{field}.contains:{_truncate_trace_value(marker)}"
                )
    if "equals" in assertion:
        expected = assertion.get("equals")
        if not any(value == expected for value in values):
            failures.append(f"output_assertion_failed:{slug}.{field}.equals")
    return failures


def _nested_field(payload: object, field: str) -> object:
    cursor = payload
    for part in field.split("."):
        if isinstance(cursor, dict) and part in cursor:
            cursor = cursor[part]
        else:
            return None
    return cursor


def _value_length(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, (str, list, tuple, set, dict)):
        return len(value)
    return len(str(value))


def _specialist_runtime_ms(run: AgentRun, budget: dict) -> int:
    runtime_seconds = budget.get("runtime_seconds")
    if isinstance(runtime_seconds, (int, float)):
        return max(0, int(float(runtime_seconds) * 1000))
    if run.started_at is None or run.completed_at is None:
        return 0
    end = run.completed_at
    if run.started_at.tzinfo is None and end.tzinfo is not None:
        end = end.replace(tzinfo=None)
    if run.started_at.tzinfo is not None and end.tzinfo is None:
        end = end.replace(tzinfo=run.started_at.tzinfo)
    return max(0, int((end - run.started_at).total_seconds() * 1000))


def _specialist_fanout_batches(
    rows: list[tuple[SubagentOutput, AgentRun, SubagentSpecialist | None]],
) -> list[dict]:
    grouped: dict[str, list[AgentRun]] = {}
    for _output, run, _specialist in rows:
        batch_id = run.context_json.get("fanout_batch_id")
        if isinstance(batch_id, str) and batch_id:
            grouped.setdefault(batch_id, []).append(run)
    batches: list[dict] = []
    for batch_id, runs in grouped.items():
        statuses: dict[str, int] = {}
        for run in runs:
            statuses[run.status] = statuses.get(run.status, 0) + 1
        first = runs[0]
        batches.append(
            {
                "fanout_batch_id": batch_id,
                "size": len(runs),
                "expected_total": first.context_json.get("fanout_total"),
                "aggregation": first.context_json.get("fanout_aggregation"),
                "statuses": statuses,
            }
        )
    return sorted(batches, key=lambda item: str(item["fanout_batch_id"]))



__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
