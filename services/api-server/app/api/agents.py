import hashlib
import json
import re
import time
import unicodedata
from collections.abc import Iterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.executor import PLANNER_SYSTEM_PROMPT, Executor
from app.agents.model_gateway import (
    AuditedModelGateway,
    ModelGatewayError,
    ModelMessage,
    ModelRequest,
)
from app.agents.orchestrator import MultiAgentOrchestrator
from app.agents.planner import PLANNER_PROMPT_VERSION, DeterministicPlanner
from app.agents.registry import ensure_default_agents
from app.agents.schemas import ExecutionPlan as ExecutionPlanSchema
from app.api.schemas import (
    AgentAssignmentResponse,
    AgentAutoResponse,
    AgentChatRequest,
    AgentChatResponse,
    AgentChatStreamRequest,
    AgentHandoffResponse,
    AgentMessagePage,
    AgentOrchestrateResponse,
    AgentPage,
    AgentPlanRequest,
    AgentPlanResponse,
    AgentResponse,
    AgentRunCreateRequest,
    AgentRunWorkspaceResponse,
    AgentSessionCreateRequest,
    AgentSessionPage,
    AgentSessionResponse,
    EventResponse,
    KnowledgeCitationResponse,
    KnowledgeDocumentResponse,
    KnowledgeGroundingResponse,
    KnowledgePolicyAuditResponse,
    KnowledgeRetrievalHitResponse,
    KnowledgeSourceCreateRequest,
    KnowledgeSourcePage,
    KnowledgeSourceResponse,
    ModelCallResponse,
    PromptAssemblyManifestResponse,
    RetrievalSessionResponse,
    SubagentResponse,
    TaskPage,
    TaskPlanResponse,
    TaskPlanStepState,
    TaskResponse,
    ToolApprovalResponse,
    ToolCallResponse,
    WebResearchSourceResponse,
    WorkspaceContextCompressionRequest,
    WorkspaceContextCompressionResponse,
)
from app.db.models import (
    Agent,
    AgentAssignment,
    AgentEvent,
    AgentHandoff,
    AgentMessage,
    AgentRun,
    AgentSession,
    CitationRecord,
    ExecutionPlan,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeEmbedding,
    KnowledgePolicyAudit,
    KnowledgeSource,
    ModelCall,
    PromptAssemblyManifest,
    RetrievalHit,
    RetrievalSession,
    Task,
    ToolApproval,
    ToolCall,
    WebResearchSource,
    utc_now,
)
from app.db.session import get_db_session
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.knowledge import (
    KnowledgeGroundingResult,
    ground_query,
    ingest_knowledge_source,
    list_knowledge_sources,
)
from app.security.auth import Principal, require_role
from app.tools.registry import ToolMetadata, ToolRegistry
from app.tools.runner import ToolExecution, ToolRunner

router = APIRouter(prefix="/agents", tags=["agents"])
DbSession = Annotated[Session, Depends(get_db_session)]

SUMMARY_SCHEMA_VERSION = "workspace-context-summary-v1"
COMPRESSION_PROMPT_VERSION = "workspace-context-compression-v1"
CJK_TOKEN_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af]")
ASCII_WORD_RE = re.compile(r"[A-Za-z0-9_]+(?:[-'][A-Za-z0-9_]+)*")


# ---------------------------------------------------------------------------
# v4 SSE response headers (Req 6.1 / 6.5).
#
# Every route that returns `text/event-stream` should attach these headers so
# Nginx / other reverse proxies disable buffering and the browser keeps the
# connection open while incremental deltas arrive.
#
# The `X-Accel-Buffering` hint tells Nginx to skip its own response buffer
# (reiterated with `add_header X-Accel-Buffering no always;` in
# `deploy/nginx/agent-harness.conf`).
#
# Do NOT enable `GZipMiddleware` on these routes — gzip re-chunks the stream
# and breaks per-event delivery. See `app/main.py` for the guard-rail note.
# ---------------------------------------------------------------------------
_SSE_HEADERS: dict[str, str] = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.get(
    "",
    response_model=AgentPage,
    summary="查询 Agent 注册表",
    description="返回组织内可用的具名 Agent。默认 preset 会自动初始化。",
)
def list_agents(session: DbSession, principal: Principal) -> AgentPage:
    require_role(principal, {"admin", "engineer", "operator"})
    ensure_default_agents(session, principal.organization_id)
    session.commit()
    agents = list(
        session.execute(
            select(Agent)
            .order_by(Agent.id.asc())
        ).scalars()
    )
    return AgentPage(items=agents)


@router.get(
    "/{agent_id}/sessions",
    response_model=AgentSessionPage,
    summary="查询 Agent 会话",
)
def list_agent_sessions(
    agent_id: str,
    session: DbSession,
    principal: Principal,
) -> AgentSessionPage:
    require_role(principal, {"admin", "engineer", "operator"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    sessions = list(
        session.execute(
            select(AgentSession)
            .where(
                AgentSession.organization_id == principal.organization_id,
                AgentSession.agent_id == agent_id,
            )
            .order_by(AgentSession.updated_at.desc(), AgentSession.id.asc())
        ).scalars()
    )
    return AgentSessionPage(items=sessions)


@router.post(
    "/{agent_id}/sessions",
    response_model=AgentSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建 Agent 会话",
)
def create_agent_session(
    agent_id: str,
    request: AgentSessionCreateRequest,
    session: DbSession,
    principal: Principal,
) -> AgentSession:
    require_role(principal, {"admin", "engineer"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    now = utc_now()
    agent_session = AgentSession(
        organization_id=principal.organization_id,
        agent_id=agent_id,
        created_by=principal.user_id,
        title=request.title or "New Agent Session",
        status="ACTIVE",
        created_at=now,
        updated_at=now,
    )
    session.add(agent_session)
    session.commit()
    session.refresh(agent_session)
    return agent_session


@router.get(
    "/{agent_id}/knowledge/sources",
    response_model=KnowledgeSourcePage,
    summary="查询 Agent 知识源",
)
def list_agent_knowledge_sources(
    agent_id: str,
    session: DbSession,
    principal: Principal,
) -> KnowledgeSourcePage:
    require_role(principal, {"admin", "engineer", "operator"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    sources = list_knowledge_sources(
        session,
        organization_id=principal.organization_id,
        agent_id=agent_id,
    )
    return KnowledgeSourcePage(
        items=[_knowledge_source_response(session, source) for source in sources]
    )


@router.post(
    "/{agent_id}/knowledge/sources",
    response_model=KnowledgeSourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建 Agent 知识源并索引文档",
)
def create_agent_knowledge_source(
    agent_id: str,
    request: KnowledgeSourceCreateRequest,
    session: DbSession,
    principal: Principal,
) -> KnowledgeSourceResponse:
    require_role(principal, {"admin", "engineer"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    source_was_new = _knowledge_source_exists(
        session=session,
        organization_id=principal.organization_id,
        agent_id=agent_id,
        name=request.name,
        idempotency_key=request.idempotency_key,
    ) is False
    source, document, chunks, embeddings = ingest_knowledge_source(
        session,
        organization_id=principal.organization_id,
        agent_id=agent_id,
        name=request.name,
        description=request.description,
        source_type=request.source_type,
        title=request.title,
        content=request.content,
        uri=request.uri,
        mime_type=request.mime_type,
        created_by=principal.user_id,
        idempotency_key=request.idempotency_key,
    )
    _record_knowledge_ingestion_events(
        session=session,
        principal=principal,
        agent_id=agent_id,
        source=source,
        document=document,
        chunks=chunks,
        embeddings=embeddings,
        idempotency_key=request.idempotency_key,
        source_was_new=source_was_new,
    )
    session.commit()
    session.refresh(source)
    return _knowledge_source_response(session, source)


@router.get(
    "/sessions/{session_id}/messages",
    response_model=AgentMessagePage,
    summary="查询 Agent 会话消息",
)
def list_agent_messages(
    session_id: str,
    session: DbSession,
    principal: Principal,
) -> AgentMessagePage:
    require_role(principal, {"admin", "engineer", "operator"})
    agent_session = _owned_session(session_id=session_id, session=session, principal=principal)
    messages = list(
        session.execute(
            select(AgentMessage)
            .where(AgentMessage.session_id == agent_session.id)
            .order_by(AgentMessage.created_at.asc(), AgentMessage.id.asc())
        ).scalars()
    )
    return AgentMessagePage(items=messages)


@router.post(
    "/sessions/{session_id}/messages",
    response_model=AgentChatResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
    summary="内部兼容：发送 Agent 会话消息",
)
def send_agent_message(
    session_id: str,
    request: AgentChatRequest,
    session: DbSession,
    principal: Principal,
) -> AgentChatResponse:
    require_role(principal, {"admin", "engineer"})
    agent_session = _owned_session(session_id=session_id, session=session, principal=principal)
    now = utc_now()
    user_message = AgentMessage(
        session_id=agent_session.id,
        agent_id=agent_session.agent_id,
        role="user",
        content=request.content,
        metadata_json={},
        created_at=now,
    )
    session.add(user_message)
    session.flush()
    assistant_message = AgentMessage(
        session_id=agent_session.id,
        agent_id=agent_session.agent_id,
        role="assistant",
        content=_chat_reply(agent_id=agent_session.agent_id, content=request.content),
        metadata_json={"mode": "chat", "agent_id": agent_session.agent_id},
        created_at=utc_now(),
    )
    agent_session.updated_at = now
    session.add(assistant_message)
    session.commit()
    session.refresh(agent_session)
    session.refresh(user_message)
    session.refresh(assistant_message)
    return AgentChatResponse(
        session=agent_session,
        messages=[user_message, assistant_message],
    )


@router.post(
    "/{agent_id}/runs",
    response_model=AgentPlanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建 Agent Run",
    description="Agent Workspace 的主入口，固定使用 Plan 模式生成可审计 DAG，不自动执行工具。",
)
def create_agent_run(
    agent_id: str,
    request: AgentRunCreateRequest,
    session: DbSession,
    principal: Principal,
) -> AgentPlanResponse:
    require_role(principal, {"admin", "engineer"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    payload = request.model_copy(update={"agent_id": agent_id})
    return plan_with_agent(request=payload, session=session, principal=principal)


@router.post(
    "/{agent_id}/runs/plan/stream",
    summary="流式创建 Agent Plan",
    description=(
        "Claude Code 风格入口：用户只提交目标，服务端流式返回计划进度，"
        "最终创建 Agent Run。"
    ),
)
def stream_agent_plan_run(
    agent_id: str,
    request: AgentRunCreateRequest,
    session: DbSession,
    principal: Principal,
) -> StreamingResponse:
    require_role(principal, {"admin", "engineer"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)

    def sse(event: str, payload: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def iterator() -> Iterator[str]:
        yield sse(
            "delta",
            {"content": "我会先理解目标，然后生成一个可审计的执行计划。\n"},
        )
        time.sleep(0.05)
        yield sse(
            "delta",
            {"content": "Planner 正在拆解步骤，Harness 会同步记录事件流。\n"},
        )
        time.sleep(0.05)
        try:
            payload = request.model_copy(update={"agent_id": agent_id, "mode": "plan"})
            planned = plan_with_agent(request=payload, session=session, principal=principal)
        except Exception as exc:
            yield sse("error", {"message": str(exc)})
            return
        yield sse(
            "delta",
            {"content": f"计划已生成：{len(planned.plan.steps)} 个步骤。右侧已同步 Plan DAG。\n"},
        )
        yield sse(
            "run_created",
            {
                "run_id": planned.run_id,
                "status": planned.task.status,
                "step_count": len(planned.plan.steps),
                "message": planned.message,
            },
        )

    return StreamingResponse(iterator(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post(
    "/{agent_id}/runs/chat/stream",
    summary="Workspace Pro 对话流",
    description=(
        "Cursor/Claude Artifacts 风格 Workspace Pro 入口。服务端通过 SSE 返回 "
        "think、delta、artifact、usage 和 done 事件；底层仍创建 Agent Run 和可审计 Plan。"
    ),
)
def stream_agent_chat_run(
    agent_id: str,
    request: AgentChatStreamRequest,
    session: DbSession,
    principal: Principal,
) -> StreamingResponse:
    require_role(principal, {"admin", "engineer"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)

    def sse(event: str, payload: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def message_goal() -> str:
        if request.goal and request.goal.strip():
            return request.goal.strip()
        user_messages = [node for node in request.messages if node.role == "user"]
        if user_messages:
            return user_messages[-1].content.strip()
        return "Start a normal assistant conversation."

    def estimated_input_tokens() -> int:
        pinned = {
            node.id for node in request.messages if node.id in set(request.pinned_node_ids)
        }
        coverage_ids = (
            set(request.compressed_context.coverage_node_ids)
            if request.compressed_context is not None
            else set()
        )
        carried = [
            node
            for node in request.messages[-request.context_window_turns :]
            if node.role in {"user", "assistant", "system"}
            and (node.id in pinned or node.id not in coverage_ids)
        ]
        pinned_nodes = [
            node for node in request.messages if node.id in pinned and node not in carried
        ]
        summary_length = (
            len(request.compressed_context.summary)
            if request.compressed_context is not None
            else 0
        )
        content_length = summary_length + sum(
            len(node.content) for node in [*pinned_nodes, *carried]
        )
        return max(1, content_length // 4)

    def requested_tool_payload(
        mention,
        metadata: ToolMetadata,
        tool_call_id: str,
        status: str,
        input_json: dict,
        approval_id: str | None = None,
    ) -> dict:
        payload = {
            "tool_call_id": tool_call_id,
            "tool_name": mention.name,
            "source": mention.source or metadata.source,
            "status": status,
            "input_json": input_json,
            "risk": metadata.category,
            "sandbox": "sandboxed" if metadata.requires_sandbox else "none",
        }
        if approval_id is not None:
            payload["approval_id"] = approval_id
        return payload

    def result_payload(execution: ToolExecution, tool_call_id: str) -> dict:
        tool_call = execution.tool_call
        output_json = tool_call.output_json if isinstance(tool_call.output_json, dict) else {}
        payload = {
            "tool_call_id": tool_call_id,
            "tool_name": tool_call.tool_name,
            "status": _workspace_tool_status(tool_call.status),
            "output_summary": _tool_output_summary(tool_call, output_json),
            "output_json": output_json,
            "duration_ms": tool_call.duration_ms,
            "trace_id": _trace_id_for_tool_call(tool_call.id, session=session),
        }
        approval_id = output_json.get("approval_id")
        if isinstance(approval_id, str):
            payload["approval_id"] = approval_id
        return payload

    def workspace_text_events(
        *,
        run: Task,
        messages: list[ModelMessage],
        query_goal: str,
        started_at: float,
        first_byte_at: float,
        run_created_message: str,
        done_message: str,
        enable_knowledge_grounding: bool = False,
    ) -> Iterator[str]:
        grounding: KnowledgeGroundingResult | None = None
        if enable_knowledge_grounding:
            query = query_goal.strip() or next(
                (
                    message.content.strip()
                    for message in reversed(messages)
                    if message.role == "user"
                ),
                "",
            )
            if query:
                grounding = ground_query(
                    session,
                    organization_id=principal.organization_id,
                    agent_id=agent_id,
                    run_id=run.id,
                    query=query,
                )
                if messages and messages[0].role == "system":
                    messages = [
                        messages[0],
                        ModelMessage(role="system", content=grounding.evidence_summary),
                        *messages[1:],
                    ]
                else:
                    messages = [
                        ModelMessage(role="system", content=grounding.evidence_summary),
                        *messages,
                    ]
        run.status = "RUNNING"
        run.updated_at = utc_now()
        session.flush()
        yield sse(
            "run_created",
            {
                "run_id": run.id,
                "status": run.status,
                "step_count": 0,
                "message": run_created_message,
            },
        )
        content_accumulator = ""
        usage: dict = {}
        first_delta_at: float | None = None
        stream_iter = None
        try:
            gateway = AuditedModelGateway(
                session=session,
                task_id=run.id,
                agent_run_id=None,
                grounding_correlation_id=(
                    grounding.prompt_manifest.grounding_correlation_id
                    if grounding and grounding.prompt_manifest
                    else None
                ),
                prompt_manifest_id=(
                    grounding.prompt_manifest.id
                    if grounding and grounding.prompt_manifest
                    else None
                ),
                prompt_manifest_version=(
                    str(grounding.prompt_manifest.metadata_json.get("prompt_manifest_version"))
                    if grounding
                    and grounding.prompt_manifest
                    and isinstance(grounding.prompt_manifest.metadata_json, dict)
                    else None
                ),
                retrieval_evidence_ids=(
                    list(grounding.prompt_manifest.included_retrieval_hit_ids_json)
                    if grounding and grounding.prompt_manifest
                    else []
                ),
                evidence_text_sha256=(
                    grounding.prompt_manifest.evidence_text_sha256
                    if grounding and grounding.prompt_manifest
                    else None
                ),
            )
            stream_iter = gateway.stream(
                ModelRequest(
                    model_provider=run.model_provider,
                    model_name=run.model_name,
                    response_format="text",
                    messages=messages,
                )
            )
            for chunk in stream_iter:
                if chunk.text:
                    content_accumulator += chunk.text
                    if first_delta_at is None:
                        first_delta_at = time.monotonic()
                    if not enable_knowledge_grounding:
                        yield sse("delta", {"content": chunk.text})
                if chunk.usage:
                    usage.update(chunk.usage)

            content = _require_normal_chat_content(content_accumulator)
            normalized_content = _normalize_grounding_citations(
                content=content,
                grounding=grounding,
            )
            if normalized_content != content:
                content = normalized_content
                content_accumulator = content
            citation_suffix = _missing_grounding_citation_suffix(
                content=content,
                grounding=grounding,
            )
            if citation_suffix:
                content += citation_suffix
                content_accumulator = content
            if enable_knowledge_grounding:
                if first_delta_at is None:
                    first_delta_at = time.monotonic()
                yield sse("delta", {"content": content})
            run.status = "COMPLETED"
            run.completed_at = utc_now()
            run.updated_at = utc_now()
            session.commit()
            ttfb_source = first_delta_at if first_delta_at is not None else first_byte_at
            yield sse(
                "usage",
                {
                    "input_tokens": int(usage.get("prompt_tokens", 0) or estimated_input_tokens()),
                    "output_tokens": int(
                        usage.get("completion_tokens", 0) or max(1, len(content) // 4)
                    ),
                    "cost_usd": None,
                    "cost_unavailable": True,
                    "ttfb_ms": int((ttfb_source - started_at) * 1000),
                    "duration_ms": int((time.monotonic() - started_at) * 1000),
                    "model_call_id": _latest_model_call_id(run.id, session=session),
                },
            )
            yield sse(
                "done",
                {
                    "run_id": run.id,
                    "active_branch_id": request.active_branch_id,
                    "continue_from_node_id": request.continue_from_node_id,
                    "status": run.status,
                    "step_count": 0,
                    "message": done_message,
                    "knowledge_grounding": grounding.evidence_message if grounding else None,
                },
            )
        except ModelGatewayError as exc:
            run.status = "FAILED"
            run.updated_at = utc_now()
            session.commit()
            yield sse("error", {"message": str(exc), "recoverable": True, "run_id": run.id})
        except GeneratorExit:
            if stream_iter is not None:
                stream_iter.close()
            run.status = "CANCELLED"
            run.completed_at = utc_now()
            run.updated_at = utc_now()
            EventStore(session).append(
                task_id=run.id,
                event_type=EventType.TASK_CANCELLED,
                payload_json={"task_id": run.id, "reason": "client_disconnected"},
            )
            session.commit()
            raise

    def iterator() -> Iterator[str]:
        started_at = time.monotonic()
        first_byte_at = time.monotonic()
        goal = message_goal()
        try:
            if request.run_id and request.mode == "plan":
                existing_run = _owned_run(
                    run_id=request.run_id,
                    session=session,
                    principal=principal,
                )
                planned = _agent_plan_response_from_run(
                    agent_id=agent_id,
                    run=existing_run,
                    session=session,
                    message_prefix="已继续原 Run",
                )
            elif request.run_id:
                existing_run = _owned_run(
                    run_id=request.run_id,
                    session=session,
                    principal=principal,
                )
                run = (
                    existing_run
                    if _latest_plan(run_id=existing_run.id, session=session) is None
                    else _create_workspace_chat_run(
                        agent_id=agent_id,
                        goal=goal,
                        session=session,
                        principal=principal,
                        mode="chat" if request.mode == "chat" else "codex_plan",
                        model_provider=request.model_provider,
                        model_name=request.model_name,
                    )
                )
                if request.mode == "codex_plan":
                    yield from workspace_text_events(
                        run=run,
                        messages=_workspace_codex_plan_messages(
                            agent_id=agent_id,
                            goal=goal,
                            request=request,
                        ),
                        query_goal=goal,
                        started_at=started_at,
                        first_byte_at=first_byte_at,
                        run_created_message="Codex plan run started.",
                        done_message="Codex plan response completed.",
                        enable_knowledge_grounding=False,
                    )
                    return
                yield from workspace_text_events(
                    run=run,
                    messages=_workspace_chat_messages(
                        agent_id=agent_id,
                        goal=goal,
                        request=request,
                    ),
                    query_goal=goal,
                    started_at=started_at,
                    first_byte_at=first_byte_at,
                    run_created_message="Chat run started.",
                    done_message="Chat response completed.",
                    enable_knowledge_grounding=True,
                )
                return
            else:
                if request.mode == "plan":
                    payload = AgentPlanRequest(
                        agent_id=agent_id,
                        goal=goal,
                        title=None,
                        model_provider=request.model_provider or "default",
                        model_name=request.model_name or "default",
                        max_runtime_seconds=1800,
                        max_subagents=5,
                        enable_sandbox=True,
                        enable_network=False,
                    )
                    yield sse(
                        "think_delta",
                        {
                            "content": (
                                "已读取当前分支、Pinned 消息和上下文窗口，"
                                "准备生成可审计计划。\n"
                            ),
                            "active_leaf_id": request.active_leaf_id,
                            "active_branch_id": request.active_branch_id,
                            "pinned_node_ids": request.pinned_node_ids,
                            "context_window_turns": request.context_window_turns,
                        },
                    )
                    planned = plan_with_agent(request=payload, session=session, principal=principal)
                elif request.mode == "codex_plan":
                    run = _create_workspace_chat_run(
                        agent_id=agent_id,
                        goal=goal,
                        session=session,
                        principal=principal,
                        mode="codex_plan",
                        model_provider=request.model_provider,
                        model_name=request.model_name,
                    )
                    yield from workspace_text_events(
                        run=run,
                        messages=_workspace_codex_plan_messages(
                            agent_id=agent_id,
                            goal=goal,
                            request=request,
                        ),
                        query_goal=goal,
                        started_at=started_at,
                        first_byte_at=first_byte_at,
                        run_created_message="Codex plan run started.",
                        done_message="Codex plan response completed.",
                        enable_knowledge_grounding=False,
                    )
                    return
                else:
                    run = _create_workspace_chat_run(
                        agent_id=agent_id,
                        goal=goal,
                        session=session,
                        principal=principal,
                        mode="chat",
                        model_provider=request.model_provider,
                        model_name=request.model_name,
                    )
                    yield from workspace_text_events(
                        run=run,
                        messages=_workspace_chat_messages(
                            agent_id=agent_id,
                            goal=goal,
                            request=request,
                        ),
                        query_goal=goal,
                        started_at=started_at,
                        first_byte_at=first_byte_at,
                        run_created_message="Chat run started.",
                        done_message="Chat response completed.",
                        enable_knowledge_grounding=True,
                    )
                    return
        except HTTPException as exc:
            if request.run_id:
                yield sse(
                    "error",
                    {
                        "message": f"run_id cannot be continued: {request.run_id}",
                        "recoverable": True,
                        "run_id": request.run_id,
                    },
                )
                return
            yield sse("error", {"message": str(exc.detail), "recoverable": True})
            return
        except Exception as exc:
            yield sse("error", {"message": str(exc), "recoverable": False})
            return
        yield sse(
            "run_created",
            {
                "run_id": planned.run_id,
                "status": planned.task.status,
                "step_count": len(planned.plan.steps),
                "message": planned.message,
            },
        )
        registry = ToolRegistry.default()
        runner = ToolRunner(session=session, registry=registry)
        if request.tool_mentions:
            for index, mention in enumerate(request.tool_mentions):
                metadata = registry.tools.get(mention.name)
                tool_call_id = f"workspace-tool-{planned.run_id}-{index}"
                if metadata is None:
                    yield sse(
                        "tool_call_requested",
                        {
                            "tool_call_id": tool_call_id,
                            "tool_name": mention.name,
                            "source": mention.source,
                            "input_json": mention.payload,
                            "status": "failed",
                            "risk": "unknown",
                            "sandbox": "none",
                        },
                    )
                    yield sse(
                        "tool_call_result",
                        {
                            "tool_call_id": tool_call_id,
                            "tool_name": mention.name,
                            "status": "failed",
                            "output_summary": "unknown tool",
                            "output_json": {},
                            "duration_ms": 0,
                            "trace_id": None,
                        },
                    )
                    continue
                input_json = _normalize_tool_mention_payload(mention.name, mention.payload, goal)
                executable = (
                    metadata.risk_level == "low"
                    and metadata.idempotent
                    and not metadata.requires_sandbox
                    and metadata.network_policy in {"none", "restricted"}
                )
                if not executable:
                    execution = runner.request_approval(
                        task_id=planned.run_id,
                        agent_run_id=planned.run_id,
                        tool_name=mention.name,
                        input_json=input_json,
                    )
                    run = session.get(Task, planned.run_id)
                    if run is not None:
                        run.status = "WAITING_APPROVAL"
                        run.updated_at = utc_now()
                    session.commit()
                    approval_id = execution.output.get("approval_id")
                    yield sse(
                        "tool_call_requested",
                        requested_tool_payload(
                            mention,
                            metadata,
                            execution.tool_call.id,
                            "pending_approval",
                            input_json,
                            approval_id if isinstance(approval_id, str) else None,
                        ),
                    )
                    continue
                yield sse(
                    "tool_call_requested",
                    requested_tool_payload(mention, metadata, tool_call_id, "running", input_json),
                )
                execution = runner.execute(
                    task_id=planned.run_id,
                    agent_run_id=planned.run_id,
                    tool_name=mention.name,
                    input_json=input_json,
                    roles=principal.roles,
                )
                session.commit()
                yield sse("tool_call_result", result_payload(execution, tool_call_id))
        plan_json = planned.plan.plan_json
        summary = planned.plan.summary or planned.message
        yield sse("delta", {"content": f"{summary}\n"})
        yield sse(
            "artifact_created",
            {
                "name": "plan.json",
                "artifact_type": "json",
                "status": "ready",
                "content": plan_json,
                "run_id": planned.run_id,
            },
        )
        output_tokens = max(1, len(summary) // 4)
        yield sse(
            "usage",
            {
                "input_tokens": estimated_input_tokens(),
                "output_tokens": output_tokens,
                "cost_usd": None,
                "cost_unavailable": True,
                "ttfb_ms": int((first_byte_at - started_at) * 1000),
                "duration_ms": int((time.monotonic() - started_at) * 1000),
                "model_call_id": _latest_model_call_id(planned.run_id, session=session),
            },
        )
        yield sse(
            "done",
            {
                "run_id": planned.run_id,
                "active_branch_id": request.active_branch_id,
                "continue_from_node_id": request.continue_from_node_id,
                "status": _run_status(
                    planned.run_id,
                    fallback=planned.task.status,
                    session=session,
                ),
                "step_count": len(planned.plan.steps),
                "message": planned.message,
            },
        )

    return StreamingResponse(iterator(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post(
    "/{agent_id}/context/compress",
    response_model=WorkspaceContextCompressionResponse,
    summary="压缩 Workspace 对话上下文",
)
def compress_agent_workspace_context(
    agent_id: str,
    request: WorkspaceContextCompressionRequest,
    session: DbSession,
    principal: Principal,
) -> WorkspaceContextCompressionResponse:
    require_role(principal, {"admin", "engineer"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)

    now = utc_now()
    provider = _normalize_model_id(request.model_provider or "default")
    model = _normalize_model_id(request.model_name or "default")
    prior_provider = _normalize_model_id(request.compressor_provider or provider)
    prior_model = _normalize_model_id(request.compressor_model or model)
    pinned_ids = set(request.pinned_node_ids)
    eligible = [
        node
        for node in request.messages
        if node.role in {"user", "assistant", "system"}
        and node.id not in pinned_ids
        and node.content.strip()
    ]
    coverage_node_ids = [node.id for node in eligible]
    coverage_path_hash = _workspace_context_path_hash(eligible)
    estimated_original_tokens = _estimate_nodes_tokens(eligible)
    estimated_uncovered_tokens = _estimate_nodes_tokens(
        [
            node
            for node in request.messages
            if node.role in {"user", "assistant", "system"}
            and node.id not in set(coverage_node_ids)
            and node.content.strip()
        ]
    )

    validation_status: Literal["ok", "missing_raw_nodes", "hash_mismatch"] = "ok"
    if request.prior_coverage_node_ids:
        raw_ids = {node.id for node in request.messages}
        if any(node_id not in raw_ids for node_id in request.prior_coverage_node_ids):
            validation_status = "missing_raw_nodes"
        elif (
            request.prior_coverage_path_hash
            and request.prior_coverage_path_hash != coverage_path_hash
        ):
            validation_status = "hash_mismatch"
        elif request.summary_schema_version != SUMMARY_SCHEMA_VERSION:
            validation_status = "hash_mismatch"
        elif request.compression_prompt_version != COMPRESSION_PROMPT_VERSION:
            validation_status = "hash_mismatch"
        elif prior_provider != provider or prior_model != model:
            validation_status = "hash_mismatch"

    if (
        validation_status == "ok"
        and request.existing_summary
        and request.prior_coverage_node_ids == coverage_node_ids
        and request.prior_coverage_path_hash == coverage_path_hash
    ):
        summary = request.existing_summary.strip()
        return WorkspaceContextCompressionResponse(
            status="ok",
            cache_status="accepted",
            summary=summary,
            coverage_node_ids=coverage_node_ids,
            coverage_path_hash=coverage_path_hash,
            last_covered_node_id=coverage_node_ids[-1] if coverage_node_ids else None,
            summary_schema_version=SUMMARY_SCHEMA_VERSION,
            compression_prompt_version=COMPRESSION_PROMPT_VERSION,
            compressor_provider=provider,
            compressor_model=model,
            estimated_original_tokens=estimated_original_tokens,
            estimated_summary_tokens=max(1, len(summary) // 4) if summary else 0,
            estimated_uncovered_tokens=estimated_uncovered_tokens,
            created_at=now,
            updated_at=now,
            error=None,
        )

    if not eligible:
        return WorkspaceContextCompressionResponse(
            status="missing_raw_nodes",
            cache_status="error",
            summary="",
            coverage_node_ids=[],
            coverage_path_hash="",
            last_covered_node_id=None,
            summary_schema_version=SUMMARY_SCHEMA_VERSION,
            compression_prompt_version=COMPRESSION_PROMPT_VERSION,
            compressor_provider=provider,
            compressor_model=model,
            estimated_original_tokens=0,
            estimated_summary_tokens=0,
            estimated_uncovered_tokens=estimated_uncovered_tokens,
            created_at=now,
            updated_at=now,
            error="no eligible raw messages supplied for compression",
        )

    prompt = _workspace_compression_prompt(eligible)
    audit_task = _create_workspace_chat_run(
        agent_id=agent_id,
        goal="Compress workspace conversation context",
        session=session,
        principal=principal,
        mode="context_compression",
        model_provider=request.model_provider,
        model_name=request.model_name,
    )
    audit_task.status = "RUNNING"
    try:
        response = AuditedModelGateway(session=session, task_id=audit_task.id).complete(
            ModelRequest(
                model_provider=request.model_provider or "default",
                model_name=request.model_name or "default",
                response_format="text",
                messages=[
                    ModelMessage(
                        role="system",
                        content=(
                            "Summarize prior chat context for future assistant turns. "
                            "Preserve user goals, decisions, constraints, open questions, "
                            "named files, and important facts. Do not mention attachment "
                            "contents unless they appear in the supplied messages."
                        ),
                    ),
                    ModelMessage(role="user", content=prompt),
                ],
            )
        )
    except ModelGatewayError as exc:
        audit_task.status = "FAILED"
        audit_task.updated_at = utc_now()
        session.commit()
        return WorkspaceContextCompressionResponse(
            status="provider_error",
            cache_status="error",
            summary="",
            coverage_node_ids=coverage_node_ids,
            coverage_path_hash=coverage_path_hash,
            last_covered_node_id=coverage_node_ids[-1] if coverage_node_ids else None,
            summary_schema_version=SUMMARY_SCHEMA_VERSION,
            compression_prompt_version=COMPRESSION_PROMPT_VERSION,
            compressor_provider=provider,
            compressor_model=model,
            estimated_original_tokens=estimated_original_tokens,
            estimated_summary_tokens=0,
            estimated_uncovered_tokens=estimated_uncovered_tokens,
            created_at=now,
            updated_at=utc_now(),
            error=str(exc),
        )

    summary = response.content.strip()
    audit_task.status = "COMPLETED"
    audit_task.completed_at = utc_now()
    audit_task.updated_at = audit_task.completed_at
    session.commit()

    status: Literal["ok", "stale", "missing_raw_nodes", "hash_mismatch", "provider_error"]
    status = validation_status
    cache_status: Literal["accepted", "recomputed", "stale_rejected", "error"]
    cache_status = "recomputed" if validation_status == "ok" else "stale_rejected"
    return WorkspaceContextCompressionResponse(
        status=status,
        cache_status=cache_status,
        summary=summary,
        coverage_node_ids=coverage_node_ids,
        coverage_path_hash=coverage_path_hash,
        last_covered_node_id=coverage_node_ids[-1] if coverage_node_ids else None,
        summary_schema_version=SUMMARY_SCHEMA_VERSION,
        compression_prompt_version=COMPRESSION_PROMPT_VERSION,
        compressor_provider=_normalize_model_id(response.model_provider or provider),
        compressor_model=_normalize_model_id(response.model_name or model),
        estimated_original_tokens=estimated_original_tokens,
        estimated_summary_tokens=max(1, len(summary) // 4) if summary else 0,
        estimated_uncovered_tokens=estimated_uncovered_tokens,
        created_at=now,
        updated_at=utc_now(),
        error=None,
    )


@router.post(
    "/plan",
    response_model=AgentPlanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Agent Plan 模式",
    description="在 Agent 工作台中只做任务分解与规划，不执行工具、Subagent 或 Sandbox。",
)
def plan_with_agent(
    request: AgentPlanRequest,
    session: DbSession,
    principal: Principal,
) -> AgentPlanResponse:
    require_role(principal, {"admin", "engineer"})
    task = Task(
        organization_id=principal.organization_id,
        created_by=principal.user_id,
        title=request.title or _title_from_goal(request.goal),
        goal=request.goal,
        status="CREATED",
        model_provider=request.model_provider,
        model_name=request.model_name,
        max_runtime_seconds=request.max_runtime_seconds,
        max_subagents=request.max_subagents,
        enable_sandbox=request.enable_sandbox,
        enable_network=request.enable_network,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(task)
    session.flush()
    event_store = EventStore(session)
    event_store.append(
        task_id=task.id,
        event_type=EventType.TASK_CREATED,
        payload_json={
            "task_id": task.id,
            "title": task.title,
            "goal": task.goal,
            "agent_id": request.agent_id,
            "mode": "plan",
        },
        actor_type="user",
        actor_id=principal.user_id,
    )
    task.status = "PLANNING"
    task.updated_at = utc_now()
    event_store.append(
        task_id=task.id,
        event_type=EventType.PLAN_REQUESTED,
        payload_json={
            "task_id": task.id,
            "goal": task.goal,
            "agent_id": request.agent_id,
            "mode": "plan",
            "prompt_version": PLANNER_PROMPT_VERSION,
        },
    )
    try:
        planner_response_content = _complete_plan_prompt(task=task, session=session)
    except ModelGatewayError as exc:
        task.status = "FAILED"
        task.updated_at = utc_now()
        event_store.append(
            task_id=task.id,
            event_type=EventType.TASK_FAILED,
            payload_json={
                "task_id": task.id,
                "goal": task.goal,
                "agent_id": request.agent_id,
                "mode": "plan",
                "reason": str(exc),
            },
        )
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Plan 模型调用失败：{exc}",
        ) from exc
    planner = DeterministicPlanner()
    plan = planner.parse_model_plan(
        planner_response_content,
        planner_source="llm",
        planner_attempts=1,
    )
    if plan is None:
        event_store.append(
            task_id=task.id,
            event_type=EventType.PLAN_REJECTED,
            payload_json={
                "reason": "model_plan_schema_invalid",
                "attempt": 1,
                "content_preview": planner_response_content[:500],
                "prompt_version": PLANNER_PROMPT_VERSION,
            },
        )
        repaired_content = _repair_plan_prompt(
            task=task,
            invalid_content=planner_response_content,
            session=session,
        )
        if repaired_content is not None:
            plan = planner.parse_model_plan(
                repaired_content,
                planner_source="llm_repaired",
                planner_attempts=2,
            )
            if plan is None:
                event_store.append(
                    task_id=task.id,
                    event_type=EventType.PLAN_REJECTED,
                    payload_json={
                        "reason": "model_plan_repair_schema_invalid",
                        "attempt": 2,
                        "content_preview": repaired_content[:500],
                        "prompt_version": PLANNER_PROMPT_VERSION,
                    },
                )
        else:
            event_store.append(
                task_id=task.id,
                event_type=EventType.PLAN_REJECTED,
                payload_json={
                    "reason": "model_plan_repair_call_failed",
                    "attempt": 2,
                    "prompt_version": PLANNER_PROMPT_VERSION,
                },
            )
        if plan is None:
            plan = planner.create_plan(task)
    try:
        plan = ExecutionPlanSchema.model_validate(plan)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    plan_row = ExecutionPlan(
        task_id=task.id,
        version=1,
        status="GENERATED",
        plan_json=plan.model_dump(),
        created_at=utc_now(),
    )
    session.add(plan_row)
    session.flush()
    event_store.append(
        task_id=task.id,
        event_type=EventType.PLAN_GENERATED,
        payload_json={
            "plan_id": plan_row.id,
            "plan": plan.model_dump(),
            "agent_id": request.agent_id,
            "mode": "plan",
            "prompt_version": PLANNER_PROMPT_VERSION,
            "trace_summary": "Agent Plan 模式已生成计划，等待用户确认执行。",
        },
    )
    task.status = "PLANNED"
    task.updated_at = utc_now()
    session.commit()
    session.refresh(task)
    session.refresh(plan_row)
    return AgentPlanResponse(
        agent_id=request.agent_id,
        run_id=task.id,
        task=task,
        plan=_plan_response(plan_row),
        message=f"已为目标生成 {len(plan.steps)} 个步骤的计划，当前未执行任何工具。",
    )


@router.post(
    "/auto",
    response_model=AgentAutoResponse,
    status_code=status.HTTP_202_ACCEPTED,
    include_in_schema=False,
    summary="内部兼容：自动执行 Agent Run",
    description="内部兼容端点。主产品入口只暴露 Plan，自动执行能力保留给测试和后台编排。",
)
def auto_with_agent(
    request: AgentPlanRequest,
    session: DbSession,
    principal: Principal,
) -> AgentAutoResponse:
    require_role(principal, {"admin", "engineer"})
    planned = plan_with_agent(request=request, session=session, principal=principal)
    ensure_default_agents(session, principal.organization_id)
    run = _owned_run(run_id=planned.run_id, session=session, principal=principal)
    orchestrator = MultiAgentOrchestrator(session)
    assignments, handoffs = orchestrator.execute_assignments(run=run)
    routing_strategy = orchestrator.routing_strategy(run=run)
    routing_reasoning = orchestrator.routing_reasoning(run=run)
    session.commit()
    run = _owned_run(run_id=planned.run_id, session=session, principal=principal)
    executed = Executor(session).execute_existing_plan(run)
    session.commit()
    session.refresh(executed)
    plan = _latest_plan(run_id=executed.id, session=session)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent Run 尚未规划")
    return AgentAutoResponse(
        agent_id=request.agent_id,
        run_id=executed.id,
        task=executed,
        plan=_plan_response(plan),
        orchestration=AgentOrchestrateResponse(
            run_id=executed.id,
            strategy=routing_strategy,
            routing_reasoning=routing_reasoning,
            assignments=assignments,
            handoffs=handoffs,
            message=f"已执行 {len(assignments)} 个具名 Agent assignment 并完成 Reduce。",
        ),
        message="内部自动流程已完成计划、多 Agent 编排和 Run 执行。",
    )


@router.get(
    "/runs",
    response_model=TaskPage,
    summary="查询 Agent Run 历史",
    description="返回 Agent Workspace 创建的 Run 历史；底层兼容 tasks 表。",
)
def list_agent_runs(
    session: DbSession,
    principal: Principal,
) -> TaskPage:
    require_role(principal, {"admin", "engineer", "operator"})
    runs = list(
        session.execute(
            select(Task)
            .where(Task.organization_id == principal.organization_id)
            .order_by(Task.created_at.desc())
            .limit(100)
        ).scalars()
    )
    return TaskPage(items=runs)


@router.get(
    "/runs/{run_id}/workspace",
    response_model=AgentRunWorkspaceResponse,
    summary="查询 Agent Workspace 聚合视图",
    description=(
        "返回一个 Agent Run 的 Plan DAG、事件流、Subagent、工具调用、"
        "模型调用、审批和多 Agent 编排状态。"
    ),
)
def get_agent_run_workspace(
    run_id: str,
    session: DbSession,
    principal: Principal,
    retrieval_session_id: str | None = Query(default=None),
    prompt_manifest_id: str | None = Query(default=None),
) -> AgentRunWorkspaceResponse:
    require_role(principal, {"admin", "engineer", "operator"})
    run = _owned_run(run_id=run_id, session=session, principal=principal)
    plan = _latest_plan(run_id=run.id, session=session)
    events = list(
        session.execute(
            select(AgentEvent)
            .where(AgentEvent.task_id == run.id)
            .order_by(AgentEvent.sequence.asc())
            .limit(200)
        ).scalars()
    )
    subagents = list(
        session.execute(
            select(AgentRun)
            .where(AgentRun.task_id == run.id)
            .order_by(AgentRun.started_at.asc().nullsfirst(), AgentRun.id.asc())
        ).scalars()
    )
    tool_calls = list(
        session.execute(
            select(ToolCall)
            .where(ToolCall.task_id == run.id)
            .order_by(ToolCall.created_at.desc())
            .limit(100)
        ).scalars()
    )
    model_calls = list(
        session.execute(
            select(ModelCall)
            .where(ModelCall.task_id == run.id)
            .order_by(ModelCall.created_at.desc())
            .limit(100)
        ).scalars()
    )
    approvals = list(
        session.execute(
            select(ToolApproval)
            .where(ToolApproval.task_id == run.id)
            .order_by(ToolApproval.created_at.desc())
            .limit(50)
        ).scalars()
    )
    assignments = list(
        session.execute(
            select(AgentAssignment)
            .where(AgentAssignment.run_id == run.id)
            .order_by(AgentAssignment.created_at.asc(), AgentAssignment.id.asc())
        ).scalars()
    )
    handoffs = list(
        session.execute(
            select(AgentHandoff)
            .where(AgentHandoff.run_id == run.id)
            .order_by(AgentHandoff.created_at.asc(), AgentHandoff.id.asc())
        ).scalars()
    )
    trace_ids = _trace_ids_by_subject(events=events)
    return AgentRunWorkspaceResponse(
        run=run,
        plan=_plan_response(plan) if plan is not None else None,
        events=[EventResponse.model_validate(event) for event in events],
        knowledge_grounding=_knowledge_grounding_response(
            session,
            run=run,
            retrieval_session_id=retrieval_session_id,
            prompt_manifest_id=prompt_manifest_id,
        ),
        subagents=[SubagentResponse.model_validate(subagent) for subagent in subagents],
        tool_calls=[
            _tool_call_response(call, trace_id=trace_ids.get(("tool", call.id)))
            for call in tool_calls
        ],
        model_calls=[
            _model_call_response(call, trace_id=trace_ids.get(("model", call.id)))
            for call in model_calls
        ],
        approvals=[ToolApprovalResponse.model_validate(approval) for approval in approvals],
        assignments=assignments,
        handoffs=handoffs,
    )


@router.post(
    "/runs/{run_id}/execute",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="执行 Agent Run 的既有计划",
    description="确认 Plan 模式生成的计划后，复用同一个 Agent Run 执行步骤，不重新规划。",
)
def execute_agent_run(
    run_id: str,
    session: DbSession,
    principal: Principal,
) -> Task:
    require_role(principal, {"admin", "engineer"})
    task = (
        session.query(Task)
        .filter(Task.id == run_id, Task.organization_id == principal.organization_id)
        .one_or_none()
    )
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent Run 未找到")
    if task.status != "PLANNED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="只有 PLANNED 状态的 Agent Run 可以确认执行",
        )
    try:
        executed = Executor(session).execute_existing_plan(task)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    session.commit()
    session.refresh(executed)
    return executed


@router.post(
    "/runs/{run_id}/orchestrate",
    response_model=AgentOrchestrateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建多 Agent 编排分配",
    description="基于已规划 Run 选择具名 Agent，创建 assignments 和 handoffs，不执行分支。",
)
def orchestrate_agent_run(
    run_id: str,
    session: DbSession,
    principal: Principal,
) -> AgentOrchestrateResponse:
    require_role(principal, {"admin", "engineer"})
    ensure_default_agents(session, principal.organization_id)
    run = _owned_run(run_id=run_id, session=session, principal=principal)
    if _latest_plan(run_id=run.id, session=session) is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent Run 尚未规划")
    orchestrator = MultiAgentOrchestrator(session)
    assignments, handoffs = orchestrator.orchestrate(
        run=run,
        entry_agent_id="default",
    )
    routing_strategy = orchestrator.routing_strategy(run=run)
    routing_reasoning = orchestrator.routing_reasoning(run=run)
    session.commit()
    return AgentOrchestrateResponse(
        run_id=run.id,
        strategy=routing_strategy,
        routing_reasoning=routing_reasoning,
        assignments=assignments,
        handoffs=handoffs,
        message=f"已为 Run 创建 {len(assignments)} 个具名 Agent assignment。",
    )


@router.post(
    "/runs/{run_id}/orchestrate/execute",
    response_model=AgentOrchestrateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="执行多 Agent 编排 assignments",
    description="执行 Run 的具名 Agent assignments，并用 Reducer 聚合分支输出。",
)
def execute_agent_orchestration(
    run_id: str,
    session: DbSession,
    principal: Principal,
) -> AgentOrchestrateResponse:
    require_role(principal, {"admin", "engineer"})
    ensure_default_agents(session, principal.organization_id)
    run = _owned_run(run_id=run_id, session=session, principal=principal)
    if _latest_plan(run_id=run.id, session=session) is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent Run 尚未规划")
    orchestrator = MultiAgentOrchestrator(session)
    assignments, handoffs = orchestrator.execute_assignments(run=run)
    routing_strategy = orchestrator.routing_strategy(run=run)
    routing_reasoning = orchestrator.routing_reasoning(run=run)
    session.commit()
    return AgentOrchestrateResponse(
        run_id=run.id,
        strategy=routing_strategy,
        routing_reasoning=routing_reasoning,
        assignments=assignments,
        handoffs=handoffs,
        message=f"已执行 {len(assignments)} 个具名 Agent assignment 并完成 Reduce。",
    )


@router.post(
    "/runs/{run_id}/orchestrate/enqueue",
    response_model=AgentOrchestrateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="入队执行多 Agent 编排 assignments",
    description="将 Run 的具名 Agent assignments 投递到 Dramatiq 队列。",
)
def enqueue_agent_orchestration(
    run_id: str,
    session: DbSession,
    principal: Principal,
) -> AgentOrchestrateResponse:
    require_role(principal, {"admin", "engineer"})
    ensure_default_agents(session, principal.organization_id)
    run = _owned_run(run_id=run_id, session=session, principal=principal)
    if _latest_plan(run_id=run.id, session=session) is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent Run 尚未规划")
    orchestrator = MultiAgentOrchestrator(session)
    assignments, handoffs = orchestrator.enqueue_assignments(run=run)
    routing_strategy = orchestrator.routing_strategy(run=run)
    routing_reasoning = orchestrator.routing_reasoning(run=run)
    session.commit()
    return AgentOrchestrateResponse(
        run_id=run.id,
        strategy=routing_strategy,
        routing_reasoning=routing_reasoning,
        assignments=assignments,
        handoffs=handoffs,
        message=f"已将 {len(assignments)} 个具名 Agent assignment 投递到队列。",
    )


@router.get(
    "/runs/{run_id}/assignments",
    response_model=list[AgentAssignmentResponse],
    summary="查询 Run 的 Agent assignments",
)
def list_agent_run_assignments(
    run_id: str,
    session: DbSession,
    principal: Principal,
) -> list[AgentAssignment]:
    require_role(principal, {"admin", "engineer", "operator"})
    run = _owned_run(run_id=run_id, session=session, principal=principal)
    return list(
        session.execute(
            select(AgentAssignment)
            .where(AgentAssignment.run_id == run.id)
            .order_by(AgentAssignment.created_at.asc(), AgentAssignment.id.asc())
        ).scalars()
    )


@router.get(
    "/runs/{run_id}/handoffs",
    response_model=list[AgentHandoffResponse],
    summary="查询 Run 的 Agent handoffs",
)
def list_agent_run_handoffs(
    run_id: str,
    session: DbSession,
    principal: Principal,
) -> list[AgentHandoff]:
    require_role(principal, {"admin", "engineer", "operator"})
    run = _owned_run(run_id=run_id, session=session, principal=principal)
    return list(
        session.execute(
            select(AgentHandoff)
            .where(AgentHandoff.run_id == run.id)
            .order_by(AgentHandoff.created_at.asc(), AgentHandoff.id.asc())
        ).scalars()
    )


@router.get(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="查询 Agent 详情",
    description="返回指定具名 Agent 的模型、工具、角色和路由标签。",
)
def get_agent(agent_id: str, session: DbSession, principal: Principal) -> Agent:
    require_role(principal, {"admin", "engineer", "operator"})
    return _get_agent(agent_id=agent_id, session=session, principal=principal)


def _complete_plan_prompt(*, task: Task, session: Session) -> str:
    response = AuditedModelGateway(session=session, task_id=task.id).complete(
        ModelRequest(
            model_provider=task.model_provider,
            model_name=task.model_name,
            messages=[
                ModelMessage(role="system", content=PLANNER_SYSTEM_PROMPT),
                ModelMessage(
                    role="user",
                    content=(
                        f"Agent Plan mode only. Do not execute tools.\n\n"
                        f"Task title:\n{task.title}\n\n"
                        f"Task goal:\n{task.goal}\n\n"
                        f"Max subagents: {task.max_subagents}\n"
                        f"Sandbox enabled: {task.enable_sandbox}\n"
                        f"Network enabled: {task.enable_network}"
                    ),
                ),
            ],
        )
    )
    return response.content


def _repair_plan_prompt(*, task: Task, invalid_content: str, session: Session) -> str | None:
    try:
        response = AuditedModelGateway(session=session, task_id=task.id).complete(
            ModelRequest(
                model_provider=task.model_provider,
                model_name=task.model_name,
                messages=[
                    ModelMessage(
                        role="system",
                        content=(
                            f"{PLANNER_SYSTEM_PROMPT}\nRepair the previous Planner output. "
                            "Return one valid JSON object that matches the required schema."
                        ),
                    ),
                    ModelMessage(
                        role="user",
                        content=(
                            "Task goal:\n"
                            f"{task.goal}\n\nInvalid Planner output:\n{invalid_content}"
                        ),
                    ),
                ],
            )
        )
    except ModelGatewayError:
        return None
    return response.content


def _create_workspace_chat_run(
    *,
    agent_id: str,
    goal: str,
    session: Session,
    principal: Principal,
    mode: Literal["chat", "codex_plan", "context_compression"] = "chat",
    model_provider: str | None = None,
    model_name: str | None = None,
) -> Task:
    task = Task(
        organization_id=principal.organization_id,
        created_by=principal.user_id,
        title=_title_from_goal(goal),
        goal=goal,
        status="CREATED",
        model_provider=model_provider or "default",
        model_name=model_name or "default",
        max_runtime_seconds=1800,
        max_subagents=0,
        enable_sandbox=False,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(task)
    session.flush()
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
    session.flush()
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
        if node.role in {"user", "assistant", "system"}
        and node.id not in pinned_ids
        and node.id not in coverage_ids
    ]
    pinned = [
        node
        for node in request.messages
        if node.id in pinned_ids and node.role in {"user", "assistant", "system"}
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
        role = node.role if node.role in {"user", "assistant", "system"} else "user"
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
            f"\n<message id=\"{node.id}\" role=\"{node.role}\" state=\"{node.state}\">\n"
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
            "Do not infer or fabricate their contents. File names: "
            + ", ".join(attachment_names)
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
                f"\n<attachment index=\"{index}\" name=\"{name}\" mime=\"{mime_type}\" "
                f"size_bytes=\"{size}\" status=\"readable{truncated_note}\">\n"
                f"{content}\n</attachment>"
            )
        else:
            reason = "read failed" if status == "error" else "content unavailable to this model"
            blocks.append(
                f"\n<attachment index=\"{index}\" name=\"{name}\" mime=\"{mime_type}\" "
                f"size_bytes=\"{size}\" status=\"unreadable\" reason=\"{reason}\" />"
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


def _plan_response(plan: ExecutionPlan) -> TaskPlanResponse:
    steps = []
    for raw_step in plan.plan_json.get("steps", []):
        step_key = str(raw_step.get("key", ""))
        steps.append(
            TaskPlanStepState(
                step_key=step_key,
                description=str(raw_step.get("description", "")),
                depends_on=_string_list(raw_step.get("depends_on")),
                execution_mode=str(raw_step.get("execution_mode", "")),
                requires_sandbox=bool(raw_step.get("requires_sandbox", False)),
                can_spawn_subagent=bool(raw_step.get("can_spawn_subagent", False)),
                tool_hints=_string_list(raw_step.get("tool_hints")),
                acceptance_criteria=_string_list(raw_step.get("acceptance_criteria")),
                risk_level=str(raw_step.get("risk_level") or "low"),
                artifact_expectations=_string_list(raw_step.get("artifact_expectations")),
                quality_notes=_string_list(raw_step.get("quality_notes")),
                status="PENDING",
                assigned_agent_id=None,
                error_message=None,
                trace_summary=None,
                last_event_sequence=None,
                execution_trace=[],
            )
        )
    return TaskPlanResponse(
        id=plan.id,
        task_id=plan.task_id,
        version=plan.version,
        status=plan.status,
        summary=plan.plan_json.get("summary"),
        planner_source=str(plan.plan_json.get("planner_source", "deterministic")),
        planner_attempts=int(plan.plan_json.get("planner_attempts", 1) or 1),
        planner_prompt_version=str(plan.plan_json.get("planner_prompt_version") or "1.1.0"),
        quality_score=int(plan.plan_json.get("quality_score", 100) or 100),
        validation_warnings=_string_list(plan.plan_json.get("validation_warnings")),
        quality_gates=(
            plan.plan_json.get("quality_gates")
            if isinstance(plan.plan_json.get("quality_gates"), dict)
            else {}
        ),
        plan_json=plan.plan_json,
        steps=steps,
        created_at=plan.created_at,
    )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _title_from_goal(goal: str) -> str:
    title = " ".join(goal.strip().split())
    if len(title) <= 48:
        return title or "Agent Plan"
    return title[:45] + "..."


def _owned_run(*, run_id: str, session: Session, principal: Principal) -> Task:
    run = session.execute(
        select(Task).where(
            Task.id == run_id,
            Task.organization_id == principal.organization_id,
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent Run 未找到")
    return run


def _latest_plan(*, run_id: str, session: Session) -> ExecutionPlan | None:
    return session.execute(
        select(ExecutionPlan)
        .where(ExecutionPlan.task_id == run_id)
        .order_by(ExecutionPlan.version.desc())
        .limit(1)
    ).scalar_one_or_none()


def _latest_model_call_id(run_id: str, *, session: Session) -> str | None:
    model_call = session.execute(
        select(ModelCall)
        .where(ModelCall.task_id == run_id)
        .order_by(ModelCall.created_at.desc(), ModelCall.id.desc())
    ).scalars().first()
    return model_call.id if model_call is not None else None


def _run_status(run_id: str, *, fallback: str, session: Session) -> str:
    run = session.get(Task, run_id)
    return run.status if run is not None else fallback


def _agent_plan_response_from_run(
    *,
    agent_id: str,
    run: Task,
    session: Session,
    message_prefix: str,
) -> AgentPlanResponse:
    plan = _latest_plan(run_id=run.id, session=session)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent Run 尚未规划")
    return AgentPlanResponse(
        agent_id=agent_id,
        run_id=run.id,
        task=run,
        plan=_plan_response(plan),
        message=f"{message_prefix} {run.id}，当前未执行新的规划。",
    )


def _knowledge_source_exists(
    *,
    session: Session,
    organization_id: str | None,
    agent_id: str,
    name: str,
    idempotency_key: str | None,
) -> bool:
    statement = select(KnowledgeSource).where(
        KnowledgeSource.organization_id == organization_id,
        KnowledgeSource.agent_id == agent_id,
    )
    if idempotency_key:
        statement = statement.where(KnowledgeSource.idempotency_key == idempotency_key)
    else:
        statement = statement.where(KnowledgeSource.name == name)
    return session.execute(statement.limit(1)).scalar_one_or_none() is not None


def _record_knowledge_ingestion_events(
    *,
    session: Session,
    principal: Principal,
    agent_id: str,
    source: KnowledgeSource,
    document: KnowledgeDocument,
    chunks: list[KnowledgeChunk],
    embeddings: list[KnowledgeEmbedding],
    idempotency_key: str | None,
    source_was_new: bool,
) -> None:
    now = utc_now()
    audit_task = Task(
        organization_id=principal.organization_id,
        created_by=principal.user_id,
        title=f"Knowledge ingestion: {source.name}",
        goal=f"Index knowledge document {document.title}",
        status="COMPLETED",
        model_provider="system",
        model_name="knowledge-harness",
        max_runtime_seconds=0,
        max_subagents=0,
        enable_sandbox=False,
        enable_network=False,
        created_at=now,
        updated_at=now,
        completed_at=now,
    )
    session.add(audit_task)
    session.flush()
    event_store = EventStore(session)
    base_payload = {
        "schema_version": "knowledge-grounding-v1",
        "org_id": principal.organization_id,
        "agent_id": agent_id,
        "run_id": audit_task.id,
        "correlation_id": audit_task.id,
        "causation_id": audit_task.id,
        "idempotency_key": idempotency_key,
        "source_id": source.id,
        "document_id": document.id,
    }
    if source_was_new:
        event_store.append(
            task_id=audit_task.id,
            event_type=EventType.KNOWLEDGE_SOURCE_CREATED,
            payload_json={
                **base_payload,
                "source_type": source.source_type,
                "source_version": source.version,
            },
            actor_type="user",
            actor_id=principal.user_id,
        )
    event_store.append(
        task_id=audit_task.id,
        event_type=EventType.KNOWLEDGE_DOCUMENT_INDEXED,
        payload_json={
            **base_payload,
            "document_version": document.version,
            "chunk_ids": [chunk.id for chunk in chunks],
            "chunk_count": len(chunks),
            "embedding_ids": [embedding.id for embedding in embeddings],
        },
        actor_type="user",
        actor_id=principal.user_id,
    )


def _missing_grounding_citation_suffix(
    *,
    content: str,
    grounding: KnowledgeGroundingResult | None,
) -> str:
    if grounding is None or not grounding.citations:
        return ""
    missing_keys = [
        citation.citation_key
        for citation in grounding.citations
        if citation.citation_key not in content
    ]
    if not missing_keys:
        return ""
    return "\n\nSources: " + ", ".join(missing_keys)


def _normalize_grounding_citations(
    *,
    content: str,
    grounding: KnowledgeGroundingResult | None,
) -> str:
    if grounding is None:
        return content
    valid_keys = {citation.citation_key for citation in grounding.citations}
    invalid_keys: set[str] = set()

    def replace_invalid(match: re.Match[str]) -> str:
        citation_key = match.group(0)
        if citation_key in valid_keys:
            return citation_key
        invalid_keys.add(citation_key)
        return "[unsupported-citation]"

    normalized = re.sub(r"\[(?:web-)?\d+\]", replace_invalid, content)
    if not invalid_keys:
        return content
    return (
        f"{normalized}\n\nUnsupported citations removed: "
        f"{len(invalid_keys)}"
    )


def _knowledge_source_response(
    session: Session,
    source: KnowledgeSource,
) -> KnowledgeSourceResponse:
    documents = list(
        session.execute(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.source_id == source.id)
            .order_by(KnowledgeDocument.version.desc(), KnowledgeDocument.created_at.desc())
        ).scalars()
    )
    latest_document_ids = [document.id for document in documents[:5]]
    chunk_counts = dict(
        session.execute(
            select(KnowledgeChunk.document_id, func.count(KnowledgeChunk.id))
            .where(
                KnowledgeChunk.document_id.in_(latest_document_ids),
                KnowledgeChunk.status == "ACTIVE",
            )
            .group_by(KnowledgeChunk.document_id)
        ).all()
    ) if latest_document_ids else {}
    latest_documents = [
        KnowledgeDocumentResponse.model_validate(document).model_copy(
            update={"chunk_count": int(chunk_counts.get(document.id, 0))}
        )
        for document in documents[:5]
    ]
    return KnowledgeSourceResponse(
        id=source.id,
        organization_id=source.organization_id,
        agent_id=source.agent_id,
        name=source.name,
        description=source.description,
        source_type=source.source_type,
        status=source.status,
        version=source.version,
        settings_json=source.settings_json if isinstance(source.settings_json, dict) else {},
        metadata_json=source.metadata_json if isinstance(source.metadata_json, dict) else {},
        idempotency_key=source.idempotency_key,
        created_by=source.created_by,
        created_at=source.created_at,
        updated_at=source.updated_at,
        latest_documents=latest_documents,
    )


def _knowledge_grounding_response(
    session: Session,
    *,
    run: Task,
    retrieval_session_id: str | None = None,
    prompt_manifest_id: str | None = None,
) -> KnowledgeGroundingResponse | None:
    inferred_fallback = False
    fallback_reason: str | None = None
    prompt_manifest: PromptAssemblyManifest | None = None
    if prompt_manifest_id:
        prompt_manifest = session.get(PromptAssemblyManifest, prompt_manifest_id)
        if (
            prompt_manifest is None
            or prompt_manifest.run_id != run.id
            or prompt_manifest.organization_id != run.organization_id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Prompt manifest not found",
            )
        if (
            retrieval_session_id is not None
            and prompt_manifest.retrieval_session_id != retrieval_session_id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Prompt manifest does not belong to retrieval session",
            )
        retrieval_session = session.get(RetrievalSession, prompt_manifest.retrieval_session_id)
    elif retrieval_session_id:
        retrieval_session = session.get(RetrievalSession, retrieval_session_id)
        if (
            retrieval_session is None
            or retrieval_session.run_id != run.id
            or retrieval_session.organization_id != run.organization_id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Retrieval session not found",
            )
    else:
        inferred_fallback = True
        fallback_reason = "latest_run_retrieval_session"
        retrieval_session = session.execute(
            select(RetrievalSession)
            .where(RetrievalSession.run_id == run.id)
            .order_by(RetrievalSession.created_at.desc(), RetrievalSession.id.desc())
            .limit(1)
        ).scalar_one_or_none()
    if retrieval_session is None:
        return None
    hits = list(
        session.execute(
            select(RetrievalHit)
            .where(RetrievalHit.retrieval_session_id == retrieval_session.id)
            .order_by(RetrievalHit.rank.asc(), RetrievalHit.id.asc())
        ).scalars()
    )
    citations = list(
        session.execute(
            select(CitationRecord)
            .where(CitationRecord.retrieval_session_id == retrieval_session.id)
            .order_by(CitationRecord.created_at.asc(), CitationRecord.id.asc())
        ).scalars()
    )
    web_sources = list(
        session.execute(
            select(WebResearchSource)
            .where(WebResearchSource.retrieval_session_id == retrieval_session.id)
            .order_by(WebResearchSource.fetched_at.asc(), WebResearchSource.id.asc())
        ).scalars()
    )
    if prompt_manifest is None:
        prompt_manifest = session.execute(
            select(PromptAssemblyManifest)
            .where(PromptAssemblyManifest.retrieval_session_id == retrieval_session.id)
            .order_by(PromptAssemblyManifest.created_at.desc(), PromptAssemblyManifest.id.desc())
            .limit(1)
        ).scalar_one_or_none()
    policy_audits = list(
        session.execute(
            select(KnowledgePolicyAudit)
            .where(KnowledgePolicyAudit.retrieval_session_id == retrieval_session.id)
            .order_by(KnowledgePolicyAudit.created_at.asc(), KnowledgePolicyAudit.id.asc())
        ).scalars()
    )
    evidence_summary = "Local knowledge grounded the answer."
    if retrieval_session.local_status != "sufficient":
        evidence_summary = (
            "Local knowledge is insufficient; no web research provider is configured."
        )
        if web_sources:
            evidence_summary = (
                "Local knowledge is insufficient; controlled web research grounded the answer."
            )
    is_grounded = bool(citations) and (
        retrieval_session.local_status == "sufficient" or bool(web_sources)
    )
    if is_grounded and prompt_manifest is not None:
        evidence_summary = str(
            prompt_manifest.metadata_json.get("evidence_message") or evidence_summary
        )
    return KnowledgeGroundingResponse(
        retrieval_session=RetrievalSessionResponse.model_validate(retrieval_session),
        retrieval_hits=[KnowledgeRetrievalHitResponse.model_validate(hit) for hit in hits],
        citations=[KnowledgeCitationResponse.model_validate(citation) for citation in citations],
        prompt_manifest=(
            PromptAssemblyManifestResponse.model_validate(prompt_manifest)
            if prompt_manifest is not None
            else None
        ),
        policy_audits=[
            KnowledgePolicyAuditResponse.model_validate(audit) for audit in policy_audits
        ],
        web_sources=[WebResearchSourceResponse.model_validate(source) for source in web_sources],
        vector_capability=retrieval_session.vector_capability,
        local_status=retrieval_session.local_status,
        grounded=is_grounded,
        evidence_summary=evidence_summary,
        inferred_fallback=inferred_fallback,
        fallback_reason=fallback_reason,
        selected_retrieval_session_id=retrieval_session.id,
        selected_prompt_manifest_id=prompt_manifest.id if prompt_manifest else None,
    )


def _normalize_tool_mention_payload(tool_name: str, payload: dict, goal: str) -> dict:
    if tool_name == "mcp_context_search" and "query" not in payload:
        return {**payload, "query": goal, "limit": int(payload.get("limit", 5) or 5)}
    if tool_name == "list_files" and "root" not in payload:
        return {**payload, "root": ".", "glob": str(payload.get("glob", "**/*"))}
    if tool_name == "read_file" and "path" not in payload:
        return {**payload, "path": "pyproject.toml"}
    return payload


def _trace_id_for_tool_call(tool_call_id: str, *, session: Session) -> str | None:
    event = session.execute(
        select(AgentEvent)
        .where(AgentEvent.payload_json["tool_call_id"].as_string() == tool_call_id)
        .order_by(AgentEvent.sequence.desc())
    ).scalars().first()
    return event.trace_id if event is not None else None


def _trace_ids_by_subject(*, events: list[AgentEvent]) -> dict[tuple[str, str], str]:
    trace_ids: dict[tuple[str, str], str] = {}
    for event in events:
        if not isinstance(event.trace_id, str):
            continue
        model_call_id = event.payload_json.get("model_call_id")
        if isinstance(model_call_id, str):
            trace_ids.setdefault(("model", model_call_id), event.trace_id)
        tool_call_id = event.payload_json.get("tool_call_id")
        if isinstance(tool_call_id, str):
            trace_ids.setdefault(("tool", tool_call_id), event.trace_id)
    return trace_ids


def _workspace_tool_status(status_value: str) -> str:
    return {
        "SUCCESS": "success",
        "FAILED": "failed",
        "TIMEOUT": "failed",
        "DENIED": "rejected",
        "PENDING_APPROVAL": "pending_approval",
        "RUNNING": "running",
    }.get(status_value, status_value.lower())


def _model_call_response(
    model_call: ModelCall,
    *,
    trace_id: str | None,
) -> ModelCallResponse:
    return ModelCallResponse(
        id=model_call.id,
        task_id=model_call.task_id,
        agent_run_id=model_call.agent_run_id,
        trace_id=trace_id,
        model_provider=model_call.model_provider,
        model_name=model_call.model_name,
        status=model_call.status,
        prompt_tokens=model_call.prompt_tokens,
        completion_tokens=model_call.completion_tokens,
        duration_ms=model_call.duration_ms,
        grounding_correlation_id=model_call.grounding_correlation_id,
        prompt_manifest_id=model_call.prompt_manifest_id,
        model_request_sha256=model_call.model_request_sha256,
        attempt_index=model_call.attempt_index,
        terminal_status=model_call.terminal_status,
        request_json=model_call.request_json,
        response_json=model_call.response_json,
        error_message=model_call.error_message,
        created_at=model_call.created_at,
    )


def _tool_call_response(
    tool_call: ToolCall,
    *,
    trace_id: str | None,
) -> ToolCallResponse:
    output = tool_call.output_json if isinstance(tool_call.output_json, dict) else {}
    return ToolCallResponse(
        id=tool_call.id,
        task_id=tool_call.task_id,
        agent_run_id=tool_call.agent_run_id,
        trace_id=trace_id,
        tool_name=tool_call.tool_name,
        status=tool_call.status,
        risk_level=tool_call.risk_level,
        requires_sandbox=tool_call.requires_sandbox,
        sandbox_id=tool_call.sandbox_id,
        duration_ms=tool_call.duration_ms,
        input_json=tool_call.input_json,
        output_json=tool_call.output_json,
        output_kind=_tool_output_kind(tool_call, output),
        output_summary=_tool_output_summary(tool_call, output),
        timeout_category="tool_timeout" if tool_call.status == "TIMEOUT" else None,
        error_message=tool_call.error_message,
        created_at=tool_call.created_at,
    )


def _tool_output_kind(tool_call: ToolCall, output: dict) -> str:
    if tool_call.status == "DENIED":
        return "policy_denied"
    if tool_call.status == "TIMEOUT":
        return "timeout"
    if "content" in output:
        return "file_content"
    if "files" in output:
        return "file_list"
    if "exit_code" in output:
        return "shell_result"
    if "status_code" in output:
        return "http_response"
    if "path" in output and "bytes_written" in output:
        return "file_write"
    if tool_call.status == "FAILED":
        return "error"
    return "empty" if not output else "json"


def _tool_output_summary(tool_call: ToolCall, output: dict) -> str:
    if tool_call.error_message and tool_call.status in {"DENIED", "FAILED", "TIMEOUT"}:
        return tool_call.error_message[:300]
    if "content" in output:
        content = str(output.get("content") or "")
        return f"文件内容 {len(content)} 字符"
    if "files" in output and isinstance(output.get("files"), list):
        return f"文件列表 {len(output['files'])} 项"
    if "exit_code" in output:
        return f"命令退出码 {output.get('exit_code')}"
    if "status_code" in output:
        return f"HTTP {output.get('status_code')}"
    if "path" in output and "bytes_written" in output:
        return f"写入 {output.get('path')}，{output.get('bytes_written')} bytes"
    if not output:
        return "无输出"
    return f"JSON 输出字段 {len(output)} 个"


def _get_agent(*, agent_id: str, session: Session, principal: Principal) -> Agent:
    ensure_default_agents(session, principal.organization_id)
    session.commit()
    agent = session.execute(select(Agent).where(Agent.id == agent_id)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent 未找到")
    return agent


def _owned_session(
    *,
    session_id: str,
    session: Session,
    principal: Principal,
) -> AgentSession:
    agent_session = session.execute(
        select(AgentSession).where(
            AgentSession.id == session_id,
            AgentSession.organization_id == principal.organization_id,
        )
    ).scalar_one_or_none()
    if agent_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent Session 未找到")
    return agent_session


def _chat_reply(*, agent_id: str, content: str) -> str:
    return (
        f"{agent_id} 已收到你的消息。"
        "当前会话端点仅作为内部兼容层；主工作台固定使用 Plan 模式。"
        f"消息摘要：{content[:80]}"
    )
