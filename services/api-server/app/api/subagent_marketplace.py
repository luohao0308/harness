from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.specialists import (
    SpecialistValidationError,
    normalize_budget,
    validate_output_schema,
)
from app.api.schemas import (
    SpecialistInstallationResponse,
    SpecialistMarketplaceApproveRequest,
    SpecialistMarketplaceInstallRequest,
    SpecialistMarketplaceListingCreateRequest,
    SpecialistMarketplaceListingPage,
    SpecialistMarketplaceListingResponse,
    SpecialistMarketplaceListingUpdateRequest,
)
from app.api.subagent_specialists import _to_specialist_response
from app.db.models import (
    Capability,
    SpecialistInstallation,
    SpecialistMarketplaceListing,
    SubagentSpecialist,
    utc_now,
)
from app.db.session import get_db_session
from app.security.auth import Principal, require_role
from app.tools.capabilities import CapabilityRegistry, tool_capability_key
from app.tools.registry import ToolRegistry

router = APIRouter(prefix="/subagent-marketplace", tags=["subagent-marketplace"])
DbSession = Annotated[Session, Depends(get_db_session)]

MARKETPLACE_SIGNATURE_SECRET_ENV = "SPECIALIST_MARKETPLACE_HMAC_SECRET"
DEFAULT_SIGNATURE_SECRET = "harness-specialist-marketplace-dev-secret"
SENSITIVE_PROMPT_TERMS = {
    "ignore previous instructions",
    "developer message",
    "system message",
    "泄露密钥",
    "忽略以上",
    "覆盖系统",
    "bypass policy",
    "disable guardrail",
}


@router.get(
    "/listings",
    response_model=SpecialistMarketplaceListingPage,
    summary="浏览子 Agent 专家市场",
)
def list_marketplace_listings(
    session: DbSession,
    principal: Principal,
    include_unverified: bool = Query(default=False, description="admin 可查看待审核 listing"),
) -> SpecialistMarketplaceListingPage:
    statement = select(SpecialistMarketplaceListing).order_by(
        SpecialistMarketplaceListing.verified.desc(),
        SpecialistMarketplaceListing.download_count.desc(),
        SpecialistMarketplaceListing.updated_at.desc(),
    )
    if not include_unverified or "admin" not in principal.roles:
        statement = statement.where(SpecialistMarketplaceListing.verified.is_(True))
    listings = list(session.execute(statement).scalars())
    installs = _installations_for_org(session, principal.organization_id)
    return SpecialistMarketplaceListingPage(
        items=[_to_listing_response(listing, installs) for listing in listings],
        next_cursor=None,
    )


@router.post(
    "/listings",
    response_model=SpecialistMarketplaceListingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="发布子 Agent 专家到市场",
)
def create_marketplace_listing(
    request: SpecialistMarketplaceListingCreateRequest,
    session: DbSession,
    principal: Principal,
) -> SpecialistMarketplaceListingResponse:
    require_role(principal, {"admin", "engineer"})
    _validate_manifest(session, request.manifest_json)
    _verify_signature(request.manifest_json, request.signature)
    now = utc_now()
    listing = SpecialistMarketplaceListing(
        slug=request.slug,
        display_name=request.display_name,
        description=request.description,
        author_org_id=principal.organization_id,
        author_name=request.author_name,
        version=request.version,
        manifest_json=request.manifest_json,
        signature=request.signature,
        verified=False,
        download_count=0,
        created_at=now,
        updated_at=now,
    )
    session.add(listing)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="专家市场 slug 已存在",
        ) from exc
    session.refresh(listing)
    return _to_listing_response(listing, {})


@router.get(
    "/listings/{listing_id}",
    response_model=SpecialistMarketplaceListingResponse,
    summary="查询专家市场 listing 详情",
)
def get_marketplace_listing(
    listing_id: str,
    session: DbSession,
    principal: Principal,
) -> SpecialistMarketplaceListingResponse:
    listing = _get_listing(session, listing_id)
    if (
        not listing.verified
        and "admin" not in principal.roles
        and listing.author_org_id != principal.organization_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="专家市场条目未找到")
    installs = _installations_for_org(session, principal.organization_id)
    return _to_listing_response(listing, installs)


@router.patch(
    "/listings/{listing_id}",
    response_model=SpecialistMarketplaceListingResponse,
    summary="更新专家市场 listing（不修改审核状态）",
)
def update_marketplace_listing(
    listing_id: str,
    request: SpecialistMarketplaceListingUpdateRequest,
    session: DbSession,
    principal: Principal,
) -> SpecialistMarketplaceListingResponse:
    require_role(principal, {"admin", "engineer"})
    listing = _get_listing(session, listing_id)
    if listing.author_org_id != principal.organization_id and "admin" not in principal.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能更新本组织发布的 listing",
        )
    updates = request.model_dump(exclude_unset=True)
    manifest = updates.get("manifest_json") or listing.manifest_json
    signature = updates.get("signature") or listing.signature
    if "manifest_json" in updates or "signature" in updates:
        _validate_manifest(session, manifest)
        _verify_signature(manifest, signature)
    requires_review = any(
        updates.get(key) is not None and updates.get(key) != getattr(listing, key)
        for key in {"manifest_json", "signature", "version"}
        if key in updates
    )
    for key, value in updates.items():
        if value is not None:
            setattr(listing, key, value)
    if requires_review:
        listing.verified = False
    listing.updated_at = utc_now()
    session.commit()
    session.refresh(listing)
    return _to_listing_response(listing, _installations_for_org(session, principal.organization_id))


@router.post(
    "/listings/{listing_id}/approve",
    response_model=SpecialistMarketplaceListingResponse,
    summary="审核专家市场 listing",
)
def approve_marketplace_listing(
    listing_id: str,
    request: SpecialistMarketplaceApproveRequest,
    session: DbSession,
    principal: Principal,
) -> SpecialistMarketplaceListingResponse:
    require_role(principal, {"admin"})
    listing = _get_listing(session, listing_id)
    _validate_manifest(session, listing.manifest_json)
    _verify_signature(listing.manifest_json, listing.signature)
    listing.verified = request.verified
    listing.updated_at = utc_now()
    session.commit()
    session.refresh(listing)
    return _to_listing_response(listing, _installations_for_org(session, principal.organization_id))


@router.post(
    "/listings/{listing_id}/install",
    response_model=SpecialistInstallationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="安装专家市场 listing 到当前组织",
)
def install_marketplace_listing(
    listing_id: str,
    request: SpecialistMarketplaceInstallRequest,
    session: DbSession,
    principal: Principal,
) -> SpecialistInstallationResponse:
    require_role(principal, {"admin", "engineer"})
    listing = _get_listing(session, listing_id)
    if not listing.verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="listing 尚未通过审核")
    existing = session.execute(
        select(SpecialistInstallation).where(
            SpecialistInstallation.listing_id == listing.id,
            SpecialistInstallation.installed_org_id == principal.organization_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该专家已安装")
    _validate_manifest(session, listing.manifest_json)
    _verify_signature(listing.manifest_json, listing.signature)
    specialist = _specialist_from_manifest(
        session=session,
        manifest=listing.manifest_json,
        organization_id=principal.organization_id,
        created_by=principal.user_id,
        listing=listing,
    )
    session.add(specialist)
    session.flush()
    installation = SpecialistInstallation(
        listing_id=listing.id,
        installed_org_id=principal.organization_id,
        installed_specialist_id=specialist.id,
        installed_version=listing.version,
        auto_update_enabled=request.auto_update_enabled,
        installed_at=utc_now(),
    )
    listing.download_count += 1
    session.add(installation)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该专家已安装") from exc
    session.refresh(installation)
    return _to_installation_response(installation)


@router.delete(
    "/installations/{installation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="卸载已安装的市场专家",
)
def uninstall_marketplace_listing(
    installation_id: str,
    session: DbSession,
    principal: Principal,
) -> None:
    require_role(principal, {"admin", "engineer"})
    installation = session.get(SpecialistInstallation, installation_id)
    if installation is None or installation.installed_org_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="安装记录未找到")
    specialist = session.get(SubagentSpecialist, installation.installed_specialist_id)
    session.delete(installation)
    if specialist is not None:
        specialist.status = "ARCHIVED"
        specialist.updated_at = utc_now()
    session.commit()


def marketplace_signature(manifest: dict) -> str:
    payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    secret = os.getenv(MARKETPLACE_SIGNATURE_SECRET_ENV) or DEFAULT_SIGNATURE_SECRET
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"hmac-sha256:{digest}"


def _verify_signature(manifest: dict, signature: str) -> None:
    expected = marketplace_signature(manifest)
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="专家 manifest 签名无效",
        )


def _validate_manifest(session: Session, manifest: dict) -> None:
    if not isinstance(manifest, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="manifest 必须是对象",
        )
    schema = manifest.get("output_schema_json")
    budget = manifest.get("budget_json")
    try:
        validate_output_schema(schema if isinstance(schema, dict) else {})
        normalize_budget(budget if isinstance(budget, dict) else {})
    except SpecialistValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    prompt = str(manifest.get("system_prompt") or "").casefold()
    for term in SENSITIVE_PROMPT_TERMS:
        if term.casefold() in prompt:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"system_prompt 命中安全黑名单: {term}",
            )
    unknown_capabilities = sorted(
        set(_string_list(manifest.get("capability_slugs_json"))) - _known_capability_slugs(session)
    )
    if unknown_capabilities:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="未知 capability: " + ", ".join(unknown_capabilities),
        )


def _known_capability_slugs(session: Session) -> set[str]:
    CapabilityRegistry(session, None).ensure_builtin_capabilities()
    keys = {
        str(key)
        for key in session.execute(select(Capability.capability_key)).scalars()
        if isinstance(key, str)
    }
    tool_names = {metadata.name for metadata in ToolRegistry.default().list_tools()}
    return keys | tool_names | {tool_capability_key(name) for name in tool_names}


def _specialist_from_manifest(
    *,
    session: Session,
    manifest: dict,
    organization_id: str,
    created_by: str,
    listing: SpecialistMarketplaceListing,
) -> SubagentSpecialist:
    base_slug = str(manifest.get("slug") or listing.slug).strip()[:64]
    slug = _available_specialist_slug(session, organization_id, base_slug)
    raw_budget = manifest.get("budget_json")
    budget = raw_budget if isinstance(raw_budget, dict) else {}
    return SubagentSpecialist(
        organization_id=organization_id,
        slug=slug,
        display_name=str(manifest.get("display_name") or listing.display_name),
        description=str(manifest.get("description") or listing.description),
        role=str(manifest.get("role") or "specialist")[:32],
        system_prompt=str(manifest.get("system_prompt") or "Return JSON matching the schema."),
        capability_slugs_json=_string_list(manifest.get("capability_slugs_json")),
        output_schema_json=dict(manifest.get("output_schema_json") or {}),
        budget_json=normalize_budget(budget),
        trigger_keywords_json=_string_list(manifest.get("trigger_keywords_json")),
        visibility="org",
        status="ACTIVE",
        created_by=created_by,
        created_at=utc_now(),
        updated_at=utc_now(),
    )


def _available_specialist_slug(session: Session, organization_id: str, slug: str) -> str:
    normalized = slug or "marketplace-specialist"
    existing = {
        value
        for value in session.execute(
            select(SubagentSpecialist.slug).where(
                SubagentSpecialist.organization_id == organization_id,
            )
        ).scalars()
    }
    if normalized not in existing:
        return normalized
    suffix = 2
    while f"{normalized[:55]}-{suffix}" in existing:
        suffix += 1
    return f"{normalized[:55]}-{suffix}"


def _get_listing(session: Session, listing_id: str) -> SpecialistMarketplaceListing:
    listing = session.get(SpecialistMarketplaceListing, listing_id)
    if listing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="专家市场条目未找到")
    return listing


def _installations_for_org(
    session: Session,
    organization_id: str,
) -> dict[str, SpecialistInstallation]:
    rows = list(
        session.execute(
            select(SpecialistInstallation).where(
                SpecialistInstallation.installed_org_id == organization_id,
            )
        ).scalars()
    )
    return {row.listing_id: row for row in rows}


def _to_listing_response(
    listing: SpecialistMarketplaceListing,
    installations: dict[str, SpecialistInstallation],
) -> SpecialistMarketplaceListingResponse:
    installation = installations.get(listing.id)
    return SpecialistMarketplaceListingResponse(
        id=listing.id,
        slug=listing.slug,
        display_name=listing.display_name,
        description=listing.description,
        author_org_id=listing.author_org_id,
        author_name=listing.author_name,
        version=listing.version,
        manifest_json=listing.manifest_json,
        signature=listing.signature,
        verified=listing.verified,
        download_count=listing.download_count,
        installed=installation is not None,
        installed_specialist_id=(
            installation.installed_specialist_id if installation is not None else None
        ),
        created_at=listing.created_at,
        updated_at=listing.updated_at,
    )


def _to_installation_response(
    installation: SpecialistInstallation,
) -> SpecialistInstallationResponse:
    specialist = installation.installed_specialist
    return SpecialistInstallationResponse(
        id=installation.id,
        listing_id=installation.listing_id,
        installed_org_id=installation.installed_org_id,
        installed_specialist_id=installation.installed_specialist_id,
        installed_version=installation.installed_version,
        auto_update_enabled=installation.auto_update_enabled,
        installed_at=installation.installed_at,
        specialist=_to_specialist_response(specialist) if specialist is not None else None,
    )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]
