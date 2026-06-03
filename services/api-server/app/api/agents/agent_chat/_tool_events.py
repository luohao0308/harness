"""Workspace chat tool-event helpers."""

# ruff: noqa: F401,F403,F405,I001,UP037
from collections.abc import Callable

from ..common import *
from .._capability_helpers import *
from .._grounding_helpers import *
from .._knowledge_helpers import *
from .._plan_helpers import *
from .._session_helpers import *
from .._tool_helpers import *
from .._workspace_chat_helpers import *
from .._workspace_response_helpers import *


class WorkspaceToolEventService:
    def __init__(
        self,
        *,
        agent_id: str,
        request: AgentChatStreamRequest,
        session: DbSession,
        principal: Principal,
        sse: Callable[[str, dict], str],
        estimated_input_tokens: Callable[[], int],
    ) -> None:
        self.agent_id = agent_id
        self.request = request
        self.session = session
        self.principal = principal
        self.sse = sse
        self.estimated_input_tokens = estimated_input_tokens

    def requested_tool_payload(
        self,
        mention,
        metadata: ToolMetadata,
        tool_call_id: str,
        status_value: str,
        input_json: dict,
        approval_id: str | None = None,
    ) -> dict:
        payload = {
            "tool_call_id": tool_call_id,
            "tool_name": mention.name,
            "source": mention.source or metadata.source,
            "status": status_value,
            "input_json": input_json,
            "risk": metadata.category,
            "sandbox": "sandboxed" if metadata.requires_sandbox else "none",
        }
        if approval_id is not None:
            payload["approval_id"] = approval_id
        return payload

    def result_payload(self, execution: ToolExecution, tool_call_id: str) -> dict:
        tool_call = execution.tool_call
        output_json = tool_call.output_json if isinstance(tool_call.output_json, dict) else {}
        payload = {
            "tool_call_id": tool_call_id,
            "tool_name": tool_call.tool_name,
            "status": _workspace_tool_status(tool_call.status),
            "output_summary": _tool_output_summary(tool_call, output_json),
            "output_json": output_json,
            "duration_ms": tool_call.duration_ms,
            "trace_id": _trace_id_for_tool_call(tool_call.id, session=self.session),
        }
        approval_id = output_json.get("approval_id")
        if isinstance(approval_id, str):
            payload["approval_id"] = approval_id
        return payload

    def append_tool_summary(
        self,
        summaries: list[dict],
        execution: ToolExecution,
        input_json: dict,
    ) -> None:
        tool_call = execution.tool_call
        output_json = tool_call.output_json if isinstance(tool_call.output_json, dict) else {}
        approval_id = execution.output.get("approval_id")
        summaries.append(
            {
                "tool_name": tool_call.tool_name,
                "status": tool_call.status,
                "input_json": input_json,
                "output_json": output_json,
                "output_summary": _tool_output_summary(tool_call, output_json),
                "error_message": tool_call.error_message,
                "approval_id": approval_id if isinstance(approval_id, str) else None,
            }
        )

    def workspace_tool_delta(self, summaries: list[dict]) -> str:
        if not summaries:
            return "没有可执行的工具请求。\n"
        sections: list[str] = []
        for summary in summaries:
            tool_name = str(summary["tool_name"])
            status_value = str(summary["status"])
            output_json = summary["output_json"] if isinstance(summary["output_json"], dict) else {}
            if status_value == "SUCCESS" and tool_name == "list_files":
                files = [str(item) for item in output_json.get("files", [])]
                preview = "\n".join(f"- `{item}`" for item in files[:50])
                more = f"\n- ...还有 {len(files) - 50} 项未显示" if len(files) > 50 else ""
                body = f"\n\n{preview}{more}" if preview else ""
                sections.append(f"已列出工作区文件，共 {len(files)} 项。{body}")
                continue
            if status_value == "SUCCESS" and tool_name == "read_file":
                content = str(output_json.get("content") or "")
                preview = content[:4000]
                truncated = "\n\n...内容已截断" if len(content) > len(preview) else ""
                sections.append(
                    f"已读取文件，共 {len(content)} 字符。\n\n"
                    f"```text\n{preview}\n```{truncated}"
                )
                continue
            if status_value == "SUCCESS":
                visible_result = _workspace_visible_tool_result_summary([summary])
                if visible_result:
                    sections.append(visible_result)
                    continue
            if status_value == "PENDING_APPROVAL":
                sections.append(
                    f"工具 `{tool_name}` 需要审批，已创建审批请求。请在运行详情的审批区域处理。"
                )
                continue
            if status_value == "DENIED":
                reason = str(summary.get("error_message") or "权限策略拒绝")
                sections.append(f"工具 `{tool_name}` 被权限策略拒绝：{reason}")
                continue
            if status_value in {"FAILED", "TIMEOUT"}:
                reason = str(summary.get("error_message") or summary.get("output_summary") or "")
                sections.append(f"工具 `{tool_name}` 执行失败：{reason}")
                continue
            sections.append(f"工具 `{tool_name}` 状态：{status_value}")
        return "\n\n".join(sections).strip() + "\n"

    def workspace_tool_mention_events(
        self,
        *,
        run_id: str,
        goal: str,
        summaries: list[dict],
        mentions: list[ToolMention] | None = None,
    ) -> Iterator[str]:
        capability_registry = CapabilityRegistry(self.session, self.principal.organization_id)
        registry, registry_snapshot = capability_registry.tool_registry_for_agent(self.agent_id)
        static_registry = ToolRegistry.default()
        run = self.session.get(Task, run_id)
        if run is not None:
            run.capability_snapshot_json = registry_snapshot
        runner = ToolRunner(
            session=self.session,
            registry=static_registry,
            agent_id=self.agent_id,
            capability_registry=capability_registry,
        )
        for index, raw_mention in enumerate(mentions or self.request.tool_mentions):
            mention = _resolve_workspace_tool_mention(raw_mention, registry=registry)
            metadata = registry.tools.get(mention.name)
            fallback_metadata = static_registry.tools.get(mention.name)
            input_json = _normalize_tool_mention_payload(mention.name, mention.payload, goal)
            if metadata is None:
                if fallback_metadata is None:
                    tool_call_id = f"workspace-tool-{run_id}-{index}"
                    yield self.sse(
                        "tool_call_requested",
                        {
                            "tool_call_id": tool_call_id,
                            "tool_name": mention.name,
                            "source": mention.source,
                            "input_json": input_json,
                            "status": "failed",
                            "risk": "unknown",
                            "sandbox": "none",
                        },
                    )
                    yield self.sse(
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
                    summaries.append(
                        {
                            "tool_name": mention.name,
                            "status": "FAILED",
                            "input_json": input_json,
                            "output_json": {},
                            "output_summary": "unknown tool",
                            "error_message": "unknown tool",
                            "approval_id": None,
                        }
                    )
                    continue
                execution = runner.execute(
                    task_id=run_id,
                    agent_run_id=None,
                    tool_name=mention.name,
                    input_json=input_json,
                    roles=self.principal.roles,
                )
                self.session.commit()
                yield self.sse(
                    "tool_call_requested",
                    self.requested_tool_payload(
                        mention,
                        fallback_metadata,
                        execution.tool_call.id,
                        _workspace_tool_status(execution.tool_call.status),
                        input_json,
                    ),
                )
                yield self.sse(
                    "tool_call_result",
                    self.result_payload(execution, execution.tool_call.id),
                )
                self.append_tool_summary(summaries, execution, input_json)
                continue
            executable = (
                metadata.risk_level == "low"
                and metadata.idempotent
                and not metadata.requires_sandbox
                and metadata.network_policy in {"none", "restricted"}
            )
            if not executable:
                execution = runner.request_approval(
                    task_id=run_id,
                    agent_run_id=None,
                    tool_name=mention.name,
                    input_json=input_json,
                )
                current_run = self.session.get(Task, run_id)
                if current_run is not None and execution.tool_call.status == "PENDING_APPROVAL":
                    current_run.status = "WAITING_APPROVAL"
                    current_run.updated_at = utc_now()
                self.session.commit()
                approval_id = execution.output.get("approval_id")
                yield self.sse(
                    "tool_call_requested",
                    self.requested_tool_payload(
                        mention,
                        metadata,
                        execution.tool_call.id,
                        _workspace_tool_status(execution.tool_call.status),
                        input_json,
                        approval_id if isinstance(approval_id, str) else None,
                    ),
                )
                if execution.tool_call.status != "PENDING_APPROVAL":
                    yield self.sse(
                        "tool_call_result",
                        self.result_payload(execution, execution.tool_call.id),
                    )
                self.append_tool_summary(summaries, execution, input_json)
                continue
            execution = runner.execute(
                task_id=run_id,
                agent_run_id=None,
                tool_name=mention.name,
                input_json=input_json,
                roles=self.principal.roles,
            )
            self.session.commit()
            yield self.sse(
                "tool_call_requested",
                self.requested_tool_payload(
                    mention,
                    metadata,
                    execution.tool_call.id,
                    "running",
                    input_json,
                ),
            )
            yield self.sse(
                "tool_call_result",
                self.result_payload(execution, execution.tool_call.id),
            )
            self.append_tool_summary(summaries, execution, input_json)

    def complete_after_tool_calls(
        self,
        *,
        run: Task,
        messages: list[ModelMessage],
        query_goal: str,
        assistant_content: str,
        tool_summaries: list[dict],
    ) -> str:
        stripped_content = _strip_function_calls(assistant_content).strip()
        tool_result_prompt = (
            "工具已经执行完成。请直接用中文回答用户，概括工具结果；"
            "不要输出任何工具调用标记、XML、JSON 调用块或内部工具调用格式。\n\n"
            f"用户问题：{query_goal}\n\n"
            f"助手原始说明（已去除工具调用标记）：\n{stripped_content or '无'}\n\n"
            f"工具结果：\n{_workspace_tool_result_prompt(tool_summaries)}"
        )
        response = AuditedModelGateway(
            session=self.session,
            task_id=run.id,
            agent_run_id=None,
        ).complete(
            ModelRequest(
                model_provider=run.model_provider,
                model_name=run.model_name,
                response_format="text",
                messages=[
                    *messages,
                    ModelMessage(role="assistant", content=stripped_content or "我需要调用工具。"),
                    ModelMessage(role="user", content=tool_result_prompt),
                ],
            )
        )
        return _strip_function_calls(response.content).strip()

    def workspace_tool_only_events(
        self,
        *,
        run: Task,
        goal: str,
        started_at: float,
        first_byte_at: float,
    ) -> Iterator[str]:
        run.status = "RUNNING"
        run.updated_at = utc_now()
        self.session.flush()
        yield self.sse(
            "run_created",
            {
                "run_id": run.id,
                "status": run.status,
                "step_count": 0,
                "message": "Chat tool run started.",
            },
        )
        summaries: list[dict] = []
        yield from self.workspace_tool_mention_events(run_id=run.id, goal=goal, summaries=summaries)
        content = self.workspace_tool_delta(summaries)
        current_run = self.session.get(Task, run.id)
        pending_approval = any(summary["status"] == "PENDING_APPROVAL" for summary in summaries)
        if current_run is not None:
            current_run.status = "WAITING_APPROVAL" if pending_approval else "COMPLETED"
            if not pending_approval:
                current_run.completed_at = utc_now()
            current_run.updated_at = utc_now()
        self.session.commit()
        yield self.sse("delta", {"content": content})
        yield self.sse(
            "usage",
            {
                "input_tokens": self.estimated_input_tokens(),
                "output_tokens": max(1, len(content) // 4),
                "cost_usd": None,
                "cost_unavailable": True,
                "ttfb_ms": int((first_byte_at - started_at) * 1000),
                "duration_ms": int((time.monotonic() - started_at) * 1000),
                "model_call_id": None,
            },
        )
        yield self.sse(
            "done",
            {
                "run_id": run.id,
                "active_branch_id": self.request.active_branch_id,
                "continue_from_node_id": self.request.continue_from_node_id,
                "status": _run_status(run.id, fallback=run.status, session=self.session),
                "step_count": 0,
                "message": "Chat tool run completed.",
                "knowledge_grounding": None,
            },
        )
