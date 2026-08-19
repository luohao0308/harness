import os
import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    AdminAuditEvent,
    AgentEvent,
    AgentRun,
    DeletedEntity,
    ModelCall,
    Task,
    Team,
    TeamAgent,
    TeamGoal,
    TeamTask,
    ToolApproval,
    ToolCall,
)
from app.db.session import get_db_session
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.security.auth import Principal, require_role

router = APIRouter(prefix="/desktop", tags=["desktop-sync"])

DbSession = Annotated[Session, Depends(get_db_session)]


class TaskSyncResponse(BaseModel):
    """Individual task in sync response."""

    id: str
    title: str
    goal: str
    status: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    model_provider: str
    model_name: str


class DesktopSyncResponse(BaseModel):
    """Response from desktop sync endpoint."""

    tasks: list[TaskSyncResponse] = Field(description="List of tasks")
    server_timestamp: str = Field(description="Current server timestamp in ISO format")


class DesktopAttentionItem(BaseModel):
    """Actionable server-owned item projected into the Desktop attention queue."""

    id: str
    category: Literal["approvals", "runs", "teams"]
    kind: Literal[
        "tool_approval",
        "run_failed",
        "run_cancelled",
        "run_waiting",
        "team_goal_blocked",
        "team_agent_failed",
        "team_task_blocked",
    ]
    severity: Literal["critical", "warning"]
    title: str
    description: str
    status: str
    occurred_at: datetime
    target_path: str
    task_id: str | None = None
    team_id: str | None = None
    approval_id: str | None = None
    tool_name: str | None = None
    risk_level: str | None = None
    actions: list[Literal["approve", "reject", "open"]]


class DesktopAttentionCounts(BaseModel):
    total: int
    approvals: int
    runs: int
    teams: int


class DesktopAttentionResponse(BaseModel):
    items: list[DesktopAttentionItem]
    counts: DesktopAttentionCounts
    generated_at: datetime
    truncated: bool


class DesktopChangeReviewAuditRequest(BaseModel):
    operation_id: str = Field(min_length=1, max_length=128)
    phase: Literal["requested", "completed", "failed"]
    action: Literal["stage", "unstage", "revert"]
    path: str = Field(min_length=1, max_length=4096)
    hunk_ids: list[str] = Field(min_length=1, max_length=200)
    preview_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_id: str | None = Field(default=None, max_length=128)
    run_id: str | None = Field(default=None, max_length=128)
    approval_id: str | None = Field(default=None, max_length=128)
    error_code: str | None = Field(default=None, max_length=128)

    @field_validator("path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        parts = value.split("/")
        if value.startswith(("/", "\\")) or "\\" in value or any(
            part in {"", ".", ".."} for part in parts
        ):
            raise ValueError("path must be a normalized repository-relative path")
        return value

    @field_validator("hunk_ids")
    @classmethod
    def validate_hunk_ids(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(
            re.fullmatch(r"(?:staged|worktree):\d+", hunk_id) is None
            for hunk_id in value
        ):
            raise ValueError("hunk_ids must contain unique diff hunk identifiers")
        return value


class DesktopChangeReviewAuditResponse(BaseModel):
    accepted: bool
    audit_id: str
    event_id: str | None = None
    operation_id: str
    phase: Literal["requested", "completed", "failed"]


class SyncOperation(BaseModel):
    """A single operation to apply during sync."""

    type: Literal["create", "update", "delete"]
    entity_type: Literal["task", "offline_agent_run"]
    entity_id: str
    data: dict | None = None
    timestamp: str
    operation_id: str | None = None
    operation_id: str | None = None


class SyncOperationsRequest(BaseModel):
    """Request to apply multiple operations."""

    operations: list[SyncOperation]


class ConflictInfo(BaseModel):
    """Information about a sync conflict."""

    entity_id: str
    entity_type: str
    server_version: dict
    client_version: dict
    operation_id: str | None = None
    operation_id: str | None = None


class SyncOperationsResponse(BaseModel):
    """Response after applying sync operations."""

    applied: int = Field(description="Number of operations successfully applied")
    conflicts: list[ConflictInfo] = Field(description="List of conflicts that need user resolution")


class ChangeInfo(BaseModel):
    """Information about a changed entity."""

    entity_id: str
    entity_type: str
    change_type: Literal["created", "updated", "deleted"]
    data: dict
    timestamp: str


class SyncChangesResponse(BaseModel):
    """Response from sync changes endpoint."""

    changes: list[ChangeInfo] = Field(description="List of changes since last sync")
    total: int = Field(description="Total number of changes")
    server_timestamp: str = Field(description="Current server timestamp")


class DesktopUpdateCheckResponse(BaseModel):
    """Release-channel update metadata for desktop clients."""

    update_available: bool
    channel: Literal["stable", "beta"]
    current_version: str
    latest_version: str
    platform: str
    arch: str
    release_url: str
    feed_url: str
    metadata_url: str
    checked_at: str
    notes: str | None = None


class DesktopFeedbackRequest(BaseModel):
    """Application feedback from the desktop client."""

    title: str = Field(description="Short feedback title")
    description: str = Field(description="Feedback body")
    category: Literal["bug", "idea", "praise", "support"] = "bug"
    channel: Literal["stable", "beta"] = "stable"
    app_version: str = Field(description="Desktop client version")
    platform: str = Field(description="Electron process.platform value")
    logs: list[str] = Field(default_factory=list)
    screenshot_data_url: str | None = Field(default=None, description="Optional PNG data URL")
    metadata: dict[str, Any] = Field(default_factory=dict)


class DesktopFeedbackResponse(BaseModel):
    """Acknowledgement for desktop feedback submission."""

    received: bool
    feedback_id: str
    received_at: str


class DesktopMetricSampleRequest(BaseModel):
    """Single desktop metric sample."""

    metric_name: Literal["startup_time_ms", "crash_event", "sync_success", "sync_failure"]
    channel: Literal["stable", "beta"] = "stable"
    app_version: str = Field(description="Desktop client version")
    platform: str = Field(description="Electron process.platform value")
    value: float = Field(default=1.0, description="Metric sample value")
    metadata: dict[str, Any] = Field(default_factory=dict)


class DesktopMetricSampleResponse(BaseModel):
    """Ack for desktop metric sample."""

    received: bool
    metric_name: str
    recorded_at: str


class DesktopMetricsSummaryResponse(BaseModel):
    """Aggregated desktop metrics for release monitoring."""

    startup_count: int
    startup_avg_ms: float | None
    startup_p95_ms: float | None
    crash_events: int
    sync_successes: int
    sync_failures: int
    sync_success_rate: float | None


_SEMVER_RE = re.compile(
    r"^v?(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?$"
)


def _parse_semver(value: str) -> tuple[int, int, int, int, tuple[tuple[int, int, str], ...]]:
    match = _SEMVER_RE.match(value.strip())
    if not match:
        raise ValueError("version must be semver, for example 1.2.3 or 1.2.3-beta.1")

    prerelease = match.group("prerelease")
    prerelease_rank: int
    prerelease_key: tuple[tuple[int, int, str], ...]
    if prerelease:
        parts: list[tuple[int, int, str]] = []
        for part in prerelease.split("."):
            parts.append((0, int(part), "") if part.isdigit() else (1, 0, part))
        prerelease_rank = 0
        prerelease_key = tuple(parts)
    else:
        prerelease_rank = 1
        prerelease_key = ()

    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        prerelease_rank,
        prerelease_key,
    )


def _is_newer_version(latest: str, current: str) -> bool:
    return _parse_semver(latest) > _parse_semver(current)


def _desktop_update_metadata_file(platform: str) -> str:
    normalized = platform.lower()
    if normalized in {"darwin", "mac", "macos"}:
        return "latest-mac.yml"
    if normalized in {"win32", "windows", "win"}:
        return "latest.yml"
    return "latest-linux.yml"


def _desktop_latest_version(channel: str) -> str:
    if channel == "beta":
        return (
            os.getenv("DESKTOP_UPDATE_BETA_VERSION")
            or os.getenv("DESKTOP_UPDATE_LATEST_VERSION")
            or os.getenv("DESKTOP_UPDATE_STABLE_VERSION")
            or "0.1.0"
        )
    return (
        os.getenv("DESKTOP_UPDATE_STABLE_VERSION")
        or os.getenv("DESKTOP_UPDATE_LATEST_VERSION")
        or "0.1.0"
    )


def _desktop_event_store() -> dict[str, list[dict[str, Any]]]:
    return _DESKTOP_EVENT_STORE


def _record_desktop_event(event_type: str, payload: dict[str, Any]) -> str:
    event_id = f"desktop-{len(_DESKTOP_EVENT_STORE['events']) + 1}"
    record = {
        "id": event_id,
        "event_type": event_type,
        "payload": payload,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _DESKTOP_EVENT_STORE["events"].append(record)
    return event_id


def _metric_samples(metric_name: str) -> list[dict[str, Any]]:
    return [
        event["payload"]
        for event in _DESKTOP_EVENT_STORE["metrics"]
        if event["payload"]["metric_name"] == metric_name
    ]


_DESKTOP_EVENT_STORE: dict[str, list[dict[str, Any]]] = {
    "events": [],
    "metrics": [],
}


@router.get("/updates/check", response_model=DesktopUpdateCheckResponse)
def check_desktop_updates(
    current_version: Annotated[str, Query(description="Current desktop app version")],
    channel: Annotated[Literal["stable", "beta"], Query(description="Release channel")] = "stable",
    platform: Annotated[str, Query(description="Electron process.platform value")] = "darwin",
    arch: Annotated[str, Query(description="Electron process.arch value")] = "x64",
) -> DesktopUpdateCheckResponse:
    """
    Check Harness Desktop update availability for stable or beta release channels.

    The desktop app still downloads signed artifacts from GitHub Releases through
    electron-updater metadata. This endpoint is the backend policy gate that
    selects the channel/version and returns the metadata feed URL for the client.
    """
    latest_version = _desktop_latest_version(channel)
    try:
        update_available = _is_newer_version(latest_version, current_version)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    repo = os.getenv("DESKTOP_UPDATE_GITHUB_REPO", "luohao0308/harness")
    tag = latest_version if latest_version.startswith("v") else f"v{latest_version}"
    release_base_url = os.getenv("DESKTOP_UPDATE_RELEASE_BASE_URL", f"https://github.com/{repo}/releases")
    feed_base_url = os.getenv(
        "DESKTOP_UPDATE_FEED_BASE_URL",
        f"https://github.com/{repo}/releases/download/{tag}",
    )
    metadata_file = _desktop_update_metadata_file(platform)

    return DesktopUpdateCheckResponse(
        update_available=update_available,
        channel=channel,
        current_version=current_version,
        latest_version=latest_version,
        platform=platform,
        arch=arch,
        release_url=f"{release_base_url}/tag/{tag}",
        feed_url=feed_base_url,
        metadata_url=f"{feed_base_url.rstrip('/')}/{metadata_file}",
        checked_at=datetime.now(UTC).isoformat(),
        notes=os.getenv("DESKTOP_UPDATE_NOTES"),
    )


@router.post("/feedback", response_model=DesktopFeedbackResponse)
def submit_desktop_feedback(request: DesktopFeedbackRequest) -> DesktopFeedbackResponse:
    feedback_id = _record_desktop_event(
        "desktop.feedback",
        {
            "title": request.title,
            "description": request.description,
            "category": request.category,
            "channel": request.channel,
            "app_version": request.app_version,
            "platform": request.platform,
            "logs": request.logs[:20],
            "screenshot_data_url_present": bool(request.screenshot_data_url),
            "metadata": request.metadata,
        },
    )
    return DesktopFeedbackResponse(
        received=True,
        feedback_id=feedback_id,
        received_at=datetime.now(UTC).isoformat(),
    )


@router.post("/metrics", response_model=DesktopMetricSampleResponse)
def record_desktop_metric_sample(
    request: DesktopMetricSampleRequest,
) -> DesktopMetricSampleResponse:
    _DESKTOP_EVENT_STORE["metrics"].append(
        {
            "id": f"metric-{len(_DESKTOP_EVENT_STORE['metrics']) + 1}",
            "payload": request.model_dump(),
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    return DesktopMetricSampleResponse(
        received=True,
        metric_name=request.metric_name,
        recorded_at=datetime.now(UTC).isoformat(),
    )


@router.get("/metrics/summary", response_model=DesktopMetricsSummaryResponse)
def get_desktop_metrics_summary() -> DesktopMetricsSummaryResponse:
    startup_samples = [float(sample["value"]) for sample in _metric_samples("startup_time_ms")]
    crash_events = len(_metric_samples("crash_event"))
    sync_successes = len(_metric_samples("sync_success"))
    sync_failures = len(_metric_samples("sync_failure"))
    total_sync = sync_successes + sync_failures
    return DesktopMetricsSummaryResponse(
        startup_count=len(startup_samples),
        startup_avg_ms=(sum(startup_samples) / len(startup_samples)) if startup_samples else None,
        startup_p95_ms=_p95(startup_samples),
        crash_events=crash_events,
        sync_successes=sync_successes,
        sync_failures=sync_failures,
        sync_success_rate=(sync_successes / total_sync) if total_sync else None,
    )


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * 0.95))))
    return ordered[index]


@router.get("/attention", response_model=DesktopAttentionResponse)
def get_desktop_attention(
    session: DbSession,
    principal: Principal,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> DesktopAttentionResponse:
    """Return one bounded, organization-scoped projection of actionable Desktop work."""
    organization_id = principal.organization_id
    source_limit = max(limit * 2, 100)
    can_decide_approvals = "admin" in principal.roles
    items: list[DesktopAttentionItem] = []

    approval_rows = session.execute(
        select(ToolApproval, Task, ToolCall)
        .join(Task, Task.id == ToolApproval.task_id)
        .join(ToolCall, ToolCall.id == ToolApproval.tool_call_id)
        .where(
            ToolApproval.organization_id == organization_id,
            ToolApproval.status == "PENDING",
            Task.organization_id == organization_id,
        )
        .order_by(ToolApproval.created_at.desc(), ToolApproval.id.asc())
        .limit(source_limit)
    ).all()
    approval_task_ids: set[str] = set()
    for approval, task, tool_call in approval_rows:
        approval_task_ids.add(task.id)
        items.append(
            DesktopAttentionItem(
                id=f"approval:{approval.id}",
                category="approvals",
                kind="tool_approval",
                severity=(
                    "critical"
                    if approval.risk_level.lower() in {"high", "critical"}
                    else "warning"
                ),
                title=task.title,
                description=approval.reason or f"{tool_call.tool_name} 需要审批",
                status=approval.status,
                occurred_at=_as_utc(approval.created_at),
                target_path=f"/runs/{task.id}",
                task_id=task.id,
                approval_id=approval.id,
                tool_name=tool_call.tool_name,
                risk_level=approval.risk_level,
                actions=(
                    ["approve", "reject", "open"]
                    if can_decide_approvals
                    else ["open"]
                ),
            )
        )

    abnormal_tasks = list(
        session.execute(
            select(Task)
            .where(
                Task.organization_id == organization_id,
                Task.status.in_(("FAILED", "CANCELLED", "WAITING_APPROVAL")),
            )
            .order_by(Task.updated_at.desc(), Task.id.asc())
            .limit(source_limit)
        ).scalars()
    )
    for task in abnormal_tasks:
        if task.status == "WAITING_APPROVAL" and task.id in approval_task_ids:
            continue
        kind, severity, description = _run_attention_details(task.status)
        items.append(
            DesktopAttentionItem(
                id=f"run:{task.id}",
                category="runs",
                kind=kind,
                severity=severity,
                title=task.title,
                description=description,
                status=task.status,
                occurred_at=_as_utc(task.updated_at),
                target_path=f"/runs/{task.id}",
                task_id=task.id,
                actions=["open"],
            )
        )

    blocked_goals = session.execute(
        select(TeamGoal, Team)
        .join(Team, Team.id == TeamGoal.team_id)
        .where(
            TeamGoal.organization_id == organization_id,
            TeamGoal.status == "blocked",
            Team.organization_id == organization_id,
        )
        .order_by(TeamGoal.updated_at.desc(), TeamGoal.id.asc())
        .limit(source_limit)
    ).all()
    for goal, team in blocked_goals:
        items.append(
            DesktopAttentionItem(
                id=f"team-goal:{goal.id}",
                category="teams",
                kind="team_goal_blocked",
                severity="critical",
                title=team.name,
                description="目标被阻塞",
                status=goal.status,
                occurred_at=_as_utc(goal.updated_at),
                target_path=f"/teams/{team.id}",
                team_id=team.id,
                actions=["open"],
            )
        )

    failed_agents = session.execute(
        select(TeamAgent, Team)
        .join(Team, Team.id == TeamAgent.team_id)
        .where(
            TeamAgent.organization_id == organization_id,
            TeamAgent.status == "failed",
            Team.organization_id == organization_id,
        )
        .order_by(TeamAgent.updated_at.desc(), TeamAgent.id.asc())
        .limit(source_limit)
    ).all()
    for agent, team in failed_agents:
        items.append(
            DesktopAttentionItem(
                id=f"team-agent:{agent.id}",
                category="teams",
                kind="team_agent_failed",
                severity="critical",
                title=team.name,
                description=f"成员 {agent.agent_name} 执行失败",
                status=agent.status,
                occurred_at=_as_utc(agent.updated_at),
                target_path=f"/teams/{team.id}",
                team_id=team.id,
                actions=["open"],
            )
        )

    team_task_rows = session.execute(
        select(TeamTask, Team)
        .join(Team, Team.id == TeamTask.team_id)
        .where(
            TeamTask.organization_id == organization_id,
            TeamTask.status.in_(("pending", "in_progress")),
            Team.organization_id == organization_id,
        )
        .order_by(TeamTask.updated_at.desc(), TeamTask.id.asc())
        .limit(source_limit)
    ).all()
    for team_task, team in team_task_rows:
        if not team_task.blocked_by_json:
            continue
        items.append(
            DesktopAttentionItem(
                id=f"team-task:{team_task.id}",
                category="teams",
                kind="team_task_blocked",
                severity="warning",
                title=team.name,
                description=f"任务“{team_task.subject}”存在未解决依赖",
                status="blocked",
                occurred_at=_as_utc(team_task.updated_at),
                target_path=f"/teams/{team.id}",
                team_id=team.id,
                actions=["open"],
            )
        )

    items.sort(key=_attention_sort_key)
    counts = DesktopAttentionCounts(
        total=len(items),
        approvals=sum(item.category == "approvals" for item in items),
        runs=sum(item.category == "runs" for item in items),
        teams=sum(item.category == "teams" for item in items),
    )
    return DesktopAttentionResponse(
        items=items[:limit],
        counts=counts,
        generated_at=datetime.now(UTC),
        truncated=len(items) > limit,
    )


def _run_attention_details(
    status: str,
) -> tuple[
    Literal["run_failed", "run_cancelled", "run_waiting"],
    Literal["critical", "warning"],
    str,
]:
    if status == "FAILED":
        return "run_failed", "critical", "运行失败，需要检查"
    if status == "CANCELLED":
        return "run_cancelled", "warning", "运行已取消，请确认是否需要重试"
    return "run_waiting", "warning", "运行正在等待人工处理"


def _attention_sort_key(item: DesktopAttentionItem) -> tuple[int, float, str]:
    occurred_at = _as_utc(item.occurred_at)
    severity_rank = 0 if item.severity == "critical" else 1
    return severity_rank, -occurred_at.timestamp(), item.id


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@router.post(
    "/change-review/audit",
    response_model=DesktopChangeReviewAuditResponse,
)
def record_desktop_change_review_audit(
    request: DesktopChangeReviewAuditRequest,
    session: DbSession,
    principal: Principal,
) -> DesktopChangeReviewAuditResponse:
    """Persist an organization-scoped audit record for a local Git mutation phase."""
    require_role(principal, {"admin", "engineer"})
    task, approval = _resolve_change_review_references(
        session=session,
        principal=principal,
        request=request,
    )
    audit_action = f"desktop.change_review.{request.phase}"
    operation_audits = list(
        session.execute(
            select(AdminAuditEvent)
            .where(
                AdminAuditEvent.organization_id == principal.organization_id,
                AdminAuditEvent.event_type
                == EventType.DESKTOP_CHANGE_REVIEW_AUDITED.value,
                AdminAuditEvent.resource_type == "desktop_change_review",
                AdminAuditEvent.resource_id == request.operation_id,
            )
            .order_by(AdminAuditEvent.created_at.asc(), AdminAuditEvent.id.asc())
        ).scalars()
    )
    identity = {
        "action": request.action,
        "path": request.path,
        "hunk_ids": request.hunk_ids,
        "preview_sha256": request.preview_sha256,
        "task_id": task.id if task is not None else None,
        "run_id": request.run_id,
        "approval_id": approval.id if approval is not None else None,
    }
    identity_fields = tuple(identity)
    for operation_audit in operation_audits:
        persisted_identity = {
            field: operation_audit.payload_json.get(field) for field in identity_fields
        }
        if persisted_identity != identity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Change review operation identity does not match",
            )

    existing = next(
        (audit for audit in operation_audits if audit.action == audit_action),
        None,
    )
    if existing is not None:
        return DesktopChangeReviewAuditResponse(
            accepted=True,
            audit_id=existing.id,
            event_id=existing.payload_json.get("event_id"),
            operation_id=request.operation_id,
            phase=request.phase,
        )

    payload = request.model_dump(exclude_none=True)
    event_id: str | None = None
    if task is not None:
        event = EventStore(session).append(
            task_id=task.id,
            event_type=EventType.DESKTOP_CHANGE_REVIEW_AUDITED,
            payload_json=payload,
            actor_type="user",
            actor_id=principal.user_id,
        )
        event_id = event.id

    audit_payload = {
        **payload,
        "task_id": task.id if task is not None else None,
        "run_id": request.run_id,
        "approval_id": approval.id if approval is not None else None,
        "event_id": event_id,
    }
    audit = AdminAuditEvent(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        event_type=EventType.DESKTOP_CHANGE_REVIEW_AUDITED.value,
        resource_type="desktop_change_review",
        resource_id=request.operation_id,
        action=audit_action,
        payload_json=audit_payload,
    )
    session.add(audit)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        existing = session.execute(
            select(AdminAuditEvent).where(
                AdminAuditEvent.organization_id == principal.organization_id,
                AdminAuditEvent.event_type == EventType.DESKTOP_CHANGE_REVIEW_AUDITED.value,
                AdminAuditEvent.resource_type == "desktop_change_review",
                AdminAuditEvent.resource_id == request.operation_id,
                AdminAuditEvent.action == audit_action,
            )
        ).scalar_one_or_none()
        if existing is None:
            raise error
        persisted_identity = {
            field: existing.payload_json.get(field) for field in identity_fields
        }
        if persisted_identity != identity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Change review operation identity does not match",
            ) from error
        return DesktopChangeReviewAuditResponse(
            accepted=True,
            audit_id=existing.id,
            event_id=existing.payload_json.get("event_id"),
            operation_id=request.operation_id,
            phase=request.phase,
        )
    session.refresh(audit)
    return DesktopChangeReviewAuditResponse(
        accepted=True,
        audit_id=audit.id,
        event_id=event_id,
        operation_id=request.operation_id,
        phase=request.phase,
    )


def _resolve_change_review_references(
    *,
    session: Session,
    principal: Principal,
    request: DesktopChangeReviewAuditRequest,
) -> tuple[Task | None, ToolApproval | None]:
    task: Task | None = None
    approval: ToolApproval | None = None

    if request.task_id is not None:
        task = session.execute(
            select(Task).where(
                Task.id == request.task_id,
                Task.organization_id == principal.organization_id,
            )
        ).scalar_one_or_none()
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if request.run_id is not None:
        run_task = session.execute(
            select(Task).where(
                Task.id == request.run_id,
                Task.organization_id == principal.organization_id,
            )
        ).scalar_one_or_none()
        if run_task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
        if task is not None and task.id != run_task.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Run does not belong to task",
            )
        task = task or run_task

    if request.approval_id is not None:
        approval_row = session.execute(
            select(ToolApproval, Task)
            .join(Task, Task.id == ToolApproval.task_id)
            .where(
                ToolApproval.id == request.approval_id,
                ToolApproval.organization_id == principal.organization_id,
                Task.organization_id == principal.organization_id,
            )
        ).one_or_none()
        if approval_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Approval not found",
            )
        approval, approval_task = approval_row
        if task is not None and task.id != approval.task_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Approval does not belong to task",
            )
        task = task or approval_task

    return task, approval


@router.get("/sync", response_model=DesktopSyncResponse)
def sync_desktop_data(
    session: DbSession,
    principal: Principal,
    since: Annotated[
        str | None,
        Query(description="ISO timestamp - return tasks updated after this time"),
    ] = None,
    start_date: Annotated[
        str | None,
        Query(description="ISO date - filter tasks created on or after this date"),
    ] = None,
    end_date: Annotated[
        str | None,
        Query(description="ISO date - filter tasks created on or before this date"),
    ] = None,
) -> DesktopSyncResponse:
    """
    Sync desktop application data.

    Returns tasks owned by the authenticated user, with optional filtering:
    - since: Only return tasks updated after this timestamp
    - start_date: Only return tasks created on or after this date
    - end_date: Only return tasks created on or before this date
    """
    # Build query
    query = select(Task).where(Task.created_by == principal.user_id)

    # Apply 'since' filter
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid 'since' timestamp format. Expected ISO 8601 format: {e}",
            ) from e
        query = query.where(Task.updated_at > since_dt)

    # Apply date range filters
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date).replace(tzinfo=UTC)
        except (ValueError, AttributeError) as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid 'start_date' format. Expected ISO 8601 date format: {e}",
            ) from e
        query = query.where(Task.created_at >= start_dt)

    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date).replace(tzinfo=UTC)
            # Include the entire end date by adding 1 day
            end_dt = end_dt + timedelta(days=1)
        except (ValueError, AttributeError) as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid 'end_date' format. Expected ISO 8601 date format: {e}",
            ) from e
        query = query.where(Task.created_at < end_dt)

    # Execute query
    tasks = session.execute(query).scalars().all()

    # Convert to response model
    task_responses = [
        TaskSyncResponse(
            id=task.id,
            title=task.title,
            goal=task.goal,
            status=task.status,
            created_at=task.created_at,
            updated_at=task.updated_at,
            completed_at=task.completed_at,
            model_provider=task.model_provider,
            model_name=task.model_name,
        )
        for task in tasks
    ]

    # Generate server timestamp
    server_timestamp = datetime.now(UTC).isoformat()

    return DesktopSyncResponse(
        tasks=task_responses,
        server_timestamp=server_timestamp,
    )


@router.get("/sync/changes", response_model=SyncChangesResponse)
def get_sync_changes(
    session: DbSession,
    principal: Principal,
    last_sync: Annotated[str, Query(description="ISO timestamp of last sync")],
) -> SyncChangesResponse:
    """
    Get changes since the last sync timestamp.

    Returns all tasks created, updated, or deleted since the given timestamp.
    Deleted tasks are tracked separately (future enhancement).
    """
    try:
        last_sync_dt = datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid 'last_sync' timestamp format. Expected ISO 8601 format: {e}",
        ) from e

    # Query for tasks created or updated since last sync
    query = select(Task).where(
        Task.created_by == principal.user_id,
        Task.updated_at > last_sync_dt,
    )

    tasks = session.execute(query).scalars().all()

    # Convert to change info
    changes = []
    for task in tasks:
        # Ensure task.created_at is timezone-aware for comparison
        task_created_at = task.created_at
        if task_created_at.tzinfo is None:
            task_created_at = task_created_at.replace(tzinfo=UTC)

        # Determine change type based on created_at vs last_sync
        if task_created_at > last_sync_dt:
            change_type = "created"
        else:
            change_type = "updated"

        changes.append(
            ChangeInfo(
                entity_id=task.id,
                entity_type="task",
                change_type=change_type,
                data={
                    "id": task.id,
                    "title": task.title,
                    "goal": task.goal,
                    "status": task.status,
                    "created_at": task.created_at.isoformat(),
                    "updated_at": task.updated_at.isoformat(),
                    "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                    "model_provider": task.model_provider,
                    "model_name": task.model_name,
                },
                timestamp=task.updated_at.isoformat(),
            )
        )

    # Query for deleted entities since last sync
    deleted_query = select(DeletedEntity).where(
        DeletedEntity.entity_type == "task",
        DeletedEntity.deleted_by == principal.user_id,
        DeletedEntity.deleted_at > last_sync_dt,
    )

    deleted_entities = session.execute(deleted_query).scalars().all()

    # Add deleted entities to changes
    for deleted in deleted_entities:
        changes.append(
            ChangeInfo(
                entity_id=deleted.entity_id,
                entity_type=deleted.entity_type,
                change_type="deleted",
                data=deleted.data_snapshot,
                timestamp=deleted.deleted_at.isoformat(),
            )
        )

    return SyncChangesResponse(
        changes=changes,
        total=len(changes),
        server_timestamp=datetime.now(UTC).isoformat(),
    )


@router.post("/sync/operations", response_model=SyncOperationsResponse)
def apply_sync_operations(
    request: SyncOperationsRequest,
    session: DbSession,
    principal: Principal,
) -> SyncOperationsResponse:
    """
    Apply a batch of sync operations from the desktop client.

    Operations are applied in order. If a conflict is detected (server version is newer
    than client timestamp), the operation is skipped and added to the conflicts list.
    """
    applied_count = 0
    conflicts: list[ConflictInfo] = []

    for operation in request.operations:
        try:
            # Parse operation timestamp
            operation_timestamp = datetime.fromisoformat(operation.timestamp.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            # Skip operations with invalid timestamps
            continue

        if operation.entity_type == "offline_agent_run":
            if operation.type not in {"create", "update"} or not operation.data:
                continue
            if _apply_offline_agent_run(
                session=session,
                operation=operation,
                principal=principal,
                operation_timestamp=operation_timestamp,
            ):
                applied_count += 1
            else:
                conflicts.append(ConflictInfo(
                    entity_id=operation.entity_id,
                    entity_type=operation.entity_type,
                    server_version={},
                    client_version=operation.data,
                    operation_id=operation.operation_id,
                ))
            continue

        if operation.type == "create":
            # Create new task
            if not operation.data:
                continue

            new_task = Task(
                id=operation.entity_id,
                organization_id=None,
                created_by=principal.user_id,
                title=operation.data.get("title", ""),
                goal=operation.data.get("goal", ""),
                status=operation.data.get("status", "pending"),
                model_provider=operation.data.get("model_provider", "anthropic"),
                model_name=operation.data.get("model_name", "claude-opus-4"),
                created_at=operation_timestamp,
                updated_at=operation_timestamp,
            )
            session.add(new_task)
            applied_count += 1

        elif operation.type == "update":
            # Update existing task
            task = session.execute(
                select(Task).where(
                    Task.id == operation.entity_id,
                    Task.created_by == principal.user_id,
                )
            ).scalar_one_or_none()

            if not task:
                continue

            # Check for conflicts: if server version is newer, report conflict
            # Ensure both timestamps are timezone-aware for comparison
            server_updated_at = task.updated_at
            if server_updated_at.tzinfo is None:
                server_updated_at = server_updated_at.replace(tzinfo=UTC)

            # Ensure operation_timestamp is timezone-aware
            if operation_timestamp.tzinfo is None:
                operation_timestamp = operation_timestamp.replace(tzinfo=UTC)

            if server_updated_at > operation_timestamp:
                conflicts.append(
                    ConflictInfo(
                        entity_id=task.id,
                        entity_type="task",
                        server_version={
                            "id": task.id,
                            "title": task.title,
                            "goal": task.goal,
                            "status": task.status,
                            "updated_at": server_updated_at.isoformat(),
                        },
                        client_version=operation.data or {},
                        operation_id=operation.operation_id,
                    )
                )
                continue

            # Apply update
            if operation.data:
                for key, value in operation.data.items():
                    if hasattr(task, key):
                        setattr(task, key, value)
                task.updated_at = operation_timestamp
                applied_count += 1

        elif operation.type == "delete":
            # Delete task
            task = session.execute(
                select(Task).where(
                    Task.id == operation.entity_id,
                    Task.created_by == principal.user_id,
                )
            ).scalar_one_or_none()

            if task:
                # Record deletion for sync tracking
                deleted_entity = DeletedEntity(
                    entity_type="task",
                    entity_id=task.id,
                    deleted_by=principal.user_id,
                    deleted_at=operation_timestamp,
                    data_snapshot={
                        "id": task.id,
                        "title": task.title,
                        "goal": task.goal,
                        "status": task.status,
                        "created_at": task.created_at.isoformat(),
                        "updated_at": task.updated_at.isoformat(),
                        "completed_at": (
                            task.completed_at.isoformat() if task.completed_at else None
                        ),
                        "model_provider": task.model_provider,
                        "model_name": task.model_name,
                    },
                )
                session.add(deleted_entity)
                session.delete(task)
                applied_count += 1

    # Commit all changes
    session.commit()

    return SyncOperationsResponse(
        applied=applied_count,
        conflicts=conflicts,
    )


def _apply_offline_agent_run(
    *,
    session: Session,
    operation: SyncOperation,
    principal: Principal,
    operation_timestamp: datetime,
) -> bool:
    """Import a terminal Desktop Run snapshot without duplicating evidence on retry."""
    data = operation.data or {}
    run = data.get("run")
    events = data.get("events")
    model_calls = data.get("modelCalls")
    tool_calls = data.get("toolCalls")
    approvals = data.get("approvals")
    if not isinstance(run, dict) or run.get("id") != operation.entity_id:
        return False
    if not _is_uuid(operation.entity_id):
        return False
    if not isinstance(events, list) or not isinstance(model_calls, list):
        return False
    if not isinstance(tool_calls, list) or not isinstance(approvals, list):
        return False

    status = str(run.get("status", ""))
    if status not in {"COMPLETED", "FAILED", "CANCELLED"}:
        return False
    prompt = str(run.get("prompt", "")).strip()
    if not prompt or len(prompt) > 120_000:
        return False
    result = run.get("result")
    if result is not None and (not isinstance(result, str) or len(result) > 500_000):
        return False
    sync_revision = _offline_sync_revision(run.get("syncRevision"))
    if sync_revision is None:
        return False
    if not _offline_agent_snapshot_ownership_matches(
        session=session,
        run_id=operation.entity_id,
        principal=principal,
        events=events,
        model_calls=model_calls,
        tool_calls=tool_calls,
        approvals=approvals,
    ):
        return False

    task = session.get(Task, operation.entity_id)
    if task is not None:
        if (
            task.created_by != principal.user_id
            or task.organization_id != principal.organization_id
        ):
            return False
        snapshot = task.capability_snapshot_json or {}
        if snapshot.get("source") != "desktop-offline-agent":
            return False
        stored_revision = _offline_sync_revision(snapshot.get("sync_revision"))
        if stored_revision is None:
            return False
        if sync_revision < stored_revision:
            return False
        if sync_revision == stored_revision:
            return True
        task.title = prompt[:120]
        task.goal = _offline_agent_goal(prompt, result)
        task.status = status
        task.model_provider = str(run.get("modelProvider") or "desktop-offline")[:256]
        task.model_name = str(run.get("modelName") or "deterministic-v1")[:256]
        task.capability_snapshot_json = {
            "source": "desktop-offline-agent",
            "offline_run_id": operation.entity_id,
            "sync_revision": sync_revision,
        }
        task.updated_at = operation_timestamp
        task.completed_at = operation_timestamp
    else:
        task = Task(
            id=operation.entity_id,
            organization_id=principal.organization_id,
            agent_id=None,
            created_by=principal.user_id,
            title=prompt[:120],
            goal=_offline_agent_goal(prompt, result),
            status=status,
            model_provider=str(run.get("modelProvider") or "desktop-offline")[:256],
            model_name=str(run.get("modelName") or "deterministic-v1")[:256],
            max_runtime_seconds=3600,
            max_subagents=0,
            enable_sandbox=False,
            enable_network=False,
            capability_snapshot_json={
                "source": "desktop-offline-agent",
                "offline_run_id": operation.entity_id,
                "sync_revision": sync_revision,
            },
            created_at=operation_timestamp,
            updated_at=operation_timestamp,
            completed_at=operation_timestamp,
        )
        session.add(task)
        session.flush()

    agent_run = session.get(AgentRun, operation.entity_id)
    if agent_run is None:
        agent_run = AgentRun(
            id=operation.entity_id,
            task_id=task.id,
            agent_type="root",
            status=status,
            context_json={"source": "desktop-offline-agent"},
            capability_snapshot_json={"source": "desktop-offline-agent"},
            started_at=_parse_optional_timestamp(run.get("startedAt")) or operation_timestamp,
            completed_at=_parse_optional_timestamp(run.get("completedAt")) or operation_timestamp,
        )
        session.add(agent_run)
    else:
        agent_run.status = status
        agent_run.completed_at = (
            _parse_optional_timestamp(run.get("completedAt")) or operation_timestamp
        )

    for event in events[:2_000]:
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("id", ""))
        sequence = event.get("sequence")
        event_type = str(event.get("eventType", ""))
        if (
            not _is_uuid(event_id)
            or not isinstance(sequence, int)
            or sequence < 1
            or not event_type
        ):
            continue
        existing = session.get(AgentEvent, event_id)
        if existing is not None:
            continue
        sequence_existing = session.execute(
            select(AgentEvent).where(
                AgentEvent.task_id == task.id,
                AgentEvent.sequence == sequence,
            )
        ).scalar_one_or_none()
        if sequence_existing is not None:
            continue
        actor_type = str(event.get("actorType") or "system")
        if actor_type not in {"system", "user"}:
            actor_type = "system"
        session.add(AgentEvent(
            id=event_id,
            task_id=task.id,
            agent_run_id=agent_run.id,
            sequence=sequence,
            event_type=event_type[:128],
            payload_json=event.get("payload") if isinstance(event.get("payload"), dict) else {},
            actor_type=actor_type,
            created_at=_parse_optional_timestamp(event.get("createdAt")) or operation_timestamp,
        ))

    for model_call in model_calls[:200]:
        if not isinstance(model_call, dict):
            continue
        call_id = str(model_call.get("id", ""))
        if not _is_uuid(call_id) or session.get(ModelCall, call_id) is not None:
            continue
        call_status = str(model_call.get("status") or "SUCCESS")
        if call_status not in {"SUCCESS", "FAILED", "CANCELLED"}:
            continue
        session.add(ModelCall(
            id=call_id,
            task_id=task.id,
            agent_run_id=agent_run.id,
            model_provider=str(model_call.get("modelProvider") or "desktop-offline")[:256],
            model_name=str(model_call.get("modelName") or "deterministic-v1")[:256],
            status=call_status[:64],
            duration_ms=_nonnegative_int(model_call.get("durationMs")),
            prompt_tokens=0,
            completion_tokens=0,
            capability_snapshot_json={"source": "desktop-offline-agent"},
            model_request_sha256=str(model_call.get("requestSha256") or "")[:64] or None,
            model_request_hash_schema_version=2,
            request_message_hashes_json=[],
            hash_recomputability_status="offline_snapshot",
            attempt_index=1,
            terminal_status=call_status.lower(),
            request_json={"source": "desktop-offline-agent"},
            response_json=(
                {"text": model_call.get("responseText")}
                if model_call.get("responseText")
                else {}
            ),
            error_message=(
                str(model_call.get("errorMessage"))
                if model_call.get("errorMessage")
                else None
            ),
            created_at=(
                _parse_optional_timestamp(model_call.get("createdAt"))
                or operation_timestamp
            ),
        ))

    tool_call_ids: set[str] = set()
    for tool_call in tool_calls[:200]:
        if not isinstance(tool_call, dict):
            continue
        call_id = str(tool_call.get("id", ""))
        if not _is_uuid(call_id):
            continue
        tool_name = str(tool_call.get("toolName") or "")
        if tool_name not in {
            "workspace.list_files",
            "workspace.read_text",
            "workspace.write_text",
        }:
            continue
        input_json = tool_call.get("input") if isinstance(tool_call.get("input"), dict) else {}
        output_json = tool_call.get("output") if isinstance(tool_call.get("output"), dict) else {}
        tool_status = str(tool_call.get("status") or "FAILED")
        if tool_status not in {"PENDING", "RUNNING", "SUCCESS", "FAILED", "DENIED", "CANCELLED"}:
            continue
        risk_level = str(tool_call.get("riskLevel") or "LOW")
        if risk_level not in {"LOW", "HIGH"}:
            continue
        tool_call_ids.add(call_id)
        if session.get(ToolCall, call_id) is not None:
            continue
        session.add(ToolCall(
            id=call_id,
            task_id=task.id,
            agent_run_id=agent_run.id,
            tool_name=tool_name,
            status=tool_status,
            risk_level=risk_level,
            capability_snapshot_json={"source": "desktop-offline-agent"},
            requires_sandbox=False,
            duration_ms=_nonnegative_int(tool_call.get("durationMs")),
            input_json=input_json,
            output_json=output_json,
            error_message=(
                str(tool_call.get("errorMessage"))
                if tool_call.get("errorMessage")
                else None
            ),
            created_at=_parse_optional_timestamp(tool_call.get("createdAt")) or operation_timestamp,
        ))

    for approval in approvals[:200]:
        if not isinstance(approval, dict):
            continue
        approval_id = str(approval.get("id", ""))
        tool_call_id = str(approval.get("toolCallId", ""))
        if not _is_uuid(approval_id) or tool_call_id not in tool_call_ids:
            continue
        if session.get(ToolApproval, approval_id) is not None:
            continue
        approval_status = str(approval.get("status") or "PENDING")
        if approval_status not in {"PENDING", "APPROVED", "REJECTED", "CANCELLED"}:
            continue
        session.add(ToolApproval(
            id=approval_id,
            task_id=task.id,
            tool_call_id=tool_call_id,
            organization_id=principal.organization_id,
            requested_by=principal.user_id,
            decided_by=principal.user_id if approval.get("status") != "PENDING" else None,
            status=approval_status,
            risk_level="HIGH",
            reason=str(approval.get("reason") or "Desktop offline agent approval")[:500],
            request_json=(
                approval.get("request")
                if isinstance(approval.get("request"), dict)
                else {}
            ),
            decision_json=(
                approval.get("decision")
                if isinstance(approval.get("decision"), dict)
                else {}
            ),
            created_at=_parse_optional_timestamp(approval.get("createdAt")) or operation_timestamp,
            decided_at=_parse_optional_timestamp(approval.get("decidedAt")),
        ))
    return True


def _offline_agent_snapshot_ownership_matches(
    *,
    session: Session,
    run_id: str,
    principal: Principal,
    events: list,
    model_calls: list,
    tool_calls: list,
    approvals: list,
) -> bool:
    """Reject an offline snapshot before writes if any UUID belongs to another graph."""
    task = session.get(Task, run_id)
    if task is not None and (
        task.created_by != principal.user_id
        or task.organization_id != principal.organization_id
    ):
        return False

    agent_run = session.get(AgentRun, run_id)
    if agent_run is not None and (
        agent_run.task_id != run_id
        or task is None
        or task.organization_id != principal.organization_id
    ):
        return False

    evidence_models = (
        (events, AgentEvent),
        (model_calls, ModelCall),
        (tool_calls, ToolCall),
    )
    for evidence_items, model in evidence_models:
        for item in evidence_items:
            if not isinstance(item, dict):
                continue
            evidence_id = str(item.get("id", ""))
            if not _is_uuid(evidence_id):
                continue
            existing = session.get(model, evidence_id)
            if existing is not None and (
                existing.task_id != run_id
                or existing.agent_run_id != run_id
                or task is None
                or task.organization_id != principal.organization_id
            ):
                return False

    for approval in approvals:
        if not isinstance(approval, dict):
            continue
        approval_id = str(approval.get("id", ""))
        if not _is_uuid(approval_id):
            continue
        existing = session.get(ToolApproval, approval_id)
        if existing is None:
            continue
        expected_tool_call_id = str(approval.get("toolCallId", ""))
        existing_tool_call = session.get(ToolCall, existing.tool_call_id)
        if (
            existing.task_id != run_id
            or existing.organization_id != principal.organization_id
            or existing.tool_call_id != expected_tool_call_id
            or existing_tool_call is None
            or existing_tool_call.task_id != run_id
            or existing_tool_call.agent_run_id != run_id
        ):
            return False

    return True


def _offline_sync_revision(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _offline_agent_goal(prompt: str, result: object) -> str:
    result_text = result if isinstance(result, str) else ""
    return f"{prompt}\n\nDesktop offline result:\n{result_text}"[:600_000]


def _parse_optional_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _is_uuid(value: object) -> bool:
    try:
        return str(UUID(str(value))) == str(value).lower()
    except (ValueError, AttributeError, TypeError):
        return False


def _nonnegative_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0
