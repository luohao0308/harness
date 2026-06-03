from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.agents.registry import ensure_default_agents
from app.agents.specialists import ensure_system_specialists
from app.db.models import (
    Agent,
    AgentEvent,
    EvalCase,
    EvalDataset,
    ExecutionPlan,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeEmbedding,
    KnowledgeSource,
    RetrievalHit,
    SubagentSpecialist,
    Task,
    ToolCall,
    UserOnboardingState,
    utc_now,
)
from app.events.event_store import EventStore
from app.events.event_types import EventType

DEMO_MARKER = "first-run-demo-v1"


@dataclass
class DemoSeedResult:
    status: str
    agent_ids: list[str] = field(default_factory=list)
    knowledge_source_ids: list[str] = field(default_factory=list)
    dataset_id: str | None = None
    task_id: str | None = None
    specialist_ids: list[str] = field(default_factory=list)
    demo_loaded: bool = False


DEMO_AGENTS = [
    {
        "id": "demo-research-assistant",
        "name": "Demo 研究助手",
        "description": "用于首轮引导的资料研究智能体。",
        "role": "researcher",
        "system_prompt": "Summarize evidence with citations and clear caveats.",
        "tools_json": ["mcp_context_search", "web_research"],
        "routing_tags": ["demo", "research", "grounding"],
    },
    {
        "id": "demo-code-reviewer",
        "name": "Demo 代码审查",
        "description": "用于演示代码审查和风险分级。",
        "role": "reviewer",
        "system_prompt": "Review diffs and return concise findings.",
        "tools_json": ["read_file", "git_command", "run_tests"],
        "routing_tags": ["demo", "review"],
    },
    {
        "id": "demo-support-agent",
        "name": "Demo 客服回复",
        "description": "用于演示受控工具和知识库回复。",
        "role": "support",
        "system_prompt": "Answer support questions from approved knowledge only.",
        "tools_json": ["knowledge_search"],
        "routing_tags": ["demo", "support"],
    },
]


def load_demo_data(session: Session, *, organization_id: str, user_id: str) -> DemoSeedResult:
    state = _state(session=session, organization_id=organization_id, user_id=user_id)
    current = _current_result(
        session=session,
        organization_id=organization_id,
        status="already_loaded",
    )
    if _has_demo_artifacts(current):
        _mark_state_demo_loaded(state, current)
        session.flush()
        return current
    ensure_default_agents(session, organization_id)
    ensure_system_specialists(session)
    agent_ids = _upsert_demo_agents(session=session, organization_id=organization_id)
    knowledge_source_ids = _seed_knowledge(
        session=session,
        organization_id=organization_id,
        user_id=user_id,
    )
    dataset_id = _seed_eval_dataset(
        session=session,
        organization_id=organization_id,
        user_id=user_id,
    )
    task_id = _seed_historical_task(
        session=session,
        organization_id=organization_id,
        user_id=user_id,
    )
    specialist_ids = _system_specialist_ids(session)
    state.demo_loaded = True
    state.agent_id = agent_ids[0] if agent_ids else state.agent_id
    state.demo_task_id = task_id
    state.updated_at = utc_now()
    session.flush()
    return DemoSeedResult(
        status="loaded",
        agent_ids=agent_ids,
        knowledge_source_ids=knowledge_source_ids,
        dataset_id=dataset_id,
        task_id=task_id,
        specialist_ids=specialist_ids,
        demo_loaded=True,
    )


def sync_onboarding_demo_state(
    session: Session,
    *,
    organization_id: str,
    user_id: str,
) -> UserOnboardingState:
    state = _state(session=session, organization_id=organization_id, user_id=user_id)
    current = _current_result(
        session=session,
        organization_id=organization_id,
        status="already_loaded",
    )
    if _has_demo_artifacts(current):
        _mark_state_demo_loaded(state, current)
    elif state.demo_loaded or state.demo_task_id is not None:
        state.demo_loaded = False
        state.demo_task_id = None
        state.updated_at = utc_now()
    session.flush()
    return state


def reset_demo_data(session: Session, *, organization_id: str, user_id: str) -> DemoSeedResult:
    demo_task_ids = list(
        session.execute(
            select(Task.id).where(
                Task.organization_id == organization_id,
                Task.capability_snapshot_json["demo_marker"].as_string() == DEMO_MARKER,
            )
        ).scalars()
    )
    demo_source_ids = list(
        session.execute(
            select(KnowledgeSource.id).where(
                KnowledgeSource.organization_id == organization_id,
                KnowledgeSource.metadata_json["demo_marker"].as_string() == DEMO_MARKER,
            )
        ).scalars()
    )
    demo_document_ids = list(
        session.execute(
            select(KnowledgeDocument.id).where(KnowledgeDocument.source_id.in_(demo_source_ids))
        ).scalars()
    )
    demo_chunk_ids = list(
        session.execute(
            select(KnowledgeChunk.id).where(KnowledgeChunk.document_id.in_(demo_document_ids))
        ).scalars()
    )
    if demo_document_ids:
        session.execute(delete(RetrievalHit).where(RetrievalHit.document_id.in_(demo_document_ids)))
    if demo_chunk_ids:
        session.execute(delete(KnowledgeEmbedding).where(KnowledgeEmbedding.chunk_id.in_(demo_chunk_ids)))
        session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id.in_(demo_document_ids)))
    if demo_document_ids:
        session.execute(delete(KnowledgeDocument).where(KnowledgeDocument.id.in_(demo_document_ids)))
    if demo_source_ids:
        session.execute(delete(KnowledgeSource).where(KnowledgeSource.id.in_(demo_source_ids)))
    demo_dataset_ids = list(
        session.execute(
            select(EvalDataset.id).where(
                EvalDataset.organization_id == organization_id,
                EvalDataset.description.like(f"%{DEMO_MARKER}%"),
            )
        ).scalars()
    )
    if demo_dataset_ids:
        session.execute(delete(EvalCase).where(EvalCase.dataset_id.in_(demo_dataset_ids)))
        session.execute(delete(EvalDataset).where(EvalDataset.id.in_(demo_dataset_ids)))
    if demo_task_ids:
        session.execute(delete(ToolCall).where(ToolCall.task_id.in_(demo_task_ids)))
        session.execute(delete(ExecutionPlan).where(ExecutionPlan.task_id.in_(demo_task_ids)))
        session.execute(delete(AgentEvent).where(AgentEvent.task_id.in_(demo_task_ids)))
        session.execute(delete(Task).where(Task.id.in_(demo_task_ids)))
    session.execute(
        delete(Agent).where(
            Agent.organization_id == organization_id,
            Agent.id.in_([agent["id"] for agent in DEMO_AGENTS]),
        )
    )
    now = utc_now()
    session.execute(
        update(UserOnboardingState)
        .where(UserOnboardingState.organization_id == organization_id)
        .values(demo_loaded=False, demo_task_id=None, updated_at=now)
    )
    state = _state(session=session, organization_id=organization_id, user_id=user_id)
    state.demo_loaded = False
    state.demo_task_id = None
    state.updated_at = now
    session.flush()
    return DemoSeedResult(status="reset", demo_loaded=False)


def _state(*, session: Session, organization_id: str, user_id: str) -> UserOnboardingState:
    state = session.execute(
        select(UserOnboardingState).where(
            UserOnboardingState.organization_id == organization_id,
            UserOnboardingState.user_id == user_id,
        )
    ).scalar_one_or_none()
    if state is None:
        state = UserOnboardingState(
            organization_id=organization_id,
            user_id=user_id,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(state)
        session.flush()
    return state


def _upsert_demo_agents(*, session: Session, organization_id: str) -> list[str]:
    now = utc_now()
    agent_ids = []
    for payload in DEMO_AGENTS:
        agent_ids.append(payload["id"])
        existing = session.get(Agent, payload["id"])
        if existing is not None:
            continue
        session.add(
            Agent(
                id=payload["id"],
                organization_id=organization_id,
                name=payload["name"],
                description=payload["description"],
                role=payload["role"],
                status="ACTIVE",
                model_provider="default",
                model_name="default",
                system_prompt=payload["system_prompt"],
                tools_json=list(payload["tools_json"]),
                routing_tags=list(payload["routing_tags"]),
                max_parallel_assignments=2,
                created_at=now,
                updated_at=now,
            )
        )
    session.flush()
    return agent_ids


def _seed_knowledge(*, session: Session, organization_id: str, user_id: str) -> list[str]:
    source_ids = []
    for index, scope_agent_id in enumerate(["demo-research-assistant", None], start=1):
        content = (
            "# Harness Demo Knowledge\n\n"
            "Model + Harness = Agent. The Harness owns prompt control, tools, "
            "policy, memory, Eval, Observability, replay, and recovery."
        )
        digest = hashlib.sha256(f"{index}:{content}".encode()).hexdigest()
        source = KnowledgeSource(
            organization_id=organization_id,
            agent_id=scope_agent_id,
            name=f"Demo 知识源 {index}",
            description=f"{DEMO_MARKER} seeded knowledge",
            source_type="markdown",
            status="ACTIVE",
            health_status="HEALTHY",
            metadata_json={"demo_marker": DEMO_MARKER},
            idempotency_key=f"{DEMO_MARKER}:source:{index}",
            created_by=user_id,
            created_at=utc_now(),
            updated_at=utc_now(),
            last_indexed_at=utc_now(),
        )
        session.add(source)
        session.flush()
        document = KnowledgeDocument(
            source_id=source.id,
            organization_id=organization_id,
            agent_id=scope_agent_id,
            title=f"Demo Harness Brief {index}",
            uri=f"seed-fixture://{DEMO_MARKER}/{index}",
            content_sha256=digest,
            mime_type="text/markdown",
            status="INDEXED",
            metadata_json={"demo_marker": DEMO_MARKER, "content": content},
            idempotency_key=f"{DEMO_MARKER}:document:{index}",
            created_by=user_id,
            created_at=utc_now(),
            updated_at=utc_now(),
            indexed_at=utc_now(),
        )
        session.add(document)
        source_ids.append(source.id)
    session.flush()
    return source_ids


def _seed_eval_dataset(*, session: Session, organization_id: str, user_id: str) -> str:
    dataset = EvalDataset(
        organization_id=organization_id,
        name="Demo Grounding Dataset",
        description=f"{DEMO_MARKER} eval dataset",
        status="ACTIVE",
        created_by=user_id,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(dataset)
    session.flush()
    for index in range(1, 4):
        session.add(
            EvalCase(
                dataset_id=dataset.id,
                input_json={"question": f"Demo grounding question {index}"},
                expected_json={"must_mention": ["Harness", "Agent"]},
                capability_snapshot_json={"demo_marker": DEMO_MARKER},
                tags_json=["demo", "grounding"],
                created_at=utc_now(),
            )
        )
    session.flush()
    return dataset.id


def _seed_historical_task(*, session: Session, organization_id: str, user_id: str) -> str:
    task = Task(
        organization_id=organization_id,
        agent_id="demo-research-assistant",
        created_by=user_id,
        title="Demo Task: Explain Model + Harness",
        goal="Explain why Model + Harness = Agent with grounding evidence.",
        status="COMPLETED",
        model_provider="default",
        model_name="default",
        capability_snapshot_json={"demo_marker": DEMO_MARKER},
        created_at=utc_now(),
        updated_at=utc_now(),
        completed_at=utc_now(),
    )
    session.add(task)
    session.flush()
    event_store = EventStore(session)
    event_store.append(
        task_id=task.id,
        event_type=EventType.TASK_CREATED,
        payload_json={"title": task.title, "demo_marker": DEMO_MARKER},
        actor_type="user",
        actor_id=user_id,
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.TASK_COMPLETED,
        payload_json={"summary": "Demo run completed with grounded Harness evidence."},
    )
    return task.id


def _system_specialist_ids(session: Session) -> list[str]:
    return list(
        session.execute(
            select(SubagentSpecialist.id)
            .where(SubagentSpecialist.visibility == "system")
            .order_by(SubagentSpecialist.slug.asc())
        ).scalars()
    )


def _current_result(*, session: Session, organization_id: str, status: str) -> DemoSeedResult:
    agent_ids = [
        agent["id"]
        for agent in DEMO_AGENTS
        if session.get(Agent, agent["id"]) is not None
    ]
    source_ids = list(
        session.execute(
            select(KnowledgeSource.id).where(
                KnowledgeSource.organization_id == organization_id,
                KnowledgeSource.metadata_json["demo_marker"].as_string() == DEMO_MARKER,
            )
        ).scalars()
    )
    dataset_id = session.execute(
        select(EvalDataset.id).where(
            EvalDataset.organization_id == organization_id,
            EvalDataset.description.like(f"%{DEMO_MARKER}%"),
        ).order_by(EvalDataset.created_at.desc())
    ).scalars().first()
    task_id = session.execute(
        select(Task.id).where(
            Task.organization_id == organization_id,
            Task.capability_snapshot_json["demo_marker"].as_string() == DEMO_MARKER,
        ).order_by(Task.created_at.desc())
    ).scalars().first()
    demo_loaded = bool(source_ids or dataset_id or task_id)
    return DemoSeedResult(
        status=status,
        agent_ids=agent_ids,
        knowledge_source_ids=source_ids,
        dataset_id=dataset_id,
        task_id=task_id,
        specialist_ids=_system_specialist_ids(session),
        demo_loaded=demo_loaded,
    )


def _has_demo_artifacts(result: DemoSeedResult) -> bool:
    return bool(result.knowledge_source_ids or result.dataset_id or result.task_id)


def _mark_state_demo_loaded(state: UserOnboardingState, result: DemoSeedResult) -> None:
    state.demo_loaded = True
    if result.agent_ids and state.agent_id is None:
        state.agent_id = result.agent_ids[0]
    if result.task_id is not None:
        state.demo_task_id = result.task_id
    state.updated_at = utc_now()
