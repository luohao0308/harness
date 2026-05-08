import dramatiq
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.orchestrator import MultiAgentOrchestrator
from app.db.models import AgentAssignment, Task
from app.db.session import SessionLocal
from app.workers.broker import broker


def execute_agent_assignment(
    assignment_id: str,
    session: Session | None = None,
) -> str:
    if session is not None:
        return _execute_agent_assignment_with_session(
            session=session,
            assignment_id=assignment_id,
        )
    with SessionLocal() as local_session:
        status = _execute_agent_assignment_with_session(
            session=local_session,
            assignment_id=assignment_id,
        )
        local_session.commit()
        return status


def _execute_agent_assignment_with_session(
    *,
    session: Session,
    assignment_id: str,
) -> str:
    assignment = session.get(AgentAssignment, assignment_id)
    if assignment is None:
        raise ValueError(f"AgentAssignment not found: {assignment_id}")
    run = session.get(Task, assignment.run_id)
    if run is None:
        raise ValueError(f"Agent Run not found: {assignment.run_id}")
    orchestrator = MultiAgentOrchestrator(session)
    orchestrator.execute_assignment(run=run, assignment=assignment)
    assignments = list(
        session.execute(
            select(AgentAssignment)
            .where(AgentAssignment.run_id == run.id)
            .order_by(AgentAssignment.created_at.asc(), AgentAssignment.id.asc())
        ).scalars()
    )
    orchestrator._reduce(run=run, assignments=assignments)
    session.flush()
    return assignment.status


@dramatiq.actor(
    broker=broker,
    max_retries=0,
    queue_name="agent_assignments",
)
def run_agent_assignment(assignment_id: str) -> None:
    execute_agent_assignment(assignment_id)
