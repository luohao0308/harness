from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, description="任务标题")
    goal: str = Field(min_length=1, description="任务目标")
    model_provider: str = Field(description="模型供应商")
    model_name: str = Field(description="模型名称")
    max_runtime_seconds: int = Field(default=1800, description="最大运行秒数")
    max_subagents: int = Field(default=5, description="最大子 Agent 数")
    enable_sandbox: bool = Field(default=True, description="是否启用容器沙箱")
    enable_network: bool = Field(default=False, description="是否启用网络访问")


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
    items: list[TaskResponse] = Field(description="任务列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class TaskArtifact(BaseModel):
    name: str = Field(description="产物名称")
    artifact_type: str = Field(description="产物类型")
    description: str = Field(description="产物说明")
    status: str = Field(description="产物状态")


class TaskSubagentResult(BaseModel):
    id: str = Field(description="子 Agent ID")
    step_key: str | None = Field(default=None, description="来源步骤键")
    status: str = Field(description="子 Agent 状态")
    summary: str | None = Field(default=None, description="子 Agent 结果摘要")
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


class TaskPlanStepState(BaseModel):
    step_key: str = Field(description="步骤键")
    description: str = Field(description="步骤说明")
    execution_mode: str = Field(description="执行模式")
    requires_sandbox: bool = Field(description="是否需要沙箱")
    can_spawn_subagent: bool = Field(description="是否可派生子 Agent")
    status: str = Field(description="当前步骤状态")
    assigned_agent_id: str | None = Field(default=None, description="分配的 Agent ID")
    error_message: str | None = Field(default=None, description="错误信息")


class TaskPlanResponse(BaseModel):
    id: str = Field(description="计划 ID")
    task_id: str = Field(description="任务 ID")
    version: int = Field(description="计划版本")
    status: str = Field(description="计划状态")
    summary: str | None = Field(default=None, description="计划摘要")
    planner_source: str = Field(description="计划来源")
    planner_attempts: int = Field(description="计划生成尝试次数")
    plan_json: dict = Field(description="计划原始 JSON")
    steps: list[TaskPlanStepState] = Field(description="计划步骤状态")
    created_at: datetime = Field(description="创建时间")


class ReplayRequest(BaseModel):
    sequence: int | None = Field(default=None, ge=1, description="重放到指定事件序号")


class ReplayResponse(BaseModel):
    task_id: str = Field(description="任务 ID")
    sequence: int = Field(description="重放序号")
    state_summary: str = Field(description="状态摘要")
    failure_point: dict | None = Field(default=None, description="故障点")
    diagnosis: str = Field(description="诊断结论")
    requires_manual_review: bool = Field(description="是否需要人工复核")


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


class SubagentCreateRequest(BaseModel):
    assignment: dict = Field(description="子 Agent 任务上下文")
    parent_agent_id: str | None = Field(default=None, description="父 Agent ID")
    timeout_seconds: int = Field(default=900, ge=1, description="超时秒数")
    enqueue: bool = Field(default=False, description="是否进入 Dramatiq 队列")


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


class WarmPoolResponse(BaseModel):
    enabled: bool = Field(description="是否启用")
    min_size: int = Field(description="最小数量")
    max_size: int = Field(description="最大数量")
    idle: int = Field(description="空闲数量")
    busy: int = Field(description="忙碌数量")
    failed: int = Field(description="失败数量")
    hit_total: int = Field(description="命中总数")
    miss_total: int = Field(description="未命中总数")


class CountItem(BaseModel):
    name: str = Field(description="名称")
    count: int = Field(description="数量")


class ObservabilitySummaryResponse(BaseModel):
    tasks_by_status: list[CountItem] = Field(description="任务状态分布")
    subagents_by_status: list[CountItem] = Field(description="子 Agent 状态分布")
    model_calls_by_status: list[CountItem] = Field(description="模型调用状态分布")
    tool_calls_by_status: list[CountItem] = Field(description="工具调用状态分布")
    sandboxes_by_status: list[CountItem] = Field(description="沙箱状态分布")
    warm_pool: WarmPoolResponse = Field(description="WarmPool 状态")
    event_total: int = Field(description="事件总数")
    task_total: int = Field(description="任务总数")
    failed_task_total: int = Field(description="失败任务总数")
    model_call_total: int = Field(description="模型调用总数")
    tool_call_total: int = Field(description="工具调用总数")
    sandbox_total: int = Field(description="沙箱总数")


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


class ObservabilityTraceResponse(BaseModel):
    trace_id: str = Field(description="Trace ID")
    spans: list[ObservabilityTraceSpan] = Field(description="Span 列表")
    source: str = Field(description="数据来源")


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


class ObservabilityServicesHealthResponse(BaseModel):
    services: list[ObservabilityServiceHealthResponse] = Field(description="服务健康列表")


class ModelCallResponse(BaseModel):
    id: str = Field(description="模型调用 ID")
    task_id: str = Field(description="任务 ID")
    agent_run_id: str | None = Field(default=None, description="Agent 运行 ID")
    model_provider: str = Field(description="模型供应商")
    model_name: str = Field(description="模型名称")
    status: str = Field(description="调用状态")
    prompt_tokens: int = Field(description="提示词 token 数")
    completion_tokens: int = Field(description="输出 token 数")
    duration_ms: int = Field(description="耗时（毫秒）")
    request_json: dict = Field(description="请求内容")
    response_json: dict = Field(description="响应内容")
    error_message: str | None = Field(default=None, description="错误信息")
    created_at: datetime = Field(description="创建时间")

    model_config = ConfigDict(from_attributes=True)


class ModelCallPage(BaseModel):
    items: list[ModelCallResponse] = Field(description="模型调用列表")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class ToolCallResponse(BaseModel):
    id: str = Field(description="工具调用 ID")
    task_id: str = Field(description="任务 ID")
    agent_run_id: str | None = Field(default=None, description="Agent 运行 ID")
    tool_name: str = Field(description="工具名称")
    status: str = Field(description="调用状态")
    risk_level: str = Field(description="风险等级")
    requires_sandbox: bool = Field(description="是否需要沙箱")
    sandbox_id: str | None = Field(default=None, description="沙箱 ID")
    duration_ms: int = Field(description="耗时（毫秒）")
    input_json: dict = Field(description="输入内容")
    output_json: dict = Field(description="输出内容")
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


class ModelSettingsResponse(BaseModel):
    default_provider: str = Field(description="默认供应商")
    default_model: str = Field(description="默认模型")
    providers: list[dict] = Field(description="供应商列表")
    rate_limits: dict = Field(description="限流信息")
    health: dict = Field(description="健康状态")


class ModelHealthResponse(BaseModel):
    provider: str = Field(description="模型供应商")
    model: str = Field(description="模型名称")
    status: str = Field(description="健康状态")
    mode: str = Field(description="探测模式")
    checked_at: datetime = Field(description="检查时间")
    latency_ms: int = Field(description="探测耗时（毫秒）")
    error_message: str | None = Field(default=None, description="错误信息")


class ModelHealthPage(BaseModel):
    items: list[ModelHealthResponse] = Field(description="模型健康状态列表")


class PolicySettingsResponse(BaseModel):
    risk_levels: list[dict] = Field(description="风险等级")
    approvals: dict = Field(description="审批规则")
    sandbox: dict = Field(description="沙箱规则")
    audit: dict = Field(description="审计规则")
