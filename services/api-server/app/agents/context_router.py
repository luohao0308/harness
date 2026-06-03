from __future__ import annotations

import hashlib
import html
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.agents.model_gateway import (
    DEFAULT_MODEL_SETTINGS,
    MODEL_SETTINGS_KEY,
    ModelMessage,
    ModelRequest,
    ModelSettingsResolver,
)
from app.core.config import get_settings
from app.db.models import (
    AgentCapabilityAttachment,
    AgentEvent,
    AgentMemoryRecord,
    AgentRun,
    Capability,
    CapabilityVersion,
    ContextAssemblyManifest,
    ContextAssemblyManifestLifecycle,
    ExecutionPlan,
    ModelCall,
    PromptAssemblyManifest,
    SystemSetting,
    Task,
    ToolCall,
    WorkspaceContextCache,
    utc_now,
)
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.tools.capabilities import (
    CAPABILITY_TYPE_CONTEXT_OPTIMIZER,
    stable_json_sha256,
    validate_package_manifest,
)

CONTEXT_ASSEMBLY_SETTINGS_KEY = "settings.context_assembly_v2_enabled"
POLICY_SETTINGS_KEY = "settings.policies"
CONTEXT_MANIFEST_SCHEMA_VERSION = "context-assembly-v1"
CURRENT_SUMMARY_SCHEMA_VERSION = "workspace-context-summary-v1"
CONTEXT_CACHE_SCHEMA_VERSION = "workspace-context-cache-v1"
CACHE_SOURCE_COMPRESSION_SUMMARY = "compression_summary"
CACHE_SOURCE_RAG_RETRIEVAL = "rag_retrieval"
CACHE_SOURCE_LONG_TERM_MEMORY = "long_term_memory"
DEFAULT_CONTEXT_ASSEMBLY_V2_ENABLED = True
MAX_SNIPPET_CHARS = 240
MAX_SECTIONS_PER_MANIFEST = 64
MAX_OMITTED_REFS_LOGGED = 128
MEMORY_INJECTION_PATTERN = re.compile(
    r"(?i)ignore (all )?previous|system prompt|you are now",
)
CONTROL_CHARS_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class TokenEstimator:
    name = "base"

    def estimate(self, text: str) -> int:
        raise NotImplementedError


class TiktokenTokenEstimator(TokenEstimator):
    name = "tiktoken_cl100k_base"

    def __init__(self) -> None:
        import tiktoken

        self._encoding = tiktoken.get_encoding("cl100k_base")

    def estimate(self, text: str) -> int:
        return len(self._encoding.encode(text or ""))


class ConservativeCharTokenEstimator(TokenEstimator):
    name = "chars_div_4"

    def estimate(self, text: str) -> int:
        if not text:
            return 0
        return max(1, math.ceil(len(text) / 4))


def token_estimator_for_model(model_id: str | None) -> TokenEstimator:
    normalized = (model_id or "").strip().lower()
    known_prefixes = ("gpt-", "o1", "o3", "o4", "chatgpt-")
    if normalized.startswith(known_prefixes):
        try:
            return TiktokenTokenEstimator()
        except Exception:
            return ConservativeCharTokenEstimator()
    return ConservativeCharTokenEstimator()


@dataclass
class ContextSection:
    section_id: str
    section_type: str
    role: str
    text: str
    priority: int
    ref: dict[str, Any]
    drop_order: int = 0
    score: float = 0
    metadata: dict[str, Any] | None = None


@dataclass
class ContextAssemblyResult:
    messages: list[ModelMessage]
    manifest: ContextAssemblyManifest
    included_refs: list[dict[str, Any]]
    omitted_refs: list[dict[str, Any]]


@dataclass
class OptimizerContext:
    capability_version_ids: list[str]
    policy_hash: str | None
    decisions: list[dict[str, Any]]
    effective_strategy: dict[str, Any]
    low_cost_route_hint: str | None = None


BASELINE_OPTIMIZER_STRATEGY: dict[str, Any] = {
    "schema_version": "context-optimizer-internal-v1",
    "protected_section_types": ["system_developer", "pinned"],
    "protected_ref_types": ["current_user_goal"],
    "drop_order": [
        "system_developer",
        "pinned",
        "recent_window_oldest_first",
        "attachments_summary",
        "long_term_memory_low_score_first",
        "compressed_summary",
        "rag_evidence_low_relevance_first",
    ],
    "section_limits": {},
    "prefer_valid_compressed_summary": False,
}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _safe_snippet(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_SNIPPET_CHARS:
        return text, False
    return text[:MAX_SNIPPET_CHARS], True


def strip_control_chars(value: str) -> str:
    return CONTROL_CHARS_PATTERN.sub("", value)


class ContextAssemblyService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def context_assembly_v2_enabled(self, *, organization_id: str | None) -> bool:
        if organization_id is None:
            return DEFAULT_CONTEXT_ASSEMBLY_V2_ENABLED
        for key in (CONTEXT_ASSEMBLY_SETTINGS_KEY, POLICY_SETTINGS_KEY):
            setting = self.session.execute(
                select(SystemSetting).where(
                    SystemSetting.organization_id == organization_id,
                    SystemSetting.key == key,
                )
            ).scalar_one_or_none()
            if setting is None:
                continue
            value = setting.value_json
            if isinstance(value, dict):
                if key == CONTEXT_ASSEMBLY_SETTINGS_KEY and "enabled" in value:
                    return bool(value["enabled"])
                if "context_assembly_v2_enabled" in value:
                    return bool(value["context_assembly_v2_enabled"])
        return DEFAULT_CONTEXT_ASSEMBLY_V2_ENABLED

    def assemble_workspace_chat(
        self,
        *,
        task: Task,
        agent_id: str,
        owner_user_id: str,
        request: Any,
        authority_messages: list[ModelMessage],
        goal: str,
        mode: str,
        prompt_manifest: PromptAssemblyManifest | None = None,
        retrieval_session_id: str | None = None,
    ) -> ContextAssemblyResult:
        estimator = token_estimator_for_model(task.model_name)
        requested_budget = int(getattr(request, "context_max_tokens", None) or 0)
        budget = 0 if mode == "shadow" else requested_budget
        sections = self._workspace_sections(
            task=task,
            agent_id=agent_id,
            owner_user_id=owner_user_id,
            request=request,
            authority_messages=authority_messages,
            goal=goal,
            prompt_manifest=prompt_manifest,
        )
        optimizer_context = self._optimizer_context(
            agent_id=agent_id,
            organization_id=task.organization_id,
            requested_budget=budget,
        )
        included, omitted = self._apply_budget(
            sections=sections,
            estimator=estimator,
            budget=budget,
            optimizer_context=optimizer_context,
        )
        messages = [ModelMessage(role=section.role, content=section.text) for section in included]
        rendered_context = "\n\n".join(f"{section.role}:{section.text}" for section in included)
        now = utc_now()
        included_prompt_manifest_id = (
            prompt_manifest.id
            if prompt_manifest is not None
            and any(section.section_type == "rag_evidence" for section in included)
            else None
        )
        included_tokens = sum(estimator.estimate(section.text) for section in included)
        omitted_tokens = sum(estimator.estimate(section.text) for section in omitted)
        candidate_tokens = included_tokens + omitted_tokens
        token_savings_percent = (
            round((omitted_tokens / candidate_tokens) * 100, 2) if candidate_tokens else 0
        )
        context_cache = self._context_cache_summary(included + omitted)
        manifest = ContextAssemblyManifest(
            organization_id=task.organization_id,
            agent_id=agent_id,
            run_id=task.id,
            retrieval_session_id=retrieval_session_id,
            prompt_manifest_id=included_prompt_manifest_id,
            active_branch_id=getattr(request, "active_branch_id", None),
            active_leaf_id=getattr(request, "active_leaf_id", None),
            mode=mode,
            token_budget_json={
                "requested_max_tokens": requested_budget or None,
                "estimator": estimator.name,
                "backend_authoritative": mode == "authoritative",
                "drop_order": [
                    "system_developer",
                    "pinned",
                    "recent_window_oldest_first",
                    "attachments_summary",
                    "long_term_memory_low_score_first",
                    "compressed_summary",
                    "rag_evidence_low_relevance_first",
                ],
                "estimated_included_tokens": included_tokens,
                "estimated_omitted_tokens": omitted_tokens,
                "estimated_candidate_tokens": candidate_tokens,
                "pruning_applied": bool(omitted),
                "baseline_strategy": BASELINE_OPTIMIZER_STRATEGY,
                "effective_strategy": optimizer_context.effective_strategy,
                "optimizer_capability_version_ids": optimizer_context.capability_version_ids,
                "optimizer_policy_hash": optimizer_context.policy_hash,
                "optimizer_decisions": optimizer_context.decisions,
                "optimized_vs_baseline": {
                    "baseline_estimated_tokens": candidate_tokens,
                    "optimized_estimated_tokens": included_tokens,
                    "estimated_saved_tokens": omitted_tokens,
                    "estimated_savings_percent": token_savings_percent,
                },
                "actual_usage": {
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "source": "model_call_binding_pending",
                },
                "retrieval_cache": {
                    "hit_count": context_cache["hit_count"],
                    "miss_count": context_cache["miss_count"],
                    "stale_count": context_cache["stale_count"],
                    "status_counts": context_cache["status_counts"],
                },
                "context_cache": context_cache,
            },
            sections_json=self._sections_manifest(included + omitted)[:MAX_SECTIONS_PER_MANIFEST],
            included_refs_json=[self._included_ref(section, estimator) for section in included],
            omitted_refs_json=[
                self._omitted_ref(section, estimator, "token_budget")
                for section in omitted[:MAX_OMITTED_REFS_LOGGED]
            ],
            policy_decisions_json=[
                decision
                for section in included + omitted
                for decision in (section.metadata or {}).get("policy_decisions", [])
                if isinstance(decision, dict)
            ],
            tombstoned_refs_json=[],
            context_text_sha256=_sha256_text(rendered_context),
            metadata_json={
                "schema_version": CONTEXT_MANIFEST_SCHEMA_VERSION,
                "source": "workspace_chat",
                "max_snippet_chars": MAX_SNIPPET_CHARS,
                "max_sections_per_manifest": MAX_SECTIONS_PER_MANIFEST,
                "max_omitted_refs_logged": MAX_OMITTED_REFS_LOGGED,
                "prompt_manifest_id_source_of_truth": True,
            },
            created_at=now,
        )
        self.session.add(manifest)
        self.session.flush()
        self.session.add(
            ContextAssemblyManifestLifecycle(
                context_manifest_id=manifest.id,
                organization_id=task.organization_id,
                lifecycle_status="active",
                expires_at=now + timedelta(days=get_settings().context_manifest_retention_days),
                metadata_json={"retention_days": get_settings().context_manifest_retention_days},
                created_at=now,
                updated_at=now,
            )
        )
        self.session.flush()
        return ContextAssemblyResult(
            messages=messages,
            manifest=manifest,
            included_refs=manifest.included_refs_json,
            omitted_refs=manifest.omitted_refs_json,
        )

    def _workspace_sections(
        self,
        *,
        task: Task,
        agent_id: str,
        owner_user_id: str,
        request: Any,
        authority_messages: list[ModelMessage],
        goal: str,
        prompt_manifest: PromptAssemblyManifest | None = None,
    ) -> list[ContextSection]:
        sections: list[ContextSection] = []
        for index, message in enumerate(authority_messages):
            sections.append(
                ContextSection(
                    section_id=f"authority:{index}",
                    section_type="system_developer",
                    role=message.role,
                    text=message.content,
                    priority=0,
                    ref={"type": "system", "index": index},
                    drop_order=index,
                )
            )

        pinned_ids = set(getattr(request, "pinned_node_ids", []) or [])
        compressed_context = getattr(request, "compressed_context", None)
        coverage_ids = set(getattr(compressed_context, "coverage_node_ids", []) or [])
        messages = list(getattr(request, "messages", []) or [])
        context_window_turns = int(getattr(request, "context_window_turns", 8) or 8)
        recent_candidates = [
            node
            for node in messages[-context_window_turns:]
            if getattr(node, "role", "") in {"user", "assistant", "system"}
            and getattr(node, "id", None) not in pinned_ids
            and getattr(node, "id", None) not in coverage_ids
        ]
        pinned = [
            node
            for node in messages
            if getattr(node, "id", None) in pinned_ids
            and getattr(node, "role", "") in {"user", "assistant", "system"}
        ]
        for index, node in enumerate(pinned):
            self._append_node_section(
                sections,
                node=node,
                section_type="pinned",
                priority=1,
                drop_order=index,
            )

        for index, node in enumerate(recent_candidates):
            # Oldest recent messages are dropped first under pressure.
            self._append_node_section(
                sections,
                node=node,
                section_type="recent_window",
                priority=2,
                drop_order=index,
            )

        attachment_context = self._attachment_context(request)
        if attachment_context:
            sections.append(
                ContextSection(
                    section_id="attachments:summary",
                    section_type="attachments_summary",
                    role="system",
                    text=attachment_context,
                    priority=3,
                    ref={"type": "attachments_summary"},
                )
            )

        sections.extend(
            self._memory_sections(
                task=task,
                agent_id=agent_id,
                owner_user_id=owner_user_id,
            )
        )

        summary_section = self._compressed_summary_section(
            request=request,
            active_branch_id=getattr(request, "active_branch_id", None),
            organization_id=task.organization_id,
        )
        if summary_section is not None:
            sections.append(summary_section)

        rag_section = self._rag_evidence_section(prompt_manifest=prompt_manifest)
        if rag_section is not None:
            sections.append(rag_section)

        if goal.strip() and not any(
            section.role == "user" and section.text.strip() == goal.strip() for section in sections
        ):
            sections.append(
                ContextSection(
                    section_id="goal:current",
                    section_type="recent_window",
                    role="user",
                    text=goal,
                    priority=2,
                    drop_order=len(recent_candidates) + 1,
                    ref={"type": "current_user_goal"},
                )
            )
        return sections

    def _rag_evidence_section(
        self,
        *,
        prompt_manifest: PromptAssemblyManifest | None,
    ) -> ContextSection | None:
        if prompt_manifest is None:
            return None
        metadata = (
            prompt_manifest.metadata_json if isinstance(prompt_manifest.metadata_json, dict) else {}
        )
        evidence_text = self._prompt_manifest_evidence_text(prompt_manifest=prompt_manifest)
        if not evidence_text:
            return None
        return ContextSection(
            section_id=f"rag_evidence:{prompt_manifest.id}",
            section_type="rag_evidence",
            role="system",
            text=evidence_text,
            priority=6,
            ref={
                "type": "rag_evidence",
                "prompt_manifest_id": prompt_manifest.id,
                "retrieval_session_id": prompt_manifest.retrieval_session_id,
                "included_retrieval_hit_ids": prompt_manifest.included_retrieval_hit_ids_json,
                "evidence_text_sha256": prompt_manifest.evidence_text_sha256,
            },
            score=1.0,
            metadata={
                "prompt_manifest_version": metadata.get("prompt_manifest_version")
                or metadata.get("schema_version"),
                **self._cache_metadata_from_mapping(
                    metadata,
                    default_source=CACHE_SOURCE_RAG_RETRIEVAL,
                ),
            },
        )

    def _prompt_manifest_evidence_text(self, *, prompt_manifest: PromptAssemblyManifest) -> str:
        for section in prompt_manifest.prompt_sections_json or []:
            if not isinstance(section, dict):
                continue
            if section.get("section") != "knowledge_evidence":
                continue
            for key in ("content", "text", "evidence_summary"):
                value = section.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        metadata = (
            prompt_manifest.metadata_json if isinstance(prompt_manifest.metadata_json, dict) else {}
        )
        metadata_evidence = str(metadata.get("evidence_summary") or "").strip()
        if metadata_evidence:
            return metadata_evidence
        # Compatibility for manifests created before evidence_summary was persisted.
        evidence_message = str(metadata.get("evidence_message") or "").strip()
        if (
            evidence_message
            and hashlib.sha256(evidence_message.encode("utf-8")).hexdigest()
            == prompt_manifest.evidence_text_sha256
        ):
            return evidence_message
        return ""

    def _append_node_section(
        self,
        sections: list[ContextSection],
        *,
        node: Any,
        section_type: str,
        priority: int,
        drop_order: int,
    ) -> None:
        content = str(getattr(node, "content", "") or "").strip()
        if not content:
            return
        role = getattr(node, "role", "user")
        if role not in {"user", "assistant", "system"}:
            role = "user"
        node_id = str(getattr(node, "id", "") or "")
        text = content
        section_role = role
        ref = {"type": "conversation_node", "node_id": node_id}
        if section_type == "pinned":
            section_role = "system"
            text = (
                f'<pinned_message id="{html.escape(node_id, quote=True)}" '
                f'original_role="{html.escape(role, quote=True)}">'
                f"{html.escape(content)}</pinned_message>"
            )
            ref["original_role"] = role
        sections.append(
            ContextSection(
                section_id=f"{section_type}:{node_id or drop_order}",
                section_type=section_type,
                role=section_role,
                text=text,
                priority=priority,
                ref=ref,
                drop_order=drop_order,
            )
        )

    def _memory_sections(
        self,
        *,
        task: Task,
        agent_id: str,
        owner_user_id: str,
    ) -> list[ContextSection]:
        now = utc_now()
        rows, cache_metadata = self._memory_candidate_rows(
            task=task,
            agent_id=agent_id,
            owner_user_id=owner_user_id,
            now=now,
        )
        sections: list[ContextSection] = []
        for index, row in enumerate(rows):
            sanitized = strip_control_chars(row.canonical_text)[:2000]
            flags = list(row.policy_flags_json or [])
            if MEMORY_INJECTION_PATTERN.search(sanitized):
                flags = sorted(set([*flags, "prompt_injection_suspected"]))
            trust = "low" if "prompt_injection_suspected" in flags else "evidence"
            text = (
                f'<memory id="{html.escape(row.id, quote=True)}" '
                f'source_type="{html.escape(row.source_type, quote=True)}" '
                f'trust="{trust}">{html.escape(sanitized)}</memory>'
            )
            decisions = []
            if flags:
                decisions.append(
                    {
                        "memory_id": row.id,
                        "decision": "inject_with_low_trust" if trust == "low" else "inject",
                        "policy_flags": flags,
                    }
                )
            sections.append(
                ContextSection(
                    section_id=f"memory:{row.id}",
                    section_type="long_term_memory",
                    role="system",
                    text=text,
                    priority=4,
                    ref={
                        "type": "memory",
                        "memory_id": row.id,
                        "content_sha256": row.content_sha256,
                        "content_length": row.content_length,
                        "scope": row.scope,
                        "lifecycle_status": row.lifecycle_status,
                    },
                    drop_order=index,
                    score=row.score,
                    metadata={
                        "policy_decisions": decisions,
                        "trust": trust,
                        "policy_flags": flags,
                        **cache_metadata,
                    },
                )
            )
        return sections

    def _memory_candidate_rows(
        self,
        *,
        task: Task,
        agent_id: str,
        owner_user_id: str,
        now: datetime,
    ) -> tuple[list[AgentMemoryRecord], dict[str, Any]]:
        if self._has_run_scoped_memory(task=task, now=now):
            return self._query_memory_rows(
                task=task,
                agent_id=agent_id,
                owner_user_id=owner_user_id,
                now=now,
                include_run_scope=True,
            ), {}

        cache_lookup = self._memory_cache_lookup(
            task=task,
            agent_id=agent_id,
            owner_user_id=owner_user_id,
            now=now,
        )
        cache_row, cache_key_hash, signature = cache_lookup
        if cache_row is not None:
            cached_rows = self._memory_rows_from_cache(
                cache_row=cache_row,
                task=task,
                agent_id=agent_id,
                owner_user_id=owner_user_id,
                now=now,
            )
            if cached_rows is not None:
                cache_metadata = self._memory_cache_metadata(
                    cache_lookup=cache_lookup,
                    task=task,
                    agent_id=agent_id,
                    owner_user_id=owner_user_id,
                    memory_ids=[row.id for row in cached_rows],
                    now=now,
                )
                return cached_rows, cache_metadata
            cache_row.stale_count += 1
            cache_row.updated_at = now

        rows = self._query_memory_rows(
            task=task,
            agent_id=agent_id,
            owner_user_id=owner_user_id,
            now=now,
            include_run_scope=False,
        )
        if not rows:
            return rows, {}
        cache_metadata = self._memory_cache_metadata(
            cache_lookup=(cache_row, cache_key_hash, signature),
            task=task,
            agent_id=agent_id,
            owner_user_id=owner_user_id,
            memory_ids=[row.id for row in rows],
            now=now,
            recompute_reason=(
                "memory_candidates_stale_recomputed"
                if cache_row is not None
                else "memory_candidates_computed"
            ),
        )
        return rows, cache_metadata

    def _has_run_scoped_memory(self, *, task: Task, now: datetime) -> bool:
        count = self.session.execute(
            select(func.count(AgentMemoryRecord.id)).where(
                AgentMemoryRecord.organization_id == task.organization_id,
                AgentMemoryRecord.scope == "run",
                AgentMemoryRecord.run_id == task.id,
                AgentMemoryRecord.lifecycle_status == "active",
                or_(
                    AgentMemoryRecord.expires_at.is_(None),
                    AgentMemoryRecord.expires_at > now,
                ),
            )
        ).scalar_one()
        return int(count or 0) > 0

    def _query_memory_rows(
        self,
        *,
        task: Task,
        agent_id: str,
        owner_user_id: str,
        now: datetime,
        include_run_scope: bool,
    ) -> list[AgentMemoryRecord]:
        scope_filters = [
            AgentMemoryRecord.scope == "org",
            and_(
                AgentMemoryRecord.scope == "agent",
                AgentMemoryRecord.agent_id == agent_id,
            ),
            and_(
                AgentMemoryRecord.scope == "user",
                AgentMemoryRecord.owner_user_id == owner_user_id,
            ),
        ]
        if include_run_scope:
            scope_filters.append(
                and_(
                    AgentMemoryRecord.scope == "run",
                    AgentMemoryRecord.run_id == task.id,
                )
            )
        return list(
            self.session.execute(
                select(AgentMemoryRecord)
                .where(
                    AgentMemoryRecord.organization_id == task.organization_id,
                    AgentMemoryRecord.lifecycle_status == "active",
                    or_(
                        AgentMemoryRecord.expires_at.is_(None),
                        AgentMemoryRecord.expires_at > now,
                    ),
                    or_(*scope_filters),
                )
                .order_by(AgentMemoryRecord.score.desc(), AgentMemoryRecord.created_at.desc())
                .limit(12)
            ).scalars()
        )

    def _memory_rows_from_cache(
        self,
        *,
        cache_row: WorkspaceContextCache,
        task: Task,
        agent_id: str,
        owner_user_id: str,
        now: datetime,
    ) -> list[AgentMemoryRecord] | None:
        payload = cache_row.payload_json if isinstance(cache_row.payload_json, dict) else {}
        memory_ids = [str(item) for item in payload.get("memory_ids", []) if item]
        if not memory_ids:
            return None
        rows = list(
            self.session.execute(
                select(AgentMemoryRecord).where(
                    AgentMemoryRecord.id.in_(memory_ids),
                    AgentMemoryRecord.organization_id == task.organization_id,
                    AgentMemoryRecord.lifecycle_status == "active",
                    or_(
                        AgentMemoryRecord.expires_at.is_(None),
                        AgentMemoryRecord.expires_at > now,
                    ),
                    or_(
                        AgentMemoryRecord.scope == "org",
                        and_(
                            AgentMemoryRecord.scope == "agent",
                            AgentMemoryRecord.agent_id == agent_id,
                        ),
                        and_(
                            AgentMemoryRecord.scope == "user",
                            AgentMemoryRecord.owner_user_id == owner_user_id,
                        ),
                    ),
                )
            ).scalars()
        )
        by_id = {row.id: row for row in rows}
        if any(memory_id not in by_id for memory_id in memory_ids):
            return None
        return [by_id[memory_id] for memory_id in memory_ids]

    def _memory_cache_lookup(
        self,
        *,
        task: Task,
        agent_id: str,
        owner_user_id: str,
        now: datetime,
    ) -> tuple[WorkspaceContextCache | None, str, str]:
        signature = self._memory_cache_signature(
            organization_id=task.organization_id,
            agent_id=agent_id,
            owner_user_id=owner_user_id,
            now=now,
        )
        cache_key_hash = _sha256_text(signature)
        row = self.session.execute(
            select(WorkspaceContextCache).where(
                WorkspaceContextCache.organization_id == task.organization_id,
                WorkspaceContextCache.cache_source == CACHE_SOURCE_LONG_TERM_MEMORY,
                WorkspaceContextCache.cache_key_hash == cache_key_hash,
                WorkspaceContextCache.status == "active",
                or_(
                    WorkspaceContextCache.expires_at.is_(None),
                    WorkspaceContextCache.expires_at > now,
                ),
            )
        ).scalar_one_or_none()
        return row, cache_key_hash, signature

    def _memory_cache_signature(
        self,
        *,
        organization_id: str | None,
        agent_id: str,
        owner_user_id: str,
        now: datetime,
    ) -> str:
        rows = list(
            self.session.execute(
                select(AgentMemoryRecord)
                .where(
                    AgentMemoryRecord.organization_id == organization_id,
                    AgentMemoryRecord.lifecycle_status == "active",
                    or_(
                        AgentMemoryRecord.expires_at.is_(None),
                        AgentMemoryRecord.expires_at > now,
                    ),
                    or_(
                        AgentMemoryRecord.scope == "org",
                        and_(
                            AgentMemoryRecord.scope == "agent",
                            AgentMemoryRecord.agent_id == agent_id,
                        ),
                        and_(
                            AgentMemoryRecord.scope == "user",
                            AgentMemoryRecord.owner_user_id == owner_user_id,
                        ),
                    ),
                ),
            ).scalars()
        )
        high_water = max((row.updated_at for row in rows), default=None)
        snapshot = [
            {
                "id": row.id,
                "scope": row.scope,
                "agent_id": row.agent_id,
                "owner_user_id": row.owner_user_id,
                "content_sha256": row.content_sha256,
                "score": row.score,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            }
            for row in sorted(rows, key=lambda item: item.id)
        ]
        payload = {
            "schema_version": CONTEXT_CACHE_SCHEMA_VERSION,
            "cache_source": CACHE_SOURCE_LONG_TERM_MEMORY,
            "organization_id": organization_id,
            "agent_id": agent_id,
            "owner_user_id": owner_user_id,
            "memory_high_water_mark": high_water.isoformat() if high_water else None,
            "memory_snapshot_sha256": _sha256_text(
                json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            ),
            "active_memory_count": len(rows),
            "scope_policy": ["org", "agent", "user"],
            "limit": 12,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def _memory_cache_metadata(
        self,
        *,
        cache_lookup: tuple[WorkspaceContextCache | None, str, str],
        task: Task,
        agent_id: str,
        owner_user_id: str,
        memory_ids: list[str],
        now: datetime,
        recompute_reason: str = "memory_candidates_computed",
    ) -> dict[str, Any]:
        row, cache_key_hash, signature = cache_lookup
        is_hit = row is not None and recompute_reason == "memory_candidates_computed"
        status = "hit" if is_hit else "miss"
        reason = "memory_candidates_reused" if is_hit else recompute_reason
        estimated_saved_tokens = 0
        if is_hit and row is not None:
            row.hit_count += 1
            row.last_hit_at = now
            row.updated_at = now
            payload = row.payload_json if isinstance(row.payload_json, dict) else {}
            estimated_saved_tokens = int(payload.get("estimated_saved_tokens") or 0)
        else:
            estimated_saved_tokens = max(0, len(memory_ids) * 8)
            payload_json = {
                "memory_ids": memory_ids,
                "signature_sha256": _sha256_text(signature),
                "estimated_saved_tokens": estimated_saved_tokens,
            }
            if row is None:
                self.session.add(
                    WorkspaceContextCache(
                        organization_id=task.organization_id,
                        agent_id=agent_id,
                        owner_user_id=owner_user_id,
                        cache_source=CACHE_SOURCE_LONG_TERM_MEMORY,
                        cache_key_hash=cache_key_hash,
                        schema_version=CONTEXT_CACHE_SCHEMA_VERSION,
                        status="active",
                        payload_json=payload_json,
                        metadata_json={"reason": reason},
                        hit_count=0,
                        miss_count=1,
                        stale_count=0,
                        estimated_saved_tokens=estimated_saved_tokens,
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                row.payload_json = payload_json
                row.metadata_json = {"reason": reason}
                row.miss_count += 1
                row.estimated_saved_tokens = estimated_saved_tokens
                row.updated_at = now
        return {
            "cache_status": status,
            "cache_source": CACHE_SOURCE_LONG_TERM_MEMORY,
            "cache_key_hash": cache_key_hash,
            "cache_reason": reason,
            "cache_estimated_saved_tokens": estimated_saved_tokens,
        }

    def _compressed_summary_section(
        self,
        *,
        request: Any,
        active_branch_id: str | None,
        organization_id: str | None,
    ) -> ContextSection | None:
        compressed = getattr(request, "compressed_context", None)
        if compressed is None:
            return None
        summary = str(getattr(compressed, "summary", "") or "").strip()
        if not summary:
            return None
        schema_version = str(getattr(compressed, "summary_schema_version", "") or "")
        metadata = {
            "summary_schema_version": schema_version,
            "producer_model": str(getattr(compressed, "compressor_model", "") or ""),
            "branch_id": str(getattr(compressed, "branch_id", "") or ""),
            "coverage_path_hash": str(getattr(compressed, "coverage_path_hash", "") or ""),
            "active_branch_id": active_branch_id,
        }
        cache_status = str(getattr(compressed, "cache_status", "") or "")
        if cache_status in {"accepted", "recomputed", "stale_rejected", "error"}:
            original_tokens = int(getattr(compressed, "estimated_original_tokens", None) or 0)
            summary_tokens = int(getattr(compressed, "estimated_summary_tokens", None) or 0)
            metadata["cache_status"] = cache_status
            metadata["cache_source"] = CACHE_SOURCE_COMPRESSION_SUMMARY
            metadata["cache_reason"] = f"compression_summary_{cache_status}"
            metadata["cache_estimated_saved_tokens"] = max(0, original_tokens - summary_tokens)
            metadata["cache_key_hash"] = _sha256_text(
                json.dumps(
                    {
                        "organization_id": organization_id,
                        "branch_id": metadata["branch_id"],
                        "coverage_path_hash": metadata["coverage_path_hash"],
                        "schema_version": schema_version,
                        "producer_model": metadata["producer_model"],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        base_ref = {"type": "compressed_summary", **metadata}
        if schema_version != CURRENT_SUMMARY_SCHEMA_VERSION:
            return ContextSection(
                section_id="compressed_summary:ineligible",
                section_type="compressed_summary",
                role="system",
                text="",
                priority=5,
                ref=base_ref,
                metadata={"omission_reason": "compression_schema_mismatch"},
            )
        if not self._producer_model_allowed(
            organization_id=organization_id,
            producer_model=metadata["producer_model"],
        ):
            return ContextSection(
                section_id="compressed_summary:ineligible",
                section_type="compressed_summary",
                role="system",
                text="",
                priority=5,
                ref=base_ref,
                metadata={"omission_reason": "compression_model_not_allowed"},
            )
        if not self._compressed_branch_matches(request=request, compressed=compressed):
            return ContextSection(
                section_id="compressed_summary:ineligible",
                section_type="compressed_summary",
                role="system",
                text="",
                priority=5,
                ref=base_ref,
                metadata={"omission_reason": "compression_branch_mismatch"},
            )
        return ContextSection(
            section_id="compressed_summary",
            section_type="compressed_summary",
            role="system",
            text=(
                "Compressed prior workspace context. Treat this as lossy reference; "
                "raw pinned and recent messages take precedence.\n\n"
                f"{summary}"
            ),
            priority=5,
            ref=base_ref,
            metadata=metadata,
        )

    def _producer_model_allowed(
        self,
        *,
        organization_id: str | None,
        producer_model: str,
    ) -> bool:
        if not producer_model:
            return False
        settings = self._model_settings_for_org(organization_id)
        allowed = {str(settings.get("default_model") or "")}
        for provider in settings.get("providers", []) if isinstance(settings, dict) else []:
            if not isinstance(provider, dict):
                continue
            model = provider.get("model") or provider.get("model_name")
            if model:
                allowed.add(str(model))
            provider_models = provider.get("models")
            for model_entry in provider_models if isinstance(provider_models, list) else []:
                if isinstance(model_entry, str):
                    allowed.add(model_entry)
                elif isinstance(model_entry, dict) and model_entry.get("name"):
                    allowed.add(str(model_entry["name"]))
        return producer_model in allowed

    def _model_settings_for_org(self, organization_id: str | None) -> dict[str, Any]:
        if organization_id is None:
            return dict(DEFAULT_MODEL_SETTINGS)
        setting = self.session.execute(
            select(SystemSetting).where(
                SystemSetting.organization_id == organization_id,
                SystemSetting.key == MODEL_SETTINGS_KEY,
            )
        ).scalar_one_or_none()
        if setting is None or not isinstance(setting.value_json, dict):
            return dict(DEFAULT_MODEL_SETTINGS)
        return setting.value_json

    def _compressed_branch_matches(self, *, request: Any, compressed: Any) -> bool:
        active_branch_id = str(getattr(request, "active_branch_id", "") or "")
        compressed_branch_id = str(getattr(compressed, "branch_id", "") or "")
        if not active_branch_id or compressed_branch_id != active_branch_id:
            return False
        coverage_ids = set(getattr(compressed, "coverage_node_ids", []) or [])
        if not coverage_ids:
            return False
        covered_nodes = [
            node
            for node in list(getattr(request, "messages", []) or [])
            if getattr(node, "id", None) in coverage_ids
        ]
        if len(covered_nodes) != len(coverage_ids):
            return False
        expected = self._workspace_context_path_hash(covered_nodes)
        return expected == str(getattr(compressed, "coverage_path_hash", "") or "")

    def _workspace_context_path_hash(self, nodes: list[Any]) -> str:
        payload = []
        for node in nodes:
            payload.append(
                {
                    "id": getattr(node, "id", None),
                    "parent_id": getattr(node, "parent_id", None),
                    "role": getattr(node, "role", None),
                    "content": (
                        str(getattr(node, "content", "") or "")
                        .replace("\r\n", "\n")
                        .replace("\r", "\n")
                    ),
                    "state": getattr(node, "state", None),
                    "created_at": getattr(node, "created_at", None),
                }
            )
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _attachment_context(self, request: Any) -> str:
        attachments = list(getattr(request, "attachments", []) or [])[:12]
        if not attachments:
            attachment_names = [
                str(name).strip()[:160]
                for name in (getattr(request, "attachment_names", []) or [])[:12]
                if str(name).strip()
            ]
            if not attachment_names:
                return ""
            return (
                "User selected attachments, but their contents were not provided to the model. "
                "Do not infer or fabricate their contents. File names: "
                + ", ".join(attachment_names)
            )
        blocks = [
            "User selected attachments. Use only the explicit content below. "
            "For any file marked unavailable, do not infer or fabricate its contents."
        ]
        for attachment in attachments:
            name = str(getattr(attachment, "name", "") or "unnamed")[:160]
            status = str(getattr(attachment, "content_status", "") or "unsupported")
            content = str(getattr(attachment, "content_text", "") or "").strip()
            if status == "ready" and content:
                snippet = content[:6000]
                blocks.append(
                    f'\n<attachment name="{name}" status="ready">\n{snippet}\n</attachment>'
                )
            else:
                blocks.append(f'\n<attachment name="{name}" status="unavailable" />')
        return "\n".join(blocks)

    def _apply_budget(
        self,
        *,
        sections: list[ContextSection],
        estimator: TokenEstimator,
        budget: int,
        optimizer_context: OptimizerContext | None = None,
    ) -> tuple[list[ContextSection], list[ContextSection]]:
        if optimizer_context is None:
            optimizer_context = OptimizerContext(
                capability_version_ids=[],
                policy_hash=None,
                decisions=[],
                effective_strategy=dict(BASELINE_OPTIMIZER_STRATEGY),
            )
        eligible = [section for section in sections if section.text.strip()]
        omitted = [section for section in sections if not section.text.strip()]
        eligible, limit_omitted = self._apply_optimizer_section_limits(
            sections=eligible,
            optimizer_context=optimizer_context,
        )
        omitted.extend(limit_omitted)
        if budget <= 0:
            return eligible, omitted
        included = list(eligible)
        effective_budget = self._optimizer_budget(
            budget=budget,
            candidate_tokens=sum(estimator.estimate(section.text) for section in included),
            optimizer_context=optimizer_context,
        )

        def total_tokens() -> int:
            return sum(estimator.estimate(section.text) for section in included)

        while included and total_tokens() > effective_budget:
            candidates = [section for section in included if self._section_can_be_omitted(section)]
            if not candidates:
                break
            victim = self._select_budget_victim(
                candidates=candidates,
                optimizer_context=optimizer_context,
            )
            included.remove(victim)
            victim.metadata = {
                **(victim.metadata or {}),
                "omission_reason": self._optimizer_budget_omission_reason(optimizer_context),
                **self._optimizer_ref_metadata(optimizer_context),
            }
            omitted.append(victim)
        included.sort(key=lambda section: (section.priority, section.drop_order))
        return included, omitted

    def _optimizer_context(
        self,
        *,
        agent_id: str,
        organization_id: str | None,
        requested_budget: int,
    ) -> OptimizerContext:
        versions = self._context_optimizer_versions(
            agent_id=agent_id,
            organization_id=organization_id,
        )
        effective_strategy: dict[str, Any] = {
            **BASELINE_OPTIMIZER_STRATEGY,
            "section_limits": {},
        }
        decisions: list[dict[str, Any]] = []
        active_version_ids: list[str] = []
        low_cost_route_hint: str | None = None
        for version in versions:
            manifest = self._package_manifest_for_version(version)
            validation = validate_package_manifest(manifest)
            if validation["status"] != "valid":
                decisions.append(
                    {
                        "decision": "optimizer_rejected",
                        "capability_version_id": version.id,
                        "reason": "invalid_context_optimizer_manifest",
                        "errors": validation.get("errors", []),
                    }
                )
                continue
            optimizer = manifest.get("optimizer") if isinstance(manifest, dict) else None
            if not isinstance(optimizer, dict) or optimizer.get("mode") != "budget_overlay":
                decisions.append(
                    {
                        "decision": "optimizer_rejected",
                        "capability_version_id": version.id,
                        "reason": "invalid_context_optimizer_manifest",
                    }
                )
                continue
            active_version_ids.append(version.id)
            candidate_ratio = optimizer.get("max_candidate_tokens_ratio")
            if isinstance(candidate_ratio, (int, float)) and not isinstance(candidate_ratio, bool):
                ratio = max(0.05, min(1.0, float(candidate_ratio)))
                current_ratio = effective_strategy.get("max_candidate_tokens_ratio")
                effective_strategy["max_candidate_tokens_ratio"] = (
                    min(float(current_ratio), ratio) if current_ratio is not None else ratio
                )
            if isinstance(optimizer.get("section_limits"), dict):
                section_limits = dict(effective_strategy.get("section_limits") or {})
                for section_type, limit in optimizer["section_limits"].items():
                    if isinstance(limit, int) and not isinstance(limit, bool) and limit >= 0:
                        current_limit = section_limits.get(section_type)
                        section_limits[section_type] = (
                            min(int(current_limit), limit)
                            if isinstance(current_limit, int)
                            else limit
                        )
                effective_strategy["section_limits"] = section_limits
            if isinstance(optimizer.get("drop_order"), list):
                effective_strategy["drop_order"] = [
                    str(item) for item in optimizer["drop_order"] if isinstance(item, str)
                ]
            if optimizer.get("prefer_valid_compressed_summary") is True:
                effective_strategy["prefer_valid_compressed_summary"] = True
            if isinstance(optimizer.get("low_cost_route_hint"), str):
                low_cost_route_hint = optimizer["low_cost_route_hint"][:200]
                effective_strategy["low_cost_route_hint"] = low_cost_route_hint
            decisions.append(
                {
                    "decision": "optimizer_applied",
                    "capability_version_id": version.id,
                    "capability_type": version.type,
                    "package_name": manifest.get("name"),
                    "mode": optimizer.get("mode"),
                }
            )
        policy_hash = (
            stable_json_sha256(
                {
                    "version_ids": active_version_ids,
                    "effective_strategy": effective_strategy,
                    "requested_budget": requested_budget,
                }
            )
            if active_version_ids
            else None
        )
        return OptimizerContext(
            capability_version_ids=active_version_ids,
            policy_hash=policy_hash,
            decisions=decisions,
            effective_strategy=effective_strategy,
            low_cost_route_hint=low_cost_route_hint,
        )

    def _context_optimizer_versions(
        self,
        *,
        agent_id: str,
        organization_id: str | None,
    ) -> list[CapabilityVersion]:
        return list(
            self.session.execute(
                select(CapabilityVersion)
                .join(
                    AgentCapabilityAttachment,
                    AgentCapabilityAttachment.capability_version_id == CapabilityVersion.id,
                )
                .join(Capability, AgentCapabilityAttachment.capability_id == Capability.id)
                .where(
                    AgentCapabilityAttachment.agent_id == agent_id,
                    AgentCapabilityAttachment.enabled.is_(True),
                    Capability.status == "active",
                    CapabilityVersion.status == "active",
                    CapabilityVersion.type == CAPABILITY_TYPE_CONTEXT_OPTIMIZER,
                    or_(
                        AgentCapabilityAttachment.organization_id == organization_id,
                        AgentCapabilityAttachment.organization_id.is_(None),
                    ),
                    or_(
                        Capability.organization_id == organization_id,
                        Capability.organization_id.is_(None),
                    ),
                )
                .order_by(
                    AgentCapabilityAttachment.priority.asc(),
                    AgentCapabilityAttachment.attached_at.asc(),
                )
            ).scalars()
        )

    def _package_manifest_for_version(self, version: CapabilityVersion) -> dict[str, Any]:
        content = version.content_json if isinstance(version.content_json, dict) else {}
        manifest = content.get("package_manifest")
        return manifest if isinstance(manifest, dict) else {}

    def _optimizer_budget(
        self,
        *,
        budget: int,
        candidate_tokens: int,
        optimizer_context: OptimizerContext,
    ) -> int:
        ratio = optimizer_context.effective_strategy.get("max_candidate_tokens_ratio")
        if isinstance(ratio, (int, float)) and not isinstance(ratio, bool):
            bounded_ratio = max(0.05, min(1.0, float(ratio)))
            candidate_budget = int(math.floor(candidate_tokens * bounded_ratio))
            return max(1, min(budget, candidate_budget))
        return budget

    def _section_can_be_omitted(self, section: ContextSection) -> bool:
        if section.priority <= 0:
            return False
        if section.section_type == "pinned":
            return False
        if section.ref.get("type") == "current_user_goal":
            return False
        return True

    def _apply_optimizer_section_limits(
        self,
        *,
        sections: list[ContextSection],
        optimizer_context: OptimizerContext,
    ) -> tuple[list[ContextSection], list[ContextSection]]:
        section_limits = optimizer_context.effective_strategy.get("section_limits")
        if not isinstance(section_limits, dict) or not section_limits:
            return sections, []
        limited_by_type: dict[str, set[str]] = {}
        for section_type, raw_limit in section_limits.items():
            if not isinstance(raw_limit, int) or isinstance(raw_limit, bool):
                continue
            candidates = [
                section
                for section in sections
                if section.section_type == section_type and self._section_can_be_omitted(section)
            ]
            if len(candidates) <= raw_limit:
                continue
            kept = sorted(candidates, key=self._section_limit_keep_sort_key)[:raw_limit]
            limited_by_type[section_type] = {section.section_id for section in kept}

        included: list[ContextSection] = []
        omitted: list[ContextSection] = []
        for section in sections:
            limit = section_limits.get(section.section_type)
            if (
                isinstance(limit, int)
                and not isinstance(limit, bool)
                and self._section_can_be_omitted(section)
            ):
                keep_ids = limited_by_type.get(section.section_type)
                if keep_ids is not None and section.section_id not in keep_ids:
                    section.metadata = {
                        **(section.metadata or {}),
                        "omission_reason": "optimizer_section_limit",
                        **self._optimizer_ref_metadata(optimizer_context),
                    }
                    omitted.append(section)
                    continue
            included.append(section)
        return included, omitted

    def _section_limit_keep_sort_key(self, section: ContextSection) -> tuple:
        if section.section_type == "recent_window":
            return (-section.drop_order, -section.score)
        if section.section_type in {"long_term_memory", "rag_evidence"}:
            return (-section.score, section.drop_order)
        return (section.drop_order, -section.score)

    def _select_budget_victim(
        self,
        *,
        candidates: list[ContextSection],
        optimizer_context: OptimizerContext,
    ) -> ContextSection:
        if not optimizer_context.capability_version_ids:
            return max(candidates, key=self._default_budget_sort_key)
        drop_order = optimizer_context.effective_strategy.get("drop_order")
        if isinstance(drop_order, list):
            for rule in drop_order:
                matching = [
                    section
                    for section in candidates
                    if self._section_matches_optimizer_drop_rule(section, str(rule))
                ]
                if matching:
                    return max(matching, key=self._default_budget_sort_key)
        return max(candidates, key=self._default_budget_sort_key)

    def _section_matches_optimizer_drop_rule(self, section: ContextSection, rule: str) -> bool:
        return (
            (rule == "rag_evidence_low_relevance_first" and section.section_type == "rag_evidence")
            or (
                rule == "long_term_memory_low_score_first"
                and section.section_type == "long_term_memory"
            )
            or (rule == "compressed_summary" and section.section_type == "compressed_summary")
            or (
                rule == "compressed_summary_if_stale"
                and section.section_type == "compressed_summary"
            )
            or (rule == "attachments_summary" and section.section_type == "attachments_summary")
            or (
                rule == "recent_window_oldest_first"
                and section.section_type == "recent_window"
            )
        )

    def _default_budget_sort_key(self, section: ContextSection) -> tuple:
        score_rank = (
            -section.score if section.section_type in {"long_term_memory", "rag_evidence"} else 0
        )
        drop_rank = (
            -section.drop_order
            if section.section_type == "recent_window"
            else section.drop_order
        )
        return (
            section.priority,
            score_rank,
            drop_rank,
        )

    def _optimizer_budget_omission_reason(self, optimizer_context: OptimizerContext) -> str:
        return (
            "optimizer_budget"
            if optimizer_context.capability_version_ids
            else "token_budget"
        )

    def _optimizer_ref_metadata(self, optimizer_context: OptimizerContext) -> dict[str, Any]:
        if not optimizer_context.capability_version_ids:
            return {}
        metadata: dict[str, Any] = {
            "optimizer_capability_version_ids": optimizer_context.capability_version_ids,
            "optimizer_policy_hash": optimizer_context.policy_hash,
        }
        if optimizer_context.low_cost_route_hint:
            metadata["low_cost_routing_reason"] = optimizer_context.low_cost_route_hint
        return metadata

    def _sections_manifest(self, sections: list[ContextSection]) -> list[dict[str, Any]]:
        rows = []
        for index, section in enumerate(sections):
            snippet, truncated = _safe_snippet(section.text)
            row = {
                "index": index,
                "section_id": section.section_id,
                "section_type": section.section_type,
                "role": section.role,
                "content_sha256": _sha256_text(section.text),
                "content_length": len(section.text),
                "ref": section.ref,
                "metadata": {
                    **(section.metadata or {}),
                    "truncated": truncated,
                },
            }
            if section.section_type != "long_term_memory":
                row["snippet"] = snippet
            rows.append(row)
        return rows

    def _included_ref(self, section: ContextSection, estimator: TokenEstimator) -> dict[str, Any]:
        metadata = section.metadata or {}
        return {
            **section.ref,
            "section_id": section.section_id,
            "section_type": section.section_type,
            "estimated_tokens": estimator.estimate(section.text),
            **{
                key: metadata[key]
                for key in (
                    "optimizer_capability_version_ids",
                    "optimizer_policy_hash",
                    "low_cost_routing_reason",
                    "cache_source",
                    "cache_status",
                    "cache_key_hash",
                    "cache_reason",
                    "cache_estimated_saved_tokens",
                )
                if key in metadata
            },
        }

    def _omitted_ref(
        self,
        section: ContextSection,
        estimator: TokenEstimator,
        default_reason: str,
    ) -> dict[str, Any]:
        metadata = section.metadata or {}
        return {
            **section.ref,
            "section_id": section.section_id,
            "section_type": section.section_type,
            "estimated_tokens": estimator.estimate(section.text),
            "omission_reason": metadata.get("omission_reason") or default_reason,
            **{
                key: metadata[key]
                for key in (
                    "optimizer_capability_version_ids",
                    "optimizer_policy_hash",
                    "low_cost_routing_reason",
                    "cache_source",
                    "cache_status",
                    "cache_key_hash",
                    "cache_reason",
                    "cache_estimated_saved_tokens",
                )
                if key in metadata
            },
        }

    def _cache_metadata_from_mapping(
        self,
        mapping: dict[str, Any],
        *,
        default_source: str,
    ) -> dict[str, Any]:
        status = str(mapping.get("cache_status") or "")
        if status not in {"hit", "miss", "accepted", "recomputed", "stale", "stale_rejected"}:
            return {}
        out: dict[str, Any] = {
            "cache_status": status,
            "cache_source": str(mapping.get("cache_source") or default_source),
        }
        for key in ("cache_key_hash", "cache_reason", "cache_estimated_saved_tokens"):
            if key in mapping:
                out[key] = mapping[key]
        return out

    def _context_cache_summary(self, sections: list[ContextSection]) -> dict[str, Any]:
        sources: dict[str, dict[str, Any]] = {}
        status_counts: Counter[str] = Counter()
        seen_events: set[tuple[str, str, str]] = set()
        for section in sections:
            metadata = section.metadata or {}
            status = metadata.get("cache_status")
            if status is None:
                continue
            status_text = str(status)
            source = str(metadata.get("cache_source") or "unknown")
            cache_key_hash = str(metadata.get("cache_key_hash") or section.section_id)
            event_key = (source, status_text, cache_key_hash)
            if event_key in seen_events:
                continue
            seen_events.add(event_key)
            status_counts[status_text] += 1
            row = sources.setdefault(
                source,
                {
                    "cache_source": source,
                    "label": self._cache_source_label(source),
                    "hit_count": 0,
                    "miss_count": 0,
                    "stale_count": 0,
                    "estimated_saved_tokens": 0,
                    "reason": None,
                },
            )
            if status_text in {"hit", "accepted"}:
                row["hit_count"] += 1
            elif status_text in {"miss", "recomputed"}:
                row["miss_count"] += 1
            elif status_text in {"stale", "stale_rejected"}:
                row["stale_count"] += 1
            row["estimated_saved_tokens"] += int(metadata.get("cache_estimated_saved_tokens") or 0)
            if metadata.get("cache_reason"):
                row["reason"] = str(metadata["cache_reason"])
        hit_count = sum(int(row["hit_count"]) for row in sources.values())
        miss_count = sum(int(row["miss_count"]) for row in sources.values())
        stale_count = sum(int(row["stale_count"]) for row in sources.values())
        return {
            "schema_version": CONTEXT_CACHE_SCHEMA_VERSION,
            "hit_count": hit_count,
            "miss_count": miss_count,
            "stale_count": stale_count,
            "status_counts": dict(status_counts),
            "sources": sorted(sources.values(), key=lambda item: str(item["cache_source"])),
        }

    def _retrieval_cache_summary(self, sections: list[ContextSection]) -> dict[str, Any]:
        summary = self._context_cache_summary(sections)
        return {
            "hit_count": summary["hit_count"],
            "miss_count": summary["miss_count"],
            "stale_count": summary["stale_count"],
            "status_counts": summary["status_counts"],
        }

    def _cache_source_label(self, source: str) -> str:
        return {
            CACHE_SOURCE_COMPRESSION_SUMMARY: "摘要缓存",
            CACHE_SOURCE_RAG_RETRIEVAL: "RAG 检索",
            CACHE_SOURCE_LONG_TERM_MEMORY: "长期记忆",
        }.get(source, source)

    def render_manifest_memory_refs(
        self,
        manifest: ContextAssemblyManifest,
    ) -> list[dict[str, Any]]:
        refs = [
            ref
            for ref in (manifest.included_refs_json or [])
            if isinstance(ref, dict) and ref.get("type") == "memory"
        ]
        if not refs:
            return []
        ids = [str(ref["memory_id"]) for ref in refs if ref.get("memory_id")]
        rows = {
            row.id: row
            for row in self.session.execute(
                select(AgentMemoryRecord).where(AgentMemoryRecord.id.in_(ids))
            ).scalars()
        }
        rendered = []
        for ref in refs:
            memory_id = str(ref.get("memory_id") or "")
            row = rows.get(memory_id)
            if row is None or row.lifecycle_status != "active":
                rendered.append({**ref, "text": "redacted_by_lifecycle"})
            else:
                rendered.append({**ref, "text": row.canonical_text})
        return rendered


class RunContextRouter:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.assembly_service = ContextAssemblyService(session)

    def build(
        self,
        *,
        task: Task,
        persist_events: bool = False,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        plan = self._latest_plan(task.id)
        events = self._events(task.id)
        model_calls = self._model_calls(task.id)
        tool_calls = self._tool_calls(task.id)
        subagents = self._subagents(task.id)
        task_type = self._classify_task_type(task=task, plan=plan, tool_calls=tool_calls)
        routing = self._route_model(task=task, task_type=task_type)
        compression = self._compress_trace(
            events=events,
            model_calls=model_calls,
            tool_calls=tool_calls,
            subagents=subagents,
        )
        generated_at = utc_now()
        context = {
            "task_id": task.id,
            "generated_at": generated_at.isoformat(),
            "working_memory": self._working_memory(task=task, plan=plan),
            "long_term_memory": self._long_term_memory(task=task),
            "artifact_memory": self._artifact_memory(tool_calls=tool_calls, subagents=subagents),
            "rag_context": self._rag_context(tool_calls=tool_calls),
            "trace_memory": self._trace_memory(events=events),
            "context_compression": compression,
            "model_routing": routing,
            "latest_agent_router": self._latest_agent_router(events=events),
            "context_assembly": self._latest_context_assembly(task=task),
            "token_optimization": self._token_optimization_evidence(
                task=task, model_calls=model_calls
            ),
        }
        if persist_events:
            self._append_context_events(
                task=task,
                context=context,
                actor_id=actor_id,
                generated_at=generated_at,
            )
        return context

    def _append_context_events(
        self,
        *,
        task: Task,
        context: dict[str, Any],
        actor_id: str | None,
        generated_at: datetime,
    ) -> None:
        event_store = EventStore(self.session)
        compression = context["context_compression"]
        routing = context["model_routing"]
        event_store.append(
            task_id=task.id,
            event_type=EventType.CONTEXT_COMPRESSED,
            payload_json={
                "task_id": task.id,
                "generated_at": generated_at.isoformat(),
                "original_event_count": compression["original_event_count"],
                "retained_event_count": compression["retained_event_count"],
                "omitted_event_count": compression["omitted_event_count"],
                "retained_sequences": compression["retained_sequences"],
                "compression_strategy": compression["compression_strategy"],
            },
            actor_type="user" if actor_id else "system",
            actor_id=actor_id,
        )
        event_store.append(
            task_id=task.id,
            event_type=EventType.MODEL_ROUTED,
            payload_json={
                "task_id": task.id,
                "task_type": routing["task_type"],
                "model_provider": routing["selected_provider"],
                "model_name": routing["selected_model"],
                "model_class": routing["model_class"],
                "reasoning": routing["reasoning"],
                "routing_policy": routing["routing_policy"],
            },
            actor_type="user" if actor_id else "system",
            actor_id=actor_id,
        )

    def _latest_plan(self, task_id: str) -> ExecutionPlan | None:
        return self.session.execute(
            select(ExecutionPlan)
            .where(ExecutionPlan.task_id == task_id)
            .order_by(ExecutionPlan.version.desc())
            .limit(1)
        ).scalar_one_or_none()

    def _events(self, task_id: str) -> list[AgentEvent]:
        return list(
            self.session.execute(
                select(AgentEvent)
                .where(AgentEvent.task_id == task_id)
                .order_by(AgentEvent.sequence.asc())
            ).scalars()
        )

    def _model_calls(self, task_id: str) -> list[ModelCall]:
        return list(
            self.session.execute(
                select(ModelCall)
                .where(ModelCall.task_id == task_id)
                .order_by(ModelCall.created_at.asc())
            ).scalars()
        )

    def _tool_calls(self, task_id: str) -> list[ToolCall]:
        return list(
            self.session.execute(
                select(ToolCall)
                .where(ToolCall.task_id == task_id)
                .order_by(ToolCall.created_at.asc())
            ).scalars()
        )

    def _subagents(self, task_id: str) -> list[AgentRun]:
        return list(
            self.session.execute(
                select(AgentRun)
                .where(AgentRun.task_id == task_id, AgentRun.agent_type == "subagent")
                .order_by(AgentRun.started_at.asc(), AgentRun.id.asc())
            ).scalars()
        )

    def _working_memory(self, *, task: Task, plan: ExecutionPlan | None) -> dict[str, Any]:
        steps = []
        if plan is not None and isinstance(plan.plan_json.get("steps"), list):
            steps = [
                {
                    "key": str(step.get("key") or step.get("step_key") or ""),
                    "description": str(step.get("description") or ""),
                    "execution_mode": str(step.get("execution_mode") or ""),
                    "risk_level": str(step.get("risk_level") or "low"),
                }
                for step in plan.plan_json["steps"]
                if isinstance(step, dict)
            ]
        return {
            "title": task.title,
            "goal": task.goal,
            "status": task.status,
            "plan_version": plan.version if plan is not None else None,
            "plan_status": plan.status if plan is not None else None,
            "plan_summary": plan.plan_json.get("summary") if plan is not None else None,
            "step_count": len(steps),
            "active_steps": steps[:8],
        }

    def _long_term_memory(self, *, task: Task) -> dict[str, Any]:
        rows = list(
            self.session.execute(
                select(Task)
                .where(
                    Task.organization_id == task.organization_id,
                    Task.id != task.id,
                    Task.status == "COMPLETED",
                )
                .order_by(Task.completed_at.desc())
                .limit(3)
            ).scalars()
        )
        return {
            "source": "completed_runs_same_org",
            "item_count": len(rows),
            "items": [
                {
                    "task_id": row.id,
                    "title": row.title,
                    "goal": row.goal[:240],
                    "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                }
                for row in rows
            ],
        }

    def _artifact_memory(
        self,
        *,
        tool_calls: list[ToolCall],
        subagents: list[AgentRun],
    ) -> dict[str, Any]:
        artifact_like_tools = [
            call
            for call in tool_calls
            if isinstance(call.output_json, dict)
            and any(key in call.output_json for key in ["path", "content", "files", "artifact"])
        ]
        subagent_artifacts = []
        for subagent in subagents:
            context = subagent.context_json if isinstance(subagent.context_json, dict) else {}
            artifacts = context.get("artifacts", [])
            if not isinstance(artifacts, list):
                artifacts = []
            for artifact in artifacts:
                if isinstance(artifact, dict):
                    subagent_artifacts.append(artifact)
        return {
            "tool_artifact_count": len(artifact_like_tools),
            "subagent_artifact_count": len(subagent_artifacts),
            "recent_tool_artifacts": [
                {
                    "tool_call_id": call.id,
                    "tool_name": call.tool_name,
                    "status": call.status,
                    "summary": self._summarize_json(call.output_json),
                }
                for call in artifact_like_tools[-5:]
            ],
            "recent_subagent_artifacts": subagent_artifacts[-5:],
        }

    def _rag_context(self, *, tool_calls: list[ToolCall]) -> dict[str, Any]:
        rag_calls = [
            call
            for call in tool_calls
            if call.tool_name in {"mcp_context_search", "browser_search", "http_request"}
        ]
        return {
            "source": "tool_trace",
            "retrieval_count": len(rag_calls),
            "items": [
                {
                    "tool_call_id": call.id,
                    "tool_name": call.tool_name,
                    "status": call.status,
                    "query": (
                        call.input_json.get("query") if isinstance(call.input_json, dict) else None
                    ),
                    "summary": self._summarize_json(call.output_json),
                }
                for call in rag_calls[-5:]
            ],
        }

    def _trace_memory(self, *, events: list[AgentEvent]) -> dict[str, Any]:
        counts = Counter(event.event_type for event in events)
        failure = next(
            (
                event
                for event in reversed(events)
                if event.event_type.endswith("FAILED") or event.event_type in {"POLICY_DENIED"}
            ),
            None,
        )
        return {
            "event_count": len(events),
            "last_sequence": events[-1].sequence if events else 0,
            "event_type_counts": dict(counts),
            "failure_point": self._event_summary(failure) if failure is not None else None,
            "recent_events": [self._event_summary(event) for event in events[-8:]],
        }

    def _compress_trace(
        self,
        *,
        events: list[AgentEvent],
        model_calls: list[ModelCall],
        tool_calls: list[ToolCall],
        subagents: list[AgentRun],
    ) -> dict[str, Any]:
        retained = events[-8:]
        status_counts = Counter(event.event_type for event in events)
        return {
            "compression_strategy": "retain_recent_8_plus_aggregate_counts",
            "original_event_count": len(events),
            "retained_event_count": len(retained),
            "omitted_event_count": max(len(events) - len(retained), 0),
            "retained_sequences": [event.sequence for event in retained],
            "model_call_count": len(model_calls),
            "tool_call_count": len(tool_calls),
            "subagent_count": len(subagents),
            "status_counts": dict(status_counts),
            "prompt_tokens": sum(call.prompt_tokens for call in model_calls),
            "completion_tokens": sum(call.completion_tokens for call in model_calls),
            "token_total": sum(call.prompt_tokens + call.completion_tokens for call in model_calls),
            "estimated_cost_usd": self._model_call_cost(model_calls),
            "tool_latency_ms": sum(call.duration_ms for call in tool_calls),
            "model_latency_ms": sum(call.duration_ms for call in model_calls),
        }


    def _model_call_cost(self, model_calls: list[ModelCall]) -> float:
        total = 0.0
        for call in model_calls:
            for payload in (call.response_json, call.request_json):
                if not isinstance(payload, dict):
                    continue
                raw = payload.get("cost_usd")
                if raw is None and isinstance(payload.get("usage"), dict):
                    raw = payload["usage"].get("cost_usd")
                try:
                    total += float(raw or 0)
                except (TypeError, ValueError):
                    continue
        return round(total, 6)

    def _route_model(self, *, task: Task, task_type: str) -> dict[str, Any]:
        request_payload = ModelRequest(
            model_provider=task.model_provider or "default",
            model_name=task.model_name or "default",
            messages=[ModelMessage(role="user", content=task.goal[:2000])],
        )
        resolved_request, _settings = ModelSettingsResolver(self.session).resolve(
            task_id=task.id,
            request_payload=request_payload,
        )
        settings = self._settings_for_org(task.organization_id)
        routing_policy = self._routing_policy(
            settings=settings,
            default_model=resolved_request.model_name,
        )
        policy_entry = routing_policy.get(task_type, routing_policy["general"])
        explicit_task_model = task.model_name not in {"", "default", None}
        explicit_task_provider = task.model_provider not in {"", "default", None}
        selected_provider = (
            resolved_request.model_provider
            if explicit_task_provider
            else str(policy_entry.get("provider") or resolved_request.model_provider)
        )
        selected_model = (
            resolved_request.model_name
            if explicit_task_model
            else str(policy_entry.get("model") or resolved_request.model_name)
        )
        model_class = str(policy_entry.get("model_class") or task_type)
        decision_source = (
            "task override" if explicit_task_model or explicit_task_provider else "routing policy"
        )
        reason = (
            f"task_type={task_type}; {decision_source} "
            f"selected {selected_provider}/{selected_model}"
        )
        return {
            "task_type": task_type,
            "selected_provider": selected_provider,
            "selected_model": selected_model,
            "model_class": model_class,
            "reasoning": reason,
            "routing_policy": routing_policy,
            "explicit_task_override": explicit_task_model or explicit_task_provider,
        }

    def _settings_for_org(self, organization_id: str | None) -> dict[str, Any]:
        if organization_id is None:
            return dict(DEFAULT_MODEL_SETTINGS)
        setting = self.session.execute(
            select(SystemSetting).where(
                SystemSetting.organization_id == organization_id,
                SystemSetting.key == MODEL_SETTINGS_KEY,
            )
        ).scalar_one_or_none()
        if setting is None:
            return dict(DEFAULT_MODEL_SETTINGS)
        if not isinstance(setting.value_json, dict):
            return dict(DEFAULT_MODEL_SETTINGS)
        return setting.value_json

    def _routing_policy(
        self,
        *,
        settings: dict[str, Any],
        default_model: str,
    ) -> dict[str, dict[str, str]]:
        configured = settings.get("model_router")
        base = {
            "planning": {
                "provider": settings.get("default_provider", "openai-compatible"),
                "model": default_model,
                "model_class": "strong-planning",
            },
            "coding": {
                "provider": settings.get("default_provider", "openai-compatible"),
                "model": default_model,
                "model_class": "strong-coding",
            },
            "grading": {
                "provider": settings.get("default_provider", "openai-compatible"),
                "model": default_model,
                "model_class": "stable-grading",
            },
            "guardrail": {
                "provider": settings.get("default_provider", "openai-compatible"),
                "model": default_model,
                "model_class": "fast-guardrail",
            },
            "summarization": {
                "provider": settings.get("default_provider", "openai-compatible"),
                "model": default_model,
                "model_class": "long-context-summarization",
            },
            "general": {
                "provider": settings.get("default_provider", "openai-compatible"),
                "model": default_model,
                "model_class": "general",
            },
        }
        if isinstance(configured, dict):
            for key, value in configured.items():
                if key in base and isinstance(value, dict):
                    base[key] = {**base[key], **{str(k): str(v) for k, v in value.items()}}
        return base

    def _classify_task_type(
        self,
        *,
        task: Task,
        plan: ExecutionPlan | None,
        tool_calls: list[ToolCall],
    ) -> str:
        haystack = f"{task.title}\n{task.goal}".lower()
        if plan is not None:
            haystack += "\n" + str(plan.plan_json).lower()
        haystack += "\n" + " ".join(call.tool_name.lower() for call in tool_calls)
        checks = [
            (
                "guardrail",
                ["guardrail", "policy", "approval", "permission", "secret", "安全策略", "审批"],
            ),
            ("grading", ["eval", "grader", "regression", "score", "评测", "评分", "回归"]),
            ("coding", ["code", "github", "bug", "test", "pytest", "react", "api", "代码", "修复"]),
            (
                "summarization",
                ["summarize", "summary", "compress", "report", "总结", "压缩", "报告"],
            ),
            ("planning", ["plan", "planner", "decompose", "architecture", "规划", "分解", "架构"]),
        ]
        for task_type, keywords in checks:
            if any(keyword in haystack for keyword in keywords):
                return task_type
        return "general"

    def _latest_agent_router(self, *, events: list[AgentEvent]) -> dict[str, Any] | None:
        for event in reversed(events):
            if event.event_type == EventType.AGENT_SELECTED.value:
                return {
                    "sequence": event.sequence,
                    "trace_id": event.trace_id,
                    "payload_json": event.payload_json,
                    "created_at": event.created_at.isoformat(),
                }
        return None

    def _event_summary(self, event: AgentEvent | None) -> dict[str, Any] | None:
        if event is None:
            return None
        return {
            "sequence": event.sequence,
            "event_type": event.event_type,
            "trace_id": event.trace_id,
            "payload_summary": self._summarize_json(event.payload_json),
            "created_at": event.created_at.isoformat(),
        }

    def _summarize_json(self, value: Any) -> str:
        if not isinstance(value, dict) or not value:
            return "empty"
        keys = ", ".join(sorted(str(key) for key in value.keys())[:8])
        return f"{len(value)} fields: {keys}"

    def organization_context_summary(self, *, organization_id: str | None) -> dict[str, int]:
        return {
            "completed_run_count": int(
                self.session.execute(
                    select(func.count(Task.id)).where(
                        Task.organization_id == organization_id,
                        Task.status == "COMPLETED",
                    )
                ).scalar_one()
                or 0
            )
        }


    def _token_optimization_evidence(
        self, *, task: Task, model_calls: list[ModelCall]
    ) -> dict[str, Any]:
        latest = self._latest_context_assembly(task=task)
        token_budget = latest.get("token_budget") if latest else {}
        optimized_vs_baseline = (
            token_budget.get("optimized_vs_baseline", {}) if isinstance(token_budget, dict) else {}
        )
        prompt_tokens = sum(call.prompt_tokens for call in model_calls)
        completion_tokens = sum(call.completion_tokens for call in model_calls)
        low_cost_routes = [
            {
                "model_call_id": call.id,
                "model_name": call.model_name,
                "reason": self._low_cost_route_reason(call),
            }
            for call in model_calls
            if self._low_cost_route_reason(call) is not None
        ]
        return {
            "requested_max_tokens": token_budget.get("requested_max_tokens")
            if isinstance(token_budget, dict)
            else None,
            "actual_prompt_tokens": prompt_tokens,
            "actual_completion_tokens": completion_tokens,
            "actual_total_tokens": prompt_tokens + completion_tokens,
            "estimated_saved_tokens": optimized_vs_baseline.get("estimated_saved_tokens", 0),
            "estimated_savings_percent": optimized_vs_baseline.get("estimated_savings_percent", 0),
            "retrieval_cache": token_budget.get("retrieval_cache", {})
            if isinstance(token_budget, dict)
            else {},
            "low_cost_routes": low_cost_routes,
            "optimizer_capability_version_ids": token_budget.get(
                "optimizer_capability_version_ids", []
            )
            if isinstance(token_budget, dict)
            else [],
            "optimizer_policy_hash": token_budget.get("optimizer_policy_hash")
            if isinstance(token_budget, dict)
            else None,
            "optimizer_decisions": token_budget.get("optimizer_decisions", [])
            if isinstance(token_budget, dict)
            else [],
            "effective_strategy": token_budget.get("effective_strategy", {})
            if isinstance(token_budget, dict)
            else {},
            "optimized_vs_baseline": optimized_vs_baseline,
        }

    def _low_cost_route_reason(self, call: ModelCall) -> str | None:
        for payload in (call.request_json, call.response_json):
            if not isinstance(payload, dict):
                continue
            reason = payload.get("low_cost_routing_reason") or payload.get("model_routing_reason")
            if reason:
                return str(reason)
            if payload.get("low_cost_route") is True:
                return "low_cost_route"
        return None

    def _latest_context_assembly(self, *, task: Task) -> dict[str, Any] | None:
        manifest = self.session.execute(
            select(ContextAssemblyManifest)
            .where(ContextAssemblyManifest.run_id == task.id)
            .order_by(ContextAssemblyManifest.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if manifest is None:
            return None
        return {
            "context_manifest_id": manifest.id,
            "mode": manifest.mode,
            "prompt_manifest_id": manifest.prompt_manifest_id,
            "included_count": len(manifest.included_refs_json or []),
            "omitted_count": len(manifest.omitted_refs_json or []),
            "omission_reasons": sorted(
                {
                    str(ref.get("omission_reason"))
                    for ref in manifest.omitted_refs_json or []
                    if isinstance(ref, dict) and ref.get("omission_reason")
                }
            ),
            "token_budget": manifest.token_budget_json,
            "created_at": manifest.created_at.isoformat() if manifest.created_at else None,
        }
