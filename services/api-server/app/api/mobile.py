from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MobileDevice, utc_now
from app.db.session import get_db_session
from app.security.auth import Principal

router = APIRouter(prefix="/mobile", tags=["mobile"])

DbSession = Annotated[Session, Depends(get_db_session)]


class MobileDeviceRegisterRequest(BaseModel):
    platform: Literal["ios", "android"]
    push_token: str = Field(min_length=12, max_length=4096)
    device_name: str | None = Field(default=None, max_length=256)
    app_version: str | None = Field(default=None, max_length=64)
    notifications_enabled: bool = True
    preferences_json: dict[str, Any] = Field(default_factory=dict)


class MobileDeviceResponse(BaseModel):
    id: str
    user_id: str
    organization_id: str | None
    platform: str
    push_token: str
    device_name: str | None
    app_version: str | None
    notifications_enabled: bool
    preferences_json: dict[str, Any]
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime


class MobileDevicePage(BaseModel):
    items: list[MobileDeviceResponse]


@router.post("/devices", response_model=MobileDeviceResponse, status_code=201)
def register_mobile_device(
    request: MobileDeviceRegisterRequest,
    session: DbSession,
    principal: Principal,
) -> MobileDeviceResponse:
    now = utc_now()
    device = session.execute(
        select(MobileDevice).where(MobileDevice.push_token == request.push_token)
    ).scalar_one_or_none()
    if device is None:
        device = MobileDevice(
            user_id=principal.user_id,
            organization_id=principal.organization_id,
            platform=request.platform,
            push_token=request.push_token,
            created_at=now,
        )
        session.add(device)

    device.user_id = principal.user_id
    device.organization_id = principal.organization_id
    device.platform = request.platform
    device.device_name = request.device_name
    device.app_version = request.app_version
    device.notifications_enabled = request.notifications_enabled
    device.preferences_json = request.preferences_json
    device.last_seen_at = now
    device.updated_at = now
    session.commit()
    session.refresh(device)
    return _device_response(device)


@router.get("/devices", response_model=MobileDevicePage)
def list_mobile_devices(
    session: DbSession,
    principal: Principal,
) -> MobileDevicePage:
    devices = session.execute(
        select(MobileDevice)
        .where(MobileDevice.user_id == principal.user_id)
        .order_by(MobileDevice.last_seen_at.desc())
    ).scalars()
    return MobileDevicePage(items=[_device_response(device) for device in devices])


def _device_response(device: MobileDevice) -> MobileDeviceResponse:
    return MobileDeviceResponse(
        id=device.id,
        user_id=device.user_id,
        organization_id=device.organization_id,
        platform=device.platform,
        push_token=_redact_token(device.push_token),
        device_name=device.device_name,
        app_version=device.app_version,
        notifications_enabled=device.notifications_enabled,
        preferences_json=dict(device.preferences_json or {}),
        last_seen_at=_aware(device.last_seen_at),
        created_at=_aware(device.created_at),
        updated_at=_aware(device.updated_at),
    )


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _redact_token(value: str) -> str:
    if len(value) <= 12:
        return "***"
    return f"{value[:8]}...{value[-4:]}"
