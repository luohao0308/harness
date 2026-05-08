from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Agent, utc_now


@dataclass(frozen=True)
class AgentPreset:
    id: str
    name: str
    description: str
    role: str
    system_prompt: str
    tools: list[str]
    routing_tags: list[str]
    max_parallel_assignments: int = 1


DEFAULT_AGENT_PRESETS = [
    AgentPreset(
        id="default",
        name="Default Agent",
        description="通用入口 Agent，负责理解目标、规划 Run，并协调执行能力。",
        role="generalist",
        system_prompt="You are the default enterprise Agent. Plan, execute, and coordinate safely.",
        tools=["read_file", "list_files", "run_shell", "run_tests"],
        routing_tags=["general", "planning", "execution"],
    ),
    AgentPreset(
        id="researcher",
        name="Researcher Agent",
        description="负责资料收集、上下文整理、方案比较和外部信息验证。",
        role="researcher",
        system_prompt=(
            "You are a research Agent. Gather evidence, compare options, and cite sources."
        ),
        tools=["read_file", "list_files", "network_request"],
        routing_tags=["research", "analysis", "evidence"],
        max_parallel_assignments=3,
    ),
    AgentPreset(
        id="coder",
        name="Coder Agent",
        description="负责代码阅读、实现、重构、测试和工程落地。",
        role="coder",
        system_prompt="You are a coding Agent. Make focused changes and verify them.",
        tools=["read_file", "list_files", "write_file", "run_shell", "run_tests", "git_command"],
        routing_tags=["code", "implementation", "tests"],
        max_parallel_assignments=2,
    ),
    AgentPreset(
        id="reviewer",
        name="Reviewer Agent",
        description="负责缺陷审查、风险识别、测试缺口和回归建议。",
        role="reviewer",
        system_prompt="You are a review Agent. Find bugs, risks, and missing verification.",
        tools=["read_file", "list_files", "run_tests"],
        routing_tags=["review", "quality", "risk"],
        max_parallel_assignments=2,
    ),
    AgentPreset(
        id="operator",
        name="Operator Agent",
        description="负责运行、部署、观测、恢复和安全隔离策略。",
        role="operator",
        system_prompt="You are an operations Agent. Handle runtime, observability, and recovery.",
        tools=["read_file", "list_files", "run_shell", "network_request"],
        routing_tags=["ops", "sandbox", "observability", "recovery"],
    ),
]


def ensure_default_agents(session: Session, organization_id: str) -> None:
    del organization_id
    existing_ids = set(
        session.execute(
            select(Agent.id).where(
                Agent.id.in_([preset.id for preset in DEFAULT_AGENT_PRESETS]),
            )
        ).scalars()
    )
    now = utc_now()
    for preset in DEFAULT_AGENT_PRESETS:
        if preset.id in existing_ids:
            continue
        session.add(
            Agent(
                id=preset.id,
                organization_id=None,
                name=preset.name,
                description=preset.description,
                role=preset.role,
                status="ACTIVE",
                model_provider="default",
                model_name="default",
                system_prompt=preset.system_prompt,
                tools_json=preset.tools,
                routing_tags=preset.routing_tags,
                max_parallel_assignments=preset.max_parallel_assignments,
                created_at=now,
                updated_at=now,
            )
        )
    session.flush()
