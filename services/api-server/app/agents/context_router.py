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
    AgentEvent,
    AgentMemoryRecord,
    AgentRun,
    ContextAssemblyManifest,
    ContextAssemblyManifestLifecycle,
    ExecutionPlan,
    ModelCall,
    PromptAssemblyManifest,
    SystemSetting,
    Task,
    ToolCall,
    utc_now,
)
from app.events.event_store import EventStore
from app.events.event_types import EventType

CONTEXT_ASSEMBLY_SETTINGS_KEY = "settings.context_assembly_v2_enabled"
POLICY_SETTINGS_KEY = "settings.policies"
CONTEXT_MANIFEST_SCHEMA_VERSION = "context-assembly-v1"
CURRENT_SUMMARY_SCHEMA_VERSION = "workspace-context-summary-v1"
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
            return False
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
                return bool(value.get("enabled") or value.get("context_assembly_v2_enabled"))
        return False

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
        included, omitted = self._apply_budget(
            sections=sections,
            estimator=estimator,
            budget=budget,
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
                "estimated_included_tokens": sum(
                    estimator.estimate(section.text) for section in included
                ),
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
        rows = list(
            self.session.execute(
                select(AgentMemoryRecord)
                .where(
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
                        and_(
                            AgentMemoryRecord.scope == "run",
                            AgentMemoryRecord.run_id == task.id,
                        ),
                    ),
                )
                .order_by(AgentMemoryRecord.score.desc(), AgentMemoryRecord.created_at.desc())
                .limit(12)
            ).scalars()
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
                    metadata={"policy_decisions": decisions, "trust": trust, "policy_flags": flags},
                )
            )
        return sections

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
    ) -> tuple[list[ContextSection], list[ContextSection]]:
        eligible = [section for section in sections if section.text.strip()]
        omitted = [section for section in sections if not section.text.strip()]
        if budget <= 0:
            return eligible, omitted
        included = list(eligible)

        def total_tokens() -> int:
            return sum(estimator.estimate(section.text) for section in included)

        while included and total_tokens() > budget:
            candidates = [section for section in included if section.priority > 0]
            if not candidates:
                break
            victim = max(
                candidates,
                key=lambda section: (
                    section.priority,
                    (
                        -section.score
                        if section.section_type in {"long_term_memory", "rag_evidence"}
                        else 0
                    ),
                    (
                        -section.drop_order
                        if section.section_type == "recent_window"
                        else section.drop_order
                    ),
                ),
            )
            included.remove(victim)
            omitted.append(victim)
        included.sort(key=lambda section: (section.priority, section.drop_order))
        return included, omitted

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
        return {
            **section.ref,
            "section_id": section.section_id,
            "section_type": section.section_type,
            "estimated_tokens": estimator.estimate(section.text),
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
        }

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
            "tool_latency_ms": sum(call.duration_ms for call in tool_calls),
            "model_latency_ms": sum(call.duration_ms for call in model_calls),
        }

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
