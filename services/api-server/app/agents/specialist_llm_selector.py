from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.model_gateway import (
    ModelGateway,
    ModelGatewayError,
    ModelMessage,
    ModelRequest,
    ModelSettingsResolver,
    model_gateway_for_provider,
)
from app.agents.specialists import SubagentSpecialistRegistry, compute_specialist_stats
from app.db.models import (
    SpecialistSelectionDecision,
    SubagentSpecialist,
    SystemSetting,
    Task,
    utc_now,
)

SPECIALIST_SELECTOR_SETTINGS_KEY = "settings.specialists"
HIGH_CONFIDENCE = 0.7
LOW_CONFIDENCE = 0.4


@dataclass(frozen=True)
class SpecialistSelectionOutcome:
    specialist: SubagentSpecialist | None
    decision: SpecialistSelectionDecision
    trace: dict[str, Any]


class SpecialistLLMSelector:
    def __init__(
        self,
        session: Session,
        *,
        organization_id: str | None,
        gateway: ModelGateway | None = None,
    ) -> None:
        self.session = session
        self.organization_id = organization_id
        self.gateway = gateway

    def select(
        self,
        *,
        task: Task,
        plan_step_key: str,
        plan_step_description: str,
        match_text: str,
    ) -> SpecialistSelectionOutcome:
        registry = SubagentSpecialistRegistry(self.session, self.organization_id)
        candidates = registry.list()
        candidate_slugs = [specialist.slug for specialist in candidates]
        if not candidates:
            decision = self._record_decision(
                task=task,
                plan_step_key=plan_step_key,
                selected_slug=None,
                confidence=0.0,
                reasoning="no active specialist candidates",
                selector="recency_fallback",
                alternative_slugs=[],
                candidate_slugs=[],
                trace={"fallback_reason": "no_candidates"},
            )
            return SpecialistSelectionOutcome(None, decision, dict(decision.trace_json))

        fallback_specialist, fallback_trace = registry.match_by_keywords_with_trace(match_text)
        settings = self._settings()
        if settings.get("use_llm_selector") is False:
            decision = self._fallback_decision(
                task=task,
                plan_step_key=plan_step_key,
                fallback_specialist=fallback_specialist,
                fallback_trace=fallback_trace,
                candidate_slugs=candidate_slugs,
                reason="llm_selector_disabled",
            )
            return SpecialistSelectionOutcome(
                fallback_specialist,
                decision,
                {**fallback_trace, "decision_id": decision.id},
            )

        try:
            llm = self._call_llm(
                task=task,
                plan_step_description=plan_step_description,
                candidates=candidates,
                settings=settings,
            )
        except Exception as exc:
            decision = self._fallback_decision(
                task=task,
                plan_step_key=plan_step_key,
                fallback_specialist=fallback_specialist,
                fallback_trace=fallback_trace,
                candidate_slugs=candidate_slugs,
                reason=f"llm_unavailable: {exc}",
            )
            return SpecialistSelectionOutcome(
                fallback_specialist,
                decision,
                {**fallback_trace, "decision_id": decision.id, "llm_error": str(exc)},
            )

        selected_slug = llm.get("selected_slug")
        confidence = _bounded_confidence(llm.get("confidence"))
        reasoning = str(llm.get("reasoning") or "")[:2000]
        alternatives = _string_list(llm.get("alternative_slugs"))
        llm_specialist = registry.get_by_slug(selected_slug) if selected_slug else None
        if llm_specialist is None:
            decision = self._fallback_decision(
                task=task,
                plan_step_key=plan_step_key,
                fallback_specialist=fallback_specialist,
                fallback_trace=fallback_trace,
                candidate_slugs=candidate_slugs,
                reason="llm_selected_unknown_slug",
                llm_payload=llm,
            )
            return SpecialistSelectionOutcome(
                fallback_specialist,
                decision,
                {**fallback_trace, "decision_id": decision.id, "llm_payload": llm},
            )

        if confidence > HIGH_CONFIDENCE:
            final = llm_specialist
            selector = "llm"
            trace = {"resolved_by": "llm", "llm_confidence": confidence}
        elif confidence >= LOW_CONFIDENCE:
            if fallback_specialist is not None and fallback_specialist.slug == llm_specialist.slug:
                final = llm_specialist
                selector = "llm"
                trace = {
                    "resolved_by": "llm_keyword_agreement",
                    "llm_confidence": confidence,
                    "fallback": fallback_trace,
                }
            else:
                final = fallback_specialist or llm_specialist
                selector = _selector_from_fallback_trace(fallback_trace)
                trace = {
                    "resolved_by": "medium_confidence_keyword_override",
                    "llm_confidence": confidence,
                    "fallback": fallback_trace,
                    "llm_selected_slug": llm_specialist.slug,
                }
        else:
            final = fallback_specialist
            selector = _selector_from_fallback_trace(fallback_trace)
            trace = {
                "resolved_by": "low_confidence_fallback",
                "llm_confidence": confidence,
                "fallback": fallback_trace,
                "llm_selected_slug": llm_specialist.slug,
            }

        decision = self._record_decision(
            task=task,
            plan_step_key=plan_step_key,
            selected_slug=final.slug if final is not None else None,
            confidence=confidence,
            reasoning=reasoning,
            selector=selector,
            alternative_slugs=alternatives,
            candidate_slugs=candidate_slugs,
            trace={**trace, "llm_payload": llm},
        )
        return SpecialistSelectionOutcome(final, decision, {**trace, "decision_id": decision.id})

    def _call_llm(
        self,
        *,
        task: Task,
        plan_step_description: str,
        candidates: list[SubagentSpecialist],
        settings: dict,
    ) -> dict:
        model_provider = str(settings.get("selector_model_provider") or "default")
        model_name = str(settings.get("selector_model_name") or "default")
        request = ModelRequest(
            model_provider=model_provider,
            model_name=model_name,
            response_format="json",
            messages=[
                ModelMessage(
                    role="system",
                    content=(
                        "Select the best subagent specialist for the plan step. "
                        "Return only JSON with selected_slug, confidence, reasoning, "
                        "and alternative_slugs. selected_slug must be one candidate slug."
                    ),
                ),
                ModelMessage(
                    role="user",
                    content=json.dumps(
                        {
                            "task": {"title": task.title, "goal": task.goal},
                            "plan_step_description": plan_step_description,
                            "candidates": [self._candidate_payload(item) for item in candidates],
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                ),
            ],
        )
        if self.gateway is None:
            resolved, resolved_settings = ModelSettingsResolver(self.session).resolve(
                task_id=task.id,
                request_payload=request,
            )
            gateway = model_gateway_for_provider(resolved_settings.provider)
            response = gateway.complete(resolved)
        else:
            response = self.gateway.complete(request)
        try:
            payload = json.loads(response.content)
        except json.JSONDecodeError as exc:
            raise ModelGatewayError("selector model returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ModelGatewayError("selector model JSON must be an object")
        return payload

    def _candidate_payload(self, specialist: SubagentSpecialist) -> dict:
        stats = compute_specialist_stats(self.session, specialist.id, "7d")
        return {
            "slug": specialist.slug,
            "display_name": specialist.display_name,
            "description": specialist.description,
            "role": specialist.role,
            "trigger_keywords": _string_list(specialist.trigger_keywords_json),
            "success_rate": stats.success_rate,
            "total_invocations": stats.total_invocations,
            "recent_failure_reasons": stats.recent_failure_reasons[:3],
        }

    def _settings(self) -> dict:
        row = self.session.execute(
            select(SystemSetting).where(
                SystemSetting.organization_id == self.organization_id,
                SystemSetting.key == SPECIALIST_SELECTOR_SETTINGS_KEY,
            )
        ).scalar_one_or_none()
        value = row.value_json if row is not None and isinstance(row.value_json, dict) else {}
        return {
            "use_llm_selector": True,
            "selector_model_provider": "default",
            "selector_model_name": "default",
            **value,
        }

    def _fallback_decision(
        self,
        *,
        task: Task,
        plan_step_key: str,
        fallback_specialist: SubagentSpecialist | None,
        fallback_trace: dict,
        candidate_slugs: list[str],
        reason: str,
        llm_payload: dict | None = None,
    ) -> SpecialistSelectionDecision:
        selector = _selector_from_fallback_trace(fallback_trace)
        trace = {**fallback_trace, "fallback_reason": reason}
        if llm_payload is not None:
            trace["llm_payload"] = llm_payload
        return self._record_decision(
            task=task,
            plan_step_key=plan_step_key,
            selected_slug=fallback_specialist.slug if fallback_specialist is not None else None,
            confidence=0.0,
            reasoning=reason,
            selector=selector,
            alternative_slugs=_string_list(fallback_trace.get("candidate_slugs")),
            candidate_slugs=candidate_slugs,
            trace=trace,
        )

    def _record_decision(
        self,
        *,
        task: Task,
        plan_step_key: str,
        selected_slug: str | None,
        confidence: float,
        reasoning: str,
        selector: str,
        alternative_slugs: list[str],
        candidate_slugs: list[str],
        trace: dict,
    ) -> SpecialistSelectionDecision:
        decision = SpecialistSelectionDecision(
            organization_id=task.organization_id,
            task_id=task.id,
            plan_step_key=plan_step_key,
            selected_slug=selected_slug,
            confidence=confidence,
            reasoning=reasoning[:4000],
            selector=selector,
            alternative_slugs_json=alternative_slugs,
            candidate_slugs_json=candidate_slugs,
            trace_json=trace,
            created_at=utc_now(),
        )
        self.session.add(decision)
        self.session.flush()
        return decision


def _selector_from_fallback_trace(trace: dict) -> str:
    resolved_by = str(trace.get("resolved_by") or "")
    if resolved_by == "success_rate_ranking":
        return "success_rate"
    if resolved_by in {"keyword_match_only", "llm_keyword_agreement"}:
        return "keyword"
    return "recency_fallback"


def _bounded_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]
