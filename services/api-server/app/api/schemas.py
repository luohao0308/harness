from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_KNOWLEDGE_MIME_TYPES = {"text/plain", "text/markdown"}
MAX_KNOWLEDGE_IMPORT_BYTES = 120_000


def _validate_knowledge_mime_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in ALLOWED_KNOWLEDGE_MIME_TYPES:
        allowed = ", ".join(sorted(ALLOWED_KNOWLEDGE_MIME_TYPES))
        raise ValueError(f"mime_type must be one of: {allowed}")
    return normalized


def _validate_knowledge_content_bytes(value: str) -> str:
    if len(value.encode("utf-8")) > MAX_KNOWLEDGE_IMPORT_BYTES:
        raise ValueError(
            f"content must be at most {MAX_KNOWLEDGE_IMPORT_BYTES} bytes after UTF-8 encoding"
        )
    return value


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, description="任务标题")
    goal: str = Field(min_length=1, description="任务目标")
    model_provider: str = Field(description="模型供应商")
    model_name: str = Field(description="模型名称")
    max_runtime_seconds: int = Field(default=1800, description="最大运行秒数")
    max_subagents: int = Field(default=5, description="最大子 Agent 数")
    enable_sandbox: bool = Field(default=True, description="是否启用容器沙箱")
    enable_network: bool = Field(default=False, description="是否启用网络访问")


class AgentPlanRequest(BaseModel):
    agent_id: str = Field(default="default", min_length=1, description="Agent ID")
    goal: str = Field(min_length=1, description="用户目标")
    title: str | None = Field(default=None, description="运行标题")
    model_provider: str = Field(
        default="default",
        description="模型供应商，default 表示使用模型设置",
    )
    model_name: str = Field(
        default="default",
        description="模型名称，default 表示使用模型设置",
    )
    max_runtime_seconds: int = Field(default=1800, ge=1, description="最大运行秒数")
    max_subagents: int = Field(default=5, ge=0, description="最大子 Agent 数")
    enable_sandbox: bool = Field(default=True, description="是否启用容器沙箱")
    enable_network: bool = Field(default=False, description="是否启用网络访问")


class AgentResponse(BaseModel):
    id: str = Field(description="Agent ID")
    name: str = Field(description="Agent 名称")
    description: str = Field(description="Agent 描述")
    role: str = Field(description="Agent 角色")
    status: str = Field(description="Agent 状态")
    model_provider: str = Field(description="默认模型供应商")
    model_name: str = Field(description="默认模型名称")
    system_prompt: str = Field(description="系统提示词")
    tools_json: list[str] = Field(description="可用工具")
    routing_tags: list[str] = Field(description="路由标签")
    max_parallel_assignments: int = Field(description="最大并行分配数")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")

    model_config = ConfigDict(from_attributes=True)


class AgentPage(BaseModel):
    items: list[AgentResponse] = Field(description="Agent 列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class AgentSessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, description="会话标题")


class AgentSessionResponse(BaseModel):
    id: str = Field(description="Session ID")
    organization_id: str | None = Field(default=None, description="组织 ID")
    agent_id: str = Field(description="Agent ID")
    created_by: str | None = Field(default=None, description="创建者")
    title: str = Field(description="会话标题")
    status: str = Field(description="会话状态")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")

    model_config = ConfigDict(from_attributes=True)


class AgentSessionPage(BaseModel):
    items: list[AgentSessionResponse] = Field(description="Agent Session 列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class AgentMessageResponse(BaseModel):
    id: str = Field(description="Message ID")
    session_id: str = Field(description="Session ID")
    agent_id: str = Field(description="Agent ID")
    role: str = Field(description="消息角色")
    content: str = Field(description="消息内容")
    metadata_json: dict = Field(description="消息元数据")
    created_at: datetime = Field(description="创建时间")

    model_config = ConfigDict(from_attributes=True)


class AgentMessagePage(BaseModel):
    items: list[AgentMessageResponse] = Field(description="消息列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class AgentChatRequest(BaseModel):
    content: str = Field(min_length=1, description="用户消息")


class AgentChatResponse(BaseModel):
    session: AgentSessionResponse = Field(description="会话")
    messages: list[AgentMessageResponse] = Field(description="本次写入的消息")


class TaskResponse(BaseModel):
    id: str = Field(description="任务 ID")
    title: str = Field(description="任务标题")
    goal: str = Field(description="任务目标")
    status: str = Field(description="任务状态")
    model_provider: str = Field(description="模型供应商")
    model_name: str = Field(description="模型名称")
    max_runtime_seconds: int = Field(description="最大运行秒数")
    max_subagents: int = Field(description="最大子 Agent 数")
    enable_sandbox: bool = Field(description="是否启用容器沙箱")
    enable_network: bool = Field(description="是否启用网络访问")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")
    completed_at: datetime | None = Field(default=None, description="完成时间")

    model_config = ConfigDict(from_attributes=True)


class TaskPage(BaseModel):
    items: list[TaskResponse] = Field(description="Agent Run 列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class AgentRunCreateRequest(AgentPlanRequest):
    mode: Literal["plan"] = Field(default="plan", description="Agent Workspace 固定使用 Plan 模式")


class ConversationNode(BaseModel):
    id: str = Field(description="对话节点 ID")
    parent_id: str | None = Field(default=None, description="父节点 ID")
    children_ids: list[str] = Field(default_factory=list, description="子节点 ID")
    role: Literal["user", "assistant", "system", "tool"] = Field(description="消息角色")
    content: str = Field(default="", description="消息内容")
    state: Literal["draft", "streaming", "paused", "done", "error"] = Field(
        default="done",
        description="节点状态",
    )
    run_id: str | None = Field(default=None, description="关联 Agent Run ID")
    metadata: dict = Field(default_factory=dict, description="消息元数据")
    tool_calls: list[dict] = Field(default_factory=list, description="工具调用摘要")
    artifacts: list[dict] = Field(default_factory=list, description="产物摘要")
    created_at: str | None = Field(default=None, description="前端对话节点创建时间")


class ToolMention(BaseModel):
    name: str = Field(description="工具名称")
    source: str | None = Field(default=None, description="工具来源")
    payload: dict = Field(default_factory=dict, description="结构化 mention 载荷")


class AttachmentPayload(BaseModel):
    name: str = Field(description="附件文件名")
    mime_type: str = Field(default="", description="附件 MIME 类型")
    size_bytes: int = Field(default=0, ge=0, description="附件大小")
    content_text: str | None = Field(default=None, description="可读文本内容")
    content_status: Literal["ready", "unsupported", "error"] = Field(
        default="unsupported",
        description="前端读取内容状态",
    )
    truncated: bool = Field(default=False, description="内容是否被前端截断")


class CompressedContext(BaseModel):
    summary: str = Field(default="", description="压缩后的上下文摘要")
    coverage_node_ids: list[str] = Field(default_factory=list, description="摘要覆盖的节点 ID")
    coverage_path_hash: str = Field(default="", description="覆盖路径哈希")
    summary_schema_version: str = Field(default="", description="摘要结构版本")
    compression_prompt_version: str = Field(default="", description="压缩提示词版本")
    compressor_provider: str = Field(default="", description="压缩模型供应商")
    compressor_model: str = Field(default="", description="压缩模型名称")


class AgentChatStreamRequest(BaseModel):
    """Accept unknown extra fields (v4 additive `context_max_tokens`, etc.)."""

    model_config = ConfigDict(extra="ignore")

    mode: Literal["chat", "markdown_plan", "plan"] = Field(
        default="chat",
        description="Workspace 输入模式",
    )
    goal: str | None = Field(default=None, description="用户目标")
    model_provider: str | None = Field(default=None, description="本次请求选择的模型供应商")
    model_name: str | None = Field(default=None, description="本次请求选择的模型名称")
    messages: list[ConversationNode] = Field(default_factory=list, description="当前分支消息")
    active_leaf_id: str | None = Field(default=None, description="当前活动叶子节点")
    run_id: str | None = Field(default=None, description="继续生成时绑定的原始 Agent Run ID")
    active_branch_id: str | None = Field(default=None, description="前端当前分支 ID")
    pinned_node_ids: list[str] = Field(default_factory=list, description="强制注入上下文节点")
    context_window_turns: int = Field(default=8, ge=1, le=50, description="最近上下文轮数")
    continue_from_node_id: str | None = Field(default=None, description="继续生成的节点 ID")
    partial_assistant_content: str | None = Field(default=None, description="已生成的片段")
    tool_mentions: list[ToolMention] = Field(default_factory=list, description="结构化工具 mention")
    attachment_names: list[str] = Field(default_factory=list, description="前端选择的附件文件名")
    attachments: list[AttachmentPayload] = Field(
        default_factory=list,
        description="前端读取后的附件内容摘要",
    )
    # v4 additive: UI-side token budget hint. Optional; backend is free to
    # ignore. See agent-workspace-chat-v4-refine/design.md §Req 5.5.
    context_max_tokens: int | None = Field(
        default=None,
        ge=1,
        description="UI-side context window budget; currently ignored by the backend",
    )
    compressed_context: CompressedContext | None = Field(
        default=None,
        description="语义压缩后的上下文摘要，服务端按固定顺序注入 prompt",
    )


class WorkspaceContextCompressionRequest(BaseModel):
    model_provider: str | None = Field(default=None, description="本次压缩选择的模型供应商")
    model_name: str | None = Field(default=None, description="本次压缩选择的模型名称")
    messages: list[ConversationNode] = Field(
        default_factory=list,
        description="完整 active path 原始消息",
    )
    pinned_node_ids: list[str] = Field(
        default_factory=list,
        description="固定节点，压缩时排除并 raw 注入",
    )
    existing_summary: str | None = Field(
        default=None,
        description="客户端已有摘要，仅作为不可信 cache hint",
    )
    prior_coverage_node_ids: list[str] = Field(
        default_factory=list,
        description="客户端已有摘要覆盖节点",
    )
    prior_coverage_path_hash: str | None = Field(
        default=None,
        description="客户端已有摘要覆盖路径哈希",
    )
    summary_schema_version: str = Field(
        default="workspace-context-summary-v1",
        description="摘要结构版本",
    )
    compression_prompt_version: str = Field(
        default="workspace-context-compression-v1",
        description="压缩提示词版本",
    )
    compressor_provider: str | None = Field(default=None, description="已有摘要使用的模型供应商")
    compressor_model: str | None = Field(default=None, description="已有摘要使用的模型名称")


class WorkspaceContextCompressionResponse(BaseModel):
    status: Literal[
        "ok",
        "stale",
        "missing_raw_nodes",
        "hash_mismatch",
        "provider_error",
    ] = Field(description="压缩状态")
    cache_status: Literal[
        "accepted",
        "recomputed",
        "stale_rejected",
        "error",
    ] = Field(description="已有摘要 cache 处理状态")
    summary: str = Field(default="", description="压缩摘要")
    coverage_node_ids: list[str] = Field(default_factory=list, description="摘要覆盖节点 ID")
    coverage_path_hash: str = Field(default="", description="覆盖路径哈希")
    last_covered_node_id: str | None = Field(default=None, description="最后覆盖节点 ID")
    summary_schema_version: str = Field(description="摘要结构版本")
    compression_prompt_version: str = Field(description="压缩提示词版本")
    compressor_provider: str = Field(description="实际压缩模型供应商")
    compressor_model: str = Field(description="实际压缩模型名称")
    estimated_original_tokens: int = Field(default=0, description="原始覆盖内容估算 token")
    estimated_summary_tokens: int = Field(default=0, description="摘要估算 token")
    estimated_uncovered_tokens: int = Field(default=0, description="未覆盖内容估算 token")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")
    error: str | None = Field(default=None, description="错误信息")


class TaskArtifact(BaseModel):
    name: str = Field(description="产物名称")
    artifact_type: str = Field(description="产物类型")
    description: str = Field(description="产物说明")
    status: str = Field(description="产物状态")


class TaskSubagentResult(BaseModel):
    class ToolResult(BaseModel):
        tool_call_id: str = Field(description="工具调用 ID")
        tool_name: str = Field(description="工具名称")
        status: str = Field(description="工具状态")
        allowed: bool = Field(description="是否允许执行")
        duration_ms: int = Field(description="耗时毫秒")
        input_json: dict = Field(default_factory=dict, description="工具输入")
        output: dict = Field(description="工具输出")
        error_message: str | None = Field(default=None, description="错误信息")

    class SubagentArtifact(BaseModel):
        name: str = Field(description="产物名称")
        artifact_type: str = Field(description="产物类型")
        source_tool: str = Field(description="来源工具")
        description: str = Field(description="产物说明")
        status: str = Field(description="产物状态")
        preview: str | None = Field(default=None, description="产物预览")

    id: str = Field(description="子 Agent ID")
    step_key: str | None = Field(default=None, description="来源步骤键")
    status: str = Field(description="子 Agent 状态")
    summary: str | None = Field(default=None, description="子 Agent 结果摘要")
    tool_results: list[ToolResult] = Field(default_factory=list, description="工具执行结果")
    artifacts: list[SubagentArtifact] = Field(default_factory=list, description="子 Agent 产物")
    react_trace: list[dict] = Field(default_factory=list, description="ReAct 执行轮次轨迹")
    context_summary: dict = Field(default_factory=dict, description="长上下文压缩摘要")
    completed_at: datetime | None = Field(default=None, description="完成时间")


class TaskResultResponse(BaseModel):
    task_id: str = Field(description="任务 ID")
    status: str = Field(description="任务状态")
    summary: str | None = Field(default=None, description="结果摘要")
    execution_plan: dict | None = Field(default=None, description="执行计划")
    artifacts: list[TaskArtifact] = Field(description="产物列表")
    subagent_results: list[TaskSubagentResult] = Field(description="子 Agent 结果聚合")
    last_sequence: int = Field(description="最后事件序号")
    pending: bool = Field(description="是否仍在运行")


class TaskStepResponse(BaseModel):
    id: str = Field(description="步骤 ID")
    task_id: str = Field(description="任务 ID")
    plan_id: str = Field(description="计划 ID")
    step_key: str = Field(description="步骤键")
    description: str = Field(description="步骤说明")
    status: str = Field(description="步骤状态")
    execution_mode: str = Field(description="执行模式")
    assigned_agent_id: str | None = Field(default=None, description="分配的 Agent ID")
    started_at: datetime | None = Field(default=None, description="开始时间")
    completed_at: datetime | None = Field(default=None, description="完成时间")
    error_message: str | None = Field(default=None, description="错误信息")

    model_config = ConfigDict(from_attributes=True)


class TaskStepPage(BaseModel):
    items: list[TaskStepResponse] = Field(description="步骤列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class StepResumeRequest(BaseModel):
    step_keys: list[str] = Field(min_length=1, description="断点步骤键列表")
    resume_mode: Literal["from_first_selected"] = Field(
        default="from_first_selected",
        description="恢复模式：from_first_selected 表示从最靠前的断点步骤续跑",
    )


class StepResumeResponse(BaseModel):
    task_id: str = Field(description="任务 ID")
    status: str = Field(description="恢复后的任务状态")
    plan_id: str = Field(description="计划 ID")
    resume_mode: str = Field(description="恢复模式")
    resume_from_step_key: str = Field(description="实际断点步骤键")
    requested_step_keys: list[str] = Field(description="请求恢复的步骤键")
    skipped_step_keys: list[str] = Field(description="恢复中跳过的已完成步骤键")
    resumed_step_keys: list[str] = Field(description="本次实际执行的步骤键")
    completed_step_keys: list[str] = Field(description="重放后已完成的步骤键")
    pending_step_keys: list[str] = Field(description="重放后仍未完成的步骤键")
    failed_step_key: str | None = Field(default=None, description="本次失败步骤键")
    error_message: str | None = Field(default=None, description="错误信息")
    last_sequence: int = Field(description="最后事件序号")


class TaskPlanStepState(BaseModel):
    step_key: str = Field(description="步骤键")
    description: str = Field(description="步骤说明")
    depends_on: list[str] = Field(default_factory=list, description="依赖步骤键")
    execution_mode: str = Field(description="执行模式")
    requires_sandbox: bool = Field(description="是否需要沙箱")
    can_spawn_subagent: bool = Field(description="是否可派生子 Agent")
    tool_hints: list[str] = Field(default_factory=list, description="计划工具意图")
    acceptance_criteria: list[str] = Field(default_factory=list, description="验收标准")
    risk_level: str = Field(default="low", description="风险等级")
    artifact_expectations: list[str] = Field(default_factory=list, description="预期产物")
    quality_notes: list[str] = Field(default_factory=list, description="步骤质量提示")
    status: str = Field(description="当前步骤状态")
    assigned_agent_id: str | None = Field(default=None, description="分配的 Agent ID")
    error_message: str | None = Field(default=None, description="错误信息")
    trace_summary: str | None = Field(default=None, description="步骤执行轨迹摘要")
    last_event_sequence: int | None = Field(default=None, description="步骤最近事件序号")
    execution_trace: list[dict] = Field(default_factory=list, description="步骤执行事件轨迹")


class TaskPlanResponse(BaseModel):
    id: str = Field(description="计划 ID")
    task_id: str = Field(description="任务 ID")
    version: int = Field(description="计划版本")
    status: str = Field(description="计划状态")
    summary: str | None = Field(default=None, description="计划摘要")
    planner_source: str = Field(description="计划来源")
    planner_attempts: int = Field(description="计划生成尝试次数")
    planner_prompt_version: str = Field(description="Planner Prompt 版本")
    quality_score: int = Field(description="计划质量分")
    validation_warnings: list[str] = Field(default_factory=list, description="计划质量告警")
    quality_gates: dict[str, bool] = Field(default_factory=dict, description="计划质量门禁")
    plan_json: dict = Field(description="计划原始 JSON")
    steps: list[TaskPlanStepState] = Field(description="计划步骤状态")
    created_at: datetime = Field(description="创建时间")


class AgentPlanResponse(BaseModel):
    agent_id: str = Field(description="Agent ID")
    run_id: str = Field(description="Agent Run ID，兼容 task_id")
    task: TaskResponse = Field(description="Run 基础信息")
    plan: TaskPlanResponse = Field(description="结构化计划")
    message: str = Field(description="Agent 给用户的计划摘要")


class AgentAssignmentResponse(BaseModel):
    id: str = Field(description="Assignment ID")
    run_id: str = Field(description="Agent Run ID")
    agent_id: str = Field(description="Agent ID")
    parent_assignment_id: str | None = Field(default=None, description="父 Assignment ID")
    step_key: str | None = Field(default=None, description="计划步骤键")
    role: str = Field(description="Agent 角色")
    status: str = Field(description="Assignment 状态")
    input_json: dict = Field(description="Assignment 输入")
    output_json: dict = Field(description="Assignment 输出")
    created_at: datetime = Field(description="创建时间")
    started_at: datetime | None = Field(default=None, description="开始时间")
    completed_at: datetime | None = Field(default=None, description="完成时间")

    model_config = ConfigDict(from_attributes=True)


class AgentHandoffResponse(BaseModel):
    id: str = Field(description="Handoff ID")
    run_id: str = Field(description="Agent Run ID")
    from_assignment_id: str | None = Field(default=None, description="来源 Assignment ID")
    to_assignment_id: str = Field(description="目标 Assignment ID")
    handoff_type: str = Field(description="交接类型")
    status: str = Field(description="交接状态")
    payload_json: dict = Field(description="交接载荷")
    created_at: datetime = Field(description="创建时间")
    completed_at: datetime | None = Field(default=None, description="完成时间")

    model_config = ConfigDict(from_attributes=True)


class AgentOrchestrateResponse(BaseModel):
    run_id: str = Field(description="Agent Run ID")
    strategy: str = Field(description="编排策略")
    routing_reasoning: str | None = Field(default=None, description="路由决策依据")
    assignments: list[AgentAssignmentResponse] = Field(description="Agent 分配列表")
    handoffs: list[AgentHandoffResponse] = Field(description="Agent 交接列表")
    message: str = Field(description="编排摘要")


class AgentAutoResponse(BaseModel):
    agent_id: str = Field(description="Agent ID")
    run_id: str = Field(description="Agent Run ID")
    task: TaskResponse = Field(description="Run 基础信息")
    plan: TaskPlanResponse = Field(description="结构化计划")
    orchestration: AgentOrchestrateResponse = Field(description="多 Agent 编排结果")
    message: str = Field(description="内部自动流程摘要")


class TaskPlanVersionSummary(BaseModel):
    id: str = Field(description="计划 ID")
    task_id: str = Field(description="任务 ID")
    version: int = Field(description="计划版本")
    status: str = Field(description="计划状态")
    summary: str | None = Field(default=None, description="计划摘要")
    planner_source: str = Field(description="计划来源")
    planner_attempts: int = Field(description="计划生成尝试次数")
    step_count: int = Field(description="步骤数量")
    created_at: datetime = Field(description="创建时间")


class TaskPlanVersionPage(BaseModel):
    items: list[TaskPlanVersionSummary] = Field(description="计划版本列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class TaskPlanStepDiff(BaseModel):
    step_key: str = Field(description="步骤键")
    change_type: str = Field(description="变更类型")
    from_step: dict | None = Field(default=None, description="来源版本步骤")
    to_step: dict | None = Field(default=None, description="目标版本步骤")


class TaskPlanDiffResponse(BaseModel):
    task_id: str = Field(description="任务 ID")
    from_version: int = Field(description="来源计划版本")
    to_version: int = Field(description="目标计划版本")
    added: int = Field(description="新增步骤数")
    removed: int = Field(description="移除步骤数")
    changed: int = Field(description="变更步骤数")
    unchanged: int = Field(description="未变更步骤数")
    step_diffs: list[TaskPlanStepDiff] = Field(description="步骤差异列表")


class ReplayRequest(BaseModel):
    sequence: int | None = Field(default=None, ge=1, description="重放到指定事件序号")


class ReplayResponse(BaseModel):
    task_id: str = Field(description="任务 ID")
    sequence: int = Field(description="重放序号")
    state_summary: str = Field(description="状态摘要")
    failure_point: dict | None = Field(default=None, description="故障点")
    diagnosis: str = Field(description="诊断结论")
    requires_manual_review: bool = Field(description="是否需要人工复核")


class RunContextResponse(BaseModel):
    task_id: str = Field(description="任务 ID")
    generated_at: datetime = Field(description="上下文生成时间")
    working_memory: dict = Field(description="单次 Run 工作记忆")
    long_term_memory: dict = Field(description="跨 Run 长期记忆摘要")
    artifact_memory: dict = Field(description="产物记忆摘要")
    rag_context: dict = Field(description="检索上下文摘要")
    trace_memory: dict = Field(description="事件 Trace 记忆")
    context_compression: dict = Field(description="上下文压缩结果")
    model_routing: dict = Field(description="模型路由决策")
    latest_agent_router: dict | None = Field(default=None, description="最近一次 Agent 路由事件")


class EventResponse(BaseModel):
    id: str = Field(description="事件 ID")
    task_id: str = Field(description="任务 ID")
    agent_run_id: str | None = Field(default=None, description="Agent 运行 ID")
    sequence: int = Field(description="事件序号")
    event_type: str = Field(description="事件类型")
    payload_json: dict = Field(description="事件载荷")
    actor_type: str = Field(description="来源类型")
    actor_id: str | None = Field(default=None, description="来源 ID")
    trace_id: str | None = Field(default=None, description="追踪 ID")
    created_at: datetime = Field(description="创建时间")

    model_config = ConfigDict(from_attributes=True)


class KnowledgeSourceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120, description="知识源名称")
    description: str = Field(default="", max_length=1_000, description="知识源说明")
    scope: Literal["agent", "org"] = Field(default="agent", description="知识源作用域")
    source_type: Literal["text", "markdown", "document"] = Field(
        default="text",
        description="知识源类型",
    )
    title: str = Field(min_length=1, max_length=200, description="文档标题")
    content: str = Field(min_length=1, max_length=120_000, description="文档内容")
    uri: str | None = Field(default=None, max_length=2_000, description="来源 URI")
    mime_type: str = Field(
        default="text/markdown",
        min_length=1,
        max_length=120,
        description="文档 MIME type",
    )
    idempotency_key: str | None = Field(default=None, max_length=200, description="幂等键")
    expires_at: datetime | None = Field(default=None, description="过期时间")

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, value: str) -> str:
        return _validate_knowledge_mime_type(value)

    @field_validator("content")
    @classmethod
    def validate_content_bytes(cls, value: str) -> str:
        return _validate_knowledge_content_bytes(value)


class KnowledgeSourceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120, description="知识源名称")
    description: str | None = Field(default=None, max_length=1_000, description="知识源说明")
    expires_at: datetime | None = Field(default=None, description="过期时间")


class KnowledgeSourceActionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500, description="操作原因")


class KnowledgeSourceScopeRequest(BaseModel):
    scope: Literal["agent", "org"] = Field(description="目标作用域")
    reason: str | None = Field(default=None, max_length=500, description="操作原因")


class KnowledgeDocumentCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200, description="文档标题")
    content: str = Field(min_length=1, max_length=120_000, description="文档内容")
    uri: str | None = Field(default=None, max_length=2_000, description="来源 URI")
    mime_type: str = Field(
        default="text/markdown",
        min_length=1,
        max_length=120,
        description="文档 MIME type",
    )
    idempotency_key: str | None = Field(default=None, max_length=200, description="幂等键")

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, value: str) -> str:
        return _validate_knowledge_mime_type(value)

    @field_validator("content")
    @classmethod
    def validate_content_bytes(cls, value: str) -> str:
        return _validate_knowledge_content_bytes(value)


class KnowledgeChunkResponse(BaseModel):
    id: str = Field(description="Chunk ID")
    document_id: str = Field(description="文档 ID")
    source_id: str = Field(description="知识源 ID")
    source_version: int = Field(description="知识源版本")
    document_version: int = Field(description="文档版本")
    chunk_version: int = Field(description="Chunk 版本")
    chunk_index: int = Field(description="Chunk 索引")
    text: str = Field(description="Chunk 文本")
    text_sha256: str = Field(description="Chunk 哈希")
    start_offset: int = Field(description="起始偏移")
    end_offset: int = Field(description="结束偏移")
    status: str = Field(description="状态")
    created_at: datetime = Field(description="创建时间")

    model_config = ConfigDict(from_attributes=True)


class KnowledgeDocumentResponse(BaseModel):
    id: str = Field(description="文档 ID")
    source_id: str = Field(description="知识源 ID")
    organization_id: str | None = Field(default=None, description="组织 ID")
    agent_id: str | None = Field(default=None, description="Agent ID")
    title: str = Field(description="标题")
    uri: str | None = Field(default=None, description="来源 URI")
    content_sha256: str = Field(description="内容哈希")
    mime_type: str = Field(description="MIME type")
    status: str = Field(description="状态")
    version: int = Field(description="版本")
    logical_document_id: str | None = Field(default=None, description="逻辑文档 ID")
    supersedes_document_id: str | None = Field(default=None, description="前一版本 ID")
    superseded_at: datetime | None = Field(default=None, description="被替换时间")
    ingestion_error: str | None = Field(default=None, description="导入错误")
    metadata_json: dict = Field(default_factory=dict, description="元数据")
    idempotency_key: str | None = Field(default=None, description="幂等键")
    created_by: str | None = Field(default=None, description="创建者")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")
    indexed_at: datetime | None = Field(default=None, description="索引时间")
    chunk_count: int = Field(default=0, description="Chunk 数量")

    model_config = ConfigDict(from_attributes=True)


class KnowledgeSourceResponse(BaseModel):
    id: str = Field(description="知识源 ID")
    organization_id: str | None = Field(default=None, description="组织 ID")
    agent_id: str | None = Field(default=None, description="Agent ID")
    name: str = Field(description="知识源名称")
    description: str = Field(description="知识源说明")
    source_type: str = Field(description="知识源类型")
    status: str = Field(description="状态")
    version: int = Field(description="版本")
    scope: Literal["agent", "org"] = Field(description="知识源作用域")
    expires_at: datetime | None = Field(default=None, description="过期时间")
    disabled_at: datetime | None = Field(default=None, description="停用时间")
    archived_at: datetime | None = Field(default=None, description="归档时间")
    last_indexed_at: datetime | None = Field(default=None, description="最后索引时间")
    last_ingestion_error: str | None = Field(default=None, description="最后导入错误")
    health_status: str = Field(description="健康状态")
    settings_json: dict = Field(default_factory=dict, description="设置")
    metadata_json: dict = Field(default_factory=dict, description="元数据")
    idempotency_key: str | None = Field(default=None, description="幂等键")
    created_by: str | None = Field(default=None, description="创建者")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")
    latest_documents: list[KnowledgeDocumentResponse] = Field(
        default_factory=list,
        description="最新文档",
    )

    model_config = ConfigDict(from_attributes=True)


class KnowledgeSourcePage(BaseModel):
    items: list[KnowledgeSourceResponse] = Field(description="知识源列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class KnowledgeRetrievalHitResponse(BaseModel):
    id: str = Field(description="Hit ID")
    chunk_id: str | None = Field(default=None, description="Chunk ID")
    web_source_id: str | None = Field(default=None, description="Web source ID")
    rank: int = Field(description="排名")
    score: float = Field(description="分数")
    source_kind: str = Field(description="来源类型")
    document_id: str | None = Field(default=None, description="文档 ID")
    document_version: int | None = Field(default=None, description="文档版本")
    snippet: str = Field(description="片段")
    metadata_json: dict = Field(default_factory=dict, description="元数据")
    created_at: datetime = Field(description="创建时间")

    model_config = ConfigDict(from_attributes=True)


class KnowledgeCitationResponse(BaseModel):
    id: str = Field(description="Citation ID")
    retrieval_hit_id: str = Field(description="Retrieval hit ID")
    citation_key: str = Field(description="引用键")
    source_kind: str = Field(description="来源类型")
    chunk_id: str | None = Field(default=None, description="Chunk ID")
    web_source_id: str | None = Field(default=None, description="Web source ID")
    claim_text: str | None = Field(default=None, description="主张文本")
    quoted_text: str | None = Field(default=None, description="引用文本")
    confidence: float = Field(description="置信度")
    metadata_json: dict = Field(default_factory=dict, description="元数据")
    created_at: datetime = Field(description="创建时间")

    model_config = ConfigDict(from_attributes=True)


class WebResearchSourceResponse(BaseModel):
    id: str = Field(description="Web source ID")
    url: str = Field(description="URL")
    title: str = Field(description="标题")
    content_sha256: str = Field(description="内容哈希")
    snippet: str = Field(description="摘要")
    status: str = Field(description="状态")
    error_message: str | None = Field(default=None, description="错误信息")
    metadata_json: dict = Field(default_factory=dict, description="元数据")
    fetched_at: datetime = Field(description="抓取时间")

    model_config = ConfigDict(from_attributes=True)


class PromptAssemblyManifestResponse(BaseModel):
    id: str = Field(description="Prompt manifest ID")
    retrieval_session_id: str = Field(description="Retrieval session ID")
    run_id: str | None = Field(default=None, description="Run ID")
    grounding_correlation_id: str = Field(description="Grounding correlation ID")
    query: str = Field(description="查询")
    included_retrieval_hit_ids_json: list = Field(description="进入 prompt/context 的命中")
    omitted_candidates_json: list = Field(description="未进入 prompt/context 的候选")
    source_snapshots_json: list = Field(description="来源快照")
    token_budget_json: dict = Field(description="Token/context budget")
    prompt_sections_json: list = Field(description="Prompt section manifest")
    evidence_text_sha256: str = Field(description="证据文本哈希")
    metadata_json: dict = Field(default_factory=dict, description="元数据")
    created_at: datetime = Field(description="创建时间")

    model_config = ConfigDict(from_attributes=True)


class KnowledgePolicyAuditResponse(BaseModel):
    id: str = Field(description="Policy audit ID")
    retrieval_session_id: str = Field(description="Retrieval session ID")
    run_id: str | None = Field(default=None, description="Run ID")
    decision: str = Field(description="策略决策")
    reason: str = Field(description="原因")
    source_kind: str | None = Field(default=None, description="来源类型")
    source_ref_id: str | None = Field(default=None, description="安全来源引用")
    safe_metadata_json: dict = Field(default_factory=dict, description="安全元数据")
    created_at: datetime = Field(description="创建时间")

    model_config = ConfigDict(from_attributes=True)


class RetrievalSessionResponse(BaseModel):
    id: str = Field(description="Retrieval session ID")
    query: str = Field(description="查询")
    mode: str = Field(description="模式")
    local_status: str = Field(description="本地状态")
    vector_capability: str = Field(description="向量能力")
    strategy: str = Field(description="检索策略")
    min_hits: int = Field(description="最少命中数")
    min_score: float = Field(description="最小分数")
    max_local_chunks: int = Field(description="最多本地 chunk")
    max_web_results: int = Field(description="最多 web 结果")
    metadata_json: dict = Field(default_factory=dict, description="元数据")
    created_at: datetime = Field(description="创建时间")

    model_config = ConfigDict(from_attributes=True)


class KnowledgeGroundingResponse(BaseModel):
    retrieval_session: RetrievalSessionResponse | None = Field(
        default=None,
        description="检索会话",
    )
    retrieval_hits: list[KnowledgeRetrievalHitResponse] = Field(
        default_factory=list,
        description="命中",
    )
    citations: list[KnowledgeCitationResponse] = Field(
        default_factory=list,
        description="引用",
    )
    prompt_manifest: PromptAssemblyManifestResponse | None = Field(
        default=None,
        description="Prompt assembly manifest",
    )
    policy_audits: list[KnowledgePolicyAuditResponse] = Field(
        default_factory=list,
        description="Policy/omission audit",
    )
    web_sources: list[WebResearchSourceResponse] = Field(
        default_factory=list,
        description="Web 来源",
    )
    vector_capability: str = Field(description="向量能力")
    local_status: str = Field(description="本地证据状态")
    grounded: bool = Field(description="是否已 grounding")
    grounding_provider: str = Field(default="none", description="Grounding provider")
    fixture_grounded: bool = Field(default=False, description="是否为 fixture evidence")
    verified_grounded: bool = Field(default=False, description="是否 verified grounding")
    grounding_verification_reason: str = Field(
        default="no_verified_evidence",
        description="Grounding verification reason code",
    )
    evidence_summary: str = Field(description="证据摘要")
    inferred_fallback: bool = Field(default=False, description="是否使用 latest fallback")
    fallback_reason: str | None = Field(default=None, description="fallback 原因")
    selected_retrieval_session_id: str | None = Field(
        default=None,
        description="选中的检索会话 ID",
    )
    selected_prompt_manifest_id: str | None = Field(
        default=None,
        description="选中的 prompt manifest ID",
    )


class EventPage(BaseModel):
    items: list[EventResponse] = Field(description="事件列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class SubagentResponse(BaseModel):
    id: str = Field(description="子 Agent ID")
    task_id: str = Field(description="任务 ID")
    parent_agent_id: str | None = Field(default=None, description="父 Agent ID")
    agent_type: str = Field(description="Agent 类型")
    status: str = Field(description="子 Agent 状态")
    context_json: dict = Field(description="上下文")
    started_at: datetime | None = Field(default=None, description="开始时间")
    completed_at: datetime | None = Field(default=None, description="完成时间")
    timeout_at: datetime | None = Field(default=None, description="超时时间")

    model_config = ConfigDict(from_attributes=True)


class SubagentPage(BaseModel):
    items: list[SubagentResponse] = Field(description="子 Agent 列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class SubagentListItemResponse(SubagentResponse):
    task_title: str = Field(description="任务标题")
    task_status: str = Field(description="任务状态")
    step_key: str | None = Field(default=None, description="来源步骤键")


class SubagentListPage(BaseModel):
    items: list[SubagentListItemResponse] = Field(description="组织子 Agent 列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class SubagentCreateRequest(BaseModel):
    assignment: dict = Field(description="子 Agent 任务上下文")
    parent_agent_id: str | None = Field(default=None, description="父 Agent ID")
    timeout_seconds: int = Field(default=900, ge=1, description="超时秒数")
    enqueue: bool = Field(default=False, description="是否进入 Dramatiq 队列")


class SubagentRecoverRequest(BaseModel):
    stale_after_seconds: int = Field(default=900, ge=1, description="运行卡住判定秒数")
    enqueue: bool = Field(default=False, description="是否重新进入 Dramatiq 队列")


class SubagentRecoveryItem(BaseModel):
    id: str = Field(description="子 Agent ID")
    previous_status: str = Field(description="恢复前状态")
    status: str = Field(description="恢复后状态")
    action: str = Field(description="恢复动作")
    reason: str = Field(description="恢复原因")
    replay_status: str | None = Field(default=None, description="Replay 中的子 Agent 状态")
    takeover_generation: int | None = Field(default=None, description="Worker 接管代次")
    takeover_owner: str | None = Field(default=None, description="Worker 接管执行者")
    takeover_at: datetime | None = Field(default=None, description="Worker 接管时间")


class SubagentRecoveryResponse(BaseModel):
    batch_id: str = Field(description="恢复批次 ID")
    task_id: str | None = Field(default=None, description="任务 ID")
    trigger: str = Field(description="触发来源")
    replay_sequence: int = Field(description="Replay 序号")
    stale_after_seconds: int = Field(description="卡住判定秒数")
    enqueue: bool = Field(description="是否重新入队")
    scanned_count: int = Field(description="扫描子 Agent 数")
    recovered_count: int = Field(description="恢复子 Agent 数")
    action_counts: dict[str, int] = Field(description="恢复动作统计")
    recovered: list[SubagentRecoveryItem] = Field(description="恢复结果列表")
    completed_at: datetime = Field(description="恢复批次完成时间")


class SubagentRecoveryBatchResponse(SubagentRecoveryResponse):
    organization_id: str | None = Field(default=None, description="组织 ID")
    lock_acquired: bool = Field(default=True, description="是否获取恢复锁")
    task_count: int = Field(default=1, description="扫描任务数")
    recovered_by_task: list[dict] = Field(default_factory=list, description="按任务聚合的恢复结果")

    model_config = ConfigDict(from_attributes=True)


class SubagentRecoveryBatchPage(BaseModel):
    items: list[SubagentRecoveryBatchResponse] = Field(description="恢复批次列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class SubagentRecoveryTaskSummary(BaseModel):
    task_id: str = Field(description="任务 ID")
    scanned_count: int = Field(description="累计扫描数")
    recovered_count: int = Field(description="累计恢复数")
    latest_batch_id: str = Field(description="最近批次 ID")
    latest_completed_at: datetime = Field(description="最近完成时间")
    latest_replay_sequence: int = Field(description="最近 Replay 序号")


class SubagentRecoverySummaryResponse(BaseModel):
    organization_id: str | None = Field(default=None, description="组织 ID")
    batch_total: int = Field(description="恢复批次数")
    task_total: int = Field(description="涉及任务数")
    scanned_total: int = Field(description="累计扫描子 Agent 数")
    recovered_total: int = Field(description="累计恢复子 Agent 数")
    lock_skipped_total: int = Field(description="未获取恢复锁次数")
    action_counts: dict[str, int] = Field(description="恢复动作统计")
    latest_completed_at: datetime | None = Field(default=None, description="最近完成时间")
    tasks: list[SubagentRecoveryTaskSummary] = Field(description="按任务聚合")
    recent_batches: list[SubagentRecoveryBatchResponse] = Field(description="最近恢复批次")


class SubagentRecoveryOrganizationSummary(BaseModel):
    organization_id: str | None = Field(default=None, description="组织 ID")
    batch_total: int = Field(description="恢复批次数")
    task_total: int = Field(description="涉及任务数")
    scanned_total: int = Field(description="累计扫描子 Agent 数")
    recovered_total: int = Field(description="累计恢复子 Agent 数")
    lock_skipped_total: int = Field(description="未获取恢复锁次数")
    action_counts: dict[str, int] = Field(description="恢复动作统计")
    latest_completed_at: datetime | None = Field(default=None, description="最近完成时间")


class SubagentRecoveryGlobalSummaryResponse(BaseModel):
    organization_count: int = Field(description="组织数量")
    batch_total: int = Field(description="恢复批次数")
    task_total: int = Field(description="涉及任务数")
    scanned_total: int = Field(description="累计扫描子 Agent 数")
    recovered_total: int = Field(description="累计恢复子 Agent 数")
    lock_skipped_total: int = Field(description="未获取恢复锁次数")
    action_counts: dict[str, int] = Field(description="恢复动作统计")
    latest_completed_at: datetime | None = Field(default=None, description="最近完成时间")
    organizations: list[SubagentRecoveryOrganizationSummary] = Field(description="按组织聚合")
    recent_batches: list[SubagentRecoveryBatchResponse] = Field(description="最近恢复批次")


class SubagentBulkActionRequest(BaseModel):
    action: Literal["cancel"] = Field(description="批量动作")
    subagent_ids: list[str] = Field(min_length=1, max_length=100, description="子 Agent ID 列表")


class SubagentBulkActionItem(BaseModel):
    id: str = Field(description="子 Agent ID")
    previous_status: str | None = Field(default=None, description="操作前状态")
    status: str | None = Field(default=None, description="操作后状态")
    action: str = Field(description="实际动作")
    success: bool = Field(description="是否成功")
    error_message: str | None = Field(default=None, description="错误信息")


class SubagentBulkActionResponse(BaseModel):
    action: str = Field(description="批量动作")
    requested_count: int = Field(description="请求数量")
    succeeded_count: int = Field(description="成功数量")
    failed_count: int = Field(description="失败数量")
    items: list[SubagentBulkActionItem] = Field(description="批量结果明细")


class SandboxResponse(BaseModel):
    id: str = Field(description="沙箱 ID")
    task_id: str = Field(description="任务 ID")
    container_id: str = Field(description="容器 ID")
    image: str = Field(description="镜像")
    status: str = Field(description="沙箱状态")
    cpu_limit: str = Field(description="CPU 限制")
    memory_limit_mb: int = Field(description="内存限制（MB）")
    network_enabled: bool = Field(description="是否启用网络")
    warm_pool_reused: bool = Field(description="是否复用 WarmPool")

    model_config = ConfigDict(from_attributes=True)


class SandboxPage(BaseModel):
    items: list[SandboxResponse] = Field(description="沙箱列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class SandboxQuotaUsageResponse(BaseModel):
    organization_id: str | None = Field(default=None, description="组织 ID")
    configured_memory_mb: int = Field(description="策略配置内存上限（MB）")
    configured_cpus: str = Field(description="策略配置 CPU 上限")
    configured_workspace_quota_mb: int = Field(description="策略配置工作区配额（MB）")
    configured_network_enabled: bool = Field(description="策略配置网络开关")
    configured_network_allowlist: list[str] = Field(description="策略配置网络白名单")
    sandbox_total: int = Field(description="沙箱总数")
    running_total: int = Field(description="运行中沙箱数")
    destroyed_total: int = Field(description="已销毁沙箱数")
    memory_limit_mb_total: int = Field(description="累计沙箱内存配额（MB）")
    running_memory_limit_mb_total: int = Field(description="运行中沙箱内存配额（MB）")
    cpu_limit_total: float = Field(description="累计沙箱 CPU 配额")
    running_cpu_limit_total: float = Field(description="运行中沙箱 CPU 配额")
    network_enabled_total: int = Field(description="启用网络的沙箱数")
    warm_pool_reused_total: int = Field(description="复用 WarmPool 的沙箱数")
    latest_created_at: datetime | None = Field(default=None, description="最近创建时间")


class SandboxQuotaHistoryItem(BaseModel):
    id: str = Field(description="沙箱 ID")
    task_id: str = Field(description="任务 ID")
    container_id: str = Field(description="容器 ID")
    status: str = Field(description="沙箱状态")
    cpu_limit: str = Field(description="CPU 限制")
    cpu_limit_value: float = Field(description="CPU 限制数值")
    memory_limit_mb: int = Field(description="内存限制（MB）")
    network_enabled: bool = Field(description="是否启用网络")
    warm_pool_reused: bool = Field(description="是否复用 WarmPool")
    lifetime_seconds: int | None = Field(default=None, description="生命周期秒数")
    created_at: datetime = Field(description="创建时间")
    destroyed_at: datetime | None = Field(default=None, description="销毁时间")


class SandboxQuotaHistoryPage(BaseModel):
    items: list[SandboxQuotaHistoryItem] = Field(description="沙箱配额历史")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class WarmPoolResponse(BaseModel):
    enabled: bool = Field(description="是否启用")
    min_size: int = Field(description="最小数量")
    max_size: int = Field(description="最大数量")
    idle: int = Field(description="空闲数量")
    busy: int = Field(description="忙碌数量")
    failed: int = Field(description="失败数量")
    hit_total: int = Field(description="命中总数")
    miss_total: int = Field(description="未命中总数")


class WarmPoolBenchmarkRequest(BaseModel):
    iterations: int = Field(default=5, ge=1, le=50, description="基准测试迭代次数")
    target_startup_ms: int = Field(default=50, ge=1, le=1000, description="目标启动耗时")
    mode: Literal["projection"] = Field(default="projection", description="基准测试模式")


class WarmPoolBenchmarkResponse(BaseModel):
    id: str = Field(description="Benchmark Run ID")
    organization_id: str | None = Field(default=None, description="组织 ID")
    mode: str = Field(description="基准测试模式")
    status: str = Field(description="状态")
    target_startup_ms: int = Field(description="目标启动耗时")
    iteration_count: int = Field(description="迭代次数")
    warm_avg_ms: int = Field(description="WarmPool 平均耗时")
    warm_p95_ms: int = Field(description="WarmPool P95 耗时")
    cold_avg_ms: int = Field(description="冷启动基线平均耗时")
    hit_rate: int = Field(description="命中率百分比")
    report_json: dict = Field(description="完整报告")
    created_by: str | None = Field(default=None, description="创建者")
    created_at: datetime = Field(description="创建时间")

    model_config = ConfigDict(from_attributes=True)


class WarmPoolBenchmarkPage(BaseModel):
    items: list[WarmPoolBenchmarkResponse] = Field(description="Benchmark Run 列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class CountItem(BaseModel):
    name: str = Field(description="名称")
    count: int = Field(description="数量")


class ObservabilityQueueResponse(BaseModel):
    pending: int = Field(description="等待执行的子 Agent 数")
    queued: int = Field(default=0, description="已入队等待 worker 消费的数量")
    running: int = Field(description="正在执行的子 Agent 数")
    success: int = Field(description="成功完成的子 Agent 数")
    failed: int = Field(description="失败的子 Agent 数")
    timeout: int = Field(description="超时的子 Agent 数")
    cancelled: int = Field(description="已取消的子 Agent 数")
    active_total: int = Field(description="等待或运行中的子 Agent 数")
    capacity: int = Field(description="当前组织活跃任务队列容量")
    available_slots: int = Field(description="剩余队列槽位")
    utilization_percent: int = Field(description="队列槽位使用率百分比")


class ObservabilitySummaryResponse(BaseModel):
    tasks_by_status: list[CountItem] = Field(description="任务状态分布")
    subagents_by_status: list[CountItem] = Field(description="子 Agent 状态分布")
    agent_assignments_by_status: list[CountItem] = Field(description="Agent Assignment 状态分布")
    model_calls_by_status: list[CountItem] = Field(description="模型调用状态分布")
    tool_calls_by_status: list[CountItem] = Field(description="工具调用状态分布")
    sandboxes_by_status: list[CountItem] = Field(description="沙箱状态分布")
    subagent_queue: ObservabilityQueueResponse = Field(description="子 Agent 队列运营摘要")
    assignment_queue: ObservabilityQueueResponse = Field(
        description="Agent Assignment 队列运营摘要"
    )
    warm_pool: WarmPoolResponse = Field(description="WarmPool 状态")
    event_total: int = Field(description="事件总数")
    task_total: int = Field(description="任务总数")
    failed_task_total: int = Field(description="失败任务总数")
    model_call_total: int = Field(description="模型调用总数")
    tool_call_total: int = Field(description="工具调用总数")
    sandbox_total: int = Field(description="沙箱总数")


class PlannerExecutorArchitectureResponse(BaseModel):
    enabled: bool = Field(description="Planner/Executor 架构是否启用")
    planner: str = Field(description="Planner 实现")
    executor: str = Field(description="Executor 实现")
    react_engine: str = Field(description="同步执行引擎")
    planner_prompt_version: str = Field(description="Planner Prompt 版本")
    plan_total: int = Field(description="当前组织计划总数")
    sync_step_total: int = Field(description="同步步骤总数")
    async_step_total: int = Field(description="异步步骤总数")
    status: str = Field(description="当前能力状态")


class EventSourcingArchitectureResponse(BaseModel):
    enabled: bool = Field(description="事件溯源是否启用")
    event_total: int = Field(description="当前组织事件总数")
    snapshot_total: int = Field(description="当前组织快照总数")
    snapshot_frequency_events: int = Field(description="每多少个事件生成快照")
    replay_enabled: bool = Field(description="是否支持重放")
    resume_enabled: bool = Field(description="是否支持断点恢复")
    audit_log_enabled: bool = Field(description="是否支持完整审计日志")
    time_travel_debugging_enabled: bool = Field(description="是否支持按序号重放调试")
    last_sequence: int = Field(description="当前组织最大事件序号")


class SubagentArchitectureResponse(BaseModel):
    enabled: bool = Field(description="Subagent 编排是否启用")
    concurrency_limit: int = Field(description="子 Agent 并发上限")
    timeout_seconds: int = Field(description="默认超时秒数")
    pending: int = Field(description="等待执行数量")
    running: int = Field(description="正在执行数量")
    success: int = Field(description="成功数量")
    failed: int = Field(description="失败数量")
    timeout: int = Field(description="超时数量")
    cancelled: int = Field(description="取消数量")
    active_total: int = Field(description="PENDING + RUNNING 数量")
    state_machine: list[str] = Field(description="状态机")
    status: str = Field(description="当前能力状态")


class WarmPoolArchitectureResponse(BaseModel):
    enabled: bool = Field(description="WarmPool 是否启用")
    target_startup_ms: int = Field(description="WarmPool 目标启动耗时毫秒")
    cold_start_min_ms: int = Field(description="传统冷启动最小耗时毫秒")
    cold_start_max_ms: int = Field(description="传统冷启动最大耗时毫秒")
    min_size: int = Field(description="预热池最小数量")
    max_size: int = Field(description="预热池最大数量")
    idle: int = Field(description="空闲数量")
    busy: int = Field(description="忙碌数量")
    failed: int = Field(description="失败数量")
    hit_total: int = Field(description="命中总数")
    miss_total: int = Field(description="未命中总数")
    status: str = Field(description="当前能力状态")


class MultiAgentArchitectureResponse(BaseModel):
    enabled: bool = Field(description="多 Agent 编排是否启用")
    agent_total: int = Field(description="当前组织可用 Agent 数")
    assignment_total: int = Field(description="当前组织 Assignment 总数")
    handoff_total: int = Field(description="当前组织 Handoff 总数")
    pending: int = Field(description="等待执行数量")
    queued: int = Field(description="已入队数量")
    running: int = Field(description="正在执行数量")
    success: int = Field(description="成功数量")
    failed: int = Field(description="失败数量")
    active_total: int = Field(description="QUEUED + RUNNING 数量")
    state_machine: list[str] = Field(description="状态机")
    strategy: str = Field(description="编排策略")
    reducer_enabled: bool = Field(description="是否启用 Reducer 聚合")
    status: str = Field(description="当前能力状态")


class RuntimeArchitectureResponse(BaseModel):
    planner_executor: PlannerExecutorArchitectureResponse = Field(
        description="Planner/Executor 任务分解与执行架构"
    )
    event_sourcing: EventSourcingArchitectureResponse = Field(description="事件溯源能力")
    multi_agent: MultiAgentArchitectureResponse = Field(description="多 Agent 编排能力")
    subagents: SubagentArchitectureResponse = Field(description="Subagent 编排能力")
    warm_pool: WarmPoolArchitectureResponse = Field(description="WarmPool 性能优化能力")
    notes: list[str] = Field(description="架构说明")


class ObservabilityLogEntry(BaseModel):
    timestamp: datetime = Field(description="日志时间")
    level: str = Field(description="日志级别")
    service: str = Field(description="服务名")
    message: str = Field(description="日志内容")
    trace_id: str | None = Field(default=None, description="Trace ID")
    task_id: str | None = Field(default=None, description="任务 ID")
    agent_run_id: str | None = Field(default=None, description="Agent 运行 ID")
    event_type: str | None = Field(default=None, description="事件类型")
    payload_json: dict = Field(default_factory=dict, description="日志载荷")
    source: str = Field(description="日志来源")


class ObservabilityLogPage(BaseModel):
    items: list[ObservabilityLogEntry] = Field(description="日志列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")
    source: str = Field(description="数据来源")
    facets: dict[str, list[CountItem]] = Field(default_factory=dict, description="日志聚合维度")


class ObservabilityTraceSpan(BaseModel):
    trace_id: str = Field(description="Trace ID")
    span_id: str = Field(description="Span ID")
    parent_span_id: str | None = Field(default=None, description="父 Span ID")
    name: str = Field(description="Span 名称")
    service: str = Field(description="服务名")
    start_time: datetime = Field(description="开始时间")
    duration_ms: int = Field(description="耗时毫秒")
    attributes: dict = Field(default_factory=dict, description="Span 属性")
    source: str = Field(description="数据来源")


class ObservabilityTraceServiceNode(BaseModel):
    service: str = Field(description="服务名")
    span_count: int = Field(description="Span 数量")
    error_count: int = Field(description="错误 Span 数量")
    total_duration_ms: int = Field(description="累计耗时毫秒")


class ObservabilityTraceServiceEdge(BaseModel):
    source: str = Field(description="上游服务")
    target: str = Field(description="下游服务")
    span_count: int = Field(description="关联 Span 数量")
    total_duration_ms: int = Field(description="累计耗时毫秒")


class ObservabilityTraceResponse(BaseModel):
    trace_id: str = Field(description="Trace ID")
    spans: list[ObservabilityTraceSpan] = Field(description="Span 列表")
    source: str = Field(description="数据来源")
    service_nodes: list[ObservabilityTraceServiceNode] = Field(
        default_factory=list,
        description="跨服务 Trace 节点",
    )
    service_edges: list[ObservabilityTraceServiceEdge] = Field(
        default_factory=list,
        description="跨服务 Trace 边",
    )


class GrafanaDashboardResponse(BaseModel):
    uid: str = Field(description="Dashboard UID")
    title: str = Field(description="Dashboard 标题")
    url: str = Field(description="Dashboard 地址")
    tags: list[str] = Field(default_factory=list, description="标签")
    source: str = Field(description="数据来源")


class GrafanaDashboardPage(BaseModel):
    items: list[GrafanaDashboardResponse] = Field(description="Dashboard 列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class ObservabilityServiceHealthResponse(BaseModel):
    name: str = Field(description="服务名")
    status: str = Field(description="健康状态")
    url: str = Field(description="服务地址")
    latency_ms: int | None = Field(default=None, description="探测耗时毫秒")
    error_message: str | None = Field(default=None, description="错误信息")
    alert_status: str = Field(default="ok", description="告警状态")
    alert_severity: str = Field(default="none", description="告警级别")
    runbook_url: str = Field(default="/docs/runbooks/troubleshooting", description="排障手册地址")


class ObservabilityServicesHealthResponse(BaseModel):
    services: list[ObservabilityServiceHealthResponse] = Field(description="服务健康列表")


class ObservabilityExportItem(BaseModel):
    name: str = Field(description="导出项名称")
    title: str = Field(description="导出项标题")
    description: str = Field(description="导出项说明")
    method: str = Field(description="HTTP 方法")
    url: str = Field(description="导出地址")
    format: str = Field(description="导出格式")
    required_roles: list[str] = Field(description="所需角色")


class ObservabilityExportPage(BaseModel):
    items: list[ObservabilityExportItem] = Field(description="观测导出入口列表")


class ObservabilityExportHistoryItem(BaseModel):
    id: str = Field(description="导出记录 ID")
    export_type: str = Field(description="导出类型")
    filename: str = Field(description="文件名")
    content_type: str = Field(description="内容类型")
    format: str = Field(description="导出格式")
    source: str = Field(description="数据来源")
    row_count: int = Field(description="导出行数")
    filter_json: dict = Field(description="导出筛选条件")
    storage_driver: str = Field(description="留存驱动")
    size_bytes: int = Field(description="文件大小字节数")
    sha256: str = Field(description="文件 SHA256")
    download_url: str = Field(description="历史文件下载地址")
    created_at: datetime = Field(description="创建时间")

    model_config = ConfigDict(from_attributes=True)


class ObservabilityExportHistoryPage(BaseModel):
    items: list[ObservabilityExportHistoryItem] = Field(description="观测导出历史")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class ModelCallResponse(BaseModel):
    id: str = Field(description="模型调用 ID")
    task_id: str = Field(description="任务 ID")
    agent_run_id: str | None = Field(default=None, description="Agent 运行 ID")
    trace_id: str | None = Field(default=None, description="Trace ID")
    model_provider: str = Field(description="模型供应商")
    model_name: str = Field(description="模型名称")
    status: str = Field(description="调用状态")
    prompt_tokens: int = Field(description="提示词 token 数")
    completion_tokens: int = Field(description="输出 token 数")
    duration_ms: int = Field(description="耗时（毫秒）")
    grounding_correlation_id: str | None = Field(
        default=None,
        description="Grounding correlation ID",
    )
    prompt_manifest_id: str | None = Field(default=None, description="Prompt manifest ID")
    model_request_sha256: str | None = Field(default=None, description="请求哈希")
    model_request_hash_schema_version: int = Field(
        default=1,
        description="请求哈希 schema version",
    )
    request_message_hashes_json: list = Field(
        default_factory=list,
        description="Ordered safe message hashes",
    )
    request_message_hashes_sha256: str | None = Field(
        default=None,
        description="Ordered message hashes digest",
    )
    hash_recomputability_status: str = Field(
        default="legacy_not_recomputable",
        description="Request hash recomputability status",
    )
    attempt_index: int = Field(default=1, description="模型调用尝试序号")
    terminal_status: str | None = Field(default=None, description="终态")
    request_json: dict = Field(description="请求内容")
    response_json: dict = Field(description="响应内容")
    error_message: str | None = Field(default=None, description="错误信息")
    created_at: datetime = Field(description="创建时间")

    model_config = ConfigDict(from_attributes=True)


class ModelCallPage(BaseModel):
    items: list[ModelCallResponse] = Field(description="模型调用列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class ModelFallbackEventItem(BaseModel):
    event_id: str = Field(description="事件 ID")
    task_id: str = Field(description="任务 ID")
    sequence: int = Field(description="事件序号")
    primary_provider: str | None = Field(default=None, description="主供应商")
    primary_model: str | None = Field(default=None, description="主模型")
    fallback_provider: str = Field(description="fallback 供应商")
    fallback_model: str = Field(description="fallback 模型")
    fallback_index: int = Field(description="fallback 顺序")
    reason: str | None = Field(default=None, description="触发原因")
    trace_id: str | None = Field(default=None, description="Trace ID")
    created_at: datetime = Field(description="创建时间")


class ModelFallbackSummaryResponse(BaseModel):
    organization_id: str | None = Field(default=None, description="组织 ID")
    fallback_total: int = Field(description="fallback 事件总数")
    primary_failure_total: int = Field(description="主模型失败次数")
    providers: list[CountItem] = Field(description="fallback 供应商分布")
    recent_events: list[ModelFallbackEventItem] = Field(description="最近 fallback 事件")


class ToolCallResponse(BaseModel):
    id: str = Field(description="工具调用 ID")
    task_id: str = Field(description="任务 ID")
    agent_run_id: str | None = Field(default=None, description="Agent 运行 ID")
    trace_id: str | None = Field(default=None, description="Trace ID")
    tool_name: str = Field(description="工具名称")
    status: str = Field(description="调用状态")
    risk_level: str = Field(description="风险等级")
    requires_sandbox: bool = Field(description="是否需要沙箱")
    sandbox_id: str | None = Field(default=None, description="沙箱 ID")
    duration_ms: int = Field(description="耗时（毫秒）")
    input_json: dict = Field(description="输入内容")
    output_json: dict = Field(description="输出内容")
    output_kind: str = Field(default="unknown", description="输出类型")
    output_summary: str = Field(default="", description="输出摘要")
    timeout_category: str | None = Field(default=None, description="超时分类")
    error_message: str | None = Field(default=None, description="错误信息")
    created_at: datetime = Field(description="创建时间")

    model_config = ConfigDict(from_attributes=True)


class ToolCallPage(BaseModel):
    items: list[ToolCallResponse] = Field(description="工具调用列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class ToolExecuteRequest(BaseModel):
    tool_name: str = Field(description="工具名称")
    input_json: dict = Field(default_factory=dict, description="工具输入")
    sandbox_id: str | None = Field(default=None, description="沙箱 ID")
    create_sandbox: bool = Field(default=False, description="需要沙箱时是否自动创建")


class ToolExecuteResponse(BaseModel):
    tool_call: ToolCallResponse = Field(description="工具调用审计记录")
    allowed: bool = Field(description="是否通过策略")
    output: dict = Field(description="工具输出")


class ToolApprovalResponse(BaseModel):
    id: str = Field(description="审批 ID")
    task_id: str = Field(description="任务 ID")
    tool_call_id: str = Field(description="工具调用 ID")
    organization_id: str | None = Field(default=None, description="组织 ID")
    requested_by: str | None = Field(default=None, description="请求人")
    decided_by: str | None = Field(default=None, description="审批人")
    status: str = Field(description="审批状态")
    risk_level: str = Field(description="风险等级")
    reason: str = Field(description="审批原因")
    request_json: dict = Field(description="审批请求")
    decision_json: dict = Field(description="审批决定")
    created_at: datetime = Field(description="创建时间")
    decided_at: datetime | None = Field(default=None, description="审批时间")

    model_config = ConfigDict(from_attributes=True)


class ToolApprovalPage(BaseModel):
    items: list[ToolApprovalResponse] = Field(description="工具审批列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class AgentRunWorkspaceResponse(BaseModel):
    run: TaskResponse = Field(description="Agent Run 基础信息")
    plan: TaskPlanResponse | None = Field(default=None, description="最新 Plan DAG")
    events: list[EventResponse] = Field(default_factory=list, description="Event Sourcing 事件流")
    knowledge_grounding: KnowledgeGroundingResponse | None = Field(
        default=None,
        description="Knowledge / RAG grounding evidence",
    )
    subagents: list[SubagentResponse] = Field(default_factory=list, description="Subagent 状态")
    tool_calls: list[ToolCallResponse] = Field(default_factory=list, description="工具调用日志")
    model_calls: list[ModelCallResponse] = Field(default_factory=list, description="模型调用日志")
    approvals: list[ToolApprovalResponse] = Field(
        default_factory=list,
        description="待处理与历史审批",
    )
    assignments: list[AgentAssignmentResponse] = Field(
        default_factory=list,
        description="多 Agent 分配",
    )
    handoffs: list[AgentHandoffResponse] = Field(default_factory=list, description="多 Agent 交接")


class ToolApprovalDecisionRequest(BaseModel):
    reason: str = Field(default="", description="审批说明")


class ToolApprovalModifyRequest(BaseModel):
    modified_input_json: dict = Field(default_factory=dict, description="修改后的工具输入")
    reason: str = Field(default="", description="修改说明")


class ToolMetadataResponse(BaseModel):
    name: str = Field(description="工具名称")
    description: str = Field(description="工具描述")
    category: str = Field(description="工具分类")
    source: str = Field(description="工具来源")
    risk_level: str = Field(description="风险等级")
    requires_sandbox: bool = Field(description="是否需要沙箱")
    network_policy: str = Field(description="网络策略")
    timeout_seconds: int = Field(description="超时秒数")
    allowed_roles: list[str] = Field(description="允许角色")
    audit_level: str = Field(description="审计等级")
    idempotent: bool = Field(description="是否幂等")
    input_schema: dict = Field(description="输入 schema")
    mcp_server: str | None = Field(default=None, description="MCP Server")
    mcp_method: str | None = Field(default=None, description="MCP Method")

    model_config = ConfigDict(from_attributes=True)


class ToolRegistryResponse(BaseModel):
    items: list[ToolMetadataResponse] = Field(description="工具列表")
    categories: list[str] = Field(description="工具分类")
    sources: list[str] = Field(description="工具来源")


class EvalDatasetCreateRequest(BaseModel):
    name: str = Field(min_length=1, description="Dataset 名称")
    description: str = Field(default="", description="Dataset 说明")


class EvalDatasetResponse(BaseModel):
    id: str = Field(description="Dataset ID")
    organization_id: str | None = Field(default=None, description="组织 ID")
    name: str = Field(description="Dataset 名称")
    description: str = Field(description="Dataset 说明")
    status: str = Field(description="Dataset 状态")
    baseline_run_id: str | None = Field(default=None, description="基线 Eval Run ID")
    created_by: str | None = Field(default=None, description="创建者")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")
    case_count: int = Field(default=0, description="Case 数量")

    model_config = ConfigDict(from_attributes=True)


class EvalDatasetPage(BaseModel):
    items: list[EvalDatasetResponse] = Field(description="Dataset 列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class EvalCaseCreateRequest(BaseModel):
    input_json: dict = Field(default_factory=dict, description="Case 输入")
    expected_json: dict = Field(default_factory=dict, description="期望输出")
    tags_json: list[str] = Field(default_factory=list, description="标签")


class EvalCaseFromRunRequest(BaseModel):
    expected_json: dict = Field(default_factory=dict, description="期望输出")
    tags_json: list[str] = Field(default_factory=list, description="标签")


class EvalCaseResponse(BaseModel):
    id: str = Field(description="Case ID")
    dataset_id: str = Field(description="Dataset ID")
    source_task_id: str | None = Field(default=None, description="来源 Run ID")
    input_json: dict = Field(description="Case 输入")
    expected_json: dict = Field(description="期望输出")
    tags_json: list[str] = Field(description="标签")
    created_at: datetime = Field(description="创建时间")

    model_config = ConfigDict(from_attributes=True)


class EvalCasePage(BaseModel):
    items: list[EvalCaseResponse] = Field(description="Case 列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class EvalRunCreateRequest(BaseModel):
    agent_id: str | None = Field(default=None, description="Agent 版本或 Agent ID")


class EvalResultResponse(BaseModel):
    id: str = Field(description="Result ID")
    eval_run_id: str = Field(description="Eval Run ID")
    eval_case_id: str = Field(description="Eval Case ID")
    task_id: str | None = Field(default=None, description="关联 Run ID")
    status: str = Field(description="评分状态")
    scores_json: dict = Field(description="评分明细")
    grader_trace_json: dict = Field(description="Grader trace")
    latency_ms: int = Field(description="耗时毫秒")
    cost_usd: str = Field(description="成本美元")
    error_message: str | None = Field(default=None, description="错误信息")
    created_at: datetime = Field(description="创建时间")

    model_config = ConfigDict(from_attributes=True)


class EvalRunResponse(BaseModel):
    id: str = Field(description="Eval Run ID")
    dataset_id: str = Field(description="Dataset ID")
    organization_id: str | None = Field(default=None, description="组织 ID")
    agent_id: str | None = Field(default=None, description="Agent ID")
    status: str = Field(description="Eval Run 状态")
    metrics_json: dict = Field(description="聚合指标")
    created_by: str | None = Field(default=None, description="创建者")
    started_at: datetime | None = Field(default=None, description="开始时间")
    completed_at: datetime | None = Field(default=None, description="完成时间")
    created_at: datetime = Field(description="创建时间")
    results: list[EvalResultResponse] = Field(default_factory=list, description="评分结果")

    model_config = ConfigDict(from_attributes=True)


class EvalRunPage(BaseModel):
    items: list[EvalRunResponse] = Field(description="Eval Run 列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class SetBaselineRequest(BaseModel):
    eval_run_id: str = Field(description="要设为基线的 Eval Run ID")


class RegressionDelta(BaseModel):
    baseline_run_id: str = Field(description="基线 Eval Run ID")
    current_run_id: str = Field(description="当前 Eval Run ID")
    task_success_rate_delta: float = Field(description="任务成功率变化（绝对百分点）")
    tool_selection_accuracy_delta: float = Field(description="工具选择准确率变化")
    avg_latency_ms_delta: int = Field(description="平均延迟变化（毫秒）")
    newly_failing_case_ids: list[str] = Field(description="新增失败 Case ID")
    newly_passing_case_ids: list[str] = Field(description="新增通过 Case ID")
    is_regression: bool = Field(description="是否回归（task_success_rate 下降 > 10pp）")
    total_cases: int = Field(description="总 Case 数")
    passed_cases: int = Field(description="通过 Case 数")
    failed_cases: int = Field(description="失败 Case 数")


class ModelSettingsResponse(BaseModel):
    default_provider: str = Field(description="默认供应商")
    default_model: str = Field(description="默认模型")
    providers: list[dict] = Field(description="供应商列表")
    rate_limits: dict = Field(description="限流信息")
    health: dict = Field(description="健康状态")
    circuit_breaker: dict = Field(default_factory=dict, description="供应商熔断规则")


class ModelHealthResponse(BaseModel):
    provider: str = Field(description="模型供应商")
    model: str = Field(description="模型名称")
    status: str = Field(description="健康状态")
    mode: str = Field(description="探测模式")
    checked_at: datetime = Field(description="检查时间")
    latency_ms: int = Field(description="探测耗时（毫秒）")
    error_message: str | None = Field(default=None, description="错误信息")
    circuit_status: str = Field(default="closed", description="熔断状态")
    circuit_open_until: str | None = Field(default=None, description="熔断打开截止时间")
    consecutive_failures: int = Field(default=0, description="连续失败次数")


class ModelHealthPage(BaseModel):
    items: list[ModelHealthResponse] = Field(description="模型健康状态列表")


class PolicySettingsResponse(BaseModel):
    risk_levels: list[dict] = Field(description="风险等级")
    approvals: dict = Field(description="审批规则")
    sandbox: dict = Field(description="沙箱规则")
    audit: dict = Field(description="审计规则")
    web_research: dict = Field(default_factory=dict, description="Web research 策略")
