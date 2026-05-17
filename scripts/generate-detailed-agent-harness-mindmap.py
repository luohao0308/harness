from __future__ import annotations

from pathlib import Path


OUTPUT = Path("artifacts/agent-harness-detailed-mindmap.svg")
W = 3400
H = 2200
CX = 1700
CY = 1080


BRANCHES = [
    {
        "title": "1. 用户与目标",
        "color": "#2563eb",
        "side": "left",
        "x": 820,
        "y": 260,
        "groups": [
            ("真实问题", ["代码工程任务", "企业知识问答", "自动化工作流", "复杂任务执行"]),
            ("核心价值", ["可靠完成任务", "减少重复错误", "过程可观测", "结果可评测"]),
            ("部署目标", ["本地开发", "私有化部署", "可接企业系统"]),
        ],
    },
    {
        "title": "2. 模型层",
        "color": "#7c3aed",
        "side": "right",
        "x": 2450,
        "y": 240,
        "groups": [
            ("模型提供商", ["OpenAI", "local Agent CLI", "DeepSeek", "本地模型"]),
            ("模型能力", ["推理", "生成", "工具调用", "多模态"]),
            ("模型网关", ["模型路由", "备用模型", "调用审计", "成本统计"]),
        ],
    },
    {
        "title": "3. Harness 驾驭层",
        "color": "#dc2626",
        "side": "right",
        "x": 2500,
        "y": 640,
        "groups": [
            ("任务控制", ["目标理解", "计划 / 执行 / 审查", "验证模式", "暂停继续"]),
            ("上下文控制", ["上下文选择", "Token 预算", "压缩总结", "提示词组装"]),
            ("权限控制", ["工具权限", "MCP 权限", "网络策略", "高风险审批"]),
            ("调度控制", ["主智能体", "必要时子智能体", "并行任务", "失败恢复"]),
            ("策略控制", ["运行策略", "记忆策略", "知识策略", "评测策略"]),
        ],
    },
    {
        "title": "4. 智能体层",
        "color": "#059669",
        "side": "right",
        "x": 2500,
        "y": 1220,
        "groups": [
            ("主智能体", ["接收目标", "拆解任务", "调用能力", "汇总结果"]),
            ("能力模式", ["计划", "搜索", "执行", "审查", "验证", "反思"]),
            ("子智能体", ["研究子任务", "代码子任务", "测试子任务", "长任务隔离"]),
            ("智能体配置", ["系统提示词", "可用工具", "可用知识", "运行预算", "评测标准"]),
        ],
    },
    {
        "title": "5. 知识与记忆层",
        "color": "#f97316",
        "side": "left",
        "x": 780,
        "y": 820,
        "groups": [
            ("短期记忆", ["当前任务状态", "会话信息", "临时决策", "待办与阻塞"]),
            ("长期记忆", ["项目事实", "用户偏好", "历史错误", "修复经验", "已验证决策"]),
            ("知识库", ["Wiki", "RAG", "本地文档", "代码索引", "外部知识源"]),
            ("知识引擎", ["文档导入", "切片向量化", "重排", "结构化答案", "来源证明"]),
        ],
    },
    {
        "title": "6. 工具与执行层",
        "color": "#ec4899",
        "side": "left",
        "x": 800,
        "y": 1450,
        "groups": [
            ("MCP 连接", ["浏览器", "搜索", "GitHub", "数据库", "第三方 API"]),
            ("本地工具", ["文件读写", "Shell 命令", "测试运行", "构建部署", "Git 操作"]),
            ("执行环境", ["沙箱", "Docker", "WarmPool", "后台进程", "私有化环境"]),
            ("执行安全", ["风险等级", "人工审批", "结果校验", "回滚方案", "密钥保护"]),
        ],
    },
    {
        "title": "7. 可观测与评测层",
        "color": "#0891b2",
        "side": "right",
        "x": 2420,
        "y": 1780,
        "groups": [
            ("可观测", ["执行时间线", "模型调用", "工具调用", "MCP 调用", "检索命中"]),
            ("回放与审计", ["Run Detail", "事件流", "Trace", "Artifact", "Diff", "日志"]),
            ("评测系统", ["评测集", "回归测试", "黄金任务", "失败案例库", "质量评分", "改进闭环"]),
        ],
    },
    {
        "title": "8. 产品与基础设施",
        "color": "#f59e0b",
        "side": "bottom",
        "x": 1700,
        "y": 1880,
        "groups": [
            ("产品界面", ["Agent Studio", "Workspace", "Run Detail", "知识控制台", "观测评测控制台"]),
            ("数据存储", ["关系数据库", "向量索引", "对象存储", "事件存储", "日志存储"]),
            ("后端服务", ["FastAPI", "Worker", "调度器", "事件总线", "模型网关"]),
            ("部署运维", ["Docker Compose", "私有化部署", "数据迁移", "健康检查", "备份恢复"]),
        ],
    },
]


def esc(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text_units(value: str) -> float:
    return sum(0.55 if char.isascii() and (char.isalnum() or char in " /-") else 1 for char in value)


def wrap(value: str, max_units: float) -> list[str]:
    lines: list[str] = []
    cur = ""
    for char in value:
        if text_units(cur + char) > max_units:
            lines.append(cur)
            cur = char
        else:
            cur += char
    if cur:
        lines.append(cur)
    return lines


def path_to(x1: int, y1: int, x2: int, y2: int, color: str) -> str:
    return (
        f'<path d="M {x1} {y1} C {(x1 + x2) / 2} {y1}, {(x1 + x2) / 2} {y2}, {x2} {y2}" '
        f'stroke="{color}" stroke-width="7" fill="none" opacity=".7"/>'
    )


def rounded_rect(x: int, y: int, w: int, h: int, r: int, fill: str, stroke: str = "", sw: int = 0) -> str:
    stroke_part = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"{stroke_part}/>'


parts = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
    '<rect width="100%" height="100%" fill="#ffffff"/>',
    """<style>
text{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",Arial,sans-serif;fill:#111827}
.root-title{font-size:48px;font-weight:850;fill:white}
.root-sub{font-size:32px;font-weight:750;fill:white}
.branch-title{font-size:34px;font-weight:850;fill:#111827}
.group-title{font-size:25px;font-weight:800;fill:#111827}
.item{font-size:22px;font-weight:620;fill:#111827}
.note{font-size:30px;font-weight:800;fill:#0f172a}
</style>""",
    """<defs>
<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
<feDropShadow dx="0" dy="8" stdDeviation="12" flood-color="#0f172a" flood-opacity="0.16"/>
</filter>
</defs>""",
]

parts.append(rounded_rect(CX - 360, CY - 92, 720, 184, 26, "#0f172a"))
parts.append(f'<text class="root-title" x="{CX}" y="{CY - 18}" text-anchor="middle">AI Agent Harness 平台</text>')
parts.append(f'<text class="root-sub" x="{CX}" y="{CY + 45}" text-anchor="middle">模型 + 驾驭层 = 可靠智能体</text>')

for branch in BRANCHES:
    color = branch["color"]
    x = branch["x"]
    y = branch["y"]
    side = branch["side"]
    parts.append(path_to(CX, CY, x, y, color))
    title_w = 390
    parts.append(
        f'<g filter="url(#shadow)">{rounded_rect(x - title_w // 2, y - 44, title_w, 88, 16, "#fffdf8", color, 5)}'
        f'<text class="branch-title" x="{x}" y="{y + 12}" text-anchor="middle">{esc(branch["title"])}</text></g>'
    )

    groups = branch["groups"]
    if side == "left":
        gx = x - 720
        base_y = y - (len(groups) * 112) // 2 + 12
        junction_x = x - title_w // 2
        for gi, (group_title, items) in enumerate(groups):
            gy = base_y + gi * 118
            parts.append(path_to(junction_x, y, gx + 610, gy + 30, color))
            parts.append(rounded_rect(gx, gy, 620, 60, 12, "#ffffff", color, 4))
            parts.append(f'<text class="group-title" x="{gx + 22}" y="{gy + 39}">{esc(group_title)}</text>')
            item_x = gx
            item_y = gy + 66
            for ii, item in enumerate(items):
                ix = item_x + (ii % 2) * 315
                iy = item_y + (ii // 2) * 42
                parts.append(rounded_rect(ix, iy, 300, 34, 9, "#ffffff", color, 2))
                label = " / ".join(wrap(item, 12))
                parts.append(f'<text class="item" x="{ix + 14}" y="{iy + 24}">{esc(label)}</text>')
    elif side == "right":
        gx = x + 100
        base_y = y - (len(groups) * 112) // 2 + 12
        junction_x = x + title_w // 2
        for gi, (group_title, items) in enumerate(groups):
            gy = base_y + gi * 118
            parts.append(path_to(junction_x, y, gx, gy + 30, color))
            parts.append(rounded_rect(gx, gy, 620, 60, 12, "#ffffff", color, 4))
            parts.append(f'<text class="group-title" x="{gx + 22}" y="{gy + 39}">{esc(group_title)}</text>')
            item_x = gx
            item_y = gy + 66
            for ii, item in enumerate(items):
                ix = item_x + (ii % 2) * 315
                iy = item_y + (ii // 2) * 42
                parts.append(rounded_rect(ix, iy, 300, 34, 9, "#ffffff", color, 2))
                label = " / ".join(wrap(item, 12))
                parts.append(f'<text class="item" x="{ix + 14}" y="{iy + 24}">{esc(label)}</text>')
    else:
        gx = 430
        gy = y + 95
        parts.append(path_to(x, y + 44, CX, CY, color))
        for gi, (group_title, items) in enumerate(groups):
            box_x = gx + gi * 640
            parts.append(rounded_rect(box_x, gy, 590, 60, 12, "#ffffff", color, 4))
            parts.append(f'<text class="group-title" x="{box_x + 22}" y="{gy + 39}">{esc(group_title)}</text>')
            for ii, item in enumerate(items):
                ix = box_x + (ii % 2) * 290
                iy = gy + 68 + (ii // 2) * 42
                parts.append(rounded_rect(ix, iy, 276, 34, 9, "#ffffff", color, 2))
                parts.append(f'<text class="item" x="{ix + 12}" y="{iy + 24}">{esc(item)}</text>')

parts.append(rounded_rect(470, 2068, 2460, 78, 18, "#f8fafc", "#0f172a", 3))
parts.append(
    '<text class="note" x="1700" y="2118" text-anchor="middle">'
    "原则：Harness 在智能体外部统一控制；智能体使用能力模式；知识、记忆、工具、权限、观测、评测是平台能力"
    "</text>"
)
parts.append("</svg>")

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text("\n".join(parts), encoding="utf-8")
print(OUTPUT)
