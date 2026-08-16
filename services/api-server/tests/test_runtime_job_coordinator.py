from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker

from app.agents.orchestrator import MultiAgentOrchestrator
from app.agents.subagent_manager import SubagentManager
from app.core.config import Settings, clear_runtime_settings, install_runtime_settings
from app.db.models import (
    AgentAssignment,
    AgentRun,
    AlertEvent,
    AlertRule,
    Base,
    Organization,
    RuntimeJob,
    SubagentRecoveryBatch,
    Task,
    utc_now,
)
from app.runtime_jobs import handlers as runtime_job_handlers
from app.runtime_jobs.handlers import default_runtime_job_handlers
from app.runtime_jobs.profile import is_local_runtime_profile
from app.runtime_jobs.repository import RuntimeJobRepository
from app.runtime_jobs.scheduler import RuntimeJobCoordinator
from app.workers import alert_evaluator, subagent_recovery_worker


def _job_database(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'runtime-jobs.sqlite3'}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    RuntimeJob.__table__.create(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def test_active_dedupe_allows_new_job_after_completion(tmp_path) -> None:
    engine, sessions = _job_database(tmp_path)
    with sessions.begin() as session:
        repository = RuntimeJobRepository(session)
        first = repository.enqueue(kind="test", payload={"value": 1}, dedupe_key="same")
        duplicate = repository.enqueue(kind="test", payload={"value": 2}, dedupe_key="same")
        assert duplicate.id == first.id

    claim = RuntimeJobRepository.claim_next(
        engine,
        lease_owner="owner-1",
        lease_seconds=30,
    )
    assert claim is not None
    with sessions.begin() as session:
        assert RuntimeJobRepository(session).complete(claim, result_json={"ok": True})
        replacement = RuntimeJobRepository(session).enqueue(
            kind="test",
            payload={"value": 3},
            dedupe_key="same",
        )
        assert replacement.id != first.id


def test_begin_immediate_claims_one_job_once_across_threads(tmp_path) -> None:
    engine, sessions = _job_database(tmp_path)
    with sessions.begin() as session:
        RuntimeJobRepository(session).enqueue(kind="test", payload={})

    def claim(owner: str):
        return RuntimeJobRepository.claim_next(
            engine,
            lease_owner=owner,
            lease_seconds=30,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, ("owner-a", "owner-b")))
    claimed = [item for item in claims if item is not None]
    assert len(claimed) == 1
    assert claimed[0].attempt == 1
    assert claimed[0].lease_generation == 1


def test_expired_lease_is_reclaimed_and_stale_generation_is_fenced(tmp_path) -> None:
    engine, sessions = _job_database(tmp_path)
    started_at = utc_now()
    with sessions.begin() as session:
        RuntimeJobRepository(session).enqueue(
            kind="test",
            payload={},
            max_attempts=3,
            available_at=started_at,
        )

    first = RuntimeJobRepository.claim_next(
        engine,
        lease_owner="owner-1",
        lease_seconds=5,
        now=started_at,
    )
    second = RuntimeJobRepository.claim_next(
        engine,
        lease_owner="owner-2",
        lease_seconds=5,
        now=started_at + timedelta(seconds=6),
    )
    assert first is not None
    assert second is not None
    assert second.id == first.id
    assert second.attempt == 2
    assert second.lease_generation == 2

    with sessions.begin() as session:
        repository = RuntimeJobRepository(session)
        assert not repository.complete(first, result_json={"stale": True})
        assert repository.complete(second, result_json={"winner": "owner-2"})


def test_stale_claim_cannot_execute_authoritative_handler_effects(tmp_path) -> None:
    engine, sessions = _job_database(tmp_path)
    started_at = utc_now()
    with sessions.begin() as session:
        RuntimeJobRepository(session).enqueue(
            kind="test",
            payload={},
            max_attempts=3,
            available_at=started_at,
        )

    stale_claim = RuntimeJobRepository.claim_next(
        engine,
        lease_owner="owner-1",
        lease_seconds=1,
        now=started_at,
    )
    current_claim = RuntimeJobRepository.claim_next(
        engine,
        lease_owner="owner-2",
        lease_seconds=30,
        now=started_at + timedelta(seconds=2),
    )
    assert stale_claim is not None
    assert current_claim is not None

    handled = False

    def handler(_payload, session=None):
        nonlocal handled
        handled = True
        if session is None:
            with sessions.begin() as local_session:
                RuntimeJobRepository(local_session).enqueue(kind="authoritative-effect", payload={})
        else:
            RuntimeJobRepository(session).enqueue(kind="authoritative-effect", payload={})
        return {"ok": True}

    coordinator = RuntimeJobCoordinator(engine=engine, handlers={"test": handler})
    asyncio.run(coordinator._execute(stale_claim))

    with sessions() as session:
        effects = list(
            session.execute(
                select(RuntimeJob).where(RuntimeJob.kind == "authoritative-effect")
            ).scalars()
        )
        current = session.get(RuntimeJob, current_claim.id)
    assert handled is False
    assert effects == []
    assert current is not None
    assert current.status == "running"
    assert current.lease_owner == "owner-2"
    assert current.lease_generation == 2


def test_handler_effects_roll_back_when_completion_fence_is_rejected(tmp_path) -> None:
    engine, sessions = _job_database(tmp_path)
    with sessions.begin() as session:
        RuntimeJobRepository(session).enqueue(kind="test", payload={})
    claim = RuntimeJobRepository.claim_next(
        engine,
        lease_owner="owner-1",
        lease_seconds=30,
    )
    assert claim is not None

    def handler(_payload, session=None):
        if session is None:
            with sessions.begin() as local_session:
                RuntimeJobRepository(local_session).enqueue(kind="authoritative-effect", payload={})
                local_session.execute(
                    update(RuntimeJob)
                    .where(RuntimeJob.id == claim.id)
                    .values(lease_generation=claim.lease_generation + 1)
                )
        else:
            RuntimeJobRepository(session).enqueue(kind="authoritative-effect", payload={})
            session.commit()
            session.execute(
                update(RuntimeJob)
                .where(RuntimeJob.id == claim.id)
                .values(lease_generation=claim.lease_generation + 1)
            )
        return {"ok": True}

    coordinator = RuntimeJobCoordinator(engine=engine, handlers={"test": handler})
    asyncio.run(coordinator._execute(claim))

    with sessions() as session:
        effects = list(
            session.execute(
                select(RuntimeJob).where(RuntimeJob.kind == "authoritative-effect")
            ).scalars()
        )
        job = session.get(RuntimeJob, claim.id)
    assert effects == []
    assert job is not None
    assert job.status == "running"
    assert job.lease_generation == claim.lease_generation


def test_retry_cancel_and_startup_lease_recovery(tmp_path) -> None:
    engine, sessions = _job_database(tmp_path)
    now = utc_now()
    with sessions.begin() as session:
        retry_job = RuntimeJobRepository(session).enqueue(
            kind="retry",
            payload={},
            max_attempts=2,
            available_at=now,
        )
        cancel_job = RuntimeJobRepository(session).enqueue(
            kind="cancel",
            payload={},
            available_at=now,
        )

    retry_claim = RuntimeJobRepository.claim_next(
        engine,
        lease_owner="owner",
        lease_seconds=30,
        now=now,
    )
    assert retry_claim is not None
    with sessions.begin() as session:
        assert RuntimeJobRepository(session).fail(
            retry_claim,
            error="temporary",
            retry_delay_seconds=5,
            now=now,
        )
        assert RuntimeJobRepository(session).request_cancel(cancel_job.id, now=now)

    with sessions() as session:
        retried = session.get(RuntimeJob, retry_job.id)
        cancelled = session.get(RuntimeJob, cancel_job.id)
        assert retried is not None and retried.status == "queued"
        assert retried.error == "temporary"
        assert cancelled is not None and cancelled.status == "cancelled"

    second_claim = RuntimeJobRepository.claim_next(
        engine,
        lease_owner="owner",
        lease_seconds=1,
        now=now + timedelta(seconds=6),
    )
    assert second_claim is not None
    with sessions.begin() as session:
        recovered = RuntimeJobRepository(session).recover_expired(
            now=now + timedelta(seconds=8)
        )
        assert recovered == {"queued": 0, "failed": 1, "cancelled": 0}


def test_coordinator_executes_handler_and_persists_result(tmp_path) -> None:
    engine, sessions = _job_database(tmp_path)
    handled = asyncio.Event()

    def handler(payload, _session):
        handled.set()
        return {"echo": payload["value"]}

    async def run() -> None:
        with sessions.begin() as session:
            RuntimeJobRepository(session).enqueue(
                kind="test",
                payload={"value": 7},
                dedupe_key="test:7",
            )
        coordinator = RuntimeJobCoordinator(
            engine=engine,
            handlers={"test": handler},
            poll_interval_seconds=0.01,
            lease_seconds=1,
            heartbeat_interval_seconds=0.1,
        )
        await coordinator.start()
        await asyncio.wait_for(handled.wait(), timeout=1)
        for _ in range(100):
            with sessions() as session:
                job = session.execute(select(RuntimeJob)).scalar_one()
                if job.status == "succeeded":
                    assert job.result_json == {"echo": 7}
                    break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("runtime job did not finish")
        await coordinator.stop()

    asyncio.run(run())


def test_coordinator_seeds_all_local_periodic_jobs(tmp_path) -> None:
    engine, sessions = _job_database(tmp_path)

    def handler(_payload, _session):
        return {}

    coordinator = RuntimeJobCoordinator(
        engine=engine,
        handlers={
            "team_runtime_tick": handler,
            "alert_evaluation": handler,
            "subagent_recovery": handler,
        },
    )
    coordinator._seed_periodic_jobs()

    with sessions() as session:
        jobs = list(session.execute(select(RuntimeJob).order_by(RuntimeJob.kind)).scalars())
    assert [(job.kind, job.dedupe_key) for job in jobs] == [
        ("alert_evaluation", "alert-evaluation:global"),
        ("subagent_recovery", "subagent-recovery"),
        ("team_runtime_tick", "team-runtime-tick"),
    ]


def test_default_runtime_handlers_cover_every_local_periodic_actor() -> None:
    assert set(default_runtime_job_handlers()) >= {
        "agent_assignment",
        "subagent",
        "team_runtime_tick",
        "alert_evaluation",
        "subagent_recovery",
    }


def test_local_periodic_alert_handler_evaluates_every_local_organization(
    db_session,
    monkeypatch,
) -> None:
    db_session.add_all(
        [
            Organization(id="org-a", name="Org A", slug="org-a"),
            Organization(id="org-b", name="Org B", slug="org-b"),
        ]
    )
    db_session.flush()
    evaluated: list[str | None] = []

    def evaluate_once(*, organization_id=None, session=None):
        assert session is db_session
        evaluated.append(organization_id)
        return [{"organization_id": organization_id}]

    monkeypatch.setattr(alert_evaluator, "evaluate_alerts_once", evaluate_once)

    result = runtime_job_handlers.evaluate_alerts({}, db_session)

    assert evaluated == ["org-a", "org-b"]
    assert result == {
        "evaluations": [
            {"organization_id": "org-a"},
            {"organization_id": "org-b"},
        ]
    }


def test_default_periodic_handlers_commit_effects_with_job_completion(tmp_path) -> None:
    database_path = tmp_path / "full-runtime.sqlite3"
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        RUNTIME_PROFILE="local",
        RUNTIME_DATA_DIR=tmp_path,
        DATABASE_URL=f"sqlite+pysqlite:///{database_path}",
        API_BASE_URL="http://127.0.0.1:8000",
    )
    install_runtime_settings(settings)
    try:
        with sessions.begin() as session:
            session.add(Organization(id="local-org", name="Local", slug="local"))
            session.add(
                AlertRule(
                    id="local-alert",
                    organization_id="local-org",
                    name="always active",
                    metric="eval_regression_triggered",
                    comparator=">=",
                    threshold=0,
                    window_seconds=300,
                    enabled=True,
                    severity="warning",
                    notification_channels_json=["in_app"],
                )
            )
            repository = RuntimeJobRepository(session)
            repository.enqueue(
                kind="alert_evaluation",
                payload={"organization_id": "local-org"},
            )
            repository.enqueue(kind="subagent_recovery", payload={"enqueue": False})

        coordinator = RuntimeJobCoordinator(engine=engine)
        for _ in range(2):
            claim = RuntimeJobRepository.claim_next(
                engine,
                lease_owner=coordinator.owner,
                lease_seconds=30,
            )
            assert claim is not None
            asyncio.run(coordinator._execute(claim))

        with sessions() as session:
            jobs = list(session.execute(select(RuntimeJob)).scalars())
            alerts = list(session.execute(select(AlertEvent)).scalars())
            recoveries = list(session.execute(select(SubagentRecoveryBatch)).scalars())
        assert {job.status for job in jobs} == {"succeeded"}
        assert len(alerts) == 1
        assert alerts[0].rule_id == "local-alert"
        assert len(recoveries) == 1
        assert recoveries[0].lock_acquired is True
    finally:
        clear_runtime_settings()
        engine.dispose()


def test_local_periodic_actors_route_to_sqlite_jobs(monkeypatch, tmp_path) -> None:
    settings = Settings(
        RUNTIME_PROFILE="local",
        RUNTIME_DATA_DIR=tmp_path,
        DATABASE_URL=f"sqlite+pysqlite:///{tmp_path / 'harness.sqlite3'}",
        API_BASE_URL="http://127.0.0.1:8000",
    )
    install_runtime_settings(settings)
    routed: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        alert_evaluator,
        "enqueue_local_alert_evaluation",
        lambda **payload: routed.append(("alert", payload)),
    )
    monkeypatch.setattr(
        subagent_recovery_worker,
        "enqueue_local_subagent_recovery",
        lambda **payload: routed.append(("recovery", payload)),
    )
    monkeypatch.setattr(
        alert_evaluator,
        "evaluate_alerts_once",
        lambda **_payload: (_ for _ in ()).throw(AssertionError("direct alert execution")),
    )
    monkeypatch.setattr(
        subagent_recovery_worker,
        "recover_stalled_subagents",
        lambda **_payload: (_ for _ in ()).throw(AssertionError("direct recovery execution")),
    )
    try:
        alert_evaluator.evaluate_alerts_actor.fn("local-org")
        subagent_recovery_worker.recover_stalled_subagents_actor.fn(120, False)
    finally:
        clear_runtime_settings()

    assert routed == [
        ("alert", {"organization_id": "local-org"}),
        ("recovery", {"stale_after_seconds": 120, "enqueue": False}),
    ]


def test_server_periodic_actors_retain_direct_worker_execution(monkeypatch, tmp_path) -> None:
    settings = Settings(
        RUNTIME_PROFILE="server",
        RUNTIME_DATA_DIR=tmp_path,
        DATABASE_URL=f"sqlite+pysqlite:///{tmp_path / 'harness.sqlite3'}",
        API_BASE_URL="http://127.0.0.1:8000",
    )
    install_runtime_settings(settings)
    executed: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        alert_evaluator,
        "evaluate_alerts_once",
        lambda **payload: executed.append(("alert", payload)),
    )
    monkeypatch.setattr(
        subagent_recovery_worker,
        "recover_stalled_subagents",
        lambda **payload: executed.append(("recovery", payload)),
    )
    monkeypatch.setattr(
        alert_evaluator,
        "enqueue_local_alert_evaluation",
        lambda **_payload: (_ for _ in ()).throw(AssertionError("local alert route")),
    )
    monkeypatch.setattr(
        subagent_recovery_worker,
        "enqueue_local_subagent_recovery",
        lambda **_payload: (_ for _ in ()).throw(AssertionError("local recovery route")),
    )
    try:
        alert_evaluator.evaluate_alerts_actor.fn("server-org")
        subagent_recovery_worker.recover_stalled_subagents_actor.fn(300, True)
    finally:
        clear_runtime_settings()

    assert executed == [
        ("alert", {"organization_id": "server-org"}),
        ("recovery", {"stale_after_seconds": 300, "enqueue": True}),
    ]


def test_local_runtime_profile_uses_installed_settings(tmp_path) -> None:
    settings = Settings(
        RUNTIME_PROFILE="local",
        RUNTIME_DATA_DIR=tmp_path,
        DATABASE_URL=f"sqlite+pysqlite:///{tmp_path / 'harness.sqlite3'}",
        API_BASE_URL="http://127.0.0.1:8000",
    )
    install_runtime_settings(settings)
    try:
        assert is_local_runtime_profile()
        assert is_local_runtime_profile(settings)
    finally:
        clear_runtime_settings()


def test_local_assignment_and_subagent_enqueue_use_runtime_jobs(
    db_session,
    tmp_path,
) -> None:
    settings = Settings(
        RUNTIME_PROFILE="local",
        RUNTIME_DATA_DIR=tmp_path,
        DATABASE_URL=f"sqlite+pysqlite:///{tmp_path / 'harness.sqlite3'}",
        API_BASE_URL="http://127.0.0.1:8000",
    )
    install_runtime_settings(settings)
    try:
        run = Task(
            id="run-local",
            title="Local routing",
            goal="local coordinator routing",
            model_provider="test",
            model_name="test",
        )
        db_session.add(run)
        db_session.flush()
        assignment = AgentAssignment(
            id="assignment-local",
            run_id=run.id,
            agent_id="default",
            role="generalist",
            status="QUEUED",
        )
        MultiAgentOrchestrator(db_session)._enqueue_assignment(
            run=run,
            assignment=assignment,
        )
        SubagentManager(db_session)._enqueue(
            agent_run=AgentRun(
                id="subagent-local",
                task_id=run.id,
                agent_type="specialist",
                status="PENDING",
            ),
            task_id=run.id,
            stage="queued",
        )
        jobs = list(
            db_session.execute(select(RuntimeJob).order_by(RuntimeJob.kind)).scalars()
        )
        assert [(job.kind, job.dedupe_key) for job in jobs] == [
            ("agent_assignment", "agent-assignment:assignment-local"),
            ("subagent", "subagent:subagent-local"),
        ]
    finally:
        clear_runtime_settings()
