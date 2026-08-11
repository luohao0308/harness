from __future__ import annotations

import os
import signal
import time

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.observability.alert_evaluator import evaluate_alert_rules
from app.runtime_jobs.profile import is_local_runtime_profile
from app.runtime_jobs.repository import RuntimeJobRepository
from app.workers.actor_registration import register_server_actor

DEFAULT_ALERT_EVALUATOR_INTERVAL_SECONDS = 60


def evaluate_alerts_once(
    *,
    organization_id: str | None = None,
    session: Session | None = None,
) -> list[dict]:
    if session is not None:
        results = evaluate_alert_rules(session=session, organization_id=organization_id)
        return [result.__dict__ for result in results]
    with SessionLocal() as session:
        results = evaluate_alert_rules(session=session, organization_id=organization_id)
        session.commit()
        return [result.__dict__ for result in results]


def enqueue_local_alert_evaluation(
    *,
    organization_id: str | None = None,
    session: Session | None = None,
) -> str:
    if not is_local_runtime_profile():
        raise RuntimeError("local alert evaluation jobs require runtime_profile=local")
    if session is not None:
        job = RuntimeJobRepository(session).enqueue(
            kind="alert_evaluation",
            payload={"organization_id": organization_id},
            dedupe_key=f"alert-evaluation:{organization_id or 'global'}",
        )
        return job.id
    with SessionLocal.begin() as local_session:
        job = RuntimeJobRepository(local_session).enqueue(
            kind="alert_evaluation",
            payload={"organization_id": organization_id},
            dedupe_key=f"alert-evaluation:{organization_id or 'global'}",
        )
        return job.id


def evaluate_alerts_actor(organization_id: str | None = None) -> None:
    if is_local_runtime_profile():
        enqueue_local_alert_evaluation(organization_id=organization_id)
        return
    evaluate_alerts_once(organization_id=organization_id)


if not is_local_runtime_profile():
    evaluate_alerts_actor = register_server_actor(
        evaluate_alerts_actor,
        max_retries=0,
        queue_name="observability",
    )


def run_alert_evaluator_loop(
    *,
    interval_seconds: int = DEFAULT_ALERT_EVALUATOR_INTERVAL_SECONDS,
    organization_id: str | None = None,
) -> None:
    running = True

    def stop(_signum, _frame) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while running:
        if is_local_runtime_profile():
            enqueue_local_alert_evaluation(organization_id=organization_id)
        else:
            evaluate_alerts_once(organization_id=organization_id)
        time.sleep(interval_seconds)


if __name__ == "__main__":
    run_alert_evaluator_loop(
        interval_seconds=int(os.getenv("ALERT_EVALUATOR_INTERVAL_SECONDS", "60")),
        organization_id=os.getenv("ALERT_EVALUATOR_ORG_ID") or None,
    )
