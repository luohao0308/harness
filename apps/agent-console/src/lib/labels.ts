const statusLabels: Record<string, string> = {
  CREATED: "已创建",
  PLANNING: "规划中",
  RUNNING: "运行中",
  WAITING_SUBAGENTS: "等待子 Agent",
  WAITING_SUBAGENT: "等待子 Agent",
  COMPLETED: "已完成",
  SUCCESS: "成功",
  FAILED: "失败",
  CANCELLED: "已取消",
  PENDING: "待处理",
  TIMEOUT: "超时",
  healthy: "健康",
  unhealthy: "异常",
};

const eventLabels: Record<string, string> = {
  TASK_CREATED: "任务已创建",
  TASK_STARTED: "任务已启动",
  TASK_PAUSED: "任务已暂停",
  TASK_RESUMED: "任务已恢复",
  TASK_CANCELLED: "任务已取消",
  TASK_FAILED: "任务失败",
  TASK_COMPLETED: "任务完成",
  PLAN_REQUESTED: "请求规划",
  PLAN_GENERATED: "规划生成",
  PLAN_UPDATED: "规划更新",
  PLAN_REJECTED: "规划拒绝",
  STEP_STARTED: "步骤开始",
  STEP_COMPLETED: "步骤完成",
  STEP_FAILED: "步骤失败",
  STEP_RETRIED: "步骤重试",
  STEP_SKIPPED: "步骤跳过",
  MODEL_CALLED: "模型调用",
  MODEL_RESPONSE_RECEIVED: "模型响应",
  MODEL_CALL_FAILED: "模型失败",
  MODEL_FALLBACK_USED: "模型降级",
  TOOL_CALLED: "工具调用",
  TOOL_RESULT_RECEIVED: "工具结果",
  TOOL_FAILED: "工具失败",
  TOOL_TIMEOUT: "工具超时",
  TOOL_DENIED_BY_POLICY: "策略拒绝",
  SUBAGENT_SPAWNED: "派生子 Agent",
  SUBAGENT_STARTED: "子 Agent 启动",
  SUBAGENT_PROGRESS: "子 Agent 进度",
  SUBAGENT_COMPLETED: "子 Agent 完成",
  SUBAGENT_FAILED: "子 Agent 失败",
  SUBAGENT_TIMEOUT: "子 Agent 超时",
  SUBAGENT_CANCELLED: "子 Agent 取消",
  SANDBOX_REQUESTED: "请求沙箱",
  SANDBOX_ALLOCATED: "沙箱分配",
  SANDBOX_REUSED_FROM_WARM_POOL: "复用 WarmPool",
  SANDBOX_COMMAND_STARTED: "沙箱命令开始",
  SANDBOX_COMMAND_COMPLETED: "沙箱命令完成",
  SANDBOX_COMMAND_FAILED: "沙箱命令失败",
  SANDBOX_RELEASED: "沙箱释放",
  SANDBOX_DESTROYED: "沙箱销毁",
  POLICY_CHECKED: "策略检查",
  POLICY_DENIED: "策略拒绝",
  SECRET_ACCESSED: "密钥访问",
  USER_ACTION: "用户操作",
  ADMIN_ACTION: "管理员操作",
};

const actorLabels: Record<string, string> = {
  system: "系统",
  user: "用户",
  admin: "管理员",
  agent: "Agent",
  subagent: "子 Agent",
};

const riskLabels: Record<string, string> = {
  low: "低风险",
  medium: "中风险",
  high: "高风险",
  critical: "关键风险",
};

const approvalLabels: Record<string, string> = {
  auto: "自动通过",
  admin: "管理员审批",
  manual: "人工审批",
};

const artifactStatusLabels: Record<string, string> = {
  ready: "就绪",
  pending: "待生成",
};

const environmentLabels: Record<string, string> = {
  production: "生产环境",
  staging: "预发环境",
  development: "开发环境",
};

const settingsKeyLabels: Record<string, string> = {
  manual_review: "人工复核",
  deny_on_missing_policy: "缺失策略时拒绝",
  default_network: "默认网络",
  default_timeout_seconds: "默认超时秒数",
  model_calls: "模型调用审计",
  tool_calls: "工具调用审计",
  policy_actions: "策略动作审计",
  rpm: "每分钟请求数",
  tpm: "每分钟 Token 数",
  status: "状态",
  updated_at: "更新时间",
};

const executionModeLabels: Record<string, string> = {
  sync: "同步执行",
  async: "异步执行",
};

export function statusLabel(status: string) {
  return statusLabels[status] ?? status;
}

export function eventLabel(eventType: string) {
  return eventLabels[eventType] ?? eventType;
}

export function actorLabel(actorType: string) {
  return actorLabels[actorType] ?? actorType;
}

export function riskLabel(risk: string) {
  return riskLabels[risk] ?? risk;
}

export function approvalLabel(approval: string) {
  return approvalLabels[approval] ?? approval;
}

export function enabledLabel(enabled: boolean) {
  return enabled ? "已启用" : "已关闭";
}

export function booleanLabel(value: unknown) {
  if (value === true) return "是";
  if (value === false) return "否";
  return String(value);
}

export function artifactStatusLabel(status: string) {
  return artifactStatusLabels[status] ?? status;
}

export function environmentLabel(environment: string) {
  return environmentLabels[environment] ?? environment;
}

export function settingsKeyLabel(key: string) {
  return settingsKeyLabels[key] ?? key;
}

export function executionModeLabel(mode: string) {
  return executionModeLabels[mode] ?? mode;
}
