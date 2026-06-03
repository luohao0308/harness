from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import quote

import httpx

MARKETPLACE_TIMEOUT_SECONDS = 6.0
MARKETPLACE_USER_AGENT = "ai-harness-capability-marketplace/1.0"
OFFICIAL_MCP_REGISTRY_URL = "https://registry.modelcontextprotocol.io/v0/servers"
SMITHERY_API_BASE_URL = "https://api.smithery.ai"


def list_capability_marketplace(
    *,
    kind: str = "all",
    query: str = "",
    limit: int = 12,
) -> dict[str, Any]:
    normalized_kind = kind if kind in {"all", "mcp", "skill"} else "all"
    normalized_limit = max(1, min(limit, 30))
    normalized_query = query.strip()
    items: list[dict[str, Any]] = _local_marketplace_items(normalized_kind, normalized_query)
    sources = [_source_summary("harness_curated", "平台推荐", "ready", len(items))]
    errors: list[dict[str, str]] = []

    headers = {"User-Agent": MARKETPLACE_USER_AGENT}
    with httpx.Client(
        timeout=MARKETPLACE_TIMEOUT_SECONDS,
        headers=headers,
        trust_env=False,
    ) as client:
        if normalized_kind in {"all", "mcp"}:
            official_items, official_error = _official_mcp_items(
                client,
                query=normalized_query,
                limit=normalized_limit,
            )
            items.extend(official_items)
            sources.append(
                _source_summary(
                    "official_mcp_registry",
                    "官方 MCP 注册表",
                    "ready" if official_error is None else "unavailable",
                    len(official_items),
                    "https://registry.modelcontextprotocol.io",
                )
            )
            if official_error:
                errors.append(official_error)

            smithery_mcp_items, smithery_mcp_error = _smithery_mcp_items(
                client,
                query=normalized_query,
                limit=normalized_limit,
            )
            items.extend(smithery_mcp_items)
            sources.append(
                _source_summary(
                    "smithery_mcp",
                    "Smithery MCP 服务库",
                    "ready" if smithery_mcp_error is None else "unavailable",
                    len(smithery_mcp_items),
                    "https://smithery.ai",
                )
            )
            if smithery_mcp_error:
                errors.append(smithery_mcp_error)

        if normalized_kind in {"all", "skill"}:
            smithery_skill_items, smithery_skill_error = _smithery_skill_items(
                client,
                query=normalized_query,
                limit=normalized_limit,
            )
            items.extend(smithery_skill_items)
            sources.append(
                _source_summary(
                    "smithery_skills",
                    "Smithery 技能库",
                    "ready" if smithery_skill_error is None else "unavailable",
                    len(smithery_skill_items),
                    "https://smithery.ai",
                )
            )
            if smithery_skill_error:
                errors.append(smithery_skill_error)

    ranked = _dedupe_items(items)
    return {
        "kind": normalized_kind,
        "query": normalized_query,
        "items": ranked[:normalized_limit],
        "sources": sources,
        "errors": errors,
    }


def _official_mcp_items(
    client: httpx.Client,
    *,
    query: str,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
    params: dict[str, Any] = {"limit": min(limit, 30), "version": "latest"}
    if query:
        params["search"] = query
    try:
        response = client.get(OFFICIAL_MCP_REGISTRY_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # pragma: no cover - exercised through endpoint tests
        return [], _source_error("official_mcp_registry", exc)

    items = []
    for entry in payload.get("servers") or []:
        if not isinstance(entry, dict):
            continue
        server = entry.get("server") if isinstance(entry.get("server"), dict) else {}
        meta = entry.get("_meta") if isinstance(entry.get("_meta"), dict) else {}
        official = meta.get("io.modelcontextprotocol.registry/official", {})
        if isinstance(official, dict) and official.get("status") == "deleted":
            continue
        items.append(_official_mcp_item(server, official))
    return items, None


def _official_mcp_item(server: dict[str, Any], official: dict[str, Any]) -> dict[str, Any]:
    name = _text(server.get("name"), "unknown/mcp-server")
    title = _text(server.get("title"), name)
    version = _text(server.get("version"), "latest")
    description = _text(server.get("description"), "MCP 服务")
    repository_url = _repository_url(server.get("repository"))
    remotes = server.get("remotes") if isinstance(server.get("remotes"), list) else []
    packages = server.get("packages") if isinstance(server.get("packages"), list) else []
    remote = _first_transport(remotes)
    package = _first_transport(packages)
    remote_url = _text(remote.get("url") if remote else None, "")
    source_uri = remote_url or repository_url or _text(server.get("websiteUrl"), "")
    if not source_uri:
        source_uri = (
            "https://registry.modelcontextprotocol.io/v0/servers/"
            f"{quote(name, safe='')}/versions/{quote(version, safe='')}"
        )
    transport = _text((remote or package or {}).get("type"), "http")
    if transport == "streamable-http":
        transport = "http"
    manifest_name = _manifest_name(name)
    return {
        "id": f"official-mcp::{name}@{version}",
        "kind": "mcp",
        "source": "official_mcp_registry",
        "source_label": "官方 MCP 注册表",
        "name": name,
        "display_name": title,
        "description": description,
        "categories": ["MCP"],
        "verified": bool(official.get("isLatest", True)),
        "stars": None,
        "use_count": None,
        "quality_score": None,
        "latest_version": version,
        "updated_at": official.get("updatedAt") or official.get("publishedAt"),
        "homepage_url": _text(server.get("websiteUrl"), ""),
        "repository_url": repository_url,
        "remote_url": remote_url,
        "package_type": "mcp_server",
        "install_mode": "marketplace_preflight",
        "install_label": "登记预检",
        "install_payload": _install_payload(
            source_uri=source_uri,
            marketplace_source="official_mcp_registry",
            marketplace_item_id=f"official-mcp::{name}@{version}",
            package_type="mcp_server",
            display_name=title,
            description=description,
            manifest={
                "name": manifest_name,
                "version": version,
                "description": description,
                "package_type": "mcp_server",
                "permissions": ["mcp:remote" if remote_url else "mcp:stdio"],
                "transport": transport if transport in {"http", "sse", "stdio"} else "http",
                "secret_refs": _secret_refs_from_transports(remotes + packages),
                "mcp_server": {
                    "registry": "official_mcp_registry",
                    "server_name": name,
                    "remote_url": remote_url or None,
                    "repository_url": repository_url or None,
                },
            },
            content={
                "marketplace": {
                    "source": "official_mcp_registry",
                    "server": server,
                    "official": official,
                }
            },
        ),
        "badges": _badges(
            [
                "MCP",
                "latest" if official.get("isLatest", True) else "",
                _text(official.get("status"), "active"),
            ]
        ),
        "risk_notes": _risk_notes_for_mcp(remote_url, remotes, packages),
        "metadata": {
            "server_name": name,
            "registry_status": official.get("status"),
            "remote_count": len(remotes),
            "package_count": len(packages),
        },
    }


def _smithery_mcp_items(
    client: httpx.Client,
    *,
    query: str,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
    params: dict[str, Any] = {"pageSize": min(limit, 20)}
    if query:
        params["q"] = query
    try:
        response = client.get(f"{SMITHERY_API_BASE_URL}/servers", params=params)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # pragma: no cover - exercised through endpoint tests
        return [], _source_error("smithery_mcp", exc)
    return [
        _smithery_mcp_item(server)
        for server in payload.get("servers") or []
        if isinstance(server, dict)
    ], None


def _smithery_mcp_item(server: dict[str, Any]) -> dict[str, Any]:
    qualified_name = _text(server.get("qualifiedName"), "smithery/server")
    display_name = _text(server.get("displayName"), qualified_name)
    description = _text(server.get("description"), "Smithery MCP 服务")
    homepage = _text(server.get("homepage"), "")
    source_uri = homepage or f"https://smithery.ai/servers/{quote(qualified_name, safe='/')}"
    manifest_name = _manifest_name(qualified_name)
    return {
        "id": f"smithery-mcp::{qualified_name}",
        "kind": "mcp",
        "source": "smithery_mcp",
        "source_label": "Smithery MCP 服务库",
        "name": qualified_name,
        "display_name": display_name,
        "description": description,
        "categories": ["MCP", "Smithery"],
        "verified": bool(server.get("verified")),
        "stars": None,
        "use_count": _optional_number(server.get("useCount")),
        "quality_score": _optional_number(server.get("score")),
        "latest_version": None,
        "updated_at": server.get("createdAt"),
        "homepage_url": homepage,
        "repository_url": "",
        "remote_url": homepage,
        "package_type": "mcp_server",
        "install_mode": "marketplace_preflight",
        "install_label": "登记预检",
        "install_payload": _install_payload(
            source_uri=source_uri,
            marketplace_source="smithery_mcp",
            marketplace_item_id=f"smithery-mcp::{qualified_name}",
            package_type="mcp_server",
            display_name=display_name,
            description=description,
            manifest={
                "name": manifest_name,
                "version": "1.0.0",
                "description": description,
                "package_type": "mcp_server",
                "permissions": ["mcp:remote"],
                "transport": "http" if server.get("remote") is not False else "stdio",
                "secret_refs": [],
                "mcp_server": {
                    "registry": "smithery_mcp",
                    "qualified_name": qualified_name,
                    "homepage": homepage or None,
                    "smithery_connection_required": True,
                },
            },
            content={"marketplace": {"source": "smithery_mcp", "server": server}},
        ),
        "badges": _badges(
            [
                "MCP",
                "verified" if server.get("verified") else "",
                "remote" if server.get("remote") else "stdio",
            ]
        ),
        "risk_notes": [
            "Smithery 连接可能需要 OAuth、API Key 或命名空间配置；导入会先进入平台预检。"
        ],
        "metadata": {
            "qualified_name": qualified_name,
            "remote": server.get("remote"),
            "is_deployed": server.get("isDeployed"),
            "by_smithery": server.get("bySmithery"),
        },
    }


def _smithery_skill_items(
    client: httpx.Client,
    *,
    query: str,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
    params: dict[str, Any] = {"pageSize": min(limit, 20)}
    if query:
        params["q"] = query
    try:
        response = client.get(f"{SMITHERY_API_BASE_URL}/skills", params=params)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # pragma: no cover - exercised through endpoint tests
        return [], _source_error("smithery_skills", exc)
    return [
        _smithery_skill_item(skill)
        for skill in payload.get("skills") or []
        if isinstance(skill, dict)
    ], None


def _smithery_skill_item(skill: dict[str, Any]) -> dict[str, Any]:
    namespace = _text(skill.get("namespace"), "community")
    slug = _text(skill.get("slug"), _text(skill.get("displayName"), "skill"))
    qualified_name = _text(skill.get("qualifiedName"), f"{namespace}/{slug}")
    display_name = _text(skill.get("displayName"), qualified_name)
    description = _text(skill.get("description"), "提示词技能")
    categories = [str(category) for category in skill.get("categories") or []]
    git_url = _text(skill.get("gitUrl"), "")
    source_uri = git_url or f"https://smithery.ai/skills/{quote(namespace)}/{quote(slug)}"
    manifest_name = _manifest_name(qualified_name)
    return {
        "id": f"smithery-skill::{qualified_name}",
        "kind": "skill",
        "source": "smithery_skills",
        "source_label": "Smithery 技能库",
        "name": qualified_name,
        "display_name": display_name,
        "description": description,
        "categories": categories or ["技能"],
        "verified": bool(skill.get("verified")),
        "stars": _optional_number(skill.get("externalStars")),
        "use_count": _optional_number(skill.get("totalActivations")),
        "quality_score": _optional_number(skill.get("qualityScore")),
        "latest_version": None,
        "updated_at": skill.get("createdAt"),
        "homepage_url": f"https://smithery.ai/skills/{quote(namespace)}/{quote(slug)}",
        "repository_url": git_url,
        "remote_url": "",
        "package_type": "skill_pack",
        "install_mode": "marketplace_preflight",
        "install_label": "登记预检",
        "install_payload": _install_payload(
            source_uri=source_uri,
            marketplace_source="smithery_skills",
            marketplace_item_id=f"smithery-skill::{qualified_name}",
            package_type="skill_pack",
            display_name=display_name,
            description=description,
            manifest={
                "name": manifest_name,
                "version": "1.0.0",
                "description": description,
                "package_type": "skill_pack",
                "permissions": ["skill:prompt"],
                "secret_refs": [],
                "skill": {
                    "registry": "smithery_skills",
                    "qualified_name": qualified_name,
                    "git_url": git_url or None,
                    "depends_on_mcp_servers": skill.get("servers") or [],
                },
            },
            content={"marketplace": {"source": "smithery_skills", "skill": skill}},
        ),
        "badges": _badges(
            [
                "技能",
                "verified" if skill.get("verified") else "",
                *(categories[:2]),
            ]
        ),
        "risk_notes": [
            "技能会改变智能体指令边界；导入后仍需经过版本预检、审批和智能体附件启用。"
        ],
        "metadata": {
            "namespace": namespace,
            "slug": slug,
            "listed": skill.get("listed"),
            "dependent_servers": skill.get("servers") or [],
        },
    }


def _local_marketplace_items(kind: str, query: str) -> list[dict[str, Any]]:
    local_items = [
        {
            "id": "harness::mcp_context_search",
            "kind": "mcp",
            "source": "harness_curated",
            "source_label": "平台推荐",
            "name": "mcp_context_search",
            "display_name": "上下文搜索",
            "description": "让智能体检索工作区上下文、知识证据和运行状态。",
            "categories": ["MCP", "Knowledge"],
            "verified": True,
            "stars": None,
            "use_count": None,
            "quality_score": 1.0,
            "latest_version": "built-in",
            "updated_at": None,
            "homepage_url": "",
            "repository_url": "",
            "remote_url": "",
            "package_type": "mcp_server",
            "install_mode": "attach_existing",
            "install_label": "直接启用",
            "install_payload": {
                "capability_id": "mcp_context_search",
                "agent_id": "default",
                "enabled": True,
                "priority": 10,
            },
            "badges": ["本地", "MCP", "可直接启用"],
            "risk_notes": ["本地内置能力，启用后仍受智能体附件和 ToolRunner 策略约束。"],
            "metadata": {"preset": True},
        },
        {
            "id": "harness::skill_context_optimizer",
            "kind": "skill",
            "source": "harness_curated",
            "source_label": "平台推荐",
            "name": "conservative-token-saver",
            "display_name": "保守上下文优化",
            "description": "声明式上下文预算优化能力，优先保留权威指令、固定上下文和高置信证据。",
            "categories": ["技能", "Context"],
            "verified": True,
            "stars": None,
            "use_count": None,
            "quality_score": 1.0,
            "latest_version": "1.0.0",
            "updated_at": None,
            "homepage_url": "",
            "repository_url": "",
            "remote_url": "",
            "package_type": "context_optimizer",
            "install_mode": "upload_install",
            "install_label": "本地安装",
            "install_payload": _install_payload(
                source_uri="",
                marketplace_source="harness_curated",
                marketplace_item_id="harness::skill_context_optimizer",
                package_type="context_optimizer",
                display_name="conservative-token-saver",
                description="声明式智能体上下文优化器",
                manifest={
                    "name": "conservative-token-saver",
                    "version": "1.0.0",
                    "description": "声明式智能体上下文优化器",
                    "package_type": "context_optimizer",
                    "permissions": ["context:optimize"],
                    "secret_refs": [],
                    "schema_version": "context-optimizer-v1",
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
                            "recent_window_oldest_first",
                        ],
                        "prefer_valid_compressed_summary": True,
                    },
                },
                content={"marketplace": {"source": "harness_curated"}},
            ),
            "badges": ["本地", "技能", "上下文"],
            "risk_notes": ["安装为不可执行的上下文优化能力，不通过工具调用执行代码。"],
            "metadata": {"preset": True},
        },
    ]
    filtered = [item for item in local_items if kind in {"all", item["kind"]}]
    if not query:
        return filtered
    folded = query.casefold()
    return [
        item
        for item in filtered
        if folded in item["name"].casefold()
        or folded in item["display_name"].casefold()
        or folded in item["description"].casefold()
    ]


def _install_payload(
    *,
    source_uri: str,
    marketplace_source: str,
    marketplace_item_id: str,
    package_type: str,
    display_name: str,
    description: str,
    manifest: dict[str, Any],
    content: dict[str, Any],
) -> dict[str, Any]:
    pinned_ref = _stable_sha256({"manifest": manifest, "content": content})
    payload = {
        "source_uri": source_uri or None,
        "pinned_ref": f"marketplace-sha256:{pinned_ref}",
        "package_type": package_type,
        "display_name": display_name,
        "description": description,
        "marketplace_source": marketplace_source,
        "marketplace_item_id": marketplace_item_id,
        "permissions": manifest.get("permissions") or [],
        "secret_refs": manifest.get("secret_refs") or [],
        "manifest": manifest,
        "content": content,
    }
    return payload


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        key = (str(item.get("kind")), str(item.get("name")).casefold())
        current = deduped.get(key)
        if current is None or _item_score(item) > _item_score(current):
            deduped[key] = item
    return sorted(
        deduped.values(),
        key=lambda item: (
            str(item.get("source")) != "harness_curated",
            -_item_score(item),
            str(item.get("display_name")),
        ),
    )


def _item_score(item: dict[str, Any]) -> float:
    score = 0.0
    if item.get("verified"):
        score += 10
    score += float(item.get("quality_score") or 0)
    score += min(float(item.get("use_count") or 0) / 1000, 5)
    score += min(float(item.get("stars") or 0) / 10000, 3)
    if item.get("source") == "harness_curated":
        score += 20
    return score


def _source_summary(
    source_id: str,
    label: str,
    status: str,
    item_count: int,
    url: str = "",
) -> dict[str, Any]:
    return {
        "id": source_id,
        "label": label,
        "status": status,
        "item_count": item_count,
        "url": url,
    }


def _source_error(source_id: str, exc: Exception) -> dict[str, str]:
    return {
        "source": source_id,
        "message": str(exc),
    }


def _repository_url(repository: Any) -> str:
    if not isinstance(repository, dict):
        return ""
    return _text(repository.get("url"), "")


def _first_transport(transports: list[Any]) -> dict[str, Any] | None:
    for transport in transports:
        if isinstance(transport, dict):
            return transport
    return None


def _secret_refs_from_transports(transports: list[Any]) -> list[str]:
    refs: list[str] = []
    for transport in transports:
        if not isinstance(transport, dict):
            continue
        for argument in transport.get("headers") or []:
            if not isinstance(argument, dict):
                continue
            if argument.get("isSecret") is True:
                name = _text(argument.get("name"), "mcp_header_secret")
                refs.append(f"secret://mcp/{_manifest_name(name)}")
        for variable in (transport.get("variables") or {}).values():
            if isinstance(variable, dict) and variable.get("isSecret") is True:
                name = _text(variable.get("name"), "mcp_variable_secret")
                refs.append(f"secret://mcp/{_manifest_name(name)}")
    return sorted(set(refs))


def _risk_notes_for_mcp(
    remote_url: str,
    remotes: list[Any],
    packages: list[Any],
) -> list[str]:
    notes = []
    if remote_url:
        notes.append("远程 MCP 服务器会引入外部网络边界；导入后需要策略和凭据检查。")
    if packages:
        notes.append("本地/stdio 包需要运行时隔离；当前导入只暂存清单，不执行代码。")
    if any(_secret_refs_from_transports([transport]) for transport in remotes + packages):
        notes.append("该能力声明了 secret 输入，安装后需配置 secret_ref。")
    return notes or ["导入只创建平台能力包预检记录，不直接执行外部代码。"]


def _badges(values: list[str]) -> list[str]:
    return [value for value in values if value]


def _manifest_name(value: str) -> str:
    normalized = "".join(
        character.lower() if character.isalnum() else "-"
        for character in value.strip()
    ).strip("-")
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized[:96] or "marketplace-capability"


def _stable_sha256(value: Any) -> str:
    import json

    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _optional_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _text(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback
