"""Agent capability and response helper functions."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *

def _resolve_agent_capability_attachment(
    *,
    request: AgentCapabilityAttachmentRequest,
    session: Session,
    principal: Principal,
) -> tuple[Capability, CapabilityVersion]:
    CapabilityRegistry(session, principal.organization_id).ensure_builtin_capabilities()
    if request.capability_version_id:
        version = session.get(CapabilityVersion, request.capability_version_id)
        if version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Capability version not found",
            )
        capability = _visible_capability_or_404(
            capability_id=version.capability_id,
            session=session,
            principal=principal,
        )
        accepted_ids = {
            capability.id,
            capability.capability_key,
            capability.capability_key.removeprefix("tool:"),
        }
        if request.capability_id not in accepted_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Capability version does not match capability_id",
            )
        return capability, version

    capability = _find_visible_capability(
        capability_ref=request.capability_id,
        session=session,
        principal=principal,
    )
    if capability is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capability not found")
    if not capability.current_version_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Capability has no current version",
        )
    version = session.get(CapabilityVersion, capability.current_version_id)
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Capability current version not found",
        )
    return capability, version


def _token_optimizer_manifest(preset_id: str) -> dict:
    config = TOKEN_OPTIMIZER_PRESETS[preset_id]
    return {
        "name": f"builtin-token-optimizer-{preset_id}",
        "version": "1.0.0",
        "description": config["description"],
        "package_type": "context_optimizer",
        "schema_version": "context-optimizer-v1",
        "display_name": config["display_name"],
        "risk_level": "low",
        "permissions": ["context:optimize"],
        "provenance": {"source": "builtin_preset", "preset_id": preset_id},
        "optimizer": config["optimizer"],
        "secret_refs": [],
    }


def _ensure_token_optimizer_preset_capability(
    *,
    preset_id: str,
    session: Session,
    principal: Principal,
) -> tuple[Capability, CapabilityVersion]:
    if preset_id not in TOKEN_OPTIMIZER_PRESETS or preset_id == "off":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown preset")
    capability_key = f"builtin:context-optimizer:{preset_id}"
    capability = session.execute(
        select(Capability).where(
            Capability.organization_id == principal.organization_id,
            Capability.capability_key == capability_key,
        )
    ).scalar_one_or_none()
    now = utc_now()
    if capability is None:
        capability = Capability(
            organization_id=principal.organization_id,
            capability_key=capability_key,
            type=CAPABILITY_TYPE_CONTEXT_OPTIMIZER,
            status="active",
            schema_version=1,
            created_by=principal.user_id,
            created_at=now,
            updated_at=now,
        )
        session.add(capability)
        session.flush()

    version = session.execute(
        select(CapabilityVersion).where(
            CapabilityVersion.capability_id == capability.id,
            CapabilityVersion.version == 1,
        )
    ).scalar_one_or_none()
    manifest = _token_optimizer_manifest(preset_id)
    content = {"package_manifest": manifest, "package_provenance": manifest["provenance"]}
    config = {
        "secret_refs": [],
        "permissions": manifest["permissions"],
        "source_kind": "builtin_preset",
        "source_uri": None,
        "pinned_ref": f"builtin:{preset_id}:v1",
        "package_id": f"builtin-context-optimizer-{preset_id}",
    }
    if version is None:
        version = CapabilityVersion(
            id=f"{capability.id}-v1",
            capability_id=capability.id,
            version=1,
            type=CAPABILITY_TYPE_CONTEXT_OPTIMIZER,
            status="active",
            content_json=content,
            config_json=config,
            content_sha256=stable_json_sha256(content),
            config_sha256=stable_json_sha256(config),
            schema_version=1,
            created_by=principal.user_id,
            created_at=now,
        )
        session.add(version)
        session.flush()
    capability.current_version_id = version.id
    capability.status = "active"
    capability.updated_at = now
    return capability, version


def _disable_agent_token_optimizer_attachments(
    *,
    agent: Agent,
    session: Session,
) -> str | None:
    disabled_id: str | None = None
    rows = list(
        session.execute(
            select(AgentCapabilityAttachment)
            .join(Capability, AgentCapabilityAttachment.capability_id == Capability.id)
            .where(
                AgentCapabilityAttachment.agent_id == agent.id,
                Capability.type == CAPABILITY_TYPE_CONTEXT_OPTIMIZER,
            )
        ).scalars()
    )
    for attachment in rows:
        attachment.enabled = False
        disabled_id = disabled_id or attachment.id
    return disabled_id


def _upsert_agent_token_optimizer_attachment(
    *,
    agent: Agent,
    capability: Capability,
    version: CapabilityVersion,
    session: Session,
    principal: Principal,
) -> AgentCapabilityAttachment:
    _disable_agent_token_optimizer_attachments(agent=agent, session=session)
    attachment = session.execute(
        select(AgentCapabilityAttachment).where(
            AgentCapabilityAttachment.agent_id == agent.id,
            AgentCapabilityAttachment.capability_version_id == version.id,
        )
    ).scalar_one_or_none()
    if attachment is None:
        attachment = AgentCapabilityAttachment(
            organization_id=agent.organization_id or principal.organization_id,
            agent_id=agent.id,
            capability_id=capability.id,
            capability_version_id=version.id,
            enabled=True,
            priority=TOKEN_OPTIMIZER_PRESET_PRIORITY,
            attached_by=principal.user_id,
            attached_at=utc_now(),
        )
        session.add(attachment)
        session.flush()
    else:
        attachment.enabled = True
        attachment.priority = TOKEN_OPTIMIZER_PRESET_PRIORITY
    return attachment


def _agent_response(agent: Agent, *, session: DbSession) -> AgentResponse:
    payload = AgentResponse.model_validate(agent)
    attachments = list(
        session.execute(
            select(AgentCapabilityAttachment, Capability, CapabilityVersion)
            .join(Capability, AgentCapabilityAttachment.capability_id == Capability.id)
            .join(
                CapabilityVersion,
                AgentCapabilityAttachment.capability_version_id == CapabilityVersion.id,
            )
            .where(AgentCapabilityAttachment.agent_id == agent.id)
            .order_by(
                AgentCapabilityAttachment.priority.asc(),
                AgentCapabilityAttachment.attached_at.asc(),
            )
        ).all()
    )
    payload.capability_attachments = [
        {
            "attachment_id": attachment.id,
            "capability_id": attachment.capability_id,
            "capability_key": capability.capability_key,
            "capability_version_id": attachment.capability_version_id,
            "capability_type": version.type,
            "enabled": attachment.enabled,
            "priority": attachment.priority,
            "status": capability.status,
        }
        for attachment, capability, version in attachments
    ]
    return payload


def _find_visible_capability(
    *,
    capability_ref: str,
    session: Session,
    principal: Principal,
) -> Capability | None:
    refs = {
        capability_ref,
        tool_capability_key(capability_ref),
    }
    return session.execute(
        select(Capability).where(
            or_(
                Capability.id == capability_ref,
                Capability.capability_key.in_(refs),
            ),
            or_(
                Capability.organization_id == principal.organization_id,
                Capability.organization_id.is_(None),
            ),
        )
    ).scalar_one_or_none()


def _visible_capability_or_404(
    *,
    capability_id: str,
    session: Session,
    principal: Principal,
) -> Capability:
    capability = session.execute(
        select(Capability).where(
            Capability.id == capability_id,
            or_(
                Capability.organization_id == principal.organization_id,
                Capability.organization_id.is_(None),
            ),
        )
    ).scalar_one_or_none()
    if capability is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capability not found")
    return capability


def _legacy_tool_name_for_capability(capability: Capability, fallback: str) -> str:
    if capability.capability_key.startswith("tool:"):
        return capability.capability_key.removeprefix("tool:")
    return fallback

__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
