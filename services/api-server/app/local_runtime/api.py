from __future__ import annotations

import hmac
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.bootstrap.local_owner import resolve_local_principal
from app.core.config import get_settings, install_runtime_settings
from app.db.models import User
from app.db.session import get_db_session
from app.local_runtime.bootstrap import validate_model_base_url, validate_model_id
from app.local_runtime.web_bootstrap import WEB_BOOTSTRAP_STORE
from app.local_runtime.workspace_authorization import WORKSPACE_AUTHORIZATION_STORE
from app.security.jwt_utils import issue_access_token

LOCAL_SESSION_COOKIE = "harness_local_session"
MODEL_DISCOVERY_MAX_BYTES = 1024 * 1024
MODEL_DISCOVERY_TIMEOUT_SECONDS = 8.0
MODEL_DISCOVERY_USER_AGENT = "Harness-Desktop-Model-Discovery/1.0"

router = APIRouter(prefix="/local-runtime", tags=["local-runtime"])
DbSession = Annotated[Session, Depends(get_db_session)]


class ModelKeyRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=8192)


class ModelConfigRequest(BaseModel):
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = Field(default=None, max_length=8192)


class ModelConfigResponse(BaseModel):
    state: Literal["setup_required", "configured"]
    base_url: str
    model: str


class ModelDiscoveryRequest(BaseModel):
    base_url: str
    api_key: str | None = Field(default=None, max_length=8192)


class ModelDiscoveryResponse(BaseModel):
    models: list[str]
    latency_ms: int


class WebBootstrapIssueResponse(BaseModel):
    token: str
    expires_at: datetime
    intended_origin: str


class WebBootstrapExchangeRequest(BaseModel):
    token: str = Field(min_length=1, max_length=1024)


class WorkspaceAuthorizationRequest(BaseModel):
    profile_id: str = Field(min_length=1, max_length=128)
    root_path: str = Field(min_length=1, max_length=4096)


class WorkspaceAuthorizationResponse(BaseModel):
    authorization: str
    label: str
    expires_at: datetime


class LocalModelStateResponse(BaseModel):
    state: Literal["setup_required", "configured", "healthy", "error"]
    provider: str
    model: str
    base_url: str
    secret_storage: Literal["persistent", "session", "unavailable"]
    message: str | None = None


@router.get("/status")
def local_runtime_status() -> dict[str, str]:
    settings = _local_settings()
    return {
        "runtime": "ready",
        "model": "configured" if settings.ai_provider_api_key.strip() else "setup_required",
    }


@router.get("/model", response_model=LocalModelStateResponse)
def local_model_state() -> LocalModelStateResponse:
    settings = _local_settings()
    configured = bool(settings.ai_provider_api_key.strip())
    if settings.persistent_secret_storage_available:
        secret_storage = "persistent"
    elif configured:
        secret_storage = "session"
    else:
        secret_storage = "unavailable"
    return LocalModelStateResponse(
        state="configured" if configured else "setup_required",
        provider=settings.ai_provider_name,
        model=settings.ai_provider_model,
        base_url=settings.ai_provider_base_url,
        secret_storage=secret_storage,
        message=None if configured else "A model provider API key is required",
    )


@router.post("/desktop-session", status_code=status.HTTP_204_NO_CONTENT)
def create_desktop_session(
    response: Response,
    session: DbSession,
    bootstrap_token: Annotated[str | None, Header(alias="X-Harness-Desktop-Bootstrap")] = None,
) -> None:
    settings = _require_desktop_bootstrap(bootstrap_token)
    _local_user(session)
    _set_local_session_cookie(response, settings=settings, session=session)


@router.post("/workspace-authorization", response_model=WorkspaceAuthorizationResponse)
def issue_workspace_authorization(
    payload: WorkspaceAuthorizationRequest,
    session: DbSession,
    bootstrap_token: Annotated[str | None, Header(alias="X-Harness-Desktop-Bootstrap")] = None,
) -> WorkspaceAuthorizationResponse:
    settings = _require_desktop_bootstrap(bootstrap_token)
    candidate = Path(payload.root_path).expanduser()
    try:
        if candidate.is_symlink():
            raise OSError("symlink workspace roots are not allowed")
        root_path = candidate.resolve(strict=True)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Workspace root must be an existing non-symlink directory",
        ) from exc
    if not root_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Workspace root must be an existing non-symlink directory",
        )
    user, organization, _membership = resolve_local_principal(session)
    token, expires_at = WORKSPACE_AUTHORIZATION_STORE.issue(
        signing_secret=settings.local_desktop_bootstrap_token,
        user_id=user.id,
        organization_id=organization.id,
        profile_id=payload.profile_id,
        root_path=root_path,
        label=root_path.name or "workspace",
        ttl_seconds=300,
    )
    return WorkspaceAuthorizationResponse(
        authorization=token,
        label=root_path.name or "workspace",
        expires_at=expires_at,
    )


@router.put("/model-key")
def apply_model_key(
    payload: ModelKeyRequest,
    bootstrap_token: Annotated[str | None, Header(alias="X-Harness-Desktop-Bootstrap")] = None,
) -> dict[str, str]:
    settings = _require_desktop_bootstrap(bootstrap_token)
    install_runtime_settings(
        settings.model_copy(
            update={
                "ai_provider_api_key": payload.api_key,
                "model_gateway_api_key": payload.api_key,
            }
        )
    )
    return {"model": "configured"}


@router.put("/model-config", response_model=ModelConfigResponse)
def apply_model_config(
    payload: ModelConfigRequest,
    bootstrap_token: Annotated[str | None, Header(alias="X-Harness-Desktop-Bootstrap")] = None,
) -> ModelConfigResponse:
    settings = _require_desktop_bootstrap(bootstrap_token)
    base_url = settings.ai_provider_base_url
    model = settings.ai_provider_model
    updates: dict[str, object] = {}
    if payload.base_url is not None:
        try:
            base_url = validate_model_base_url(payload.base_url)
        except ValueError:
            _raise_typed_error(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "INVALID_MODEL_BASE_URL",
                "The model base URL is invalid",
            )
        updates.update(
            ai_provider_base_url=base_url,
            model_gateway_base_url=base_url,
        )
    if payload.model is not None:
        try:
            model = validate_model_id(payload.model)
        except ValueError:
            _raise_typed_error(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "INVALID_MODEL_ID",
                "The model ID is invalid",
            )
        updates.update(ai_provider_model=model, ai_provider_models=(model,))
    if payload.api_key is not None:
        updates.update(
            ai_provider_api_key=payload.api_key,
            model_gateway_api_key=payload.api_key,
        )
    updated = settings.model_copy(update=updates)
    install_runtime_settings(updated)
    return ModelConfigResponse(
        state="configured" if updated.ai_provider_api_key.strip() else "setup_required",
        base_url=base_url,
        model=model,
    )


@router.post("/model-discovery", response_model=ModelDiscoveryResponse)
def discover_models(
    payload: ModelDiscoveryRequest,
    bootstrap_token: Annotated[str | None, Header(alias="X-Harness-Desktop-Bootstrap")] = None,
) -> ModelDiscoveryResponse:
    settings = _require_desktop_bootstrap(bootstrap_token)
    try:
        base_url = validate_model_base_url(payload.base_url)
    except ValueError:
        _raise_typed_error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_MODEL_BASE_URL",
            "The model base URL is invalid",
        )
    supplied_key = payload.api_key.strip() if payload.api_key is not None else ""
    api_key = supplied_key or settings.ai_provider_api_key.strip()
    if not api_key:
        _raise_typed_error(
            status.HTTP_400_BAD_REQUEST,
            "MODEL_API_KEY_REQUIRED",
            "A model provider API key is required for discovery",
        )

    started = time.monotonic()
    try:
        with httpx.Client(
            timeout=MODEL_DISCOVERY_TIMEOUT_SECONDS,
            trust_env=False,
            follow_redirects=False,
        ) as client:
            with client.stream(
                "GET",
                f"{base_url}/models",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": MODEL_DISCOVERY_USER_AGENT,
                },
            ) as response:
                if response.status_code in {
                    status.HTTP_401_UNAUTHORIZED,
                    status.HTTP_403_FORBIDDEN,
                }:
                    _raise_typed_error(
                        status.HTTP_502_BAD_GATEWAY,
                        "MODEL_DISCOVERY_AUTH_ERROR",
                        "The model provider rejected the API key",
                    )
                if response.status_code < 200 or response.status_code >= 300:
                    _raise_typed_error(
                        status.HTTP_502_BAD_GATEWAY,
                        "MODEL_DISCOVERY_UPSTREAM_ERROR",
                        "The model provider returned an unexpected status",
                    )
                body = _read_discovery_body(response)
    except HTTPException:
        raise
    except httpx.TimeoutException:
        _raise_typed_error(
            status.HTTP_504_GATEWAY_TIMEOUT,
            "MODEL_DISCOVERY_TIMEOUT",
            "The model provider request timed out",
        )
    except httpx.RequestError:
        _raise_typed_error(
            status.HTTP_502_BAD_GATEWAY,
            "MODEL_DISCOVERY_UPSTREAM_ERROR",
            "The model provider request failed",
        )

    models = _parse_discovery_models(body)
    latency_ms = max(0, round((time.monotonic() - started) * 1000))
    return ModelDiscoveryResponse(models=models, latency_ms=latency_ms)


@router.delete("/model-key")
def delete_model_key(
    bootstrap_token: Annotated[str | None, Header(alias="X-Harness-Desktop-Bootstrap")] = None,
) -> dict[str, str]:
    settings = _require_desktop_bootstrap(bootstrap_token)
    install_runtime_settings(
        settings.model_copy(update={"ai_provider_api_key": "", "model_gateway_api_key": ""})
    )
    return {"model": "setup_required"}


@router.post("/web-bootstrap", response_model=WebBootstrapIssueResponse)
def issue_web_bootstrap(
    request: Request,
    session: DbSession,
    bootstrap_token: Annotated[str | None, Header(alias="X-Harness-Desktop-Bootstrap")] = None,
) -> WebBootstrapIssueResponse:
    settings = _local_settings()
    if bootstrap_token is not None:
        _require_desktop_bootstrap(bootstrap_token)
    else:
        _require_local_cookie_principal(request, session)
    intended_origin = str(settings.api_base_url).rstrip("/")
    user, organization, _membership = resolve_local_principal(session)
    token, expires_at = WEB_BOOTSTRAP_STORE.issue(
        user_id=user.id,
        organization_id=organization.id,
        intended_origin=intended_origin,
        ttl_seconds=settings.local_web_bootstrap_ttl_seconds,
    )
    return WebBootstrapIssueResponse(
        token=token,
        expires_at=expires_at,
        intended_origin=intended_origin,
    )


@router.post("/web/bootstrap/exchange", status_code=status.HTTP_204_NO_CONTENT)
@router.post(
    "/web-bootstrap/exchange",
    status_code=status.HTTP_204_NO_CONTENT,
    include_in_schema=False,
)
def exchange_web_bootstrap(
    payload: WebBootstrapExchangeRequest,
    request: Request,
    response: Response,
    session: DbSession,
) -> None:
    settings = _local_settings()
    origin = request.headers.get("origin")
    expected_origin = str(settings.api_base_url).rstrip("/")
    if origin != expected_origin or request.headers.get("host") != urlsplit(expected_origin).netloc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    grant = WEB_BOOTSTRAP_STORE.consume(payload.token, origin=origin)
    if grant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bootstrap token",
        )
    user, organization, _membership = resolve_local_principal(session)
    if grant.user_id != user.id or grant.organization_id != organization.id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bootstrap token",
        )
    _local_user(session)
    _set_local_session_cookie(response, settings=settings, session=session)


def _local_settings():
    settings = get_settings()
    if settings.runtime_profile != "local":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return settings


def _read_discovery_body(response: httpx.Response) -> bytes:
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError:
            declared_size = 0
        if declared_size > MODEL_DISCOVERY_MAX_BYTES:
            _raise_typed_error(
                status.HTTP_413_CONTENT_TOO_LARGE,
                "MODEL_DISCOVERY_RESPONSE_TOO_LARGE",
                "The model provider response exceeded 1 MiB",
            )
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > MODEL_DISCOVERY_MAX_BYTES:
            _raise_typed_error(
                status.HTTP_413_CONTENT_TOO_LARGE,
                "MODEL_DISCOVERY_RESPONSE_TOO_LARGE",
                "The model provider response exceeded 1 MiB",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _parse_discovery_models(body: bytes) -> list[str]:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        _raise_invalid_discovery_response()
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        _raise_invalid_discovery_response()
    models: list[str] = []
    for entry in payload["data"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            _raise_invalid_discovery_response()
        try:
            model = validate_model_id(entry["id"])
        except ValueError:
            _raise_invalid_discovery_response()
        if model not in models:
            models.append(model)
    return models


def _raise_invalid_discovery_response() -> None:
    _raise_typed_error(
        status.HTTP_502_BAD_GATEWAY,
        "MODEL_DISCOVERY_INVALID_RESPONSE",
        "The model provider returned an invalid model list",
    )


def _raise_typed_error(status_code: int, code: str, message: str) -> None:
    raise HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _require_desktop_bootstrap(bootstrap_token: str | None):
    settings = _local_settings()
    expected = settings.local_desktop_bootstrap_token
    valid = (
        bootstrap_token is not None
        and expected
        and hmac.compare_digest(
            bootstrap_token,
            expected,
        )
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bootstrap token",
        )
    return settings


def _require_local_cookie_principal(request: Request, session: Session) -> None:
    token = request.cookies.get(LOCAL_SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    from app.security.auth import _principal_from_jwt

    principal = _principal_from_jwt(token, session)
    user, organization, _membership = resolve_local_principal(session)
    if principal.user_id != user.id or principal.organization_id != organization.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


def _local_user(session: Session) -> User:
    user, _organization, _membership = resolve_local_principal(session)
    if user is None or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local owner is not ready",
        )
    return user


def _set_local_session_cookie(response: Response, *, settings, session: Session) -> None:
    user, organization, membership = resolve_local_principal(session)
    token = issue_access_token(
        user_id=user.id,
        organization_id=organization.id,
        role=membership.role,
    )
    response.set_cookie(
        key=LOCAL_SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=False,
        samesite="strict",
        path="/",
        max_age=settings.auth_access_token_minutes * 60,
    )
