from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_KNOWLEDGE_MIME_TYPES = {"text/plain", "text/markdown"}
MAX_KNOWLEDGE_IMPORT_BYTES = 120_000
LEGACY_MARKDOWN_PLAN_MODE = "co" + "dex_plan"


def normalize_workspace_mode(value: str) -> str:
    normalized = str(value or "chat").strip()
    if normalized == LEGACY_MARKDOWN_PLAN_MODE:
        return "markdown_plan"
    return normalized


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
    capability_attachments: list[dict] = Field(
        default_factory=list,
        description="Agent capability attachments summary",
    )
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")

    model_config = ConfigDict(from_attributes=True)


class AgentGatewayRouteResponse(BaseModel):
    id: str = Field(description="Gateway route ID")
    agent_id: str = Field(description="Agent ID")
    slug: str = Field(description="Public route slug")
    rate_limit: int = Field(description="Requests per minute")
    enabled: bool = Field(description="Whether invocation is enabled")
    description: str = Field(description="Operator-visible route purpose")
    created_at: datetime = Field(description="Creation time")
    updated_at: datetime = Field(description="Update time")
    last_invoked_at: datetime | None = Field(default=None, description="Last invoke time")

    model_config = ConfigDict(from_attributes=True)


class AgentGatewayRoutePage(BaseModel):
    items: list[AgentGatewayRouteResponse] = Field(description="Gateway routes")


class AgentGatewayRouteCreateRequest(BaseModel):
    slug: str | None = Field(default=None, description="Public route slug")
    description: str = Field(default="", max_length=500, description="Route purpose")
    rate_limit: int = Field(default=60, ge=1, le=600, description="Requests per minute")
    enabled: bool = Field(default=True, description="Whether invocation is enabled")


class AgentGatewayRouteCreateResponse(BaseModel):
    route: AgentGatewayRouteResponse = Field(description="Created route")
    api_key: str = Field(description="Plaintext key shown once")


class AgentGatewayRouteUpdateRequest(BaseModel):
    description: str | None = Field(default=None, max_length=500, description="Route purpose")
    rate_limit: int | None = Field(default=None, ge=1, le=600, description="Requests per minute")
    enabled: bool | None = Field(default=None, description="Whether invocation is enabled")


class GatewayInvokeRequest(BaseModel):
    goal: str | None = Field(default=None, max_length=4000, description="Invocation goal")
    title: str | None = Field(default=None, max_length=200, description="Run title")
    input: dict = Field(default_factory=dict, description="External caller input payload")


class GatewayInvokeResponse(BaseModel):
    run_id: str = Field(description="Created Run ID")
    agent_id: str = Field(description="Agent ID")
    status: str = Field(description="Run status")
    route_id: str = Field(description="Gateway route ID")
    slug: str = Field(description="Gateway route slug")


class AgentVersionResponse(BaseModel):
    id: str = Field(description="Agent version ID")
    agent_id: str = Field(description="Agent ID")
    version_number: int = Field(description="Monotonic version number")
    config_snapshot: dict = Field(description="Immutable Agent config snapshot")
    created_by: str | None = Field(default=None, description="Creator user ID")
    created_at: datetime = Field(description="Creation time")
    is_active: bool = Field(description="Whether this version is active")

    model_config = ConfigDict(from_attributes=True)


class AgentVersionPage(BaseModel):
    items: list[AgentVersionResponse] = Field(description="Agent versions")


class AgentVersionCreateRequest(BaseModel):
    activate: bool = Field(default=False, description="Activate created snapshot")


class AgentPage(BaseModel):
    items: list[AgentResponse] = Field(description="Agent 列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class AgentCreateRequest(BaseModel):
    id: str = Field(min_length=1, max_length=64, description="Agent ID")
    name: str = Field(min_length=1, description="Agent 名称")
    description: str = Field(default="", description="Agent 描述")
    role: str = Field(default="generalist", min_length=1, max_length=64, description="Agent 角色")
    model_provider: str = Field(default="default", description="默认模型供应商")
    model_name: str = Field(default="default", description="默认模型名称")
    system_prompt: str = Field(min_length=1, description="系统提示词")
    tools_json: list[str] = Field(default_factory=list, description="可用工具")
    routing_tags: list[str] = Field(default_factory=list, description="路由标签")
    max_parallel_assignments: int = Field(default=1, ge=1, description="最大并行分配数")
    token_budget: int | None = Field(default=None, ge=1, description="Agent Studio token budget")
    template_id: str | None = Field(default=None, description="Agent Studio template ID")


class AgentCloneRequest(BaseModel):
    id: str = Field(min_length=1, max_length=64, description="New Agent ID")
    name: str = Field(min_length=1, description="New Agent name")


class AgentCapabilityAttachmentRequest(BaseModel):
    capability_id: str = Field(min_length=1, description="Capability ID, key, or tool name")
    capability_version_id: str | None = Field(default=None, description="Capability version ID")
    enabled: bool = Field(default=True, description="Enable attachment for future runs")
    priority: int = Field(default=100, description="Attachment priority")


class AgentCapabilityAttachmentResponse(BaseModel):
    status: str = Field(description="Attachment status")
    attachment_id: str = Field(description="Attachment ID")
    agent_id: str = Field(description="Agent ID")
    capability_id: str = Field(description="Capability ID")
    capability_version_id: str = Field(description="Capability version ID")
    enabled: bool = Field(description="Enabled")
    priority: int = Field(description="Priority")


class AgentTokenOptimizerPreset(BaseModel):
    preset_id: Literal["off", "conservative", "balanced", "aggressive"] = Field(
        description="Built-in Token Optimizer preset ID"
    )
    display_name: str = Field(description="Preset display name")
    description: str = Field(description="Preset description")
    enabled: bool = Field(description="Whether this preset enables optimizer attachment")
    priority: int | None = Field(default=None, description="Attachment priority when enabled")


class AgentTokenOptimizerPresetPage(BaseModel):
    items: list[AgentTokenOptimizerPreset] = Field(description="Built-in presets")


class AgentTokenOptimizerSelectRequest(BaseModel):
    preset_id: Literal["off", "conservative", "balanced", "aggressive"] = Field(
        description="Built-in preset to apply"
    )


class AgentTokenOptimizerSelectionResponse(BaseModel):
    status: str = Field(description="Selection status")
    preset_id: Literal["off", "conservative", "balanced", "aggressive"]
    attachment_id: str | None = Field(default=None, description="Active attachment ID")
    capability_id: str | None = Field(default=None, description="Capability ID")
    capability_version_id: str | None = Field(default=None, description="Capability version ID")
    enabled: bool = Field(description="Whether optimizer is enabled")
    priority: int | None = Field(default=None, description="Attachment priority")


class AgentTriggerResponse(BaseModel):
    id: str = Field(description="Trigger ID")
    agent_id: str = Field(description="Agent ID")
    type: Literal["webhook"] = Field(description="Trigger type")
    endpoint_path: str = Field(description="Public webhook endpoint path")
    enabled: bool = Field(description="Whether trigger is enabled")
    created_at: datetime = Field(description="Created time")
    updated_at: datetime = Field(description="Updated time")
    last_triggered_at: datetime | None = Field(default=None, description="Last successful trigger")

    model_config = ConfigDict(from_attributes=True)


class AgentTriggerPage(BaseModel):
    items: list[AgentTriggerResponse] = Field(description="Agent trigger list")


class AgentTriggerCreateRequest(BaseModel):
    type: Literal["webhook"] = Field(default="webhook", description="Trigger type")
    endpoint_path: str | None = Field(default=None, max_length=128, description="Optional path")
    enabled: bool = Field(default=True, description="Whether trigger starts enabled")


class AgentTriggerCreateResponse(BaseModel):
    trigger: AgentTriggerResponse = Field(description="Created trigger")
    secret: str = Field(description="Plaintext secret shown once")


class AgentTriggerUpdateRequest(BaseModel):
    enabled: bool | None = Field(default=None, description="Whether trigger is enabled")


class WebhookTriggerRequest(BaseModel):
    goal: str | None = Field(default=None, description="Run goal override")
    title: str | None = Field(default=None, description="Run title")
    payload: dict = Field(default_factory=dict, description="External webhook payload")


class WebhookTriggerResponse(BaseModel):
    run_id: str = Field(description="Created Agent Run ID")
    agent_id: str = Field(description="Agent ID")
    status: str = Field(description="Run status")
    trigger_id: str = Field(description="Trigger ID")


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
    agent_id: str | None = Field(default=None, description="Agent ID")
    title: str = Field(description="任务标题")
    goal: str = Field(description="任务目标")
    status: str = Field(description="任务状态")
    model_provider: str = Field(description="模型供应商")
    model_name: str = Field(description="模型名称")
    max_runtime_seconds: int = Field(description="最大运行秒数")
    max_subagents: int = Field(description="最大子 Agent 数")
    enable_sandbox: bool = Field(description="是否启用容器沙箱")
    enable_network: bool = Field(description="是否启用网络访问")
    capability_snapshot_json: dict = Field(default_factory=dict, description="Capability snapshot")
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
    branch_id: str = Field(default="", description="摘要所属前端分支 ID")
    coverage_node_ids: list[str] = Field(default_factory=list, description="摘要覆盖的节点 ID")
    coverage_path_hash: str = Field(default="", description="覆盖路径哈希")
    summary_schema_version: str = Field(default="", description="摘要结构版本")
    compression_prompt_version: str = Field(default="", description="压缩提示词版本")
    compressor_provider: str = Field(default="", description="压缩模型供应商")
    compressor_model: str = Field(default="", description="压缩模型名称")
    estimated_original_tokens: int | None = Field(
        default=None,
        ge=0,
        description="压缩前覆盖内容估算 token，仅用于上下文缓存节省证据",
    )
    estimated_summary_tokens: int | None = Field(
        default=None,
        ge=0,
        description="压缩摘要估算 token，仅用于上下文缓存节省证据",
    )
    cache_status: Literal["accepted", "recomputed", "stale_rejected", "error"] | None = Field(
        default=None,
        description="前端最近一次压缩摘要 cache 状态，仅用于上下文组装证据",
    )


class AgentChatStreamRequest(BaseModel):
    """Accept unknown extra fields (v4 additive `context_max_tokens`, etc.)."""

    model_config = ConfigDict(extra="ignore")

    mode: Literal["chat", "markdown_plan", "plan", "goal", "cli_agent"] = Field(
        default="chat",
        description="Workspace 输入模式",
    )

    @field_validator("mode", mode="before")
    @classmethod
    def normalize_mode(cls, value: str) -> str:
        return normalize_workspace_mode(value)

    interaction_mode: Literal["chat", "plan", "act"] = Field(
        default="chat",
        description="CLI 工作流模式",
    )
    act_intent: dict | None = Field(default=None, description="act 工作流意图元数据")
    orchestration_mode: Literal["auto", "none", "multi_agent", "subagent"] = Field(
        default="auto",
        description=(
            "Workspace 编排模式：auto 根据请求触发，none 禁用，"
            "multi_agent 强制具名 Agent 编排，subagent 强制派生可检查子 Agent"
        ),
    )
    specialist_slug: str | None = Field(
        default=None,
        description="Workspace 子 Agent 模式下显式选择的专家模板 slug",
    )
    goal: str | None = Field(default=None, description="用户目标")
    model_provider: str | None = Field(default=None, description="本次请求选择的模型供应商")
    model_name: str | None = Field(default=None, description="本次请求选择的模型名称")
    enable_sandbox: bool = Field(default=False, description="本次 Workspace Run 是否启用容器沙箱")
    enable_network: bool = Field(default=False, description="本次 Workspace Run 是否启用网络访问")
    messages: list[ConversationNode] = Field(default_factory=list, description="当前分支消息")
    active_leaf_id: str | None = Field(default=None, description="当前活动叶子节点")
    run_id: str | None = Field(default=None, description="继续生成时绑定的原始 Agent Run ID")
    local_bridge_task_id: str | None = Field(
        default=None,
        description="本地 Agent bridge 任务 ID；仅用于 scoped stream token 授权校验",
    )
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
    # v4 additive: UI-side token budget hint. ContextAssemblyService
    # recounts with the backend estimator and records any omissions.
    context_max_tokens: int | None = Field(
        default=None,
        ge=1,
        description="UI-side context window budget; backend recounts before model calls",
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
    fanout_batch_id: str | None = Field(default=None, description="fanout 批次 ID")
    fanout_index: int | None = Field(default=None, description="fanout 批次序号")
    fanout_total: int | None = Field(default=None, description="fanout 批次总数")
    specialist_slug: str | None = Field(default=None, description="专家 slug")
    specialist_role: str | None = Field(default=None, description="专家角色")
    specialist_output: dict | None = Field(default=None, description="结构化专家输出")
    budget_consumed_json: dict = Field(default_factory=dict, description="专家预算消耗")
    budget_exceeded_json: list[str] = Field(default_factory=list, description="超出的专家预算项")
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
    recommended_specialist_slug: str | None = Field(
        default=None,
        description="推荐专家模板 slug",
    )
    fanout_specialist_slugs: list[str] = Field(
        default_factory=list,
        description="并行 fanout 专家 slug 列表",
    )
    fanout_aggregation: str = Field(default="synthesizer_chain", description="fanout 聚合模式")
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
    context_assembly: dict | None = Field(
        default=None,
        description="Context assembly manifest summary",
    )


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
    source_type: Literal["text", "markdown", "document", "connector"] = Field(
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
    connector_settings_json: dict = Field(default_factory=dict, description="连接器设置")
    connector_secret_value: str | None = Field(
        default=None,
        max_length=10_000,
        description="连接器密钥值，仅写入服务端密钥存储，不会回显",
    )

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
    connector_settings_json: dict | None = Field(
        default=None,
        description="连接器设置，仅 connector 知识源可更新",
    )
    connector_secret_value: str | None = Field(
        default=None,
        max_length=10_000,
        description="连接器密钥值，仅写入服务端密钥存储，不会回显",
    )


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
    connector_provider: str = Field(description="连接器提供方")
    connector_release_state: Literal[
        "usable",
        "configured-but-unavailable",
        "preview-not-counted",
    ] = Field(description="连接器发布状态")
    connector_counts_toward_complete_usable: bool = Field(description="是否计入 complete usable")
    connector_validation_status: Literal["ready", "configured", "preview", "invalid"] = Field(
        default="ready",
        description="连接器配置预检状态",
    )
    connector_validation_messages: list[str] = Field(
        default_factory=list,
        description="连接器配置预检消息",
    )
    connector_secret_configured: bool = Field(
        default=False,
        description="服务端是否已保存连接器密钥",
    )
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


class ContextAssemblyManifestResponse(BaseModel):
    id: str = Field(description="Context assembly manifest ID")
    organization_id: str | None = Field(default=None, description="组织 ID")
    agent_id: str = Field(description="Agent ID")
    run_id: str | None = Field(default=None, description="Run ID")
    retrieval_session_id: str | None = Field(default=None, description="Retrieval session ID")
    prompt_manifest_id: str | None = Field(
        default=None,
        description="Authoritative retrieval prompt manifest ID",
    )
    active_branch_id: str | None = Field(default=None, description="Active branch ID")
    active_leaf_id: str | None = Field(default=None, description="Active leaf ID")
    mode: Literal["authoritative", "shadow"] | str = Field(description="Assembly mode")
    token_budget_json: dict = Field(description="Backend token budget manifest")
    sections_json: list = Field(description="Ordered context section metadata")
    included_refs_json: list = Field(description="Included context refs")
    omitted_refs_json: list = Field(description="Omitted context refs")
    policy_decisions_json: list = Field(description="Policy decisions")
    tombstoned_refs_json: list = Field(description="Compliance tombstoned refs")
    context_text_sha256: str = Field(description="Assembled context hash")
    metadata_json: dict = Field(default_factory=dict, description="元数据")
    created_at: datetime = Field(description="创建时间")

    model_config = ConfigDict(from_attributes=True)


class AgentMemoryCreateRequest(BaseModel):
    scope: Literal["org", "agent", "user", "run"] = Field(
        default="agent",
        description="Memory scope",
    )
    source_type: Literal[
        "manual",
        "run_summary",
        "user_preference",
        "decision",
        "tool_observation",
        "imported",
    ] = Field(default="manual", description="Memory source type")
    text: str = Field(min_length=1, max_length=8_000, description="Memory text")
    run_id: str | None = Field(default=None, description="Run scope ID")
    message_id: str | None = Field(default=None, description="Source message ID")
    score: float = Field(default=0, ge=0, le=1, description="Relevance score")
    metadata: dict = Field(default_factory=dict, description="Safe metadata")
    expires_at: datetime | None = Field(default=None, description="Expiration time")


class AgentMemoryActionRequest(BaseModel):
    action: Literal["disable", "archive", "delete"] = Field(description="Lifecycle action")
    reason: str | None = Field(default=None, max_length=500, description="Reason")


class AgentMemoryResponse(BaseModel):
    id: str = Field(description="Memory ID")
    organization_id: str | None = Field(default=None, description="组织 ID")
    agent_id: str | None = Field(default=None, description="Agent ID")
    owner_user_id: str | None = Field(default=None, description="Owner user ID")
    run_id: str | None = Field(default=None, description="Run ID")
    message_id: str | None = Field(default=None, description="Message ID")
    scope: str = Field(description="Scope")
    source_type: str = Field(description="Source type")
    canonical_text: str = Field(description="Memory text")
    content_sha256: str = Field(description="Content hash")
    content_length: int = Field(description="Content length")
    score: float = Field(description="Score")
    policy_flags_json: list = Field(description="Policy flags")
    metadata_json: dict = Field(description="Metadata")
    lifecycle_status: str = Field(description="Lifecycle status")
    expires_at: datetime | None = Field(default=None, description="Expiration time")
    deleted_at: datetime | None = Field(default=None, description="Deleted time")
    created_by: str | None = Field(default=None, description="Created by")
    updated_by: str | None = Field(default=None, description="Updated by")
    created_at: datetime = Field(description="Created at")
    updated_at: datetime = Field(description="Updated at")

    model_config = ConfigDict(from_attributes=True)


class AgentMemoryPage(BaseModel):
    items: list[AgentMemoryResponse] = Field(description="Memory records")


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
    evidence_message: str = Field(default="", description="证据状态摘要")
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
    specialist_id: str | None = Field(default=None, description="专家模板 ID")
    fanout_batch_id: str | None = Field(default=None, description="fanout 批次 ID")
    fanout_index: int | None = Field(default=None, description="fanout 批次序号")
    fanout_total: int | None = Field(default=None, description="fanout 批次总数")
    dynamic_fanout_origin: str | None = Field(default=None, description="动态扩缩来源子 Agent")
    dynamic_fanout_requested_by: str | None = Field(
        default=None,
        description="触发动态扩缩的子 Agent",
    )
    dynamic_fanout_reason: str | None = Field(default=None, description="动态扩缩原因")
    context_json: dict = Field(description="上下文")
    started_at: datetime | None = Field(default=None, description="开始时间")
    completed_at: datetime | None = Field(default=None, description="完成时间")
    timeout_at: datetime | None = Field(default=None, description="超时时间")
    specialist: "SubagentSpecialistSummary | None" = Field(
        default=None,
        description="专家模板摘要",
    )
    output: "SubagentOutputResponse | None" = Field(default=None, description="结构化专家输出")

    model_config = ConfigDict(from_attributes=True)


class SubagentPage(BaseModel):
    items: list[SubagentResponse] = Field(description="子 Agent 列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class SubagentListItemResponse(SubagentResponse):
    task_title: str = Field(description="任务标题")
    task_status: str = Field(description="任务状态")
    step_key: str | None = Field(default=None, description="来源步骤键")
    specialist_slug: str | None = Field(default=None, description="专家 slug")
    output_summary: str | None = Field(default=None, description="结构化输出摘要")


class SubagentListPage(BaseModel):
    items: list[SubagentListItemResponse] = Field(description="组织子 Agent 列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class FanoutBatchMemberResponse(BaseModel):
    id: str = Field(description="子 Agent ID")
    status: str = Field(description="子 Agent 状态")
    specialist_id: str | None = Field(default=None, description="专家模板 ID")
    specialist_slug: str | None = Field(default=None, description="专家 slug")
    fanout_index: int | None = Field(default=None, description="fanout 序号")
    dynamic_fanout_origin: str | None = Field(default=None, description="动态扩缩来源")
    dynamic_fanout_requested_by: str | None = Field(default=None, description="动态扩缩触发者")
    dynamic_fanout_reason: str | None = Field(default=None, description="动态扩缩原因")
    output_id: str | None = Field(default=None, description="结构化输出 ID")


class FanoutBatchResponse(BaseModel):
    fanout_batch_id: str = Field(description="fanout 批次 ID")
    task_id: str = Field(description="任务 ID")
    step_key: str | None = Field(default=None, description="来源步骤")
    fanout_total: int = Field(description="批次总数")
    aggregation: str = Field(description="聚合模式")
    statuses: dict[str, int] = Field(default_factory=dict, description="状态分布")
    members: list[FanoutBatchMemberResponse] = Field(description="批次成员")
    extend_history: list[dict] = Field(default_factory=list, description="动态扩缩历史")


class FanoutBatchPage(BaseModel):
    items: list[FanoutBatchResponse] = Field(description="fanout 批次列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class SubagentCreateRequest(BaseModel):
    assignment: dict = Field(description="子 Agent 任务上下文")
    parent_agent_id: str | None = Field(default=None, description="父 Agent ID")
    timeout_seconds: int = Field(default=900, ge=1, description="超时秒数")
    enqueue: bool = Field(default=False, description="是否进入 Dramatiq 队列")
    specialist_slug: str | None = Field(default=None, description="可选专家模板 slug")


class SubagentFanoutExtendRequest(BaseModel):
    additional_specialist_slugs: list[str] = Field(
        min_length=1,
        max_length=10,
        description="追加到当前 fanout 批次的专家 slug",
    )
    reason: str = Field(min_length=1, max_length=240, description="动态扩缩原因")


class SubagentFanoutExtendResponse(BaseModel):
    fanout_batch_id: str = Field(description="fanout 批次 ID")
    added_count: int = Field(description="新增子 Agent 数")
    fanout_total: int = Field(description="扩缩后的批次总数")
    extend_count: int = Field(description="批次动态扩缩次数")
    agent_runs: list[SubagentResponse] = Field(description="新增子 Agent")


class SubagentSpecialistSummary(BaseModel):
    id: str = Field(description="专家 ID")
    slug: str = Field(description="专家 slug")
    display_name: str = Field(description="专家名称")
    role: str = Field(description="专家角色")
    visibility: str = Field(description="可见性")
    status: str = Field(description="状态")

    model_config = ConfigDict(from_attributes=True)


class SubagentSpecialistResponse(SubagentSpecialistSummary):
    organization_id: str | None = Field(default=None, description="组织 ID")
    description: str = Field(description="专家说明")
    system_prompt: str = Field(description="系统提示词")
    capability_slugs_json: list[str] = Field(description="工具白名单")
    output_schema_json: dict = Field(description="输出 JSON Schema")
    output_schema_sha256: str = Field(description="输出 Schema SHA256")
    budget_json: dict = Field(description="预算")
    trigger_keywords_json: list[str] = Field(description="触发关键词")
    created_by: str | None = Field(default=None, description="创建者")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")

    model_config = ConfigDict(from_attributes=True)


class SubagentSpecialistPage(BaseModel):
    items: list[SubagentSpecialistResponse] = Field(description="专家模板列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class SubagentSpecialistCreateRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    display_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    role: str = Field(default="specialist", min_length=1, max_length=32)
    system_prompt: str = Field(min_length=1)
    capability_slugs_json: list[str] = Field(default_factory=list)
    output_schema_json: dict = Field(description="JSON Schema draft-07")
    budget_json: dict = Field(default_factory=dict)
    trigger_keywords_json: list[str] = Field(default_factory=list)
    visibility: Literal["org", "private"] = Field(default="org")


class SubagentSpecialistUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, min_length=1)
    role: str | None = Field(default=None, min_length=1, max_length=32)
    system_prompt: str | None = Field(default=None, min_length=1)
    capability_slugs_json: list[str] | None = Field(default=None)
    output_schema_json: dict | None = Field(default=None)
    budget_json: dict | None = Field(default=None)
    trigger_keywords_json: list[str] | None = Field(default=None)
    visibility: Literal["org", "private"] | None = Field(default=None)
    status: Literal["ACTIVE", "ARCHIVED"] | None = Field(default=None)


class SubagentSpecialistPreflightRequest(BaseModel):
    sample_output: dict = Field(default_factory=dict, description="用于校验输出 schema 的样例输出")


class SubagentSpecialistPreflightResponse(BaseModel):
    status: Literal["passed", "failed"] = Field(description="预检状态")
    output_schema_sha256: str = Field(description="Schema SHA256")
    budget_json: dict = Field(description="规范化预算")
    errors: list[str] = Field(default_factory=list, description="预检错误")


class SubagentSpecialistFailureReason(BaseModel):
    reason: str = Field(description="失败原因")
    count: int = Field(description="次数")


class SubagentSpecialistStats(BaseModel):
    specialist_id: str = Field(description="专家 ID")
    slug: str = Field(description="专家 slug")
    window: Literal["7d", "30d", "all"] = Field(description="统计窗口")
    total_invocations: int = Field(description="总调用次数")
    success_count: int = Field(description="成功次数")
    failed_count: int = Field(description="失败次数")
    budget_exceeded_count: int = Field(description="预算超限次数")
    depth_rejected_count: int = Field(description="深度拒绝次数")
    success_rate: float | None = Field(default=None, description="成功率")
    avg_runtime_ms: int | None = Field(default=None, description="平均耗时")
    p95_runtime_ms: int | None = Field(default=None, description="P95 耗时")
    avg_cost_usd: str = Field(description="平均成本")
    total_cost_usd: str = Field(description="累计成本")
    avg_tool_calls: float = Field(description="平均工具调用数")
    avg_output_size_bytes: int = Field(description="平均输出大小")
    recent_failure_reasons: list[SubagentSpecialistFailureReason] = Field(
        default_factory=list,
        description="最近失败原因",
    )


class SpecialistSelectionDecisionResponse(BaseModel):
    id: str = Field(description="选择决策 ID")
    task_id: str = Field(description="任务 ID")
    plan_step_key: str = Field(description="计划步骤 key")
    selected_slug: str | None = Field(default=None, description="选中的专家 slug")
    confidence: float = Field(description="选择置信度")
    reasoning: str = Field(description="选择理由")
    selector: Literal["llm", "keyword", "success_rate", "recency_fallback"] = Field(
        description="最终选择器"
    )
    alternative_slugs_json: list[str] = Field(default_factory=list, description="备选专家")
    candidate_slugs_json: list[str] = Field(default_factory=list, description="候选专家")
    created_at: datetime = Field(description="创建时间")

    model_config = ConfigDict(from_attributes=True)


class SpecialistCalibrationBucket(BaseModel):
    bucket: str = Field(description="置信度分桶")
    min_confidence: float = Field(description="分桶最小置信度")
    max_confidence: float = Field(description="分桶最大置信度")
    decision_count: int = Field(description="决策数")
    success_count: int = Field(description="成功数")
    success_rate: float | None = Field(default=None, description="真实成功率")
    avg_confidence: float | None = Field(default=None, description="平均置信度")
    ece_contribution: float | None = Field(default=None, description="ECE 贡献")


class SpecialistCalibrationReport(BaseModel):
    organization_id: str = Field(description="组织 ID")
    window: Literal["7d", "30d", "all"] = Field(description="统计窗口")
    decision_count: int = Field(description="决策数")
    low_sample: bool = Field(description="样本数是否不足")
    ece: float | None = Field(default=None, description="Expected Calibration Error")
    buckets: list[SpecialistCalibrationBucket] = Field(description="置信度分桶")


class SpecialistMarketplaceListingCreateRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=96, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    display_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    author_name: str = Field(default="Harness User", min_length=1)
    version: str = Field(default="1.0.0", min_length=1, max_length=32)
    manifest_json: dict = Field(description="完整专家 manifest")
    signature: str = Field(min_length=1, max_length=128, description="manifest HMAC 签名")


class SpecialistMarketplaceListingUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, min_length=1)
    author_name: str | None = Field(default=None, min_length=1)
    version: str | None = Field(default=None, min_length=1, max_length=32)
    manifest_json: dict | None = Field(default=None)
    signature: str | None = Field(default=None, min_length=1, max_length=128)


class SpecialistMarketplaceApproveRequest(BaseModel):
    verified: bool = Field(default=True, description="是否审核通过")


class SpecialistMarketplaceInstallRequest(BaseModel):
    auto_update_enabled: bool = Field(default=False, description="是否启用自动更新")


class SpecialistMarketplaceListingResponse(BaseModel):
    id: str = Field(description="Listing ID")
    slug: str = Field(description="市场 slug")
    display_name: str = Field(description="名称")
    description: str = Field(description="说明")
    author_org_id: str | None = Field(default=None, description="作者组织")
    author_name: str = Field(description="作者")
    version: str = Field(description="版本")
    manifest_json: dict = Field(description="专家 manifest")
    signature: str = Field(description="签名")
    verified: bool = Field(description="是否已审核")
    download_count: int = Field(description="安装次数")
    installed: bool = Field(default=False, description="当前组织是否已安装")
    installed_specialist_id: str | None = Field(default=None, description="已安装专家 ID")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")

    model_config = ConfigDict(from_attributes=True)


class SpecialistMarketplaceListingPage(BaseModel):
    items: list[SpecialistMarketplaceListingResponse] = Field(description="市场 Listing")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class SpecialistInstallationResponse(BaseModel):
    id: str = Field(description="安装 ID")
    listing_id: str = Field(description="Listing ID")
    installed_org_id: str = Field(description="安装组织")
    installed_specialist_id: str = Field(description="安装后的专家 ID")
    installed_version: str = Field(description="安装版本")
    auto_update_enabled: bool = Field(description="是否自动更新")
    installed_at: datetime = Field(description="安装时间")
    specialist: SubagentSpecialistResponse | None = Field(default=None, description="安装后的专家")

    model_config = ConfigDict(from_attributes=True)


class SubagentOutputResponse(BaseModel):
    id: str = Field(description="输出 ID")
    agent_run_id: str = Field(description="子 Agent Run ID")
    task_id: str = Field(description="任务 ID")
    specialist_id: str | None = Field(default=None, description="专家 ID")
    output_json: dict = Field(description="结构化输出")
    output_schema_sha256: str = Field(description="Schema SHA256")
    budget_consumed_json: dict = Field(description="预算消耗")
    budget_exceeded_json: list[str] = Field(description="超出的预算项")
    written_at: datetime = Field(description="写入时间")

    model_config = ConfigDict(from_attributes=True)


class SubagentOutputCreateRequest(BaseModel):
    output_json: dict = Field(description="结构化输出")
    budget_consumed_json: dict | None = Field(default=None, description="可选预算消耗覆盖")
    budget_exceeded_json: list[str] | None = Field(default=None, description="可选预算超限覆盖")


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
    token_optimization: dict = Field(
        default_factory=dict, description="Token/cost optimization evidence projection"
    )


class CacheSourceSummary(BaseModel):
    cache_source: str = Field(description="上下文缓存来源")
    label: str = Field(description="用户可读缓存来源名称")
    hit_count: int = Field(default=0, description="命中次数")
    miss_count: int = Field(default=0, description="未命中次数")
    stale_count: int = Field(default=0, description="失效次数")
    estimated_saved_tokens: int = Field(default=0, description="估算节省 Token")
    hit_rate: float = Field(default=0, description="命中率百分比")
    reason: str | None = Field(default=None, description="最近原因")


class TokenSavingsSummary(BaseModel):
    actual_prompt_tokens: int = Field(default=0, description="实际 Prompt Token 数")
    actual_completion_tokens: int = Field(default=0, description="实际 Completion Token 数")
    actual_total_tokens: int = Field(default=0, description="实际总 Token 数")
    estimated_candidate_tokens: int = Field(default=0, description="优化前候选上下文估算 Token")
    estimated_included_tokens: int = Field(default=0, description="优化后保留上下文估算 Token")
    estimated_omitted_tokens: int = Field(default=0, description="优化省略上下文估算 Token")
    estimated_saved_tokens: int = Field(default=0, description="估算节省 Token")
    estimated_savings_percent: float = Field(default=0, description="估算节省比例")
    context_manifest_count: int = Field(default=0, description="上下文组装证据数")
    pruning_manifest_count: int = Field(default=0, description="发生裁剪的上下文证据数")
    retrieval_cache_hit_count: int = Field(default=0, description="检索缓存命中数")
    retrieval_cache_miss_count: int = Field(default=0, description="检索缓存未命中数")
    retrieval_cache_stale_count: int = Field(default=0, description="上下文缓存失效数")
    cache_sources: list[CacheSourceSummary] = Field(
        default_factory=list,
        description="按来源聚合的上下文缓存命中证据",
    )
    low_cost_route_count: int = Field(default=0, description="低成本模型路由次数")
    optimizer_capability_version_ids: list[str] = Field(
        default_factory=list, description="生效的优化器版本 ID"
    )
    optimizer_labels: list[str] = Field(default_factory=list, description="生效的优化方案名称")
    optimizer_decision_count: int = Field(default=0, description="优化器决策数")


class TokenSavingsOmissionReason(BaseModel):
    reason: str = Field(description="省略原因")
    count: int = Field(description="出现次数")


class TokenSavingsLowCostRoute(BaseModel):
    model_call_id: str = Field(description="模型调用 ID")
    model_name: str = Field(description="模型名称")
    reason: str = Field(description="低成本路由原因")


class TokenSavingsRunItem(BaseModel):
    run_id: str = Field(description="Agent Run ID")
    agent_id: str | None = Field(default=None, description="Agent ID")
    model_names: list[str] = Field(default_factory=list, description="本次运行涉及的模型名称")
    title: str = Field(description="运行标题")
    status: str = Field(description="运行状态")
    created_at: datetime = Field(description="运行创建时间")
    updated_at: datetime = Field(description="运行更新时间")
    context_manifest_id: str = Field(description="上下文组装证据 ID")
    estimated_candidate_tokens: int = Field(default=0, description="优化前候选上下文估算 Token")
    estimated_included_tokens: int = Field(default=0, description="优化后保留上下文估算 Token")
    estimated_omitted_tokens: int = Field(default=0, description="优化省略上下文估算 Token")
    estimated_saved_tokens: int = Field(default=0, description="估算节省 Token")
    estimated_savings_percent: float = Field(default=0, description="估算节省比例")
    actual_prompt_tokens: int = Field(default=0, description="实际 Prompt Token")
    actual_completion_tokens: int = Field(default=0, description="实际 Completion Token")
    actual_total_tokens: int = Field(default=0, description="实际总 Token")
    included_count: int = Field(default=0, description="保留上下文数量")
    omitted_count: int = Field(default=0, description="省略上下文数量")
    pruning_applied: bool = Field(default=False, description="是否发生预算裁剪")
    retrieval_cache_hit_count: int = Field(default=0, description="检索缓存命中数")
    retrieval_cache_miss_count: int = Field(default=0, description="检索缓存未命中数")
    retrieval_cache_stale_count: int = Field(default=0, description="上下文缓存失效数")
    cache_sources: list[CacheSourceSummary] = Field(
        default_factory=list,
        description="按来源聚合的上下文缓存命中证据",
    )
    low_cost_routes: list[TokenSavingsLowCostRoute] = Field(
        default_factory=list, description="低成本路由证据"
    )
    optimizer_capability_version_ids: list[str] = Field(
        default_factory=list, description="生效的优化器版本 ID"
    )
    optimizer_labels: list[str] = Field(default_factory=list, description="生效的优化方案名称")
    optimizer_policy_hash: str | None = Field(default=None, description="优化策略哈希")
    optimizer_decision_count: int = Field(default=0, description="优化器决策数")
    omission_reasons: list[TokenSavingsOmissionReason] = Field(
        default_factory=list, description="省略原因聚合"
    )


class TokenSavingsPage(BaseModel):
    generated_at: datetime = Field(description="生成时间")
    summary: TokenSavingsSummary = Field(description="Token 节省汇总")
    runs: list[TokenSavingsRunItem] = Field(description="最近运行节省证据")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class ObservabilityGroundingQualityItem(BaseModel):
    eval_run_id: str = Field(description="Eval Run ID")
    eval_result_id: str = Field(description="Eval Result ID")
    eval_case_id: str = Field(description="Eval Case ID")
    task_id: str | None = Field(default=None, description="关联 Run ID")
    dataset_id: str = Field(description="Dataset ID")
    agent_id: str | None = Field(default=None, description="Agent ID")
    status: str = Field(description="Eval Result 状态")
    created_at: datetime = Field(description="Result 创建时间")
    grounding_passed: bool = Field(description="Eval 计算的 grounding pass/fail")
    grounding_failures: list[str] = Field(description="Eval 计算的 grounding failure reason")
    forbidden_evidence_leaked: bool = Field(description="Eval 计算的 forbidden evidence 泄漏状态")
    forbidden_leak_sources: list[str] = Field(description="Eval 计算的泄漏来源类型")
    fallback_expected: bool = Field(description="Eval contract fallback expectation")
    fallback_observed: bool = Field(description="Eval 计算的 fallback observed 状态")
    unsupported_marker_present: bool = Field(description="Eval 计算的 unsupported marker 状态")
    citation_keys: list[str] = Field(description="Eval trace citation keys")
    citation_hit_ids: list[str] = Field(description="Eval trace citation hit IDs")
    retrieval_session_id: str | None = Field(default=None, description="Retrieval Session ID")
    prompt_manifest_id: str | None = Field(default=None, description="Prompt Manifest ID")


class ObservabilityGroundingQualityResponse(BaseModel):
    items: list[ObservabilityGroundingQualityItem] = Field(description="Grounding quality 投影")
    metrics: dict[str, float | int] = Field(description="Eval-owned aggregate metrics projection")
    failure_facets: list[CountItem] = Field(description="Failure reason counts")
    total: int = Field(description="返回结果数")


class PlannerExecutorArchitectureResponse(BaseModel):
    enabled: bool = Field(description="Planner/Executor 架构是否启用")
    planner: str = Field(description="Planner 实现")
    executor: str = Field(description="Executor 实现")
    react_engine: str = Field(description="同步执行引擎")
    planner_prompt_version: str = Field(description="Planner Prompt 版本")
    plan_total: int = Field(description="当前组织计划总数")
    sync_step_total: int = Field(description="同步步骤总数")
    async_step_total: int = Field(description="异步步骤总数")
    langgraph_step_total: int = Field(default=0, description="LangGraph workflow node 步骤总数")
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
    end_time: datetime | None = Field(default=None, description="结束时间")
    duration_ms: int = Field(description="耗时毫秒")
    kind: str = Field(default="internal", description="Span kind")
    status: str = Field(default="OK", description="Span status")
    task_id: str | None = Field(default=None, description="任务 ID")
    agent_run_id: str | None = Field(default=None, description="Agent Run ID")
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


class TraceListItem(BaseModel):
    trace_id: str = Field(description="Trace ID")
    task_id: str | None = Field(default=None, description="任务 ID")
    root_name: str = Field(description="Root span name")
    start_time: datetime = Field(description="开始时间")
    duration_ms: int = Field(description="Trace 总耗时")
    span_count: int = Field(description="Span 数量")
    status: str = Field(description="Trace 状态")
    source: str = Field(description="数据来源")


class TraceListResponse(BaseModel):
    items: list[TraceListItem] = Field(description="Trace 列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class CostRollupBreakdownItem(BaseModel):
    key: str = Field(description="聚合键")
    label: str = Field(description="展示名称")
    cost_usd: float = Field(description="成本 USD")
    tokens_in: int = Field(description="输入 Token")
    tokens_out: int = Field(description="输出 Token")
    run_count: int = Field(description="运行数量")
    share: float = Field(description="成本占比")
    pricing_status: str = Field(default="verified", description="价格来源状态")
    pricing_blocking: bool = Field(default=False, description="是否阻塞企业成本门禁")


class CostRollupSeriesPoint(BaseModel):
    bucket_start: str = Field(description="时间桶起点")
    key: str = Field(description="聚合键")
    label: str = Field(description="展示名称")
    cost_usd: float = Field(description="成本 USD")
    tokens: int = Field(description="Token 总量")
    run_count: int = Field(description="运行数量")


class CostRollupResponse(BaseModel):
    window: Literal["24h", "7d", "30d", "all"] = Field(description="时间窗口")
    group_by: Literal["agent", "provider", "specialist", "adapter"] = Field(description="聚合维度")
    generated_at: datetime = Field(description="生成时间")
    total_cost_usd: float = Field(description="总成本 USD")
    total_tokens: int = Field(description="总 Token")
    total_runs: int = Field(description="总运行数")
    average_run_cost_usd: float = Field(description="平均运行成本")
    breakdown: list[CostRollupBreakdownItem] = Field(description="Top breakdown")
    series: list[CostRollupSeriesPoint] = Field(description="时间序列")
    pricing_statuses: list[dict] = Field(
        default_factory=list,
        description="模型价格来源状态和企业门禁阻塞详情",
    )


class AlertRuleCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128, description="规则名称")
    metric: str = Field(description="指标名")
    comparator: Literal[">", "<", ">=", "<=", "=="] = Field(description="比较符")
    threshold: float = Field(ge=0, description="阈值")
    window_seconds: int = Field(default=300, ge=60, le=86400, description="窗口秒数")
    enabled: bool = Field(default=True, description="是否启用")
    severity: Literal["info", "warning", "critical"] = Field(
        default="warning",
        description="严重级别",
    )
    notification_channels_json: list[str] = Field(
        default_factory=lambda: ["in_app"],
        description="通知通道",
    )


class AlertRuleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128, description="规则名称")
    metric: str | None = Field(default=None, description="指标名")
    comparator: Literal[">", "<", ">=", "<=", "=="] | None = Field(
        default=None,
        description="比较符",
    )
    threshold: float | None = Field(default=None, ge=0, description="阈值")
    window_seconds: int | None = Field(default=None, ge=60, le=86400, description="窗口秒数")
    enabled: bool | None = Field(default=None, description="是否启用")
    severity: Literal["info", "warning", "critical"] | None = Field(
        default=None,
        description="严重级别",
    )
    notification_channels_json: list[str] | None = Field(default=None, description="通知通道")


class AlertRuleResponse(BaseModel):
    id: str = Field(description="规则 ID")
    organization_id: str | None = Field(default=None, description="组织 ID")
    name: str = Field(description="规则名称")
    metric: str = Field(description="指标名")
    comparator: str = Field(description="比较符")
    threshold: float = Field(description="阈值")
    window_seconds: int = Field(description="窗口秒数")
    enabled: bool = Field(description="是否启用")
    severity: str = Field(description="严重级别")
    notification_channels_json: list[str] = Field(description="通知通道")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")

    model_config = ConfigDict(from_attributes=True)


class AlertRulePage(BaseModel):
    items: list[AlertRuleResponse] = Field(description="告警规则")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class AlertEventResponse(BaseModel):
    id: str = Field(description="告警事件 ID")
    organization_id: str | None = Field(default=None, description="组织 ID")
    rule_id: str = Field(description="规则 ID")
    rule_name: str = Field(description="规则名称")
    metric: str = Field(description="指标名")
    comparator: str = Field(description="比较符")
    threshold: float = Field(description="阈值")
    observed_value: float = Field(description="观测值")
    severity: str = Field(description="严重级别")
    status: str = Field(description="状态")
    message: str = Field(description="消息")
    context_json: dict = Field(description="上下文")
    triggered_at: datetime = Field(description="触发时间")
    resolved_at: datetime | None = Field(default=None, description="恢复时间")

    model_config = ConfigDict(from_attributes=True)


class AlertEventPage(BaseModel):
    items: list[AlertEventResponse] = Field(description="告警事件")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class NotificationChannelCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128, description="通道名称")
    kind: Literal["slack", "email", "webhook"] = Field(description="通道类型")
    config_json: dict = Field(default_factory=dict, description="通道配置")
    verified: bool = Field(default=False, description="是否已验证")


class NotificationChannelUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128, description="通道名称")
    kind: Literal["slack", "email", "webhook"] | None = Field(default=None, description="通道类型")
    config_json: dict | None = Field(default=None, description="通道配置")
    verified: bool | None = Field(default=None, description="是否已验证")


class NotificationChannelResponse(BaseModel):
    id: str = Field(description="通道 ID")
    organization_id: str = Field(description="组织 ID")
    name: str = Field(description="通道名称")
    kind: str = Field(description="通道类型")
    config_json: dict = Field(description="脱敏后的通道配置")
    verified: bool = Field(description="是否已验证")
    created_by: str | None = Field(default=None, description="创建者")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")

    model_config = ConfigDict(from_attributes=True)


class NotificationChannelPage(BaseModel):
    items: list[NotificationChannelResponse] = Field(description="通知通道")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class OnboardingStateResponse(BaseModel):
    id: str = Field(description="状态 ID")
    organization_id: str = Field(description="组织 ID")
    user_id: str = Field(description="用户 ID")
    current_step: int = Field(description="当前步骤")
    completed: bool = Field(description="是否完成")
    skipped: bool = Field(description="是否跳过")
    demo_loaded: bool = Field(description="Demo 是否已加载")
    provider_json: dict = Field(description="供应商配置摘要")
    agent_id: str | None = Field(default=None, description="首个 Agent ID")
    demo_task_id: str | None = Field(default=None, description="Demo Run ID")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")
    completed_at: datetime | None = Field(default=None, description="完成时间")

    model_config = ConfigDict(from_attributes=True)


class OnboardingStateUpdateRequest(BaseModel):
    current_step: int | None = Field(default=None, ge=1, le=4, description="当前步骤")
    skipped: bool | None = Field(default=None, description="是否跳过")
    provider_json: dict | None = Field(default=None, description="供应商配置摘要")
    agent_id: str | None = Field(default=None, description="首个 Agent ID")
    demo_task_id: str | None = Field(default=None, description="Demo Run ID")


class OnboardingCompleteRequest(BaseModel):
    agent_id: str | None = Field(default=None, description="首个 Agent ID")
    demo_task_id: str | None = Field(default=None, description="Demo Run ID")


class OnboardingStatusResponse(BaseModel):
    """Response for GET /api/onboarding/status - First-run detection status."""

    is_first_run: bool = Field(description="是否首次部署（无活跃用户）")
    should_show_wizard: bool = Field(description="是否应该显示引导向导")
    is_completed: bool = Field(description="引导是否已完成")
    wizard_skipped: bool = Field(description="用户是否跳过了引导")
    redirect_to: str | None = Field(default=None, description="应该重定向到的 URL")
    completed_at: datetime | None = Field(default=None, description="完成时间")


class ValidationCheckResult(BaseModel):
    """Single validation check result."""

    check: str = Field(description="Check name")
    status: Literal["pass", "warn", "fail"] = Field(description="Check status")
    message: str = Field(description="Human-readable message")
    details: dict | None = Field(default=None, description="Additional details")


class ValidationSummary(BaseModel):
    """Summary of validation results."""

    total: int = Field(description="Total number of checks")
    pass_: int = Field(alias="pass", description="Number of passed checks")
    warn: int = Field(description="Number of warnings")
    fail: int = Field(description="Number of failed checks")
    status: Literal["pass", "warn", "fail"] = Field(description="Overall status")


class ValidationResponse(BaseModel):
    """Response for validation endpoints (Story 2.1 & 2.2)."""

    checks: list[ValidationCheckResult] = Field(description="Validation check results")
    summary: ValidationSummary = Field(description="Summary statistics")


class WizardStateResponse(BaseModel):
    """Response for Story 1.2: Wizard state persistence."""

    user_id: str = Field(description="用户 ID")
    current_step: int = Field(ge=0, le=7, description="当前步骤 (0-7)")
    completed_steps: list[int] = Field(description="已完成步骤列表")
    is_completed: bool = Field(description="向导是否完成")
    completed_at: datetime | None = Field(default=None, description="完成时间")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")


class WizardTransitionRequest(BaseModel):
    """Request to transition to a specific wizard step."""

    step: int = Field(ge=0, le=7, description="目标步骤 (0-7)")


class WizardCompleteStepRequest(BaseModel):
    """Request to mark a step as completed."""

    step: int = Field(ge=1, le=7, description="要完成的步骤 (1-7)")


class DemoLoadResponse(BaseModel):
    status: Literal["loaded", "already_loaded", "reset"] = Field(description="Demo 操作状态")
    agent_ids: list[str] = Field(default_factory=list, description="Demo Agent ID")
    knowledge_source_ids: list[str] = Field(default_factory=list, description="Demo 知识源 ID")
    dataset_id: str | None = Field(default=None, description="Demo Eval Dataset ID")
    task_id: str | None = Field(default=None, description="Demo Run ID")
    specialist_ids: list[str] = Field(default_factory=list, description="Demo 专家 ID")
    demo_loaded: bool = Field(description="Demo 是否已加载")


class DemoResetRequest(BaseModel):
    confirm_token: str = Field(description="确认 token，必须是 reset-demo-data")


class FrontendErrorCreateRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048, description="前端 URL")
    error_message: str = Field(min_length=1, max_length=4000, description="错误信息")
    stack: str | None = Field(default=None, max_length=12000, description="错误堆栈")
    browser: str = Field(default="", max_length=1000, description="浏览器 UA")
    metadata_json: dict = Field(default_factory=dict, description="附加元数据")


class FrontendErrorResponse(BaseModel):
    id: str = Field(description="错误 ID")
    organization_id: str = Field(description="组织 ID")
    user_id: str = Field(description="用户 ID")
    url: str = Field(description="前端 URL")
    error_message: str = Field(description="错误信息")
    stack: str | None = Field(default=None, description="错误堆栈")
    browser: str = Field(description="浏览器 UA")
    metadata_json: dict = Field(description="附加元数据")
    created_at: datetime = Field(description="创建时间")

    model_config = ConfigDict(from_attributes=True)


class FrontendErrorPage(BaseModel):
    items: list[FrontendErrorResponse] = Field(description="前端错误")
    next_cursor: str | None = Field(default=None, description="下一页游标")


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
    context_manifest_id: str | None = Field(default=None, description="Context manifest ID")
    capability_snapshot_json: dict = Field(default_factory=dict, description="Capability snapshot")
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


class ModelPricingSourceItem(BaseModel):
    provider: str = Field(description="供应商")
    model: str = Field(description="模型")
    mapped_provider: str = Field(description="内部供应商映射")
    mapped_model: str = Field(description="内部模型映射")
    display_name: str = Field(description="展示名称")
    official_url: str = Field(description="官方来源 URL")
    retrieved_at: datetime = Field(description="来源抓取时间")
    unit: str = Field(description="计价单位")
    currency: str = Field(description="币种")
    input_per_1m: str | None = Field(default=None, description="每 1M 输入 token 价格")
    cached_input_per_1m: str | None = Field(default=None, description="每 1M 缓存输入 token 价格")
    output_per_1m: str | None = Field(default=None, description="每 1M 输出 token 价格")
    prompt_per_1k_usd: str | None = Field(default=None, description="每 1K 输入 token USD 价格")
    cache_prompt_per_1k_usd: str | None = Field(
        default=None,
        description="每 1K 缓存输入 token USD 价格",
    )
    completion_per_1k_usd: str | None = Field(default=None, description="每 1K 输出 token USD 价格")
    verification_status: str = Field(description="价格来源校验状态")
    valid_from: datetime | None = Field(default=None, description="有效开始时间")
    valid_until: datetime | None = Field(default=None, description="有效结束时间")
    region: str | None = Field(default=None, description="区域")
    token_tier: str | None = Field(default=None, description="token 档位")
    mode: str | None = Field(default=None, description="计费模式")
    context_window_tokens: int | None = Field(default=None, description="上下文窗口")
    max_output_tokens: int | None = Field(default=None, description="最大输出 token")
    source_hash: str = Field(description="来源摘录 hash")
    source_excerpt: str = Field(description="来源摘录")
    notes: str | None = Field(default=None, description="备注")
    blocks_usd_rollup: bool = Field(description="是否阻塞 USD 成本汇总")


class ModelPricingSourcePage(BaseModel):
    schema_version: str = Field(description="来源契约版本")
    retrieved_at: datetime = Field(description="来源文档抓取时间")
    parser_version: str = Field(description="来源解析版本")
    items: list[ModelPricingSourceItem] = Field(description="模型价格来源列表")
    blocking_statuses: list[str] = Field(description="阻塞企业成本门禁的状态")


class ToolCallResponse(BaseModel):
    id: str = Field(description="工具调用 ID")
    task_id: str = Field(description="任务 ID")
    agent_run_id: str | None = Field(default=None, description="Agent 运行 ID")
    trace_id: str | None = Field(default=None, description="Trace ID")
    tool_name: str = Field(description="工具名称")
    status: str = Field(description="调用状态")
    risk_level: str = Field(description="风险等级")
    capability_id: str | None = Field(default=None, description="Capability ID")
    capability_version_id: str | None = Field(default=None, description="Capability version ID")
    capability_type: str | None = Field(default=None, description="Capability type")
    capability_content_sha256: str | None = Field(
        default=None, description="Capability content hash"
    )
    capability_config_sha256: str | None = Field(default=None, description="Capability config hash")
    capability_schema_version: int | None = Field(
        default=None, description="Capability schema version"
    )
    capability_snapshot_json: dict = Field(default_factory=dict, description="Capability snapshot")
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


class AgentLocalToolEventRequest(BaseModel):
    tool_name: str = Field(min_length=1, description="本地执行的工具名称")
    input_json: dict = Field(default_factory=dict, description="工具输入")
    output_json: dict = Field(default_factory=dict, description="工具输出")
    interaction_mode: Literal["chat", "plan", "act"] = Field(
        default="chat",
        description="CLI 工作流模式",
    )
    act_intent: dict | None = Field(default=None, description="act 工作流意图元数据")
    status: Literal["SUCCESS", "FAILED", "TIMEOUT", "DENIED"] = Field(
        default="SUCCESS",
        description="本地执行结果状态",
    )
    risk_level: Literal["low", "medium", "high", "critical", "unknown"] = Field(
        default="high",
        description="CLI 侧权限引擎判定的风险等级",
    )
    requires_sandbox: bool = Field(
        default=False,
        description="本次工具是否要求沙箱；host target 的本地执行应为 false",
    )
    sandbox_id: str | None = Field(default=None, description="关联沙箱 ID")
    duration_ms: int = Field(default=0, ge=0, description="本地执行耗时")
    error_message: str | None = Field(default=None, description="错误信息")
    execution_target: Literal["host", "sandbox"] = Field(
        default="host",
        description="执行位置",
    )
    permission_mode: Literal["confirm", "auto-edit", "full-auto"] = Field(
        default="confirm",
        description="CLI 权限模式",
    )
    local_session_id: str | None = Field(default=None, description="hao 本地会话 ID")
    cwd: str | None = Field(default=None, description="hao 本地工作区")


class AgentLocalToolEventResponse(BaseModel):
    tool_call: ToolCallResponse = Field(description="写入的工具调用审计记录")
    event_sequence: int = Field(description="结果事件序号")


class LocalAgentPairingCreateRequest(BaseModel):
    agent_id: str = Field(default="default", min_length=1, description="目标 Agent ID")
    ttl_minutes: int = Field(default=10, ge=1, le=60, description="配对令牌有效分钟数")
    scope: dict = Field(default_factory=dict, description="本地 Agent 授权范围")


class LocalAgentPairingResponse(BaseModel):
    id: str = Field(description="配对记录 ID")
    agent_id: str = Field(description="目标 Agent ID")
    pair_code: str = Field(description="短配对码，仅用于 UX")
    pair_token: str | None = Field(default=None, description="明文 token，仅创建时返回一次")
    command: str | None = Field(default=None, description="可复制连接命令，仅创建时返回")
    status: str = Field(description="配对状态")
    expires_at: datetime = Field(description="过期时间")
    created_at: datetime = Field(description="创建时间")

    model_config = ConfigDict(from_attributes=True)


class LocalAgentRecoveryCommandResponse(BaseModel):
    connection_id: str = Field(description="本地 Agent 连接 ID")
    adapter_kind: str = Field(description="本地 Agent 类型")
    command: str = Field(description="可复制的 bridge 重启命令")
    state_home: str = Field(description="命令默认读取的 HAO_HOME")
    status: str = Field(description="当前连接状态")


class LocalAgentConnectionRegisterRequest(BaseModel):
    pair_token: str = Field(min_length=16, description="一次性配对 token")
    pair_code: str = Field(min_length=4, max_length=16, description="短配对码")
    adapter_kind: Literal["fake", "hao", "codex", "claude_code"] = Field(
        description="本地 Agent 类型",
    )
    display_name: str | None = Field(default=None, max_length=120, description="显示名称")
    protocol_version: str = Field(default="local-agent-v1", description="bridge 协议版本")
    bridge_version: str = Field(default="", description="bridge 版本")
    workspace_root: str | None = Field(default=None, max_length=512, description="工作目录")
    capabilities: dict = Field(default_factory=dict, description="能力声明")
    risk_capabilities: list[str] = Field(default_factory=list, description="高风险能力")
    metadata: dict = Field(default_factory=dict, description="附加元数据")


class LocalAgentConnectionRegisterResponse(BaseModel):
    connection: "LocalAgentConnectionResponse" = Field(description="连接投影")
    device_token: str = Field(description="设备凭证，仅注册时返回一次")


class LocalAgentConnectionUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120, description="连接显示名称")


class LocalAgentConnectionResponse(BaseModel):
    id: str = Field(description="连接 ID")
    agent_id: str = Field(description="目标 Agent ID")
    owner_user_id: str = Field(description="设备 owner")
    pairing_token_id: str | None = Field(default=None, description="来源配对记录 ID")
    onboarding_confirmed: bool = Field(default=True, description="是否已由用户确认接入")
    display_name: str = Field(description="显示名称")
    adapter_kind: str = Field(description="本地 Agent 类型")
    protocol_version: str = Field(description="协议版本")
    bridge_version: str = Field(description="bridge 版本")
    status: str = Field(description="连接状态")
    workspace_root: str | None = Field(default=None, description="脱敏工作目录")
    capabilities_json: dict = Field(description="能力声明")
    risk_capabilities_json: list[str] = Field(description="高风险能力")
    last_seen_at: datetime | None = Field(default=None, description="最后心跳")
    revoked_at: datetime | None = Field(default=None, description="撤销时间")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")

    model_config = ConfigDict(from_attributes=True)


class LocalAgentConnectionPage(BaseModel):
    items: list[LocalAgentConnectionResponse] = Field(description="本地 Agent 连接")


class LocalAgentHeartbeatRequest(BaseModel):
    protocol_version: str = Field(default="local-agent-v1", description="协议版本")
    bridge_version: str = Field(default="", description="bridge 版本")
    status: Literal["online", "busy"] = Field(default="online", description="bridge 状态")
    capabilities: dict | None = Field(default=None, description="能力声明更新")


class LocalAgentHeartbeatResponse(BaseModel):
    connection: LocalAgentConnectionResponse = Field(description="连接投影")


class LocalAgentConversationBindRequest(BaseModel):
    agent_session_id: str | None = Field(default=None, description="已有 AgentSession ID")
    title: str | None = Field(default=None, description="新会话标题")
    adapter_session_id: str | None = Field(default=None, description="本地适配器会话 ID")
    resume_mode: Literal["native_resume", "context_replay_new_session"] = Field(
        default="native_resume",
        description="恢复模式",
    )


class LocalAgentConversationBindingResponse(BaseModel):
    id: str = Field(description="绑定 ID")
    connection_id: str = Field(description="连接 ID")
    agent_id: str = Field(description="Agent ID")
    agent_session_id: str = Field(description="AgentSession ID")
    adapter_session_id: str | None = Field(default=None, description="本地适配器会话 ID")
    resume_mode: str = Field(description="恢复模式")
    status: str = Field(description="绑定状态")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")

    model_config = ConfigDict(from_attributes=True)


class LocalAgentConversationBindingPage(BaseModel):
    items: list[LocalAgentConversationBindingResponse] = Field(description="本地 Agent 会话绑定")


class LocalAgentSendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=120_000, description="用户消息")
    client_message_id: str = Field(min_length=1, max_length=160, description="客户端幂等 ID")
    resume_of_client_message_id: str | None = Field(
        default=None,
        max_length=160,
        description="续发来源客户端消息 ID，用于前端水合折叠同一用户轮次",
    )
    resume_of_user_message_id: str | None = Field(
        default=None,
        max_length=200,
        description="续发来源 Workspace user 节点 ID，用于审计和前端恢复",
    )
    workspace_context_provided: bool = Field(
        default=False,
        description="前端是否显式提供了当前 Workspace 上下文；为空时也禁止回放旧 session",
    )
    workspace_mode: Literal["chat", "markdown_plan", "plan", "goal", "cli_agent"] = Field(
        default="chat",
        description="Workspace 输入模式",
    )
    model_provider: str | None = Field(default=None, description="本次请求选择的模型供应商")
    model_name: str | None = Field(default=None, description="本次请求选择的模型名称")
    messages: list[ConversationNode] = Field(default_factory=list, description="当前分支消息")
    active_leaf_id: str | None = Field(default=None, description="当前活动叶子节点")
    active_branch_id: str | None = Field(default=None, description="前端当前分支 ID")
    pinned_node_ids: list[str] = Field(default_factory=list, description="强制注入上下文节点")
    context_window_turns: int = Field(default=8, ge=1, le=50, description="最近上下文轮数")
    tool_mentions: list[ToolMention] = Field(default_factory=list, description="结构化工具 mention")
    attachment_names: list[str] = Field(default_factory=list, description="前端选择的附件文件名")
    attachments: list[AttachmentPayload] = Field(
        default_factory=list,
        description="前端读取后的附件内容摘要",
    )
    context_max_tokens: int | None = Field(
        default=None,
        ge=1,
        description="UI-side context window budget; backend recounts before model calls",
    )
    compressed_context: CompressedContext | None = Field(
        default=None,
        description="语义压缩后的上下文摘要",
    )

    @field_validator("workspace_mode", mode="before")
    @classmethod
    def normalize_workspace_mode_field(cls, value: str) -> str:
        return normalize_workspace_mode(value)


class LocalAgentSendMessageResponse(BaseModel):
    bridge_task_id: str = Field(description="bridge 任务 ID")
    run_id: str = Field(description="关联 Workspace Run ID")
    agent_session_id: str = Field(description="AgentSession ID")
    user_message_id: str = Field(description="用户消息 ID")
    status: str = Field(description="任务状态")


class LocalAgentBridgeTaskResponse(BaseModel):
    id: str = Field(description="bridge 任务 ID")
    connection_id: str = Field(description="连接 ID")
    binding_id: str = Field(description="会话绑定 ID")
    agent_session_id: str = Field(description="AgentSession ID")
    run_id: str = Field(description="Workspace Run ID")
    client_message_id: str = Field(description="客户端幂等 ID")
    status: str = Field(description="任务状态")
    payload: dict = Field(description="bridge 执行载荷")


class LocalAgentBridgeTaskPage(BaseModel):
    items: list[LocalAgentBridgeTaskResponse] = Field(description="待执行 bridge 任务")


class LocalAgentBindingTaskResponse(BaseModel):
    id: str = Field(description="bridge 任务 ID")
    connection_id: str = Field(description="连接 ID")
    binding_id: str = Field(description="会话绑定 ID")
    agent_session_id: str = Field(description="AgentSession ID")
    run_id: str = Field(description="Workspace Run ID")
    user_message_id: str = Field(description="用户消息 ID")
    client_message_id: str = Field(description="客户端幂等 ID")
    status: str = Field(description="任务状态")
    error_message: str | None = Field(default=None, description="失败原因")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")


class LocalAgentBindingTaskPage(BaseModel):
    items: list[LocalAgentBindingTaskResponse] = Field(description="本地 Agent 会话未完成任务")


class LocalAgentBridgeAckRequest(BaseModel):
    status: Literal["leased", "running", "failed"] = Field(description="ack 状态")
    error_message: str | None = Field(default=None, description="错误信息")


class LocalAgentBridgeEventRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=160, description="bridge 全局事件 ID")
    bridge_task_id: str = Field(min_length=1, description="bridge 任务 ID")
    sequence: int | None = Field(default=None, ge=0, description="bridge 侧序号")
    event_type: Literal[
        "adapter_started",
        "assistant_delta",
        "assistant_done",
        "assistant_error",
        "adapter_heartbeat",
        "tool_result",
    ] = Field(description="事件类型")
    content: str | None = Field(default=None, max_length=120_000, description="输出内容")
    tool_name: str | None = Field(default=None, max_length=160, description="工具名称")
    input_json: dict = Field(default_factory=dict, description="工具输入")
    output_json: dict = Field(default_factory=dict, description="工具输出")
    status: str | None = Field(default=None, max_length=64, description="事件状态")
    risk_level: Literal["low", "medium", "high", "critical", "unknown"] = Field(
        default="unknown",
        description="工具风险等级",
    )
    duration_ms: int = Field(default=0, ge=0, description="执行耗时")
    error_message: str | None = Field(default=None, max_length=4000, description="错误信息")
    metadata: dict = Field(default_factory=dict, description="附加元数据")


class LocalAgentBridgeEventResponse(BaseModel):
    receipt_id: str = Field(description="事件收据 ID")
    duplicate: bool = Field(description="是否重复事件")
    event_sequence: int | None = Field(default=None, description="AgentEvent 序号")
    tool_call_id: str | None = Field(default=None, description="ToolCall ID")


class LocalAgentToolRequestCreateRequest(BaseModel):
    tool_request_id: str = Field(min_length=1, max_length=160, description="bridge 工具请求幂等 ID")
    bridge_task_id: str = Field(min_length=1, description="bridge 任务 ID")
    tool_name: str = Field(min_length=1, max_length=160, description="工具名称")
    input_json: dict = Field(default_factory=dict, description="工具输入")
    execution_target: Literal["host", "sandbox"] = Field(default="host", description="执行目标")
    risk_level: Literal["low", "medium", "high", "critical", "unknown"] = Field(
        default="unknown",
        description="bridge 自报风险，仅作遥测",
    )
    permission_mode: Literal["confirm", "auto-edit", "full-auto"] = Field(
        default="confirm",
        description="bridge 自报权限模式，仅作遥测",
    )
    cwd: str | None = Field(default=None, max_length=512, description="bridge 工作目录")
    target_paths: list[str] = Field(default_factory=list, description="目标路径遥测")
    requires_network: bool = Field(default=False, description="bridge 自报是否需要网络")
    requires_secret_read: bool = Field(default=False, description="bridge 自报是否读取 secret")
    pending_change_preview: dict | None = Field(default=None, description="diff-first 变更预览")
    metadata: dict = Field(default_factory=dict, description="附加元数据")


class LocalAgentToolDecisionResponse(BaseModel):
    tool_request_id: str = Field(description="bridge 工具请求 ID")
    bridge_task_id: str = Field(description="bridge 任务 ID")
    tool_call_id: str = Field(description="ToolCall ID")
    approval_id: str | None = Field(default=None, description="ToolApproval ID")
    decision: Literal[
        "allowed",
        "approval_required",
        "approved",
        "denied",
        "running",
        "succeeded",
        "failed",
        "cancelled",
        "expired",
    ] = Field(description="服务端决策/状态")
    status: str = Field(description="本地工具请求状态")
    executable: bool = Field(description="bridge 当前是否可执行")
    server_execution: bool = Field(default=False, description="是否由服务器执行")
    tool_name: str = Field(description="工具名称")
    input_json: dict = Field(default_factory=dict, description="可执行输入")
    reason: str = Field(default="", description="原因")
    decision_json: dict = Field(default_factory=dict, description="决策载荷")
    expires_at: datetime | None = Field(default=None, description="决策过期时间")


class LocalAgentPendingToolRequestPage(BaseModel):
    items: list[LocalAgentToolDecisionResponse] = Field(
        description="Bridge 可恢复的未决本地工具请求"
    )


class LocalAgentPendingChangeRefreshRequest(BaseModel):
    input_json: dict = Field(default_factory=dict, description="已批准的可执行输入")
    target_paths: list[str] = Field(default_factory=list, description="批准后的目标路径")
    pending_change_preview: dict = Field(description="批准后重建的 pending change 预览")


class LocalAgentToolResultRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=160, description="结果幂等事件 ID")
    status: Literal["SUCCESS", "FAILED", "TIMEOUT", "DENIED", "CANCELLED"] = Field(
        default="SUCCESS",
        description="执行结果",
    )
    output_json: dict = Field(default_factory=dict, description="工具输出")
    duration_ms: int = Field(default=0, ge=0, description="耗时")
    error_message: str | None = Field(default=None, max_length=4000, description="错误信息")
    command_id: str | None = Field(default=None, max_length=160, description="本地命令 ID")
    change_id: str | None = Field(default=None, max_length=160, description="pending change ID")
    diff_sha256: str | None = Field(default=None, max_length=64, description="提交 diff hash")
    metadata: dict = Field(default_factory=dict, description="附加元数据")


class LocalAgentCommandEventRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=160, description="命令事件幂等 ID")
    tool_request_id: str = Field(min_length=1, max_length=160, description="父工具请求 ID")
    event_type: Literal["started", "output", "finished", "timeout", "cancelled"] = Field(
        description="命令生命周期事件",
    )
    tool_name: str | None = Field(default=None, max_length=160, description="工具名称")
    command: str | None = Field(default=None, max_length=4000, description="命令文本")
    stdout: str | None = Field(default=None, max_length=120_000, description="stdout 片段")
    stderr: str | None = Field(default=None, max_length=120_000, description="stderr 片段")
    status: str | None = Field(default=None, max_length=64, description="命令状态")
    exit_code: int | None = Field(default=None, description="退出码")
    duration_ms: int = Field(default=0, ge=0, description="耗时")
    retry_of_command_id: str | None = Field(default=None, max_length=160, description="重试来源")
    error_message: str | None = Field(default=None, max_length=4000, description="错误信息")
    metadata: dict = Field(default_factory=dict, description="附加元数据")


class LocalAgentCommandResponse(BaseModel):
    command_id: str = Field(description="bridge 命令 ID")
    tool_request_id: str = Field(description="父工具请求 ID")
    status: str = Field(description="命令状态")
    cancel_requested: bool = Field(default=False, description="是否请求取消")


class LocalAgentCommandCancelAckRequest(BaseModel):
    status: Literal["cancelled", "failed"] = Field(default="cancelled", description="取消确认状态")
    error_message: str | None = Field(default=None, max_length=4000, description="错误信息")


class AdapterMetadataResponse(BaseModel):
    slug: str = Field(description="Adapter slug")
    server_label: str = Field(description="Adapter server label")
    method: str = Field(description="Adapter method")
    description: str = Field(description="Adapter description")
    version: str = Field(description="Adapter version")
    adapter_module: str = Field(description="Python module path")
    adapter_sha256: str = Field(description="Adapter source SHA256")
    input_schema_sha256: str = Field(description="Input schema SHA256")
    output_schema_sha256: str = Field(description="Output schema SHA256")
    input_schema: dict = Field(description="Input JSON schema")
    output_schema: dict = Field(description="Output JSON schema")
    requires_secret: bool = Field(description="Whether execution requires a secret")
    risk_level: str = Field(description="Risk level")


class AdapterMetadataPage(BaseModel):
    items: list[AdapterMetadataResponse] = Field(description="Registered adapters")


class AdapterHealthResponse(BaseModel):
    slug: str = Field(description="Adapter slug")
    ok: bool = Field(description="Health status")
    latency_ms: int = Field(description="Probe latency")
    message: str = Field(description="Probe message")
    sample: dict = Field(default_factory=dict, description="Bounded probe sample")
    last_checked_at: datetime = Field(description="Probe timestamp")


class MCPDiscoveredToolResponse(BaseModel):
    name: str = Field(description="MCP tool name")
    slug: str = Field(description="Harness adapter/capability slug")
    description: str = Field(default="", description="MCP tool description")
    input_schema: dict = Field(default_factory=dict, description="MCP input schema")
    annotations: dict = Field(default_factory=dict, description="MCP tool annotations")
    risk_level: str = Field(default="low", description="Derived Harness risk level")


class MCPServerResponse(BaseModel):
    agent_id: str = Field(description="Agent ID")
    tool_name: str = Field(description="Installed MCP server capability tool name")
    server_slug: str = Field(description="Normalized MCP server slug")
    transport: str = Field(description="Runtime transport")
    configured: bool = Field(description="Whether runtime fields are configured")
    discovery_status: str = Field(description="idle, ready, or failed")
    discovery_message: str = Field(default="", description="Last discovery message")
    discovered_tools: list[MCPDiscoveredToolResponse] = Field(default_factory=list)
    resources_count: int = Field(default=0, description="Discovered resource count")
    child_tool_count: int = Field(default=0, description="Registered child tool count")


class MCPServerPage(BaseModel):
    items: list[MCPServerResponse] = Field(default_factory=list, description="MCP servers")


class MCPServerDiscoverResponse(MCPServerResponse):
    registered_runtime_configs: list[dict] = Field(
        default_factory=list,
        description="Runtime config records created for discovered child tools",
    )


class CapabilityAdminValidationRequest(BaseModel):
    content: dict = Field(default_factory=dict, description="Capability content")
    config: dict = Field(default_factory=dict, description="Capability config")


class CapabilityAdminValidationResponse(BaseModel):
    status: str = Field(description="Validation status")
    schema_version: int = Field(description="Capability schema version")
    content_sha256: str = Field(description="Redacted content hash")
    config_sha256: str = Field(description="Redacted config hash")
    errors: list[str] = Field(default_factory=list, description="Validation errors")
    warnings: list[str] = Field(default_factory=list, description="Validation warnings")
    risk_score: int = Field(default=0, description="Capability package risk score")
    approval_required: bool = Field(
        default=False,
        description="Whether activation requires approval",
    )
    validation_mode: str = Field(
        default="manifest_only_no_execution",
        description="Validation mode",
    )
    source_policy: dict = Field(default_factory=dict, description="Public source policy result")
    manifest_summary: dict = Field(default_factory=dict, description="Package manifest summary")
    redacted_payload: dict = Field(description="Redacted validation payload")
    validation: dict = Field(default_factory=dict, description="Package manifest validation")


class CapabilityPackageStageRequest(BaseModel):
    manifest: dict = Field(description="Capability package manifest")
    content: dict = Field(default_factory=dict, description="Optional manifest-adjacent content")


class CapabilityPublicPackageStageRequest(CapabilityPackageStageRequest):
    source_kind: Literal["public_url", "public_git"] = Field(description="Public source type")
    source_uri: str = Field(min_length=1, description="Public source URL")
    pinned_ref: str = Field(min_length=1, description="Digest, commit, or archive identity")


class CapabilityPackageApproveRequest(BaseModel):
    reason: str = Field(default="", description="Approval reason")


class CapabilityPackageAttachRequest(BaseModel):
    agent_id: str = Field(min_length=1, description="Agent ID")
    enabled: bool = Field(default=True, description="Enable attachment for future runs")
    priority: int = Field(default=100, description="Attachment priority")


class CapabilityPackageRollbackRequest(BaseModel):
    capability_version_id: str = Field(min_length=1, description="Target immutable version ID")
    reason: str = Field(default="", description="Rollback reason")


class CapabilityAttachmentUpdateRequest(BaseModel):
    enabled: bool = Field(description="Enable or disable attachment for future runs")


class CapabilityPackageResponse(BaseModel):
    id: str = Field(description="Package ID")
    organization_id: str | None = Field(default=None, description="Organization ID")
    package_key: str = Field(description="Package key")
    package_type: str = Field(description="Package type")
    source_kind: str = Field(description="Source kind")
    source_uri: str | None = Field(default=None, description="Source URI")
    source_sha256: str = Field(description="Staged source hash")
    pinned_ref: str | None = Field(default=None, description="Pinned source ref")
    status: str = Field(description="Lifecycle status")
    risk_level: str = Field(description="Risk level")
    manifest_json: dict = Field(description="Redacted manifest")
    content_json: dict = Field(default_factory=dict, description="Redacted package content")
    validation_json: dict = Field(description="Validation evidence")
    provenance_json: dict = Field(description="Provenance/SBOM/signature evidence")
    audit_json: dict = Field(description="Audit evidence")
    capability_id: str | None = Field(default=None, description="Installed capability ID")
    capability_version_id: str | None = Field(default=None, description="Installed version ID")
    created_at: datetime = Field(description="Created time")
    updated_at: datetime = Field(description="Updated time")
    approved_at: datetime | None = Field(default=None, description="Approved time")

    model_config = ConfigDict(from_attributes=True)


class CapabilityPackagePage(BaseModel):
    items: list[CapabilityPackageResponse] = Field(description="Capability packages")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class CapabilityPackageAttachResponse(BaseModel):
    attachment_id: str = Field(description="Attachment ID")
    agent_id: str = Field(description="Agent ID")
    capability_id: str = Field(description="Capability ID")
    capability_version_id: str = Field(description="Capability version ID")
    enabled: bool = Field(description="Enabled")
    priority: int = Field(description="Priority")


class CapabilitySimpleInstallRequest(BaseModel):
    source_uri: str | None = Field(default=None, description="Package source URL when applicable")
    pinned_ref: str | None = Field(
        default=None,
        description="Optional digest, commit, or archive pin",
    )
    package_type: Literal[
        "agent_template",
        "skill_pack",
        "tool_definition",
        "mcp_server",
        "prompt_template",
        "knowledge_connector",
        "context_optimizer",
        "langgraph_workflow",
    ] = Field(
        default="skill_pack",
        description="Package type hint",
    )
    display_name: str = Field(
        default="operator-installed-capability",
        min_length=1,
        description="Display name",
    )
    description: str = Field(
        default="Installed from the simple capability facade",
        description="Description",
    )
    agent_id: str | None = Field(
        default=None,
        description="Optional Agent ID to attach after install",
    )
    permissions: list[str] = Field(default_factory=list, description="Declared package permissions")
    secret_refs: list[str] = Field(default_factory=list, description="Declared secret refs")
    manifest: dict | None = Field(default=None, description="Optional advanced manifest override")
    content: dict = Field(default_factory=dict, description="Optional package content")


class CapabilityMarketplacePreflightRequest(CapabilitySimpleInstallRequest):
    marketplace_source: str = Field(default="unknown", description="Marketplace source ID")
    marketplace_item_id: str = Field(default="", description="Marketplace item ID")


class CapabilitySimpleInstallResponse(BaseModel):
    package: CapabilityPackageResponse = Field(description="Package lifecycle record")
    validation_summary: dict = Field(description="Validation, risk, and source summary")
    ready_state: str = Field(description="ready, staged, invalid, or attached")
    next_step_label: str = Field(description="Recommended next UI action")
    staged_capability_id: str | None = Field(
        default=None,
        description="Public preflight staged package ID",
    )
    capability_id: str | None = Field(default=None, description="Installed capability ID")
    capability_version_id: str | None = Field(
        default=None,
        description="Installed capability version ID",
    )
    attachment: CapabilityPackageAttachResponse | None = Field(
        default=None,
        description="Attachment created by the simple facade when agent_id is supplied",
    )


class CapabilityTestInvocationRequest(BaseModel):
    agent_id: str = Field(min_length=1, description="Agent ID")
    tool_name: str = Field(min_length=1, description="Tool/capability name")
    input_json: dict = Field(default_factory=dict, description="Tool input")


class CapabilityRuntimeConfigUpdateRequest(BaseModel):
    agent_id: str = Field(min_length=1, description="Agent ID")
    tool_name: str = Field(min_length=1, description="Tool/capability name")
    transport: Literal["stdio", "http", "sse"] = Field(
        default="http",
        description="MCP runtime transport",
    )
    endpoint_url: str | None = Field(
        default=None,
        description="HTTP/SSE endpoint URL for remote MCP or provider API",
    )
    command: str | None = Field(default=None, description="stdio command")
    args: list[str] = Field(default_factory=list, description="stdio command arguments")
    secret_ref: str | None = Field(
        default=None,
        description="Server-side secret reference such as secret://mcp/brave/api-key",
    )
    secret_value: str | None = Field(
        default=None,
        description="One-time raw secret value stored server-side and never returned",
    )
    timeout_seconds: int | None = Field(
        default=None,
        ge=1,
        le=300,
        description="Runtime timeout override",
    )


class CapabilityRuntimeConfigResponse(BaseModel):
    agent_id: str = Field(description="Agent ID")
    tool_name: str = Field(description="Tool/capability name")
    tool_description: str = Field(default="", description="Tool description")
    source: str = Field(default="mcp", description="Tool source")
    capability_id: str = Field(description="Capability ID")
    capability_version_id: str = Field(description="Active capability version ID")
    capability_config_sha256: str = Field(description="Active config hash")
    attachment_id: str = Field(description="Agent attachment ID")
    attachment_enabled: bool = Field(description="Whether the attachment is enabled")
    configured: bool = Field(description="Whether required runtime fields are configured")
    missing_fields: list[str] = Field(default_factory=list, description="Missing fields")
    transport: str = Field(default="http", description="Runtime transport")
    endpoint_url: str | None = Field(default=None, description="HTTP/SSE endpoint URL")
    command: str | None = Field(default=None, description="stdio command")
    args: list[str] = Field(default_factory=list, description="stdio arguments")
    secret_ref: str | None = Field(default=None, description="Server-side secret reference")
    secret_configured: bool = Field(description="Whether secret material can be resolved")
    timeout_seconds: int = Field(description="Runtime timeout")
    config_json: dict = Field(description="Redacted runtime config snapshot")
    registry_visible: bool = Field(description="Whether the tool is visible in Agent registry")
    test_input_json: dict = Field(default_factory=dict, description="Suggested test input")


class CapabilityRuntimeConfigPage(BaseModel):
    items: list[CapabilityRuntimeConfigResponse] = Field(
        default_factory=list,
        description="Installed MCP runtime configuration records",
    )


class CapabilityMarketplaceItem(BaseModel):
    id: str = Field(description="Marketplace item ID")
    kind: Literal["mcp", "skill"] = Field(description="Marketplace item kind")
    source: str = Field(description="Marketplace source ID")
    source_label: str = Field(description="Marketplace source label")
    name: str = Field(description="Registry-qualified name")
    display_name: str = Field(description="Human-readable name")
    description: str = Field(description="Human-readable description")
    categories: list[str] = Field(default_factory=list, description="Marketplace categories")
    verified: bool = Field(default=False, description="Source verification flag")
    stars: float | None = Field(default=None, description="External stars when available")
    use_count: float | None = Field(default=None, description="Usage count when available")
    quality_score: float | None = Field(default=None, description="Quality score when available")
    latest_version: str | None = Field(default=None, description="Latest version when available")
    updated_at: str | None = Field(default=None, description="Source update timestamp")
    homepage_url: str = Field(default="", description="Homepage URL")
    repository_url: str = Field(default="", description="Repository URL")
    remote_url: str = Field(default="", description="Remote MCP URL when available")
    package_type: Literal[
        "agent_template",
        "skill_pack",
        "tool_definition",
        "mcp_server",
        "prompt_template",
        "knowledge_connector",
        "context_optimizer",
        "langgraph_workflow",
    ] = Field(description="Harness package type")
    install_mode: Literal[
        "attach_existing",
        "trusted_install",
        "public_preflight",
        "marketplace_preflight",
        "upload_install",
    ] = Field(description="Harness installation path")
    install_label: str = Field(description="Short action label")
    install_payload: dict = Field(description="Payload for the selected installation path")
    badges: list[str] = Field(default_factory=list, description="Display badges")
    risk_notes: list[str] = Field(default_factory=list, description="Risk and policy notes")
    metadata: dict = Field(default_factory=dict, description="Source-specific metadata")


class CapabilityMarketplaceSource(BaseModel):
    id: str = Field(description="Source ID")
    label: str = Field(description="Source label")
    status: str = Field(description="ready or unavailable")
    item_count: int = Field(description="Items returned by this source")
    url: str = Field(default="", description="Source URL")


class CapabilityMarketplaceError(BaseModel):
    source: str = Field(description="Source ID")
    message: str = Field(description="Error message")


class CapabilityMarketplaceResponse(BaseModel):
    kind: Literal["all", "mcp", "skill"] = Field(description="Returned marketplace kind")
    query: str = Field(description="Search query")
    items: list[CapabilityMarketplaceItem] = Field(description="Marketplace entries")
    sources: list[CapabilityMarketplaceSource] = Field(description="Source health")
    errors: list[CapabilityMarketplaceError] = Field(
        default_factory=list,
        description="Non-fatal source errors",
    )


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
    context_assembly: ContextAssemblyManifestResponse | None = Field(
        default=None,
        description="Backend context assembly evidence",
    )
    token_optimization: dict = Field(
        default_factory=dict,
        description="Run-level token budget, pruning, cache, and actual usage projection",
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
    capability_snapshot_json: dict = Field(default_factory=dict, description="Capability snapshot")
    tags_json: list[str] = Field(description="标签")
    created_at: datetime = Field(description="创建时间")

    model_config = ConfigDict(from_attributes=True)


class EvalCasePage(BaseModel):
    items: list[EvalCaseResponse] = Field(description="Case 列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class EvalRunCreateRequest(BaseModel):
    agent_id: str | None = Field(default=None, description="Agent 版本或 Agent ID")


class EvalHumanReviewRequest(BaseModel):
    verdict: Literal["approved", "rejected"] = Field(description="人工审核结论")
    notes: str | None = Field(default=None, description="人工审核备注")


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
    human_verdict: str | None = Field(default=None, description="人工审核结论")
    reviewer_id: str | None = Field(default=None, description="审核人 ID")
    reviewed_at: datetime | None = Field(default=None, description="审核时间")
    created_at: datetime = Field(description="创建时间")

    model_config = ConfigDict(from_attributes=True)


class EvalRunResponse(BaseModel):
    id: str = Field(description="Eval Run ID")
    dataset_id: str = Field(description="Dataset ID")
    organization_id: str | None = Field(default=None, description="组织 ID")
    agent_id: str | None = Field(default=None, description="Agent ID")
    status: str = Field(description="Eval Run 状态")
    capability_snapshot_json: dict = Field(default_factory=dict, description="Capability snapshot")
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


class EvalExperimentArmCreateRequest(BaseModel):
    name: str = Field(min_length=1, description="Experiment arm name")
    eval_run_id: str = Field(min_length=1, description="Linked Eval Run ID")
    arm_type: Literal["baseline", "candidate", "control"] = Field(
        default="candidate",
        description="Arm role",
    )
    status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"] | None = Field(
        default=None,
        description="Arm status",
    )
    capability_hashes_json: dict = Field(
        default_factory=dict,
        description="Capability hashes for this arm",
    )
    metadata_json: dict = Field(default_factory=dict, description="Arm metadata")
    error_message: str | None = Field(default=None, description="Arm-local failure message")


class EvalExperimentCreateRequest(BaseModel):
    name: str = Field(min_length=1, description="Experiment name")
    description: str = Field(default="", description="Experiment description")
    metadata_json: dict = Field(default_factory=dict, description="Experiment metadata")
    arms: list[EvalExperimentArmCreateRequest] = Field(
        min_length=1,
        description="Experiment arms",
    )


class EvalExperimentArmResponse(BaseModel):
    id: str = Field(description="Arm ID")
    experiment_id: str = Field(description="Experiment ID")
    dataset_id: str = Field(description="Dataset ID")
    eval_run_id: str = Field(description="Linked Eval Run ID")
    organization_id: str | None = Field(default=None, description="Organization ID")
    name: str = Field(description="Arm name")
    arm_type: str = Field(description="Arm role")
    status: str = Field(description="Arm status")
    capability_hashes_json: dict = Field(description="Capability hashes")
    metrics_json: dict = Field(description="Linked EvalRun metrics snapshot")
    error_message: str | None = Field(default=None, description="Arm-local failure")
    created_at: datetime = Field(description="Created time")

    model_config = ConfigDict(from_attributes=True)


class EvalExperimentResponse(BaseModel):
    id: str = Field(description="Experiment ID")
    dataset_id: str = Field(description="Dataset ID")
    organization_id: str | None = Field(default=None, description="Organization ID")
    name: str = Field(description="Experiment name")
    description: str = Field(description="Experiment description")
    status: str = Field(description="Experiment status")
    metadata_json: dict = Field(description="Experiment metadata")
    created_by: str | None = Field(default=None, description="Creator")
    created_at: datetime = Field(description="Created time")
    updated_at: datetime = Field(description="Updated time")
    eval_run_ids: list[str] = Field(description="Linked Eval Run IDs")
    arms: list[EvalExperimentArmResponse] = Field(default_factory=list, description="Arms")

    model_config = ConfigDict(from_attributes=True)


class EvalExperimentPage(BaseModel):
    items: list[EvalExperimentResponse] = Field(description="Eval experiment list")
    next_cursor: str | None = Field(default=None, description="Next cursor")


class SetBaselineRequest(BaseModel):
    eval_run_id: str = Field(description="要设为基线的 Eval Run ID")


class RegressionDelta(BaseModel):
    baseline_run_id: str = Field(description="基线 Eval Run ID")
    current_run_id: str = Field(description="当前 Eval Run ID")
    task_success_rate_delta: float = Field(description="任务成功率变化（绝对百分点）")
    tool_selection_accuracy_delta: float = Field(description="工具选择准确率变化")
    avg_latency_ms_delta: int = Field(description="平均延迟变化（毫秒）")
    grounding_pass_rate_delta: float = Field(description="Grounding pass rate 变化")
    citation_coverage_rate_delta: float = Field(description="Citation coverage rate 变化")
    unsupported_marker_rate_delta: float = Field(description="Unsupported marker rate 变化")
    fallback_mismatch_rate_delta: float = Field(description="Fallback mismatch rate 变化")
    forbidden_evidence_leak_rate_delta: float = Field(
        description="Forbidden evidence leak rate 变化"
    )
    required_evidence_miss_rate_delta: float = Field(description="Required evidence miss rate 变化")
    tool_contract_pass_rate_delta: float = Field(
        default=0.0, description="Tool contract pass rate 变化"
    )
    dialogue_contract_pass_rate_delta: float = Field(
        default=0.0, description="Dialogue contract pass rate 变化"
    )
    cost_contract_pass_rate_delta: float = Field(
        default=0.0, description="Cost contract pass rate 变化"
    )
    refusal_contract_pass_rate_delta: float = Field(
        default=0.0, description="Refusal contract pass rate 变化"
    )
    safety_contract_pass_rate_delta: float = Field(
        default=0.0, description="Safety contract pass rate 变化"
    )
    persona_contract_pass_rate_delta: float = Field(
        default=0.0, description="Persona contract pass rate 变化"
    )
    specialist_contract_pass_rate_delta: float = Field(
        default=0.0, description="Specialist contract pass rate 变化"
    )
    overrefusal_rate_delta: float = Field(default=0.0, description="过度拒答率变化")
    safety_violation_total_delta: int = Field(default=0, description="安全违规总数变化")
    role_drift_total_delta: int = Field(default=0, description="角色漂移总数变化")
    avg_cost_usd_delta: str = Field(default="0", description="平均成本（美元）变化")
    total_cost_usd_delta: str = Field(default="0", description="累计成本（美元）变化")
    total_prompt_tokens_delta: int = Field(default=0, description="累计 prompt token 变化")
    total_completion_tokens_delta: int = Field(default=0, description="累计 completion token 变化")
    newly_failing_case_ids: list[str] = Field(description="新增失败 Case ID")
    newly_passing_case_ids: list[str] = Field(description="新增通过 Case ID")
    newly_grounding_failing_case_ids: list[str] = Field(description="新增 grounding 失败 Case ID")
    newly_forbidden_leak_case_ids: list[str] = Field(description="新增 forbidden leak Case ID")
    is_regression: bool = Field(description="是否触发 Eval 回归 gate")
    total_cases: int = Field(description="总 Case 数")
    passed_cases: int = Field(description="通过 Case 数")
    failed_cases: int = Field(description="失败 Case 数")
    grounding_sample_count: int = Field(description="Grounding delta 样本数")
    low_sample_count: bool = Field(description="Grounding delta 是否样本过少")
    low_sample_caveat: str | None = Field(default=None, description="样本过少提示")


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


class ModelOfficialStatusResponse(BaseModel):
    provider: str = Field(description="供应商")
    label: str = Field(description="显示名称")
    status: str = Field(description="归一化状态")
    indicator: str = Field(description="官方 Statuspage indicator")
    description: str = Field(description="官方状态描述")
    page_url: str = Field(description="官方状态页 URL")
    api_url: str = Field(description="官方状态 API URL 或页面探测 URL")
    checked_at: datetime = Field(description="检查时间")
    updated_at: str | None = Field(default=None, description="官方页面更新时间")
    error_message: str | None = Field(default=None, description="错误信息")


class ModelOfficialStatusPage(BaseModel):
    items: list[ModelOfficialStatusResponse] = Field(description="官方模型服务状态列表")


class PolicySettingsResponse(BaseModel):
    risk_levels: list[dict] = Field(description="风险等级")
    approvals: dict = Field(description="审批规则")
    sandbox: dict = Field(description="沙箱规则")
    audit: dict = Field(description="审计规则")
    web_research: dict = Field(default_factory=dict, description="Web research 策略")
    context_assembly_v2_enabled: bool = Field(
        default=False,
        description="Enable authoritative backend context assembly v2",
    )


class AuthRegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, description="Email")
    password: str = Field(min_length=8, description="Password")
    name: str = Field(min_length=1, description="Display name")
    organization_name: str | None = Field(default=None, description="Personal org name")


class AuthConfigResponse(BaseModel):
    public_registration_enabled: bool = Field(description="Whether public registration is open")
    oauth_providers: list[str] = Field(description="Enabled OAuth providers")


class AuthLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, description="Email")
    password: str = Field(min_length=1, description="Password")
    organization_id: str | None = Field(default=None, description="Optional org selector")


class AuthRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, description="Refresh token")
    organization_id: str | None = Field(default=None, description="Optional target org selector")


class AuthTokenResponse(BaseModel):
    access_token: str = Field(description="JWT access token")
    refresh_token: str = Field(description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(description="Access token TTL seconds")


class OrganizationSummary(BaseModel):
    id: str = Field(description="Organization ID")
    name: str = Field(description="Organization name")
    slug: str = Field(description="Organization slug")
    role: str = Field(description="Current user role")


class AuthMeResponse(BaseModel):
    user_id: str = Field(description="User ID")
    email: str = Field(description="Email")
    name: str = Field(description="Display name")
    avatar_data_url: str | None = Field(default=None, description="Current user's avatar data URL")
    organization_id: str = Field(description="Current organization ID")
    role: str = Field(description="Current RBAC role")
    permissions: list[str] = Field(description="Granted permissions")
    organizations: list[OrganizationSummary] = Field(description="User workspaces")


class OAuthStartResponse(BaseModel):
    provider: str = Field(description="OAuth provider")
    authorization_url: str = Field(description="Provider authorization URL")
    state: str = Field(description="Opaque state value")


class StoredSecretUpsertRequest(BaseModel):
    scope: Literal["user", "org"] = Field(default="user", description="Secret scope")
    provider: str = Field(min_length=1, max_length=128, description="Provider key")
    purpose: Literal[
        "model_provider",
        "knowledge_connector",
        "mcp_runtime",
        "web_research",
        "notification_channel",
    ] = Field(description="Secret purpose")
    secret_ref: str | None = Field(default=None, max_length=500, description="Logical secret ref")
    secret_value: str = Field(min_length=1, max_length=10_000, description="One-time secret value")


class StoredSecretResponse(BaseModel):
    id: str = Field(description="Secret ID")
    organization_id: str = Field(description="Organization ID")
    owner_user_id: str | None = Field(default=None, description="Owner user for user scope")
    scope: str = Field(description="Secret scope")
    provider: str = Field(description="Provider key")
    purpose: str = Field(description="Secret purpose")
    secret_ref: str | None = Field(default=None, description="Logical secret ref")
    status: str = Field(description="Secret status")
    configured: bool = Field(description="Whether secret material is configured")
    source: str = Field(
        default="stored_secret_user",
        description="Secret source, for example stored_secret_user or stored_secret_org",
    )
    created_at: datetime = Field(description="Created time")
    updated_at: datetime = Field(description="Updated time")
    last_used_at: datetime | None = Field(default=None, description="Last used time")

    model_config = ConfigDict(from_attributes=True)


class StoredSecretPage(BaseModel):
    items: list[StoredSecretResponse] = Field(description="Stored secrets")
    next_cursor: str | None = Field(default=None, description="Next cursor")


class StoredSecretImportResponse(BaseModel):
    imported: list[StoredSecretResponse] = Field(description="Imported env secrets")
    skipped: list[dict] = Field(default_factory=list, description="Skipped env secrets")


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, description="API key name")
    scopes: list[str] = Field(default_factory=list, description="Permission scopes")
    expires_at: datetime | None = Field(default=None, description="Expiration time")


class ApiKeyResponse(BaseModel):
    id: str = Field(description="API key ID")
    organization_id: str = Field(description="Organization ID")
    user_id: str = Field(description="Creator user ID")
    name: str = Field(description="API key name")
    key_prefix: str = Field(description="Visible key prefix")
    scope_json: list[str] = Field(description="Permission scopes")
    expires_at: datetime | None = Field(default=None, description="Expiration time")
    last_used_at: datetime | None = Field(default=None, description="Last used time")
    created_at: datetime = Field(description="Created time")
    revoked_at: datetime | None = Field(default=None, description="Revoked time")

    model_config = ConfigDict(from_attributes=True)


class ApiKeyCreateResponse(ApiKeyResponse):
    key: str = Field(description="Plaintext key shown once")


class UserMemberResponse(BaseModel):
    membership_id: str = Field(description="Membership ID")
    user_id: str = Field(description="User ID")
    email: str = Field(description="Email")
    name: str = Field(description="Display name")
    role: str = Field(description="Org role")
    invited_at: datetime | None = Field(default=None, description="Invited time")
    accepted_at: datetime | None = Field(default=None, description="Accepted time")
    status: str = Field(description="User status")


class UserInviteRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, description="Invitee email")
    name: str | None = Field(default=None, description="Invitee display name")
    role: Literal["admin", "member", "viewer"] = Field(default="member")


class UserRoleUpdateRequest(BaseModel):
    role: Literal["admin", "member", "viewer"] = Field(description="New role")


class AuditEventResponse(BaseModel):
    id: str = Field(description="Audit event ID")
    organization_id: str | None = Field(default=None, description="Organization ID")
    actor_id: str | None = Field(default=None, description="Actor ID")
    event_type: str = Field(description="Event type")
    resource_type: str = Field(description="Resource type")
    resource_id: str = Field(description="Resource ID")
    action: str = Field(description="Action")
    payload_json: dict = Field(description="Payload")
    created_at: datetime = Field(description="Created time")

    model_config = ConfigDict(from_attributes=True)


class AuditEventPage(BaseModel):
    items: list[AuditEventResponse] = Field(description="Audit events")
    next_cursor: str | None = Field(default=None, description="Next cursor")


class RetentionPolicyResponse(BaseModel):
    id: str = Field(description="Policy ID")
    organization_id: str | None = Field(default=None, description="Organization ID")
    entity_type: str = Field(description="Entity type")
    action: str = Field(description="Retention action")
    retention_days: int | None = Field(default=None, description="Retention days")
    delete_after_days: int | None = Field(default=None, description="Archive delete-after days")
    enabled: bool = Field(description="Enabled")
    created_at: datetime = Field(description="Created time")
    updated_at: datetime = Field(description="Updated time")

    model_config = ConfigDict(from_attributes=True)


class RetentionPolicyPage(BaseModel):
    items: list[RetentionPolicyResponse] = Field(description="Retention policies")


class RetentionPolicyUpdateRequest(BaseModel):
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    delete_after_days: int | None = Field(default=None, ge=1, le=3650)
    enabled: bool | None = Field(default=None)


class RetentionRunResponse(BaseModel):
    id: str = Field(description="Retention run ID")
    policy_id: str | None = Field(default=None, description="Policy ID")
    organization_id: str | None = Field(default=None, description="Organization ID")
    entity_type: str = Field(description="Entity type")
    action: str = Field(description="Action")
    deleted_count: int = Field(description="Deleted count")
    archived_count: int = Field(description="Archived count")
    started_at: datetime = Field(description="Started time")
    finished_at: datetime | None = Field(default=None, description="Finished time")
    error_message: str | None = Field(default=None, description="Error")

    model_config = ConfigDict(from_attributes=True)


class RetentionRunPage(BaseModel):
    items: list[RetentionRunResponse] = Field(description="Retention runs")


class DataExportResponse(BaseModel):
    id: str = Field(description="Export ID")
    organization_id: str = Field(description="Organization ID")
    requested_by: str = Field(description="Requester")
    status: str = Field(description="Status")
    requested_at: datetime = Field(description="Requested time")
    completed_at: datetime | None = Field(default=None, description="Completed time")
    file_path: str | None = Field(default=None, description="Local file path")
    file_sha256: str | None = Field(default=None, description="File SHA256")
    size_bytes: int = Field(description="File size")
    expires_at: datetime | None = Field(default=None, description="Expiration")
    error_message: str | None = Field(default=None, description="Error")

    model_config = ConfigDict(from_attributes=True)


class DataExportPage(BaseModel):
    items: list[DataExportResponse] = Field(description="Data exports")


class OrganizationDeletionPreviewResponse(BaseModel):
    organization_id: str = Field(description="Organization ID")
    organization_name: str = Field(description="Organization name")
    counts: dict[str, int] = Field(description="Affected row counts")
    confirmation_name: str = Field(description="Name required for confirmation")


class OrganizationDeleteRequest(BaseModel):
    confirmation_name: str = Field(min_length=1, description="Organization name confirmation")


class OrganizationDeletionResponse(BaseModel):
    organization_id: str = Field(description="Organization ID")
    status: str = Field(description="Deletion status")
    deleted_counts_json: dict[str, int] = Field(description="Deleted counts")
