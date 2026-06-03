"""Workspace chat run, orchestration, and context helper functions."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
from ._plan_helpers import *

def _workspace_max_subagents(request: AgentChatStreamRequest) -> int:
    return 5 if request.orchestration_mode in {"auto", "multi_agent", "subagent"} else 0


def _workspace_auto_orchestration_mode(*, goal: str, request: AgentChatStreamRequest) -> str:
    if request.orchestration_mode != "auto":
        return request.orchestration_mode
    normalized_goal = _normalize_orchestration_text(goal)
    recent_context = _normalize_orchestration_text(
        " ".join(
            node.content
            for node in request.messages[-6:]
            if node.role in {"user", "assistant"}
        )
    )
    if _mentions_subagent(normalized_goal):
        return "subagent"
    if _mentions_multi_agent(normalized_goal):
        return "multi_agent"
    if _asks_to_invoke_agent(normalized_goal):
        if _mentions_subagent(recent_context):
            return "subagent"
        if _mentions_multi_agent(recent_context):
            return "multi_agent"
    return "none"


def _normalize_orchestration_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).lower()
    return re.sub(r"\s+", "", normalized)


def _mentions_subagent(value: str) -> bool:
    return any(
        term in value
        for term in (
            "subagent",
            "sub-agent",
            "子agent",
            "子代理",
            "子智能体",
            "派生代理",
            "派生智能体",
        )
    )


def _mentions_multi_agent(value: str) -> bool:
    return any(
        term in value
        for term in (
            "multi-agent",
            "multiagent",
            "多agent",
            "多代理",
            "多智能体",
            "多智能体协作",
        )
    )


def _asks_to_invoke_agent(value: str) -> bool:
    return any(
        term in value
        for term in (
            "调用",
            "调用一下",
            "委托",
            "派发",
            "派生",
            "启动",
            "开一下",
            "spawn",
            "delegate",
            "invoke",
        )
    )


def _apply_workspace_orchestration(
    *,
    run: Task,
    agent_id: str,
    goal: str,
    request: AgentChatStreamRequest,
    session: Session,
    principal: Principal,
) -> dict | None:
    mode = _workspace_auto_orchestration_mode(goal=goal, request=request)
    if mode == "none":
        return None
    if mode == "multi_agent":
        ensure_default_agents(session, principal.organization_id)
        orchestrator = MultiAgentOrchestrator(session)
        assignments, handoffs = orchestrator.orchestrate(run=run, entry_agent_id=agent_id)
        session.flush()
        return {
            "mode": mode,
            "run_id": run.id,
            "strategy": orchestrator.routing_strategy(run=run),
            "routing_reasoning": orchestrator.routing_reasoning(run=run),
            "assignment_ids": [assignment.id for assignment in assignments],
            "selected_agent_ids": [assignment.agent_id for assignment in assignments],
            "handoff_ids": [handoff.id for handoff in handoffs],
            "message": "Workspace chat created inspectable multi-agent orchestration evidence.",
        }
    if mode == "subagent":
        try:
            subagent = SubagentManager(session).spawn(
                task=run,
                parent_agent_id=agent_id,
                assignment={
                    "label": "Workspace forced subagent",
                    "goal": goal,
                    "description": "Forced from Workspace chat orchestration mode.",
                    "step_key": "workspace_forced_subagent",
                    "source": "workspace_chat",
                    "orchestration_mode": mode,
                },
                enqueue=False,
            )
        except SubagentLimitExceededError as exc:
            EventStore(session).append(
                task_id=run.id,
                event_type=EventType.SUBAGENT_FAILED,
                payload_json={
                    "run_id": run.id,
                    "reason": "subagent_concurrency_limit",
                    "error": str(exc),
                },
            )
            session.flush()
            return {
                "mode": mode,
                "run_id": run.id,
                "status": "failed",
                "reason": "subagent_concurrency_limit",
                "message": "Workspace chat could not spawn subagent because concurrency is full.",
            }
        session.flush()
        return {
            "mode": mode,
            "run_id": run.id,
            "subagent_id": subagent.id,
            "status": subagent.status,
            "agent_type": subagent.agent_type,
            "message": "Workspace chat spawned an inspectable subagent run.",
        }
    return None


def _create_workspace_chat_run(
    *,
    agent_id: str,
    goal: str,
    session: Session,
    principal: Principal,
    mode: Literal["chat", "codex_plan", "context_compression", "cli_agent"] = "chat",
    model_provider: str | None = None,
    model_name: str | None = None,
    max_subagents: int = 0,
) -> Task:
    task = Task(
        organization_id=principal.organization_id,
        agent_id=agent_id,
        created_by=principal.user_id,
        title=_title_from_goal(goal),
        goal=goal,
        status="CREATED",
        model_provider=model_provider or "default",
        model_name=model_name or "default",
        max_runtime_seconds=1800,
        max_subagents=max_subagents,
        enable_sandbox=False,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(task)
    session.flush()
    capability_registry = CapabilityRegistry(session, principal.organization_id)
    _registry, capability_snapshot = capability_registry.tool_registry_for_agent(agent_id)
    task.capability_snapshot_json = capability_snapshot
    EventStore(session).append(
        task_id=task.id,
        event_type=EventType.TASK_CREATED,
        payload_json={
            "task_id": task.id,
            "title": task.title,
            "goal": task.goal,
            "agent_id": agent_id,
            "mode": mode,
        },
        actor_type="user",
        actor_id=principal.user_id,
    )
    session.commit()
    session.refresh(task)
    return task


def _workspace_chat_messages(
    *,
    agent_id: str,
    goal: str,
    request: AgentChatStreamRequest,
) -> list[ModelMessage]:
    messages = [
        ModelMessage(
            role="system",
            content=(
                "You are the normal conversational assistant in AI Harness Workspace Pro. "
                "Answer the user's message directly and naturally. "
                "Do not create an execution plan unless the user explicitly asks for planning, "
                "tool use, code execution, or task decomposition. "
                "When attachments are present, use only the attachment content explicitly provided "
                "in the conversation context. If an attachment is marked unreadable or content is "
                "not provided, say you cannot inspect its contents instead of guessing. "
                f"Current agent id: {agent_id}."
            ),
        )
    ]
    messages.extend(_workspace_context_messages(request))
    if not messages or messages[-1].role != "user" or messages[-1].content.strip() != goal:
        messages.append(ModelMessage(role="user", content=goal))
    return messages


def _workspace_codex_plan_messages(
    *,
    agent_id: str,
    goal: str,
    request: AgentChatStreamRequest,
) -> list[ModelMessage]:
    messages = [
        ModelMessage(
            role="system",
            content=(
                "You are the Codex planning assistant in AI Harness Workspace Pro. "
                "Answer with concise markdown planning text only. "
                "Include assumptions, next steps, and acceptance criteria when useful. "
                "Do not execute tools or emit operational details. "
                "When attachments are present, use only the attachment content explicitly provided "
                "in the conversation context. If an attachment is marked unreadable or content is "
                "not provided, say you cannot inspect its contents instead of guessing. "
                f"Current agent id: {agent_id}."
            ),
        )
    ]
    messages.extend(_workspace_context_messages(request))
    if not messages or messages[-1].role != "user" or messages[-1].content.strip() != goal:
        messages.append(ModelMessage(role="user", content=goal))
    return messages


def _workspace_cli_agent_messages(
    *,
    agent_id: str,
    goal: str,
    request: AgentChatStreamRequest,
) -> list[ModelMessage]:
    messages = [
        ModelMessage(
            role="system",
            content=(
                "You are the hao CLI coding agent inside AI Harness. "
                "Help the user by inspecting and changing the local workspace through tool calls. "
                "When you need a tool, emit exactly one XML block in this format and wait for the "
                "CLI to return results:\n"
                "<function_calls><invoke name=\"read_file\"><parameter name=\"path\">"
                "relative/path.py</parameter></invoke></function_calls>\n"
                "Available host tools are read_file, list_files, search_files, write_file, "
                "apply_patch, run_shell, run_tests, and git. Use only relative workspace paths. "
                "Do not claim that a file was edited or a shell command ran until the CLI returns "
                "a local tool result. Keep ordinary answers concise. "
                f"Current agent id: {agent_id}."
            ),
        )
    ]
    messages.extend(_workspace_context_messages(request))
    if not messages or messages[-1].role != "user" or messages[-1].content.strip() != goal:
        messages.append(ModelMessage(role="user", content=goal))
    return messages


def _workspace_context_messages(request: AgentChatStreamRequest) -> list[ModelMessage]:
    pinned_ids = set(request.pinned_node_ids)
    coverage_ids = (
        set(request.compressed_context.coverage_node_ids)
        if request.compressed_context is not None
        else set()
    )
    carried = [
        node
        for node in request.messages[-request.context_window_turns :]
        if node.role in {"user", "assistant", "system", "tool"}
        and node.id not in pinned_ids
        and node.id not in coverage_ids
    ]
    pinned = [
        node
        for node in request.messages
        if node.id in pinned_ids and node.role in {"user", "assistant", "system", "tool"}
    ]
    messages: list[ModelMessage] = []
    attachment_context = _workspace_attachment_context(request)
    if attachment_context:
        messages.append(
            ModelMessage(
                role="system",
                content=attachment_context,
            )
        )
    if request.compressed_context is not None:
        summary = request.compressed_context.summary.strip()
        if summary:
            messages.append(
                ModelMessage(
                    role="system",
                    content=(
                        "Compressed prior workspace context. Treat this as a lossy "
                        "summary of older unpinned messages; pinned raw messages and "
                        "newer raw messages below take precedence.\n\n"
                        f"{summary}"
                    ),
                )
            )
    for node in [*pinned, *carried]:
        role = node.role if node.role in {"user", "assistant", "system", "tool"} else "user"
        content = node.content.strip()
        if content:
            messages.append(ModelMessage(role=role, content=content))
    return messages


def _normalize_model_id(value: str | None) -> str:
    return (value or "").strip().lower()


def _normalize_context_content(content: str) -> str:
    return unicodedata.normalize("NFC", content.replace("\r\n", "\n").replace("\r", "\n"))


def _workspace_context_hash_payload(nodes: list) -> list[dict]:
    payload = []
    for node in nodes:
        payload.append(
            {
                "id": node.id,
                "parent_id": node.parent_id,
                "role": node.role,
                "content": _normalize_context_content(node.content),
                "state": node.state,
                "created_at": node.created_at,
            }
        )
    return payload


def _workspace_context_path_hash(nodes: list) -> str:
    raw = json.dumps(
        _workspace_context_hash_payload(nodes),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _workspace_summary_cache_key_hash(
    *,
    organization_id: str | None,
    agent_id: str,
    provider: str,
    model: str,
    coverage_path_hash: str,
    pinned_path_hash: str,
) -> str:
    payload = {
        "schema_version": CONTEXT_CACHE_SCHEMA_VERSION,
        "cache_source": CACHE_SOURCE_COMPRESSION_SUMMARY,
        "organization_id": organization_id,
        "agent_id": agent_id,
        "provider": provider,
        "model": model,
        "coverage_path_hash": coverage_path_hash,
        "pinned_path_hash": pinned_path_hash,
        "summary_schema_version": SUMMARY_SCHEMA_VERSION,
        "compression_prompt_version": COMPRESSION_PROMPT_VERSION,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _workspace_summary_cache_lookup(
    *,
    session: Session,
    organization_id: str | None,
    agent_id: str,
    cache_key_hash: str,
    now,
) -> WorkspaceContextCache | None:
    return session.execute(
        select(WorkspaceContextCache).where(
            WorkspaceContextCache.organization_id == organization_id,
            WorkspaceContextCache.agent_id == agent_id,
            WorkspaceContextCache.cache_source == CACHE_SOURCE_COMPRESSION_SUMMARY,
            WorkspaceContextCache.cache_key_hash == cache_key_hash,
            WorkspaceContextCache.status == "active",
            or_(
                WorkspaceContextCache.expires_at.is_(None),
                WorkspaceContextCache.expires_at > now,
            ),
        )
    ).scalar_one_or_none()


def _record_workspace_summary_cache(
    *,
    session: Session,
    organization_id: str | None,
    agent_id: str,
    cache_key_hash: str,
    summary: str,
    coverage_node_ids: list[str],
    coverage_path_hash: str,
    pinned_path_hash: str,
    provider: str,
    model: str,
    estimated_original_tokens: int,
    estimated_summary_tokens: int,
    estimated_uncovered_tokens: int,
    status: str,
    now,
) -> None:
    row = session.execute(
        select(WorkspaceContextCache).where(
            WorkspaceContextCache.organization_id == organization_id,
            WorkspaceContextCache.cache_source == CACHE_SOURCE_COMPRESSION_SUMMARY,
            WorkspaceContextCache.cache_key_hash == cache_key_hash,
        )
    ).scalar_one_or_none()
    saved_tokens = max(0, estimated_original_tokens - estimated_summary_tokens)
    payload = {
        "summary": summary,
        "coverage_node_ids": coverage_node_ids,
        "coverage_path_hash": coverage_path_hash,
        "pinned_path_hash": pinned_path_hash,
        "summary_schema_version": SUMMARY_SCHEMA_VERSION,
        "compression_prompt_version": COMPRESSION_PROMPT_VERSION,
        "compressor_provider": provider,
        "compressor_model": model,
        "estimated_original_tokens": estimated_original_tokens,
        "estimated_summary_tokens": estimated_summary_tokens,
        "estimated_uncovered_tokens": estimated_uncovered_tokens,
        "estimated_saved_tokens": saved_tokens,
    }
    metadata = {"reason": f"compression_summary_{status}"}
    if row is None:
        session.add(
            WorkspaceContextCache(
                organization_id=organization_id,
                agent_id=agent_id,
                owner_user_id=None,
                cache_source=CACHE_SOURCE_COMPRESSION_SUMMARY,
                cache_key_hash=cache_key_hash,
                schema_version=CONTEXT_CACHE_SCHEMA_VERSION,
                status="active",
                payload_json=payload,
                metadata_json=metadata,
                hit_count=1 if status == "accepted" else 0,
                miss_count=1 if status == "recomputed" else 0,
                stale_count=1 if status == "stale_rejected" else 0,
                estimated_saved_tokens=saved_tokens,
                last_hit_at=now if status == "accepted" else None,
                created_at=now,
                updated_at=now,
            )
        )
    else:
        row.payload_json = payload
        row.metadata_json = metadata
        row.estimated_saved_tokens = saved_tokens
        row.updated_at = now
        if status == "accepted":
            row.hit_count += 1
            row.last_hit_at = now
        elif status == "recomputed":
            row.miss_count += 1
        elif status == "stale_rejected":
            row.stale_count += 1
    session.flush()


def _estimate_nodes_tokens(nodes: list) -> int:
    return sum(_estimate_text_tokens(node.content) for node in nodes)


def _estimate_text_tokens(content: str) -> int:
    if not content:
        return 0
    cjk_count = len(CJK_TOKEN_RE.findall(content))
    without_cjk = CJK_TOKEN_RE.sub(" ", content)
    ascii_word_chars = sum(len(match.group(0)) for match in ASCII_WORD_RE.finditer(without_cjk))
    visible_non_space = sum(1 for char in without_cjk if not char.isspace())
    symbol_chars = max(0, visible_non_space - ascii_word_chars)
    return int((cjk_count + ascii_word_chars / 4 + symbol_chars / 2) + 0.999999)


def _workspace_compression_prompt(nodes: list) -> str:
    blocks = [
        "Compress these active-path workspace messages for future prompt context.",
        (
            "Preserve user goals, decisions, constraints, named files, "
            "unresolved questions, and important facts."
        ),
        "Do not include attachment body text unless it appears directly in these messages.",
        "Return only the summary text.",
    ]
    for node in nodes:
        content = _normalize_context_content(node.content).strip()
        if not content:
            continue
        blocks.append(
            f'\n<message id="{node.id}" role="{node.role}" state="{node.state}">\n'
            f"{content}\n"
            "</message>"
        )
    return "\n".join(blocks)


def _workspace_attachment_context(request: AgentChatStreamRequest) -> str:
    attachments = request.attachments[:12]
    if not attachments:
        attachment_names = [
            name.strip()[:160] for name in request.attachment_names[:12] if name.strip()
        ]
        if not attachment_names:
            return ""
        return (
            "User selected attachments, but their contents were not provided to the model. "
            "Do not infer or fabricate their contents. File names: " + ", ".join(attachment_names)
        )

    blocks = [
        "User selected attachments. Use only the explicit content below. "
        "For any file marked unavailable, do not infer or fabricate its contents."
    ]
    for index, attachment in enumerate(attachments, start=1):
        name = attachment.name.strip()[:160] or f"attachment-{index}"
        mime_type = attachment.mime_type.strip()[:80] or "unknown"
        status = attachment.content_status
        size = attachment.size_bytes
        if status == "ready" and attachment.content_text:
            content = attachment.content_text[:120_000]
            truncated_note = (
                " (truncated)"
                if attachment.truncated or len(attachment.content_text) > 120_000
                else ""
            )
            blocks.append(
                f'\n<attachment index="{index}" name="{name}" mime="{mime_type}" '
                f'size_bytes="{size}" status="readable{truncated_note}">\n'
                f"{content}\n</attachment>"
            )
        else:
            reason = "read failed" if status == "error" else "content unavailable to this model"
            blocks.append(
                f'\n<attachment index="{index}" name="{name}" mime="{mime_type}" '
                f'size_bytes="{size}" status="unreadable" reason="{reason}" />'
            )
    return "\n".join(blocks)


def _require_normal_chat_content(content: str) -> str:
    stripped = content.strip()
    if stripped and stripped != "{}":
        return stripped
    raise ModelGatewayError(
        "模型网关没有返回可展示的真实聊天内容；"
        "请在模型设置中配置可用供应商/API Key 后再使用 Workspace Pro 聊天。"
    )

__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
