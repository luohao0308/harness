const fs = require("fs");

const output = "artifacts/agent-harness-mindmap.svg";
const W = 2400;
const H = 1600;
const cx = 1200;
const cy = 760;

const branches = [
  {
    title: "用户与目标",
    color: "#2563eb",
    x: 300,
    y: 230,
    items: ["代码工程任务", "企业知识问答", "自动化工作流", "复杂任务执行", "减少重复错误", "过程可观测", "结果可评测"],
  },
  {
    title: "模型层",
    color: "#7c3aed",
    x: 850,
    y: 170,
    items: ["OpenAI / DeepSeek / 本地模型", "私有模型", "模型路由", "备用模型", "调用审计", "成本统计"],
  },
  {
    title: "Harness 驾驭层",
    color: "#dc2626",
    x: 1500,
    y: 190,
    items: ["任务控制", "上下文控制", "权限控制", "调度控制", "策略控制", "暂停 / 继续 / 回滚", "高风险审批"],
  },
  {
    title: "智能体层",
    color: "#059669",
    x: 2050,
    y: 430,
    items: ["主智能体", "计划 / 搜索 / 执行", "审查 / 验证 / 反思", "必要时创建子智能体", "系统提示词", "工具与知识范围", "运行预算"],
  },
  {
    title: "知识与记忆层",
    color: "#0891b2",
    x: 2020,
    y: 1050,
    items: ["短期记忆", "长期记忆", "项目事实与用户偏好", "历史错误与修复经验", "Wiki", "RAG", "知识引擎", "外部知识源"],
  },
  {
    title: "工具与执行层",
    color: "#ea580c",
    x: 1450,
    y: 1330,
    items: ["MCP 连接", "浏览器 / 搜索 / GitHub", "文件读写", "Shell 命令", "测试与构建", "沙箱 / Docker / WarmPool", "审批与回滚"],
  },
  {
    title: "可观测与评测层",
    color: "#9333ea",
    x: 780,
    y: 1280,
    items: ["执行时间线", "模型调用记录", "工具调用记录", "检索命中与引用", "成本 / 延迟 / Token", "回放与审计", "评测集与回归", "失败案例库"],
  },
  {
    title: "产品与基础设施",
    color: "#475569",
    x: 270,
    y: 900,
    items: ["Agent Studio", "Workspace", "Run Detail", "知识 / 记忆控制台", "工具 / MCP 控制台", "观测 / 评测控制台", "FastAPI / Worker", "数据库 / 向量索引 / 事件存储"],
  },
];

function esc(value) {
  return String(value).replace(/[&<>]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[char]);
}

function widthUnits(value) {
  return [...value].reduce((sum, char) => sum + (/[A-Za-z0-9/ ]/.test(char) ? 0.55 : 1), 0);
}

function wrap(value, maxUnits) {
  const lines = [];
  let current = "";
  for (const char of value) {
    if (widthUnits(current + char) > maxUnits) {
      lines.push(current);
      current = char;
    } else {
      current += char;
    }
  }
  if (current) lines.push(current);
  return lines;
}

function connector(x1, y1, x2, y2, color) {
  return `<path d="M ${x1} ${y1} C ${(x1 + x2) / 2} ${y1}, ${(x1 + x2) / 2} ${y2}, ${x2} ${y2}" stroke="${color}" stroke-width="5" fill="none" opacity=".45"/>`;
}

let svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
<rect width="100%" height="100%" fill="#fbfdff"/>
<style>
text{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",Arial,sans-serif;fill:#0f172a}
.title{font-size:44px;font-weight:800}
.subtitle{font-size:24px;fill:#475569}
.branch-title{font-size:29px;font-weight:800;fill:white}
.item{font-size:23px;font-weight:560}
.note{font-size:24px;fill:#334155;font-weight:700}
.small{font-size:20px;fill:#64748b}
</style>
<defs>
<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
<feDropShadow dx="0" dy="8" stdDeviation="10" flood-color="#0f172a" flood-opacity="0.12"/>
</filter>
</defs>`;

svg += `<ellipse cx="${cx}" cy="${cy}" rx="300" ry="115" fill="#111827" filter="url(#shadow)"/>`;
svg += `<text class="title" x="${cx}" y="${cy - 20}" text-anchor="middle" fill="white">AI Agent Harness 平台</text>`;
svg += `<text class="subtitle" x="${cx}" y="${cy + 35}" text-anchor="middle" fill="#d1d5db">模型 + 驾驭层 = 可靠智能体</text>`;

for (const branch of branches) {
  svg += connector(cx, cy, branch.x, branch.y, branch.color);
  svg += `<g filter="url(#shadow)">
  <rect x="${branch.x - 210}" y="${branch.y - 42}" width="420" height="84" rx="22" fill="${branch.color}"/>
  <text class="branch-title" x="${branch.x}" y="${branch.y + 10}" text-anchor="middle">${esc(branch.title)}</text>
  </g>`;

  const startY = branch.y + 85;
  branch.items.forEach((item, index) => {
    const y = startY + index * 54;
    const lines = wrap(item, 18);
    svg += `<rect x="${branch.x - 205}" y="${y - 25}" width="410" height="42" rx="14" fill="white" stroke="${branch.color}" stroke-width="2" opacity=".98"/>`;
    svg += `<circle cx="${branch.x - 180}" cy="${y - 4}" r="5" fill="${branch.color}"/>`;
    lines.forEach((line, lineIndex) => {
      const fontSize = lines.length > 1 ? 20 : 23;
      svg += `<text class="item" x="${branch.x - 160}" y="${y + 4 + lineIndex * 21}" font-size="${fontSize}">${esc(line)}</text>`;
    });
  });
}

svg += `<rect x="680" y="1490" width="1040" height="54" rx="20" fill="#e2e8f0"/>`;
svg += `<text class="note" x="1200" y="1525" text-anchor="middle">原则：Harness 在智能体外部统一控制；少量核心智能体 + 多种能力模式 + 完整观测评测闭环</text>`;
svg += `<text class="small" x="1200" y="1572" text-anchor="middle">知识、记忆、工具、权限、沙箱、上下文、观测、评测都是 Harness 能力，不塞进单个智能体里</text>`;
svg += "</svg>\n";

fs.mkdirSync("artifacts", { recursive: true });
fs.writeFileSync(output, svg);
console.log(output);
