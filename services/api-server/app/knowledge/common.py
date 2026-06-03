"""Shared imports, constants, and data classes for knowledge modules."""

# ruff: noqa: F401,F403,F405,I001,UP037
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
import urllib.parse
from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    AdminAuditEvent,
    CitationRecord,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeEmbedding,
    KnowledgePolicyAudit,
    KnowledgeSource,
    PromptAssemblyManifest,
    RetrievalHit,
    RetrievalSession,
    SystemSetting,
    WebResearchAttempt,
    WebResearchSource,
    WorkspaceContextCache,
    utc_now,
)
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.knowledge_connectors import (
    CONNECTOR_RELEASE_STATE_CONFIGURED_BUT_UNAVAILABLE,
    CONNECTOR_RELEASE_STATE_PREVIEW_NOT_COUNTED,
    CONNECTOR_RELEASE_STATE_USABLE,
    connector_counts_toward_complete_usable,
    connector_provider_key,
    connector_provider_label,
    connector_provider_release_matrix,
    connector_release_state,
    connector_required_reference_fields,
    connector_requires_endpoint,
    connector_requires_secret_ref,
    normalize_connector_settings,
)
from app.knowledge_coze import (
    DEFAULT_COZE_MAX_RESULTS,
    DEFAULT_COZE_TIMEOUT_SECONDS,
    CozeConnectorError,
    CozeRetrievalResult,
    get_coze_retrieval_adapter,
)
from app.knowledge_dify import (
    DEFAULT_DIFY_MAX_RESULTS,
    DEFAULT_DIFY_TIMEOUT_SECONDS,
    GROUNDING_PROVIDER_COZE_CONNECTOR,
    GROUNDING_PROVIDER_DIFY_CONNECTOR,
    DifyConnectorError,
    DifyDatasetDocumentStatus,
    DifyRetrievalResult,
    get_dify_retrieval_adapter,
    resolve_connector_secret_ref,
    secret_ref_looks_like_raw_secret,
)
from app.knowledge_web import (
    DEFAULT_WEB_RESEARCH_MAX_CONTENT_BYTES,
    DEFAULT_WEB_RESEARCH_MAX_RESULTS,
    DEFAULT_WEB_RESEARCH_TIMEOUT_SECONDS,
    GROUNDING_PROVIDER_TAVILY_SEARCH,
    WEB_RESEARCH_PROVIDER_DISABLED,
    WEB_RESEARCH_PROVIDER_FAKE,
    WEB_RESEARCH_PROVIDER_TAVILY,
    WebResearchProviderError,
    WebResearchResult,
    fake_web_research_allowed,
    get_web_research_adapter,
    query_has_secret_pattern,
    redacted_query_preview,
    resolve_web_research_api_key,
)
from app.sandbox.policies import PolicyEngine, is_safe_web_research_url

VECTOR_CAPABILITY_KEY = "knowledge.vector_capability"
VECTOR_CAPABILITY_AVAILABLE = "available"
VECTOR_CAPABILITY_UNAVAILABLE = "unavailable"
VECTOR_CAPABILITY_DISABLED = "disabled"
WEB_RESEARCH_PROVIDER_KEY = "knowledge.web_research_provider"
POLICY_SETTINGS_KEY = "settings.policies"
GROUNDING_PROVIDER_LOCAL_KNOWLEDGE = "local_knowledge"
GROUNDING_PROVIDER_FAKE_WEB_FIXTURE = "fake_web_fixture"
GROUNDING_PROVIDER_NONE = "none"
GROUNDING_REASON_LOCAL_SUFFICIENT = "local_evidence_sufficient"
GROUNDING_REASON_CONNECTOR_SOURCE_BOUND = "connector_source_bound"
GROUNDING_REASON_FIXTURE_NOT_VERIFIED = "fixture_web_not_verified"
GROUNDING_REASON_REAL_SOURCE_BOUND = "real_source_bound"
GROUNDING_REASON_NO_VERIFIED_EVIDENCE = "no_verified_evidence"
POLICY_DECISION_ALLOWED = "allowed"
POLICY_DECISION_OMITTED = "omitted"
POLICY_DECISION_DENIED = "denied"
POLICY_DECISION_REDACTED = "redacted"
POLICY_DECISION_FOREIGN_TENANT_DENIED = "foreign_tenant_denied"
POLICY_DENY_MARKER = "DENY:"
POLICY_REDACT_MARKER = "REDACT:"
POLICY_REDACTION_REASON = "policy_marker"
POLICY_REDACTION_TOKEN = f"[REDACTED:{POLICY_REDACTION_REASON}]"
SOURCE_STATUS_ACTIVE = "ACTIVE"
SOURCE_STATUS_DISABLED = "DISABLED"
SOURCE_STATUS_ARCHIVED = "ARCHIVED"
SOURCE_HEALTH_HEALTHY = "HEALTHY"
SOURCE_HEALTH_ERROR = "ERROR"
CONNECTOR_RELEASE_USABLE = CONNECTOR_RELEASE_STATE_USABLE
CONNECTOR_RELEASE_CONFIGURED_UNAVAILABLE = CONNECTOR_RELEASE_STATE_CONFIGURED_BUT_UNAVAILABLE
CONNECTOR_RELEASE_PREVIEW_NOT_COUNTED = CONNECTOR_RELEASE_STATE_PREVIEW_NOT_COUNTED
DOCUMENT_STATUS_INDEXED = "INDEXED"
DOCUMENT_STATUS_SUPERSEDED = "SUPERSEDED"
DOCUMENT_STATUS_FAILED = "FAILED"
CHUNK_STATUS_ACTIVE = "ACTIVE"
CHUNK_STATUS_STALE = "STALE"

DEFAULT_MIN_HITS = 2
DEFAULT_MIN_SCORE = 0.62
DEFAULT_MAX_LOCAL_CHUNKS = 6
DEFAULT_MAX_RETRIEVAL_CANDIDATES = 200
MAX_INGESTION_CHUNKS = 200
CONTEXT_CACHE_SCHEMA_VERSION = "workspace-context-cache-v1"
CACHE_SOURCE_RAG_RETRIEVAL = "rag_retrieval"

CONNECTOR_RELEASE_STATES = {
    CONNECTOR_RELEASE_USABLE,
    CONNECTOR_RELEASE_CONFIGURED_UNAVAILABLE,
    CONNECTOR_RELEASE_PREVIEW_NOT_COUNTED,
}
CONNECTOR_SOURCE_TYPES = {
    "connector",
    "coze",
    "dify",
    "ragflow",
    "volcengine",
    "local_dify",
    "local_ragflow",
    "markdown_directory",
    "upload",
    "file",
    "notion",
    "postgres",
    "ollama",
}
CONNECTOR_PROVIDER_RELEASE_MATRIX = connector_provider_release_matrix()
CONNECTOR_ALLOWED_SYNC_MODES = {"manual", "scheduled", "reindex"}
CONNECTOR_RAW_SECRET_KEYS = ("api_key", "apikey", "token", "password", "secret", "credential")


class KnowledgeConnectorValidationError(ValueError):
    pass


class KnowledgeIngestionError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        source: KnowledgeSource,
        document: KnowledgeDocument,
    ) -> None:
        super().__init__(message)
        self.source = source
        self.document = document


ASCII_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+(?:[-'][A-Za-z0-9_]+)*")
CJK_TOKEN_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af]")
CJK_STOP_CHARS = set("的了什么吗呢啊呀吧请看查找一下里面里写有是我你他她它们这那哪")
CHUNK_TARGET_CHARS = 900
CHUNK_OVERLAP_CHARS = 140


@dataclass
class KnowledgeGroundingResult:
    retrieval_session: RetrievalSession | None
    retrieval_hits: list[RetrievalHit] = field(default_factory=list)
    citations: list[CitationRecord] = field(default_factory=list)
    web_sources: list[WebResearchSource] = field(default_factory=list)
    prompt_manifest: PromptAssemblyManifest | None = None
    policy_audits: list[KnowledgePolicyAudit] = field(default_factory=list)
    vector_capability: str = VECTOR_CAPABILITY_UNAVAILABLE
    local_status: str = "insufficient"
    grounded: bool = False
    grounding_provider: str = GROUNDING_PROVIDER_NONE
    fixture_grounded: bool = False
    verified_grounded: bool = False
    grounding_verification_reason: str = GROUNDING_REASON_NO_VERIFIED_EVIDENCE
    evidence_summary: str = ""
    evidence_message: str = ""



__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
