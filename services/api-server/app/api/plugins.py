from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SystemSetting, utc_now
from app.db.session import get_db_session
from app.security.auth import AuthenticatedPrincipal, Principal, require_role

router = APIRouter(prefix="/plugins", tags=["plugins"])
DbSession = Annotated[Session, Depends(get_db_session)]

PLUGIN_SETTINGS_KEY = "plugins.phase6"
PROMPT_TEMPLATE_SETTINGS_KEY = "prompt_templates.phase6"


class PluginMarketplaceItem(BaseModel):
    id: str = Field(description="Stable plugin marketplace id")
    name: str = Field(description="Display name")
    description: str = Field(description="What the plugin adds to Harness")
    category: Literal["tool", "prompt", "workflow", "local-model"]
    publisher: str = Field(description="Plugin publisher")
    version: str = Field(description="Marketplace version")
    permissions: list[str] = Field(default_factory=list)
    install_state: Literal["available", "installed"] = "available"
    installed_at: str | None = None
    config_json: dict = Field(default_factory=dict)


class PluginMarketplaceResponse(BaseModel):
    items: list[PluginMarketplaceItem] = Field(description="Marketplace plugin entries")
    installed_count: int = Field(description="Installed plugins for this organization")


class PluginInstallRequest(BaseModel):
    enabled: bool = True
    config_json: dict = Field(default_factory=dict)


class PromptTemplate(BaseModel):
    id: str
    name: str
    description: str
    body: str
    tags: list[str] = Field(default_factory=list)
    source: Literal["built-in", "custom", "plugin"] = "custom"
    plugin_id: str | None = None
    updated_at: str | None = None


class PromptTemplateRequest(BaseModel):
    id: str | None = Field(default=None, min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    body: str = Field(min_length=1, max_length=12000)
    tags: list[str] = Field(default_factory=list)


class PromptTemplateResponse(BaseModel):
    items: list[PromptTemplate]


_CURATED_PLUGINS: list[PluginMarketplaceItem] = [
    PluginMarketplaceItem(
        id="github-tools",
        name="GitHub 工具集",
        description="把 issue、PR 和代码搜索作为受策略约束的第三方工具接入 Agent Run。",
        category="tool",
        publisher="Harness",
        version="1.0.0",
        permissions=["tool:github.search", "tool:github.issue"],
        config_json={"tool_names": ["github.search", "github.issue"]},
    ),
    PluginMarketplaceItem(
        id="release-prompt-pack",
        name="发布审查 Prompt 包",
        description="安装一组面向发布检查、回归摘要和事故复盘的 Prompt 模板。",
        category="prompt",
        publisher="Harness",
        version="1.0.0",
        permissions=["prompt:read", "prompt:write"],
        config_json={"template_ids": ["release-readiness", "incident-review"]},
    ),
    PluginMarketplaceItem(
        id="offline-local-model",
        name="离线本地模型连接器",
        description="为桌面端提供可选本地模型推理配置，在线恢复后仍保留审计线索。",
        category="local-model",
        publisher="Harness",
        version="0.1.0",
        permissions=["local-model:invoke"],
        config_json={"provider": "ollama", "base_url": "http://127.0.0.1:11434"},
    ),
]

_BUILT_IN_PROMPTS: list[PromptTemplate] = [
    PromptTemplate(
        id="release-readiness",
        name="发布审查",
        description="检查 Run 证据、回归风险和未完成验证。",
        body="请基于当前 Run 证据列出发布风险、缺失验证和建议的下一步。",
        tags=["release", "review"],
        source="built-in",
    ),
    PromptTemplate(
        id="incident-review",
        name="事故复盘",
        description="把错误事件转成面向行动的复盘草稿。",
        body="请整理事故时间线、影响范围、根因假设、已采取动作和后续预防项。",
        tags=["incident", "ops"],
        source="built-in",
    ),
]


@router.get("/marketplace", response_model=PluginMarketplaceResponse)
def list_plugin_marketplace(
    session: DbSession,
    principal: Principal,
) -> PluginMarketplaceResponse:
    installed = _read_plugin_installations(session, principal.organization_id)
    items = []
    for item in _CURATED_PLUGINS:
        install = installed.get(item.id)
        payload = item.model_dump()
        if install is not None and install.get("enabled", True):
            payload["install_state"] = "installed"
            payload["installed_at"] = install.get("installed_at")
            install_config = (
                install.get("config_json")
                if isinstance(install.get("config_json"), dict)
                else {}
            )
            payload["config_json"] = {
                **item.config_json,
                **install_config,
            }
        items.append(PluginMarketplaceItem(**payload))
    return PluginMarketplaceResponse(
        items=items,
        installed_count=sum(1 for item in installed.values() if item.get("enabled", True)),
    )


@router.post("/marketplace/{plugin_id}/install", response_model=PluginMarketplaceItem)
def install_plugin(
    plugin_id: str,
    request: PluginInstallRequest,
    session: DbSession,
    principal: Principal,
) -> PluginMarketplaceItem:
    require_role(principal, {"admin", "engineer"})
    plugin = _curated_plugin(plugin_id)
    installed = _read_plugin_installations(session, principal.organization_id)
    now = utc_now().isoformat()
    installed[plugin_id] = {
        "enabled": request.enabled,
        "installed_at": now,
        "updated_at": now,
        "installed_by": principal.user_id,
        "config_json": request.config_json,
    }
    _write_setting(session, principal, PLUGIN_SETTINGS_KEY, {"installations": installed})
    _install_plugin_prompt_templates(session, principal, plugin_id)
    session.commit()
    payload = plugin.model_dump()
    payload["install_state"] = "installed"
    payload["installed_at"] = now
    payload["config_json"] = {**plugin.config_json, **request.config_json}
    return PluginMarketplaceItem(**payload)


@router.delete("/marketplace/{plugin_id}/install", response_model=PluginMarketplaceItem)
def uninstall_plugin(
    plugin_id: str,
    session: DbSession,
    principal: Principal,
) -> PluginMarketplaceItem:
    require_role(principal, {"admin", "engineer"})
    plugin = _curated_plugin(plugin_id)
    installed = _read_plugin_installations(session, principal.organization_id)
    if plugin_id in installed:
        installed[plugin_id]["enabled"] = False
        installed[plugin_id]["updated_at"] = utc_now().isoformat()
        installed[plugin_id]["updated_by"] = principal.user_id
    _write_setting(session, principal, PLUGIN_SETTINGS_KEY, {"installations": installed})
    session.commit()
    return plugin


@router.get("/prompt-templates", response_model=PromptTemplateResponse)
def list_prompt_templates(
    session: DbSession,
    principal: Principal,
) -> PromptTemplateResponse:
    custom_templates = _read_prompt_templates(session, principal.organization_id)
    return PromptTemplateResponse(items=[*_BUILT_IN_PROMPTS, *custom_templates])


@router.post("/prompt-templates", response_model=PromptTemplate)
def create_prompt_template(
    request: PromptTemplateRequest,
    session: DbSession,
    principal: Principal,
) -> PromptTemplate:
    require_role(principal, {"admin", "engineer"})
    templates = _read_prompt_templates(session, principal.organization_id)
    template_id = _normalize_template_id(request.id or request.name)
    if any(template.id == template_id for template in [*_BUILT_IN_PROMPTS, *templates]):
        raise HTTPException(status_code=409, detail="prompt template id already exists")
    template = PromptTemplate(
        id=template_id,
        name=request.name,
        description=request.description,
        body=request.body,
        tags=request.tags,
        source="custom",
        updated_at=utc_now().isoformat(),
    )
    _write_prompt_templates(session, principal, [*templates, template])
    session.commit()
    return template


@router.put("/prompt-templates/{template_id}", response_model=PromptTemplate)
def update_prompt_template(
    template_id: str,
    request: PromptTemplateRequest,
    session: DbSession,
    principal: Principal,
) -> PromptTemplate:
    require_role(principal, {"admin", "engineer"})
    templates = _read_prompt_templates(session, principal.organization_id)
    for index, template in enumerate(templates):
        if template.id == template_id:
            updated = PromptTemplate(
                id=template_id,
                name=request.name,
                description=request.description,
                body=request.body,
                tags=request.tags,
                source=template.source,
                plugin_id=template.plugin_id,
                updated_at=utc_now().isoformat(),
            )
            templates[index] = updated
            _write_prompt_templates(session, principal, templates)
            session.commit()
            return updated
    raise HTTPException(status_code=404, detail="prompt template not found")


@router.delete("/prompt-templates/{template_id}", response_model=PromptTemplateResponse)
def delete_prompt_template(
    template_id: str,
    session: DbSession,
    principal: Principal,
) -> PromptTemplateResponse:
    require_role(principal, {"admin", "engineer"})
    templates = _read_prompt_templates(session, principal.organization_id)
    remaining = [template for template in templates if template.id != template_id]
    if len(remaining) == len(templates):
        raise HTTPException(status_code=404, detail="prompt template not found")
    _write_prompt_templates(session, principal, remaining)
    session.commit()
    return PromptTemplateResponse(items=[*_BUILT_IN_PROMPTS, *remaining])


def _curated_plugin(plugin_id: str) -> PluginMarketplaceItem:
    for plugin in _CURATED_PLUGINS:
        if plugin.id == plugin_id:
            return plugin
    raise HTTPException(status_code=404, detail="plugin not found")


def _read_setting(session: Session, organization_id: str, key: str) -> dict:
    setting = session.execute(
        select(SystemSetting).where(
            SystemSetting.organization_id == organization_id,
            SystemSetting.key == key,
        )
    ).scalar_one_or_none()
    if setting is not None and isinstance(setting.value_json, dict):
        return setting.value_json
    return {}


def _write_setting(
    session: Session,
    principal: AuthenticatedPrincipal,
    key: str,
    value: dict,
) -> None:
    setting = session.execute(
        select(SystemSetting).where(
            SystemSetting.organization_id == principal.organization_id,
            SystemSetting.key == key,
        )
    ).scalar_one_or_none()
    if setting is None:
        session.add(
            SystemSetting(
                organization_id=principal.organization_id,
                key=key,
                value_json=value,
                updated_by=principal.user_id,
                updated_at=utc_now(),
            )
        )
        return
    setting.value_json = value
    setting.updated_by = principal.user_id
    setting.updated_at = utc_now()


def _read_plugin_installations(session: Session, organization_id: str) -> dict:
    value = _read_setting(session, organization_id, PLUGIN_SETTINGS_KEY)
    installations = value.get("installations")
    return dict(installations) if isinstance(installations, dict) else {}


def _read_prompt_templates(session: Session, organization_id: str) -> list[PromptTemplate]:
    value = _read_setting(session, organization_id, PROMPT_TEMPLATE_SETTINGS_KEY)
    raw_items = value.get("items")
    if not isinstance(raw_items, list):
        return []
    templates: list[PromptTemplate] = []
    for item in raw_items:
        if isinstance(item, dict):
            templates.append(PromptTemplate(**item))
    return templates


def _write_prompt_templates(
    session: Session,
    principal: AuthenticatedPrincipal,
    templates: list[PromptTemplate],
) -> None:
    _write_setting(
        session,
        principal,
        PROMPT_TEMPLATE_SETTINGS_KEY,
        {"items": [template.model_dump() for template in templates]},
    )


def _install_plugin_prompt_templates(
    session: Session,
    principal: AuthenticatedPrincipal,
    plugin_id: str,
) -> None:
    if plugin_id != "release-prompt-pack":
        return
    templates = _read_prompt_templates(session, principal.organization_id)
    existing_ids = {template.id for template in templates}
    plugin_templates = [
        PromptTemplate(
            id="plugin-release-risk-summary",
            name="插件：发布风险摘要",
            description="从 Run、Eval 和 Observability 证据中生成发布风险摘要。",
            body="请用三段输出：阻塞风险、可接受风险、上线后监控项。",
            tags=["plugin", "release"],
            source="plugin",
            plugin_id=plugin_id,
            updated_at=utc_now().isoformat(),
        )
    ]
    merged = [
        *templates,
        *[template for template in plugin_templates if template.id not in existing_ids],
    ]
    _write_prompt_templates(session, principal, merged)


def _normalize_template_id(value: str) -> str:
    normalized = "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")
    return normalized[:80] or "prompt-template"
