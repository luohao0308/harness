const ERROR_MESSAGES: Record<string, string> = {
  rate_limited: "请求太频繁，请稍后再试",
  tool_denied: "工具调用被拒绝，请检查权限或在工具配置中启用",
  budget_exceeded: "本次任务超出预算，请提高成本上限后重试",
  specialist_not_found: "未找到该专家，请检查专家库是否已安装",
  missing_pricing: "未配置该模型的价格表，请到模型设置添加",
  path_traversal: "文件路径不合法，请检查输入",
  frontend_error_rate_limit_exceeded: "错误上报过于频繁，系统已暂时限流",
  "frontend error rate limit exceeded": "错误上报过于频繁，系统已暂时限流",
  "请求失败 401": "登录状态无效，请重新登录后重试",
  "请求失败 403": "当前账号没有执行该操作的权限",
  "请求失败 404": "目标资源不存在或已经被删除",
  "请求失败 409": "资源状态已变化，请刷新后重试",
  "请求失败 422": "提交内容不完整或格式不正确",
  "请求失败 429": "请求太频繁，请稍后再试",
  "请求失败 500": "服务端处理失败，请稍后重试",
  "请求失败 503": "服务暂不可用，请检查后端健康状态",
};

export type LocalizedError = {
  message: string;
  technicalDetail: string | null;
};

export function localizeError(raw: unknown, fallback = "操作失败，请重试或联系管理员"): LocalizedError {
  const technicalDetail = technicalErrorDetail(raw);
  const kind = extractErrorKind(raw);
  if (kind && ERROR_MESSAGES[kind]) {
    return { message: ERROR_MESSAGES[kind], technicalDetail };
  }
  const statusKey = statusMessageKey(technicalDetail);
  if (statusKey && ERROR_MESSAGES[statusKey]) {
    return { message: ERROR_MESSAGES[statusKey], technicalDetail };
  }
  if (technicalDetail) {
    for (const [key, value] of Object.entries(ERROR_MESSAGES)) {
      if (technicalDetail.includes(key)) {
        return { message: value, technicalDetail };
      }
    }
  }
  return { message: fallback, technicalDetail };
}

export function extractErrorKind(raw: unknown): string | null {
  if (raw instanceof Error && raw.message.trim()) {
    return normalizeKind(raw.message);
  }
  if (typeof raw === "string") {
    return normalizeKind(raw);
  }
  if (raw && typeof raw === "object") {
    const record = raw as Record<string, unknown>;
    for (const key of ["kind", "code", "error", "detail"]) {
      const value = record[key];
      if (typeof value === "string" && value.trim()) {
        return normalizeKind(value);
      }
    }
  }
  return null;
}

export function technicalErrorDetail(raw: unknown): string | null {
  if (raw instanceof Error && raw.message.trim()) {
    return raw.message;
  }
  if (typeof raw === "string" && raw.trim()) {
    return raw;
  }
  if (raw === null || raw === undefined) {
    return null;
  }
  try {
    return JSON.stringify(raw);
  } catch {
    return String(raw);
  }
}

function normalizeKind(value: string) {
  return value.trim().replace(/[\s-]+/g, "_").toLowerCase();
}

function statusMessageKey(detail: string | null) {
  const match = detail?.match(/请求失败\s+(\d{3})/);
  return match ? `请求失败 ${match[1]}` : null;
}
