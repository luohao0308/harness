"""Shared imports, constants, and router for Eval API modules."""

# ruff: noqa: F401,F403,F405,I001,UP037
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.registry import ensure_default_agents
from app.api.schemas import (
    EvalCaseCreateRequest,
    EvalCaseFromRunRequest,
    EvalCasePage,
    EvalCaseResponse,
    EvalDatasetCreateRequest,
    EvalDatasetPage,
    EvalDatasetResponse,
    EvalExperimentCreateRequest,
    EvalExperimentPage,
    EvalExperimentResponse,
    EvalExperimentArmResponse,
    EvalHumanReviewRequest,
    EvalResultResponse,
    EvalRunCreateRequest,
    EvalRunPage,
    EvalRunResponse,
    RegressionDelta,
    SetBaselineRequest,
)
from app.db.models import (
    AdminAuditEvent,
    AgentAssignment,
    AgentRun,
    CitationRecord,
    EvalCase,
    EvalDataset,
    EvalExperiment,
    EvalExperimentArm,
    EvalResult,
    EvalRun,
    KnowledgePolicyAudit,
    ModelCall,
    ModelPricing,
    PromptAssemblyManifest,
    RetrievalHit,
    RetrievalSession,
    SubagentOutput,
    SubagentSpecialist,
    Task,
    ToolCall,
    User,
    WebResearchSource,
    utc_now,
)
from app.db.session import get_db_session
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.security.auth import Principal
from app.tools.capabilities import CapabilityRegistry

router = APIRouter(prefix="/evals", tags=["evals"])
DbSession = Annotated[Session, Depends(get_db_session)]

GROUNDING_TRACE_SCHEMA_VERSION = 1
LOW_GROUNDING_SAMPLE_THRESHOLD = 5
GROUNDING_PASS_RATE_REGRESSION_THRESHOLD = -0.05
TASK_SUCCESS_RATE_REGRESSION_THRESHOLD = -0.10
QUALITY_RATE_REGRESSION_THRESHOLD = 0.05
CONTRACT_PASS_RATE_REGRESSION_THRESHOLD = -0.05
SAFETY_PASS_RATE_REGRESSION_THRESHOLD = -0.02
MAX_SAFETY_PATTERN_LENGTH = 256

__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
