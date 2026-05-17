from __future__ import annotations

from pathlib import Path


OUTPUT = Path("artifacts/agent-harness-mindmap.svg")
W = 2400
H = 1600
CX = 1200
CY = 760

BRANCHES = [
    {
        "title": "用户与目标",
        "color": "#2563eb",
        "x": 300,
        "y": 230,
        "items": ["代码工程任务", "企业知识问答", "自动化工作流", "复杂任务执行", "减少重复错误", "过程可观测", "结果可评测"],
    },
    {
        "title": "模型层",
        "color": "#7c3aed",
        "x": 850,
        "y": 170,
        "items": ["OpenAI / local Agent CLI / DeepSeek", "本地模型", "模型路由", "备用模型", "调用审计", "成本统计"],
    },
    {
        "title": "Harness 驾驭层",
        "color": "#dc2626",
        "x": 1500,
        "y": 190,
        "items": ["任务控制", "上下文控制", "权限控制", "调度控制", "策略控制", "暂停 / 继续 / 回滚", "高风险审批"],
    },
    {
        "title": "智能体层",
        "color": "#059669",
        "x": 2050,
        "y": 430,
        "items": ["主智能体", "计划 / 搜索 / 执行", "审查 / 验证 / 反思", "必要时创建子智能体", "系统提示词", "工具与知识范围", "运行预算"],
    },
    {
        "title": "知识与记忆层",
        "color": "#0891b2",
        "x": 2020,
        "y": 1050,
        "items": ["短期记忆", "长期记忆", "项目事实与用户偏好", "历史错误与修复经验", "Wiki", "RAG", "知识引擎", "外部知识源"],
    },
    {
        "title": "工具与执行层",
        "color": "#ea580c",
        "x": 1450,
        "y": 1330,
        "items": ["MCP 连接", "浏览器 / 搜索 / GitHub", "文件读写", "Shell 命令", "测试与构建", "沙箱 / Docker / WarmPool", "审批与回滚"],
    },
    {
        "title": "可观测与评测层",
        "color": "#9333ea",
        "x": 780,
        "y": 1280,
        "items": ["执行时间线", "模型调用记录", "工具调用记录", "检索命中与引用", "成本 / 延迟 / Token", "回放与审计", "评测集与回归", "失败案例库"],
    },
    {
        "title": "产品与基础设施",
        "color": "#475569",
        "x": 270,
        "y": 900,
        "items": ["Agent Studio", "Workspace", "Run Detail", "知识 / 记忆控制台", "工具 / MCP 控制台", "观测 / 评测控制台", "FastAPI / Worker", "数据库 / 向量索引 / 事件存储"],
    },
]


def esc(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def width_units(value: str) -> float:
    return sum(0.55 if char.isascii() and (char.isalnum() or char in "/ ") else 1 for char in value)


def wrap(value: str, max_units: float) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in value:
        if width_units(current + char) > max_units:
            lines.append(current)
            current = char
        else:
            current += char
    if current:
        lines.append(current)
    return lines


def connector(x1: int, y1: int, x2: int, y2: int, color: str) -> str:
    return (
        f'<path d="M {x1} {y1} C {(x1 + x2) / 2} {y1}, '
        f'{(x1 + x2) / 2} {y2}, {x2} {y2}" '
        f'stroke="{color}" stroke-width="5" fill="none" opacity=".45"/>'
    )


parts = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
    '<rect width="100%" height="100%" fill="#fbfdff"/>',
    """<style>
text{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",Arial,sans-serif;fill:#0f172a}
.title{font-size:44px;font-weight:800}
.subtitle{font-size:24px;fill:#475569}
.branch-title{font-size:29px;font-weight:800;fill:white}
.item{font-size:23px;font-weight:560}
.note{font-size:24px;fill:#334155;font-weight:700}
.small{font-size:20px;fill:#64748b}
</style>""",
    """<defs>
<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
<feDropShadow dx="0" dy="8" stdDeviation="10" flood-color="#0f172a" flood-opacity="0.12"/>
</filter>
</defs>""",
    f'<ellipse cx="{CX}" cy="{CY}" rx="300" ry="115" fill="#111827" filter="url(#shadow)"/>',
    f'<text class="title" x="{CX}" y="{CY - 20}" text-anchor="middle" fill="white">AI Agent Harness 平台</text>',
    f'<text class="subtitle" x="{CX}" y="{CY + 35}" text-anchor="middle" fill="#d1d5db">模型 + 驾驭层 = 可靠智能体</text>',
]

for branch in BRANCHES:
    x = branch["x"]
    y = branch["y"]
    color = branch["color"]
    parts.append(connector(CX, CY, x, y, color))
    parts.append(
        f"""<g filter="url(#shadow)">
<rect x="{x - 210}" y="{y - 42}" width="420" height="84" rx="22" fill="{color}"/>
<text class="branch-title" x="{x}" y="{y + 10}" text-anchor="middle">{esc(branch["title"])}</text>
</g>"""
    )

    start_y = y + 85
    for index, item in enumerate(branch["items"]):
        item_y = start_y + index * 54
        lines = wrap(item, 18)
        parts.append(
            f'<rect x="{x - 205}" y="{item_y - 25}" width="410" height="42" rx="14" '
            f'fill="white" stroke="{color}" stroke-width="2" opacity=".98"/>'
        )
        parts.append(f'<circle cx="{x - 180}" cy="{item_y - 4}" r="5" fill="{color}"/>')
        for line_index, line in enumerate(lines):
            font_size = 20 if len(lines) > 1 else 23
            parts.append(
                f'<text class="item" x="{x - 160}" y="{item_y + 4 + line_index * 21}" '
                f'font-size="{font_size}">{esc(line)}</text>'
            )

parts.extend(
    [
        '<rect x="680" y="1490" width="1040" height="54" rx="20" fill="#e2e8f0"/>',
        '<text class="note" x="1200" y="1525" text-anchor="middle">原则：Harness 在智能体外部统一控制；少量核心智能体 + 多种能力模式 + 完整观测评测闭环</text>',
        '<text class="small" x="1200" y="1572" text-anchor="middle">知识、记忆、工具、权限、沙箱、上下文、观测、评测都是 Harness 能力，不塞进单个智能体里</text>',
        "</svg>",
    ]
)

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text("\n".join(parts), encoding="utf-8")
print(OUTPUT)
