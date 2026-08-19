import os
import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DeletedEntity, Task
from app.db.session import get_db_session
from app.security.auth import Principal

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


class SyncOperation(BaseModel):
    """A single operation to apply during sync."""

    type: Literal["create", "update", "delete"]
    entity_type: Literal["task"]
    entity_id: str
    data: dict | None = None
    timestamp: str


class SyncOperationsRequest(BaseModel):
    """Request to apply multiple operations."""

    operations: list[SyncOperation]


class ConflictInfo(BaseModel):
    """Information about a sync conflict."""

    entity_id: str
    entity_type: str
    server_version: dict
    client_version: dict


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
    Check Forge Harness Desktop update availability for stable or beta release channels.

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
