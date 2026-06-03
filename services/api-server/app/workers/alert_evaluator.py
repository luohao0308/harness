from __future__ import annotations

import os
import signal
import time

import dramatiq

from app.db.session import SessionLocal
from app.observability.alert_evaluator import evaluate_alert_rules
from app.workers.broker import broker

DEFAULT_ALERT_EVALUATOR_INTERVAL_SECONDS = 60


def evaluate_alerts_once(*, organization_id: str | None = None) -> list[dict]:
    with SessionLocal() as session:
        results = evaluate_alert_rules(session=session, organization_id=organization_id)
        session.commit()
        return [result.__dict__ for result in results]


@dramatiq.actor(broker=broker, max_retries=0, queue_name="observability")
def evaluate_alerts_actor(organization_id: str | None = None) -> None:
    evaluate_alerts_once(organization_id=organization_id)


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
        evaluate_alerts_once(organization_id=organization_id)
        time.sleep(interval_seconds)


if __name__ == "__main__":
    run_alert_evaluator_loop(
        interval_seconds=int(os.getenv("ALERT_EVALUATOR_INTERVAL_SECONDS", "60")),
        organization_id=os.getenv("ALERT_EVALUATOR_ORG_ID") or None,
    )
