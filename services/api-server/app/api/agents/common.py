"""Shared imports and constants for Agent API modules."""

# ruff: noqa: F401,F403,F405,I001,UP037
import hashlib
import html
import json
import re
import time
import unicodedata
from collections.abc import Iterator
from email.parser import BytesParser
from email.policy import default as email_default_policy
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.agents.context_router import (
    MEMORY_INJECTION_PATTERN,
    ContextAssemblyService,
    strip_control_chars,
)
from app.agents.executor import PLANNER_SYSTEM_PROMPT, Executor
from app.agents.model_gateway import (
    AuditedModelGateway,
    ModelGatewayError,
    ModelMessage,
    ModelRequest,
)
from app.agents.orchestrator import MultiAgentOrchestrator
from app.agents.planner import PLANNER_PROMPT_VERSION, DeterministicPlanner
from app.agents.registry import ensure_default_agents
from app.agents.schemas import ExecutionPlan as ExecutionPlanSchema
from app.agents.subagent_manager import SubagentLimitExceededError, SubagentManager
from app.api.schemas import (
    AgentAssignmentResponse,
    AgentAutoResponse,
    AgentCapabilityAttachmentRequest,
    AgentCapabilityAttachmentResponse,
    AgentChatRequest,
    AgentChatResponse,
    AgentChatStreamRequest,
    AgentCloneRequest,
    AgentCreateRequest,
    AgentHandoffResponse,
    AgentLocalToolEventRequest,
    AgentLocalToolEventResponse,
    AgentMemoryActionRequest,
    AgentMemoryCreateRequest,
    AgentMemoryPage,
    AgentMemoryResponse,
    AgentMessagePage,
    AgentOrchestrateResponse,
    AgentPage,
    AgentPlanRequest,
    AgentPlanResponse,
    AgentResponse,
    AgentRunCreateRequest,
    AgentRunWorkspaceResponse,
    AgentSessionCreateRequest,
    AgentSessionPage,
    AgentSessionResponse,
    AgentTokenOptimizerPreset,
    AgentTokenOptimizerPresetPage,
    AgentTokenOptimizerSelectionResponse,
    AgentTokenOptimizerSelectRequest,
    ContextAssemblyManifestResponse,
    EventResponse,
    KnowledgeCitationResponse,
    KnowledgeDocumentCreateRequest,
    KnowledgeDocumentResponse,
    KnowledgeGroundingResponse,
    KnowledgePolicyAuditResponse,
    KnowledgeRetrievalHitResponse,
    KnowledgeSourceActionRequest,
    KnowledgeSourceCreateRequest,
    KnowledgeSourcePage,
    KnowledgeSourceResponse,
    KnowledgeSourceScopeRequest,
    KnowledgeSourceUpdateRequest,
    ModelCallResponse,
    PromptAssemblyManifestResponse,
    RetrievalSessionResponse,
    SubagentResponse,
    TaskPage,
    TaskPlanResponse,
    TaskPlanStepState,
    TaskResponse,
    ToolApprovalResponse,
    ToolCallResponse,
    ToolMention,
    WebResearchSourceResponse,
    WorkspaceContextCompressionRequest,
    WorkspaceContextCompressionResponse,
)
from app.db.models import (
    AdminAuditEvent,
    Agent,
    AgentAssignment,
    AgentCapabilityAttachment,
    AgentEvent,
    AgentHandoff,
    AgentMemoryRecord,
    AgentMessage,
    AgentRun,
    AgentSession,
    Capability,
    CapabilityVersion,
    CitationRecord,
    ContextAssemblyManifest,
    ExecutionPlan,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeEmbedding,
    KnowledgePolicyAudit,
    KnowledgeSource,
    ModelCall,
    PromptAssemblyManifest,
    RetrievalHit,
    RetrievalSession,
    Task,
    ToolApproval,
    ToolCall,
    WebResearchSource,
    WorkspaceContextCache,
    utc_now,
)
from app.db.session import get_db_session
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.knowledge import (
    SOURCE_HEALTH_HEALTHY,
    SOURCE_STATUS_ACTIVE,
    SOURCE_STATUS_ARCHIVED,
    SOURCE_STATUS_DISABLED,
    KnowledgeGroundingResult,
    KnowledgeIngestionError,
    connector_validation_status,
    create_knowledge_lifecycle_audit,
    get_visible_knowledge_source,
    ground_query,
    ingest_knowledge_source,
    knowledge_source_lifecycle_snapshot,
    list_knowledge_sources,
)
from app.knowledge_connectors import (
    connector_counts_toward_complete_usable,
    connector_provider_key,
    connector_release_state,
    normalize_connector_settings,
)
from app.knowledge_dify import (
    read_connector_secret_ref,
    secret_ref_looks_like_raw_secret,
    store_connector_secret_ref,
)
from app.security.auth import Principal, require_role
from app.tools.capabilities import (
    CAPABILITY_TYPE_CONTEXT_OPTIMIZER,
    CapabilityRegistry,
    stable_json_sha256,
    tool_capability_key,
)
from app.tools.registry import ToolMetadata, ToolRegistry
from app.tools.runner import ToolExecution, ToolRunner

from .router import DbSession, router

SUMMARY_SCHEMA_VERSION = "workspace-context-summary-v1"
COMPRESSION_PROMPT_VERSION = "workspace-context-compression-v1"
CJK_TOKEN_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af]")
ASCII_WORD_RE = re.compile(r"[A-Za-z0-9_]+(?:[-'][A-Za-z0-9_]+)*")
FUNCTION_CALLS_BLOCK_RE = re.compile(
    r"<function_calls\b[^>]*>.*?</function_calls>",
    re.IGNORECASE | re.DOTALL,
)
FUNCTION_INVOKE_RE = re.compile(
    r"<invoke\b(?P<attrs>[^>]*)>(?P<body>.*?)</invoke>",
    re.IGNORECASE | re.DOTALL,
)
FUNCTION_PARAMETER_RE = re.compile(
    r"<parameter\b(?P<attrs>[^>]*)>(?P<value>.*?)</parameter>",
    re.IGNORECASE | re.DOTALL,
)
XML_ATTRIBUTE_RE = re.compile(
    r"([A-Za-z_][\w:-]*)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')",
    re.DOTALL,
)
KNOWLEDGE_UPLOAD_MAX_BYTES = 120_000
KNOWLEDGE_UPLOAD_MAX_MULTIPART_BYTES = KNOWLEDGE_UPLOAD_MAX_BYTES + 20_000
KNOWLEDGE_UPLOAD_MIME_TYPES = {"text/plain", "text/markdown"}
KNOWLEDGE_UPLOAD_EXTENSIONS = {".txt", ".md"}
TOKEN_OPTIMIZER_PRESET_PRIORITY = 5
CONTEXT_CACHE_SCHEMA_VERSION = "workspace-context-cache-v1"
CACHE_SOURCE_COMPRESSION_SUMMARY = "compression_summary"
TOKEN_OPTIMIZER_PRESETS: dict[str, dict] = {
    "off": {
        "display_name": "关闭",
        "description": "不启用额外 Token Optimizer，只使用默认上下文策略。",
        "optimizer": {},
    },
    "conservative": {
        "display_name": "保守省 Token",
        "description": "轻量裁剪低相关证据，优先保持最近对话和记忆。",
        "optimizer": {
            "mode": "budget_overlay",
            "max_candidate_tokens_ratio": 0.9,
            "section_limits": {
                "recent_window": 16,
                "long_term_memory": 10,
                "rag_evidence": 8,
            },
            "drop_order": [
                "rag_evidence_low_relevance_first",
                "long_term_memory_low_score_first",
                "recent_window_oldest_first",
            ],
            "prefer_valid_compressed_summary": True,
            "low_cost_route_hint": "conservative summarization under budget",
        },
    },
    "balanced": {
        "display_name": "均衡",
        "description": "推荐默认方案，在上下文质量和成本之间取得平衡。",
        "optimizer": {
            "mode": "budget_overlay",
            "max_candidate_tokens_ratio": 0.8,
            "section_limits": {
                "recent_window": 12,
                "long_term_memory": 8,
                "rag_evidence": 6,
            },
            "drop_order": [
                "rag_evidence_low_relevance_first",
                "long_term_memory_low_score_first",
                "compressed_summary_if_stale",
                "recent_window_oldest_first",
            ],
            "prefer_valid_compressed_summary": True,
            "low_cost_route_hint": "balanced summarization under budget",
        },
    },
    "aggressive": {
        "display_name": "强力省 Token",
        "description": "更积极限制候选上下文，适合长对话和成本敏感任务。",
        "optimizer": {
            "mode": "budget_overlay",
            "max_candidate_tokens_ratio": 0.6,
            "section_limits": {
                "recent_window": 8,
                "long_term_memory": 4,
                "rag_evidence": 4,
            },
            "drop_order": [
                "rag_evidence_low_relevance_first",
                "long_term_memory_low_score_first",
                "compressed_summary_if_stale",
                "recent_window_oldest_first",
            ],
            "prefer_valid_compressed_summary": True,
            "low_cost_route_hint": "aggressive summarization under budget",
        },
    },
}


# ---------------------------------------------------------------------------
# v4 SSE response headers (Req 6.1 / 6.5).
#
# Every route that returns `text/event-stream` should attach these headers so
# Nginx / other reverse proxies disable buffering and the browser keeps the
# connection open while incremental deltas arrive.
#
# The `X-Accel-Buffering` hint tells Nginx to skip its own response buffer
# (reiterated with `add_header X-Accel-Buffering no always;` in
# `deploy/nginx/agent-harness.conf`).
#
# Do NOT enable `GZipMiddleware` on these routes — gzip re-chunks the stream
# and breaks per-event delivery. See `app/main.py` for the guard-rail note.
# ---------------------------------------------------------------------------
_SSE_HEADERS: dict[str, str] = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


__all__ = [name for name in globals() if not name.startswith("__")]
