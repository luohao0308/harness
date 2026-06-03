from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from jsonschema import Draft7Validator, SchemaError, ValidationError
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    AgentEvent,
    AgentRun,
    ModelCall,
    SubagentOutput,
    SubagentSpecialist,
    ToolCall,
    utc_now,
)
from app.events.event_types import EventType

MAX_OUTPUT_SCHEMA_BYTES = 4096
MAX_SPECIALIST_DEPTH = 3
MIN_RANKING_INVOCATIONS = 10
DEFAULT_SPECIALIST_BUDGET = {
    "max_runtime_seconds": 900,
    "max_tokens": 12000,
    "max_tool_calls": 12,
    "max_cost_usd": 0,
}


DEFAULT_SYSTEM_SPECIALISTS: list[dict[str, Any]] = [
    {
        "id": "system-specialist-code-reviewer",
        "slug": "code-reviewer",
        "display_name": "代码审查专家",
        "description": "Review patches, files, and implementation risks with structured findings.",
        "role": "reviewer",
        "system_prompt": (
            "You are a code-reviewer specialist. Review only the assigned scope. "
            "Return JSON matching the output schema."
        ),
        "capability_slugs_json": ["read_file", "list_files", "git_command", "run_tests"],
        "output_schema_json": {
            "type": "object",
            "required": ["issues", "summary"],
            "properties": {
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["severity", "message"],
                        "properties": {
                            "severity": {
                                "type": "string",
                                "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                            },
                            "file": {"type": "string"},
                            "line": {"type": "integer"},
                            "message": {"type": "string"},
                        },
                    },
                },
                "summary": {"type": "string"},
            },
        },
        "budget_json": {
            "max_runtime_seconds": 900,
            "max_tokens": 12000,
            "max_tool_calls": 12,
            "max_cost_usd": 0.2,
        },
        "trigger_keywords_json": ["review", "code review", "diff", "patch", "风险", "审查"],
    },
    {
        "id": "system-specialist-researcher",
        "slug": "researcher",
        "display_name": "资料研究专家",
        "description": "Collect source-backed information and produce citations.",
        "role": "researcher",
        "system_prompt": (
            "You are a researcher specialist. Gather relevant evidence and cite sources. "
            "Return JSON matching the output schema."
        ),
        "capability_slugs_json": ["read_file", "list_files", "network_request"],
        "output_schema_json": {
            "type": "object",
            "required": ["citations", "answer"],
            "properties": {
                "citations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["url", "title", "snippet"],
                        "properties": {
                            "url": {"type": "string"},
                            "title": {"type": "string"},
                            "snippet": {"type": "string"},
                        },
                    },
                },
                "answer": {"type": "string"},
            },
        },
        "budget_json": {
            "max_runtime_seconds": 900,
            "max_tokens": 16000,
            "max_tool_calls": 16,
            "max_cost_usd": 0.25,
        },
        "trigger_keywords_json": ["research", "资料", "citation", "source", "引用", "调研"],
    },
    {
        "id": "system-specialist-safety-checker",
        "slug": "safety-checker",
        "display_name": "安全检查专家",
        "description": "Check outputs and plans for safety, policy, and release blockers.",
        "role": "checker",
        "system_prompt": (
            "You are a safety-checker specialist. Identify policy, safety, and release risks. "
            "Return JSON matching the output schema."
        ),
        "capability_slugs_json": ["read_file", "list_files"],
        "output_schema_json": {
            "type": "object",
            "required": ["passed", "violations", "recommendations"],
            "properties": {
                "passed": {"type": "boolean"},
                "violations": {"type": "array", "items": {"type": "string"}},
                "recommendations": {"type": "array", "items": {"type": "string"}},
            },
        },
        "budget_json": {
            "max_runtime_seconds": 600,
            "max_tokens": 8000,
            "max_tool_calls": 8,
            "max_cost_usd": 0.15,
        },
        "trigger_keywords_json": ["safety", "policy", "风险", "安全", "合规", "guardrail"],
    },
    {
        "id": "system-specialist-synthesizer",
        "slug": "synthesizer",
        "display_name": "综合归纳专家",
        "description": "Aggregate sub-results into concise summaries and key points.",
        "role": "synthesizer",
        "system_prompt": (
            "You are a synthesizer specialist. Merge evidence into a concise summary. "
            "Return JSON matching the output schema."
        ),
        "capability_slugs_json": ["read_file", "list_files"],
        "output_schema_json": {
            "type": "object",
            "required": ["summary", "key_points", "confidence"],
            "properties": {
                "summary": {"type": "string"},
                "key_points": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            },
        },
        "budget_json": {
            "max_runtime_seconds": 600,
            "max_tokens": 10000,
            "max_tool_calls": 6,
            "max_cost_usd": 0.15,
        },
        "trigger_keywords_json": ["synthesize", "summary", "summarize", "归纳", "汇总", "总结"],
    },
]


class SpecialistValidationError(ValueError):
    pass


class SubagentDepthExceededError(RuntimeError):
    pass


@dataclass(frozen=True)
class SpecialistBudgetState:
    consumed: dict[str, int | float]
    exceeded: list[str]


@dataclass(frozen=True)
class SubagentSpecialistStats:
    specialist_id: str
    slug: str
    window: str
    total_invocations: int
    success_count: int
    failed_count: int
    budget_exceeded_count: int
    depth_rejected_count: int
    success_rate: float | None
    avg_runtime_ms: int | None
    p95_runtime_ms: int | None
    avg_cost_usd: str
    total_cost_usd: str
    avg_tool_calls: float
    avg_output_size_bytes: int
    recent_failure_reasons: list[dict[str, int | str]]


class SubagentSpecialistRegistry:
    def __init__(self, session: Session, organization_id: str | None) -> None:
        self.session = session
        self.organization_id = organization_id

    def list(self, *, include_archived: bool = False) -> list[SubagentSpecialist]:
        statement = (
            select(SubagentSpecialist)
            .where(
                or_(
                    SubagentSpecialist.visibility == "system",
                    SubagentSpecialist.organization_id == self.organization_id,
                )
            )
            .order_by(
                SubagentSpecialist.visibility.asc(),
                SubagentSpecialist.slug.asc(),
                SubagentSpecialist.id.asc(),
            )
        )
        if not include_archived:
            statement = statement.where(SubagentSpecialist.status == "ACTIVE")
        return list(self.session.execute(statement).scalars())

    def get(self, specialist_id: str) -> SubagentSpecialist | None:
        return self.session.execute(
            select(SubagentSpecialist).where(
                SubagentSpecialist.id == specialist_id,
                or_(
                    SubagentSpecialist.visibility == "system",
                    SubagentSpecialist.organization_id == self.organization_id,
                ),
            )
        ).scalar_one_or_none()

    def get_by_slug(self, slug: str) -> SubagentSpecialist | None:
        candidates = list(
            self.session.execute(
                select(SubagentSpecialist)
                .where(
                    SubagentSpecialist.slug == slug,
                    SubagentSpecialist.status == "ACTIVE",
                    or_(
                        SubagentSpecialist.visibility == "system",
                        SubagentSpecialist.organization_id == self.organization_id,
                    ),
                )
                .order_by(
                    SubagentSpecialist.organization_id.desc().nullslast(),
                    SubagentSpecialist.visibility.asc(),
                    SubagentSpecialist.id.asc(),
                )
            ).scalars()
        )
        org_match = [
            specialist
            for specialist in candidates
            if specialist.organization_id == self.organization_id
        ]
        return (org_match or candidates)[0] if candidates else None

    def match_by_keywords(self, text: str) -> SubagentSpecialist | None:
        ranked, _reason = self.match_by_keywords_with_trace(text)
        return ranked

    def match_by_keywords_with_trace(self, text: str) -> tuple[SubagentSpecialist | None, dict]:
        normalized = text.casefold()
        if not normalized.strip():
            return None, {"resolved_by": "no_match", "candidate_slugs": []}
        candidates: list[SubagentSpecialist] = []
        for specialist in self.list():
            keywords = _string_list(specialist.trigger_keywords_json)
            if any(keyword.casefold() in normalized for keyword in keywords):
                candidates.append(specialist)
        if not candidates:
            return None, {"resolved_by": "no_match", "candidate_slugs": []}
        if len(candidates) == 1:
            return candidates[0], {
                "resolved_by": "keyword_match_only",
                "candidate_slugs": [candidates[0].slug],
                "selected_slug": candidates[0].slug,
            }
        selected, trace = select_specialist_by_ranking(
            candidates,
            lambda specialist_id: compute_specialist_stats(
                self.session,
                specialist_id,
                "7d",
            ),
        )
        return selected, trace

    def validate_output(self, specialist: SubagentSpecialist, output: dict) -> None:
        validate_output_schema(specialist.output_schema_json)
        try:
            Draft7Validator(specialist.output_schema_json).validate(output)
        except ValidationError as exc:
            path = ".".join(str(item) for item in exc.path)
            suffix = f" at {path}" if path else ""
            raise SpecialistValidationError(
                f"output_schema_violation{suffix}: {exc.message}"
            ) from exc


def ensure_system_specialists(session: Session) -> None:
    existing_ids = {
        specialist_id
        for specialist_id in session.execute(
            select(SubagentSpecialist.id).where(SubagentSpecialist.visibility == "system")
        ).scalars()
    }
    for payload in DEFAULT_SYSTEM_SPECIALISTS:
        if payload["id"] in existing_ids:
            continue
        session.add(
            SubagentSpecialist(
                organization_id=None,
                visibility="system",
                status="ACTIVE",
                created_by=None,
                **payload,
            )
        )
    session.flush()


def validate_output_schema(schema: dict) -> None:
    if not isinstance(schema, dict):
        raise SpecialistValidationError("output_schema_json must be an object")
    encoded = json.dumps(schema, ensure_ascii=False, sort_keys=True).encode("utf-8")
    if len(encoded) > MAX_OUTPUT_SCHEMA_BYTES:
        raise SpecialistValidationError(
            f"output_schema_json must be at most {MAX_OUTPUT_SCHEMA_BYTES} bytes"
        )
    try:
        Draft7Validator.check_schema(schema)
    except SchemaError as exc:
        raise SpecialistValidationError(f"invalid output_schema_json: {exc.message}") from exc


def output_schema_sha256(schema: dict) -> str:
    encoded = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def normalize_budget(raw_budget: dict | None) -> dict:
    raw = raw_budget if isinstance(raw_budget, dict) else {}
    budget = dict(DEFAULT_SPECIALIST_BUDGET)
    for key in ("max_runtime_seconds", "max_tokens", "max_tool_calls"):
        value = raw.get(key)
        if value is None:
            continue
        try:
            budget[key] = max(0, int(value))
        except (TypeError, ValueError):
            raise SpecialistValidationError(f"{key} must be an integer") from None
    raw_cost = raw.get("max_cost_usd")
    if raw_cost is not None:
        try:
            budget["max_cost_usd"] = float(Decimal(str(raw_cost)))
        except (InvalidOperation, ValueError):
            raise SpecialistValidationError("max_cost_usd must be numeric") from None
    return budget


def budget_state_for_run(session: Session, agent_run: AgentRun) -> SpecialistBudgetState:
    consumed = budget_consumed_for_run(session, agent_run)
    exceeded = budget_exceeded(consumed, agent_run.context_json.get("budget"))
    return SpecialistBudgetState(consumed=consumed, exceeded=exceeded)


def budget_consumed_for_run(session: Session, agent_run: AgentRun) -> dict[str, int | float]:
    model_calls = list(
        session.execute(select(ModelCall).where(ModelCall.agent_run_id == agent_run.id)).scalars()
    )
    tool_calls = list(
        session.execute(select(ToolCall).where(ToolCall.agent_run_id == agent_run.id)).scalars()
    )
    runtime_seconds = 0.0
    if agent_run.started_at is not None:
        end = agent_run.completed_at or utc_now()
        if agent_run.started_at.tzinfo is None and end.tzinfo is not None:
            end = end.replace(tzinfo=None)
        if agent_run.started_at.tzinfo is not None and end.tzinfo is None:
            end = end.replace(tzinfo=agent_run.started_at.tzinfo)
        if end is not None:
            runtime_seconds = max(0.0, (end - agent_run.started_at).total_seconds())
    return {
        "runtime_seconds": runtime_seconds,
        "prompt_tokens": sum(max(0, int(call.prompt_tokens or 0)) for call in model_calls),
        "completion_tokens": sum(
            max(0, int(call.completion_tokens or 0)) for call in model_calls
        ),
        "tool_calls": len(tool_calls),
        "cost_usd": _cost_from_model_calls(model_calls),
    }


def budget_exceeded(consumed: dict[str, Any], raw_budget: dict | None) -> list[str]:
    budget = normalize_budget(raw_budget)
    exceeded: list[str] = []
    runtime = float(consumed.get("runtime_seconds") or 0)
    total_tokens = int(consumed.get("prompt_tokens") or 0) + int(
        consumed.get("completion_tokens") or 0
    )
    tool_calls = int(consumed.get("tool_calls") or 0)
    cost_usd = float(consumed.get("cost_usd") or 0)
    if budget["max_runtime_seconds"] and runtime > float(budget["max_runtime_seconds"]):
        exceeded.append("max_runtime_seconds")
    if budget["max_tokens"] and total_tokens > int(budget["max_tokens"]):
        exceeded.append("max_tokens")
    if budget["max_tool_calls"] and tool_calls > int(budget["max_tool_calls"]):
        exceeded.append("max_tool_calls")
    if budget["max_cost_usd"] and cost_usd > float(budget["max_cost_usd"]):
        exceeded.append("max_cost_usd")
    return exceeded


def make_default_output(*, specialist: SubagentSpecialist, summary: str) -> dict:
    role = specialist.role
    slug = specialist.slug
    if slug == "code-reviewer" or role == "reviewer":
        return {"issues": [], "summary": summary}
    if slug == "researcher" or role == "researcher":
        return {"citations": [], "answer": summary}
    if slug == "safety-checker" or role == "checker":
        return {"passed": True, "violations": [], "recommendations": [summary]}
    if slug == "synthesizer" or role == "synthesizer":
        return {"summary": summary, "key_points": [summary], "confidence": "medium"}
    return _default_output_from_schema(specialist.output_schema_json, summary)


def collect_subagent_outputs(session: Session, task_id: str) -> list[dict]:
    rows = list(
        session.execute(
            select(SubagentOutput, SubagentSpecialist)
            .outerjoin(SubagentSpecialist, SubagentSpecialist.id == SubagentOutput.specialist_id)
            .where(SubagentOutput.task_id == task_id)
            .order_by(SubagentOutput.written_at.asc(), SubagentOutput.id.asc())
        ).all()
    )
    return [
        {
            "id": output.id,
            "agent_run_id": output.agent_run_id,
            "task_id": output.task_id,
            "specialist_id": output.specialist_id,
            "specialist_slug": specialist.slug if specialist is not None else None,
            "specialist_role": specialist.role if specialist is not None else None,
            "fanout_batch_id": output.agent_run.context_json.get("fanout_batch_id")
            if output.agent_run is not None
            else None,
            "fanout_index": output.agent_run.context_json.get("fanout_index")
            if output.agent_run is not None
            else None,
            "fanout_total": output.agent_run.context_json.get("fanout_total")
            if output.agent_run is not None
            else None,
            "output_json": output.output_json,
            "budget_consumed_json": output.budget_consumed_json,
            "budget_exceeded_json": output.budget_exceeded_json,
            "written_at": output.written_at.isoformat() if output.written_at else None,
        }
        for output, specialist in rows
    ]


def compute_specialist_stats(
    session: Session,
    specialist_id: str,
    window: str = "30d",
) -> SubagentSpecialistStats:
    specialist = session.get(SubagentSpecialist, specialist_id)
    if specialist is None:
        raise SpecialistValidationError("specialist not found")
    since = _window_since(window)
    filters = [
        AgentRun.agent_type == "subagent",
        AgentRun.specialist_id == specialist_id,
    ]
    if since is not None:
        filters.append(_agent_run_activity_at() >= since)
    runs = list(
        session.execute(
            select(AgentRun)
            .where(and_(*filters))
            .order_by(_agent_run_activity_at().desc(), AgentRun.id.desc())
        ).scalars()
    )
    total = len(runs)
    success_count = sum(1 for run in runs if run.status == "SUCCESS")
    failed_count = sum(1 for run in runs if run.status in {"FAILED", "TIMEOUT", "CANCELLED"})
    depth_rejected_count = _depth_rejected_count(session, specialist_id, since)
    runtimes = [_runtime_ms(run) for run in runs if _runtime_ms(run) is not None]
    outputs = [run.subagent_output for run in runs if run.subagent_output is not None]
    total_cost = Decimal("0")
    total_tool_calls = 0
    budget_exceeded_count = 0
    output_sizes: list[int] = []
    for output in outputs:
        budget = (
            output.budget_consumed_json
            if isinstance(output.budget_consumed_json, dict)
            else {}
        )
        try:
            total_cost += Decimal(str(budget.get("cost_usd") or "0"))
        except (InvalidOperation, ValueError):
            pass
        total_tool_calls += int(budget.get("tool_calls") or 0)
        if output.budget_exceeded_json:
            budget_exceeded_count += 1
        output_sizes.append(
            len(json.dumps(output.output_json or {}, ensure_ascii=False, default=str).encode())
        )
    failure_reasons: dict[str, int] = {}
    for run in runs:
        if run.status not in {"FAILED", "TIMEOUT", "CANCELLED"}:
            continue
        reason = run.context_json.get("failure_reason")
        if not isinstance(reason, str) or not reason:
            reason = run.status.lower()
        failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
    recent_failure_reasons = [
        {"reason": reason, "count": count}
        for reason, count in sorted(
            failure_reasons.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:10]
    ]
    return SubagentSpecialistStats(
        specialist_id=specialist.id,
        slug=specialist.slug,
        window=window,
        total_invocations=total,
        success_count=success_count,
        failed_count=failed_count,
        budget_exceeded_count=budget_exceeded_count,
        depth_rejected_count=depth_rejected_count,
        success_rate=round(success_count / total, 3) if total else None,
        avg_runtime_ms=int(sum(runtimes) / len(runtimes)) if runtimes else None,
        p95_runtime_ms=_percentile_95(runtimes),
        avg_cost_usd=_format_cost(total_cost / Decimal(len(outputs))) if outputs else "0",
        total_cost_usd=_format_cost(total_cost),
        avg_tool_calls=round(total_tool_calls / len(outputs), 2) if outputs else 0.0,
        avg_output_size_bytes=int(sum(output_sizes) / len(output_sizes)) if output_sizes else 0,
        recent_failure_reasons=recent_failure_reasons,
    )


def select_specialist_by_ranking(
    candidates: list[SubagentSpecialist],
    stats_lookup,
) -> tuple[SubagentSpecialist, dict]:
    stats_by_id: dict[str, SubagentSpecialistStats] = {}
    eligible: list[tuple[SubagentSpecialist, SubagentSpecialistStats]] = []
    for specialist in candidates:
        stats = stats_lookup(specialist.id)
        stats_by_id[specialist.id] = stats
        if stats.total_invocations >= MIN_RANKING_INVOCATIONS:
            eligible.append((specialist, stats))
    if eligible:
        eligible.sort(
            key=lambda item: (
                item[1].success_rate if item[1].success_rate is not None else -1,
                item[1].total_invocations,
                item[0].created_at,
                item[0].id,
            ),
            reverse=True,
        )
        selected = eligible[0][0]
        resolved_by = "success_rate_ranking"
    else:
        selected = sorted(
            candidates,
            key=lambda specialist: (specialist.created_at, specialist.id),
            reverse=True,
        )[0]
        resolved_by = "recency_fallback"
    return selected, {
        "resolved_by": resolved_by,
        "candidate_slugs": [candidate.slug for candidate in candidates],
        "selected_slug": selected.slug,
        "stats": {
            candidate.slug: {
                "total_invocations": stats_by_id[candidate.id].total_invocations,
                "success_rate": stats_by_id[candidate.id].success_rate,
            }
            for candidate in candidates
        },
    }


def _default_output_from_schema(schema: dict, summary: str) -> dict:
    properties = schema.get("properties") if isinstance(schema, dict) else {}
    required = schema.get("required") if isinstance(schema, dict) else []
    if not isinstance(properties, dict) or not isinstance(required, list):
        return {"summary": summary}
    output: dict[str, Any] = {}
    for key in required:
        if not isinstance(key, str):
            continue
        property_schema = properties.get(key) if isinstance(properties.get(key), dict) else {}
        output[key] = _default_value(property_schema, summary)
    if not output and "summary" in properties:
        output["summary"] = summary
    return output


def _default_value(schema: dict, summary: str) -> Any:
    value_type = schema.get("type")
    if value_type == "array":
        return []
    if value_type == "boolean":
        return True
    if value_type == "integer":
        return 0
    if value_type == "number":
        return 0
    if value_type == "object":
        return {}
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]
    return summary


def _cost_from_model_calls(model_calls: list[ModelCall]) -> float:
    total = 0.0
    for call in model_calls:
        response_json = call.response_json if isinstance(call.response_json, dict) else {}
        usage = response_json.get("usage") if isinstance(response_json.get("usage"), dict) else {}
        raw_cost = response_json.get("cost_usd", usage.get("cost_usd"))
        try:
            total += float(raw_cost or 0)
        except (TypeError, ValueError):
            continue
    return total


def _window_since(window: str):
    now = utc_now()
    if window == "7d":
        return now - timedelta(days=7)
    if window == "30d":
        return now - timedelta(days=30)
    if window == "all":
        return None
    raise SpecialistValidationError("window must be one of: 7d, 30d, all")


def _agent_run_activity_at():
    return func.coalesce(
        AgentRun.completed_at,
        AgentRun.started_at,
        AgentRun.timeout_at,
    )


def _runtime_ms(agent_run: AgentRun) -> int | None:
    if agent_run.started_at is None or agent_run.completed_at is None:
        return None
    end = agent_run.completed_at
    if agent_run.started_at.tzinfo is None and end.tzinfo is not None:
        end = end.replace(tzinfo=None)
    if agent_run.started_at.tzinfo is not None and end.tzinfo is None:
        end = end.replace(tzinfo=agent_run.started_at.tzinfo)
    return max(0, int((end - agent_run.started_at).total_seconds() * 1000))


def _percentile_95(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95)))
    return ordered[index]


def _depth_rejected_count(session: Session, specialist_id: str, since) -> int:
    filters = [
        AgentEvent.event_type == EventType.SUBAGENT_DEPTH_REJECTED.value,
        AgentEvent.payload_json["specialist_id"].as_string() == specialist_id,
    ]
    if since is not None:
        filters.append(AgentEvent.created_at >= since)
    return int(
        session.execute(
            select(func.count(AgentEvent.id)).where(and_(*filters))
        ).scalar_one()
    )


def _format_cost(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]
