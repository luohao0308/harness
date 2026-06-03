type CapabilityLike = {
  name?: string;
  display_name?: string;
  description?: string;
  tool_name?: string;
  tool_description?: string;
  kind?: string;
  source?: string;
  source_label?: string;
  categories?: string[];
  badges?: string[];
  mcp_server?: string | null;
  mcp_method?: string | null;
  transport?: string | null;
};

export type McpGuide = {
  title: string;
  summary: string;
  scenarios: string[];
  config: string;
  testQuery: string;
};

export function mcpGuideFor(capability: CapabilityLike): McpGuide {
  const text = searchableText(capability);
  const title = capability.display_name || capability.tool_name || capability.name || "MCP 能力";

  if (hasAny(text, ["brave", "brave search"])) {
    return {
      title,
      summary: "使用 Brave 独立索引进行网页、新闻、图片和视频搜索，适合查最新资料、教程、竞品信息和公开网页证据。",
      scenarios: ["查最新教程或新闻", "给回答补充公开来源", "验证某个工具/库的当前状态"],
      config: "需要 Brave Search API Key；运行端点默认使用 Brave 官方 Web Search API。",
      testQuery: "MCP 教程",
    };
  }

  if (hasAny(text, ["exa"])) {
    return {
      title,
      summary: "搜索并抓取网页内容，适合获取库、API、SDK、公司和产品的最新公开信息。",
      scenarios: ["查技术文档更新", "收集公开网页材料", "对比多个搜索结果摘要"],
      config: "通常需要 Exa API Key 和远程 API 端点；安装后到运行配置页补齐密钥。",
      testQuery: "OpenAI 最新动态",
    };
  }

  if (hasAny(text, ["gmail", "mail"])) {
    return {
      title,
      summary: "连接 Gmail，读取、搜索、发送、草拟、回复、归档或按标签整理邮件和联系人信息。",
      scenarios: ["搜索邮件线索", "草拟回复", "整理标签和归档消息"],
      config: "通常需要 Google OAuth 或 Gmail API 凭据；启用前确认账号权限范围。",
      testQuery: "查找最近的未读邮件",
    };
  }

  if (hasAny(text, ["github", "gitlab", "pull request", "issue", "repository", "repo"])) {
    return {
      title,
      summary: "连接代码托管平台，查询仓库、Issue、PR、提交记录和项目协作信息。",
      scenarios: ["查 Issue/PR 状态", "检索仓库代码线索", "汇总代码评审上下文"],
      config: "通常需要平台访问令牌；只授予当前任务必要的仓库和读写权限。",
      testQuery: "列出最近的开放 PR",
    };
  }

  if (hasAny(text, ["slack", "discord", "notion", "linear", "jira"])) {
    return {
      title,
      summary: "连接协作系统，读取或整理消息、页面、任务和项目上下文。",
      scenarios: ["查项目讨论", "汇总任务状态", "把外部协作记录带入回答"],
      config: "通常需要对应平台的 OAuth 或 API Token；注意工作区和频道权限。",
      testQuery: "查询最近的项目状态更新",
    };
  }

  if (hasAny(text, ["context7", "docs", "documentation", "doc", "library"])) {
    return {
      title,
      summary: "把版本相关的文档和代码示例接入智能体，减少模型使用过期 API 的概率。",
      scenarios: ["查某个库的最新用法", "生成带版本依据的代码", "解释新旧 API 差异"],
      config: "多为远程 MCP 或 stdio 服务；按条目说明配置端点或本地启动命令。",
      testQuery: "React useEffect 最新用法",
    };
  }

  if (hasAny(text, ["context", "knowledge", "rag", "workspace"])) {
    return {
      title,
      summary: "检索工作区上下文、知识证据和运行状态，让智能体回答时能引用当前项目材料。",
      scenarios: ["查当前项目背景", "检索知识库证据", "解释运行或发布准备状态"],
      config: "平台内置 MCP 通常无需额外密钥；安装后可直接运行案例测试。",
      testQuery: "发布准备情况",
    };
  }

  if (hasAny(text, ["database", "postgres", "mysql", "sqlite", "sql"])) {
    return {
      title,
      summary: "连接数据库或查询服务，让智能体按授权范围读取结构化数据。",
      scenarios: ["查询业务数据", "检查表结构", "生成只读分析摘要"],
      config: "需要数据库连接端点和凭据；优先使用只读账号并限制网络访问范围。",
      testQuery: "列出可查询的数据表",
    };
  }

  if (hasAny(text, ["browser", "web", "fetch", "crawl", "search"])) {
    return {
      title,
      summary: "接入网页搜索、抓取或浏览能力，用来获取模型本地知识之外的公开信息。",
      scenarios: ["查实时信息", "读取网页摘要", "补充公开资料来源"],
      config: "通常需要远程端点和 API Key；保存配置后再用案例测试确认真实返回。",
      testQuery: "MCP 教程",
    };
  }

  if (capability.kind === "skill") {
    return {
      title,
      summary: "技能会改变智能体的工作方法和提示词边界，不一定是可直接点击调用的工具。",
      scenarios: ["固定某类任务流程", "增强代码审查或写作风格", "约束上下文预算或输出格式"],
      config: "技能安装后需要挂载到目标智能体；部分技能还依赖额外 MCP 或知识源。",
      testQuery: "用这个技能处理一个小案例",
    };
  }

  return {
    title,
    summary: "把外部系统能力接入智能体，让智能体可以通过受控工具调用读取、搜索或操作该系统。",
    scenarios: ["读取外部数据", "执行受控查询", "把工具返回结果用于最终回答"],
    config: "先确认来源和权限；远程 MCP 通常需要端点和凭据，stdio MCP 通常需要本地启动命令。",
    testQuery: "MCP 教程",
  };
}

export function mcpUseSummary(capability: CapabilityLike): string {
  return mcpGuideFor(capability).summary;
}

export function mcpConfigHint(capability: CapabilityLike): string {
  return mcpGuideFor(capability).config;
}

export function mcpMentionHint(capability: CapabilityLike): string {
  const guide = mcpGuideFor(capability);
  const method =
    capability.mcp_server && capability.mcp_method
      ? ` · ${capability.mcp_server}.${capability.mcp_method}`
      : "";
  return `${guide.summary}${method}`;
}

export function localizedCapabilityDescription(capability: CapabilityLike): string {
  const description = capability.description || capability.tool_description || "";
  switch (description) {
    case "Read a file from the workspace":
    case "读取工作区文件。":
      return "读取工作区文件。";
    case "List files in the workspace":
    case "列出工作区文件。":
      return "列出工作区文件。";
    case "Search context":
      return "搜索工作区上下文。";
    case "Execute a shell command in sandbox":
      return "在沙箱中执行 Shell 命令。";
    case "Search the web via MCP adapter":
      return "通过 MCP 适配器执行网络搜索。";
    case "Execute a database query via MCP":
      return "通过 MCP 执行数据库查询。";
    default:
      return description;
  }
}

function searchableText(capability: CapabilityLike) {
  return [
    capability.name,
    capability.display_name,
    capability.description,
    capability.tool_name,
    capability.tool_description,
    capability.source,
    capability.source_label,
    capability.mcp_server,
    capability.mcp_method,
    ...(capability.categories ?? []),
    ...(capability.badges ?? []),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function hasAny(value: string, needles: string[]) {
  return needles.some((needle) => value.includes(needle));
}
