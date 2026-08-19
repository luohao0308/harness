import asyncio
import threading
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, clear_runtime_settings, install_runtime_settings
from app.db.models import Agent, Base, RuntimeJob, Task, Trigger, TriggerInvocation, utc_now
from app.runtime_jobs import handlers as runtime_job_handlers
from app.runtime_jobs.repository import RuntimeJobRepository
from app.runtime_jobs.scheduler import RuntimeJobCoordinator
from app.triggers import sources as trigger_sources
from app.triggers.sources import next_schedule_state, scan_files, scan_git, schedule_due
from app.workers import trigger_source_worker


def test_schedule_interval_and_disabled_kill_switch() -> None:
    trigger = {"enabled": True, "interval_seconds": 10}
    assert not schedule_due(trigger, {}, now=100)
    state = next_schedule_state(trigger, now=100)
    assert state == {"last_run_at": None, "next_run_at": 110}
    assert not schedule_due(trigger, state, now=109.9)
    assert schedule_due(trigger, state, now=110)
    assert next_schedule_state(trigger, state, now=135) == {
        "last_run_at": 135,
        "last_scheduled_at": 110,
        "next_run_at": 140,
    }
    assert not schedule_due({**trigger, "enabled": False}, {}, now=100)


def test_file_initial_snapshot_is_silent_then_emits_content_change(tmp_path: Path) -> None:
    watched = tmp_path / "watched.txt"
    watched.write_text("one")
    trigger = {"enabled": True, "workspace_root": str(tmp_path), "pattern": "**/*.txt"}
    events, state = scan_files(trigger)
    assert events == []
    watched.write_text("two")
    events, updated = scan_files(trigger, previous=state)
    assert len(events) == 1
    assert events[0].metadata["path"] == "watched.txt"
    assert updated["snapshot"] != state["snapshot"]


def test_file_scanner_rejects_missing_root_and_symlink(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-trigger-test.txt"
    outside.write_text("secret")
    link = tmp_path / "link.txt"
    link.symlink_to(outside)
    events, state = scan_files({"enabled": True, "workspace_root": str(tmp_path)})
    assert events == []
    assert state["snapshot"] == {}


def test_git_initial_state_silent_and_uses_observation_identity(tmp_path: Path) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Trigger Test"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("one")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "one"], cwd=tmp_path, check=True)
    trigger = {"enabled": True, "workspace_root": str(tmp_path)}
    events, state = scan_git(trigger)
    assert events == []
    (tmp_path / "a.txt").write_text("two")
    subprocess.run(["git", "commit", "-qam", "two"], cwd=tmp_path, check=True)
    events, _ = scan_git(trigger, previous=state)
    assert len(events) == 1
    assert events[0].metadata["head"]
    assert str(tmp_path) not in events[0].source_key


def test_file_scanner_emits_delete_without_leaking_absolute_root(tmp_path: Path) -> None:
    watched = tmp_path / "watched.txt"
    watched.write_text("one")
    trigger = {"enabled": True, "workspace_root": str(tmp_path)}
    _, state = scan_files(trigger)
    watched.unlink()

    events, updated = scan_files(trigger, previous=state)

    assert len(events) == 1
    assert events[0].metadata["path"] == "watched.txt"
    assert events[0].metadata["change_type"] == "deleted"
    assert events[0].metadata["changed_count"] == 1
    assert str(tmp_path) not in events[0].source_key
    assert updated == {"snapshot": {}, "generation": 1, "initialized": True}


def test_file_scanner_does_not_treat_truncation_as_deletion(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    trigger = {"enabled": True, "workspace_root": str(tmp_path), "max_files": 10}
    _, state = scan_files(trigger)

    events, updated = scan_files({**trigger, "max_files": 1}, previous=state)

    assert all(event.metadata.get("change_type") != "deleted" for event in events)
    assert updated == state


def test_file_scanner_keeps_multi_pass_initial_baseline_silent(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a")
    second = tmp_path / "b.txt"
    second.write_text("b")
    trigger = {"enabled": True, "workspace_root": str(tmp_path), "max_files": 1}

    events, partial = scan_files(trigger)
    assert events == []
    assert partial["initialized"] is False

    events, baseline = scan_files({**trigger, "max_files": 10}, previous=partial)
    assert events == []
    assert baseline["initialized"] is True
    second.write_text("changed")
    events, _ = scan_files({**trigger, "max_files": 10}, previous=baseline)
    assert len(events) == 1


def test_file_scanner_repeated_transition_gets_new_persisted_generation(
    tmp_path: Path,
) -> None:
    watched = tmp_path / "watched.txt"
    watched.write_text("a")
    trigger = {"enabled": True, "workspace_root": str(tmp_path)}
    _, state = scan_files(trigger)
    watched.write_text("b")
    first_b, state = scan_files(trigger, previous=state)
    watched.write_text("a")
    _, state = scan_files(trigger, previous=state)
    watched.write_text("b")
    second_b, state = scan_files(trigger, previous=state)

    assert first_b[0].identity != second_b[0].identity
    assert state["generation"] == 3


def test_large_unchanged_directory_reuses_persisted_hashes(
    tmp_path: Path, monkeypatch
) -> None:
    for index in range(300):
        (tmp_path / f"file-{index:04d}.txt").write_text(f"content-{index}")
    trigger = {
        "enabled": True,
        "workspace_root": str(tmp_path),
        "pattern": "*.txt",
        "max_files": 500,
        "max_duration_seconds": 5,
    }
    original_hash_file = trigger_sources._hash_file
    hashed: list[str] = []

    def counting_hash(path, **kwargs):
        hashed.append(path.name)
        return original_hash_file(path, **kwargs)

    monkeypatch.setattr(trigger_sources, "_hash_file", counting_hash)
    _, state = scan_files(trigger)
    assert len(hashed) == 300
    hashed.clear()

    events, unchanged = scan_files(trigger, previous=state)

    assert events == []
    assert hashed == []
    assert unchanged == state


def test_large_file_change_batch_emits_one_bounded_observation(tmp_path: Path) -> None:
    files = [tmp_path / f"file-{index:03d}.txt" for index in range(100)]
    for path in files:
        path.write_text("before")
    trigger = {
        "enabled": True,
        "workspace_root": str(tmp_path),
        "pattern": "*.txt",
        "max_files": 200,
        "max_duration_seconds": 5,
    }
    _, state = scan_files(trigger)
    for path in files:
        path.write_text("after")

    observations, updated = scan_files(trigger, previous=state)

    assert len(observations) == 1
    metadata = observations[0].metadata
    assert metadata["change_type"] == "batch"
    assert metadata["changed_count"] == 100
    assert len(metadata["changed_paths"]) == 20
    assert len(metadata["changes_sha256"]) == 64
    assert metadata["truncated"] is True
    assert updated["generation"] == 1


def test_git_scanner_rejects_repo_outside_workspace(tmp_path: Path) -> None:
    outside = tmp_path.parent
    events, state = scan_git(
        {
            "enabled": True,
            "workspace_root": str(tmp_path),
            "repo_root": str(outside),
        }
    )
    assert events == []
    assert state == {}


def test_git_branch_filter_establishes_silent_baseline_before_observing(
    tmp_path: Path,
) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=tmp_path, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Trigger Test"], cwd=tmp_path, check=True
    )
    (tmp_path / "a.txt").write_text("one")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "one"], cwd=tmp_path, check=True)
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    mismatched = {
        "enabled": True,
        "repo_root": str(tmp_path),
        "branch": "not-the-current-branch",
    }
    events, state = scan_git(mismatched)
    assert events == []
    assert state["branch_matched"] is False

    matched = {**mismatched, "branch": branch}
    events, state = scan_git(matched, previous=state)
    assert events == []
    (tmp_path / "a.txt").write_text("two")
    subprocess.run(["git", "commit", "-qam", "two"], cwd=tmp_path, check=True)
    events, _ = scan_git(matched, previous=state)
    assert len(events) == 1


def test_schedule_poller_persists_cursor_and_enqueues_one_job_per_due_slot(
    db_session, monkeypatch
) -> None:
    trigger = Trigger(
        id="schedule-trigger",
        organization_id="local-org",
        agent_id="default",
        type="schedule",
        name="Every ten seconds",
        config_json={"interval_seconds": 10},
        runtime_state_json={},
        enabled=True,
    )
    db_session.add(trigger)
    db_session.flush()
    created_keys: list[str] = []

    def create_invocation(*, observation, **_kwargs):
        created_keys.append(observation.dedupe_key)
        return SimpleNamespace(id=f"invocation-{len(created_keys)}"), True

    monkeypatch.setattr(trigger_source_worker, "local_triggers_enabled", lambda: True)
    monkeypatch.setattr(trigger_source_worker, "_create_invocation", create_invocation)

    initial = trigger_source_worker.poll_local_trigger_sources({}, session=db_session, now=100)
    db_session.commit()
    assert initial["enqueued"] == 0
    assert trigger.runtime_state_json == {
        "last_run_at": None,
        "next_run_at": 110,
        "_poll": {"last_polled_at": 100},
    }

    before_due = trigger_source_worker.poll_local_trigger_sources({}, session=db_session, now=109)
    due = trigger_source_worker.poll_local_trigger_sources({}, session=db_session, now=110)
    duplicate_poll = trigger_source_worker.poll_local_trigger_sources(
        {}, session=db_session, now=110
    )
    late = trigger_source_worker.poll_local_trigger_sources({}, session=db_session, now=145)

    assert before_due["enqueued"] == 0
    assert due["enqueued"] == 1
    assert duplicate_poll["enqueued"] == 0
    assert late["enqueued"] == 1
    assert len(created_keys) == len(set(created_keys)) == 2
    assert trigger.runtime_state_json["last_scheduled_at"] == 120
    assert trigger.runtime_state_json["next_run_at"] == 150
    jobs = list(
        db_session.execute(
            select(RuntimeJob).where(RuntimeJob.kind == "trigger_invocation")
        ).scalars()
    )
    assert [job.payload["invocation_id"] for job in jobs] == [
        "invocation-1",
        "invocation-2",
    ]


def test_multiple_file_triggers_rotate_persisted_poll_cursor(
    db_session, monkeypatch
) -> None:
    triggers = [
        Trigger(
            id=f"file-trigger-{suffix}",
            organization_id="local-org",
            agent_id="default",
            type="file",
            name=f"File {suffix}",
            config_json={"workspace_root": f"/workspace/{suffix}"},
            runtime_state_json={},
            enabled=True,
        )
        for suffix in ("a", "b", "c")
    ]
    db_session.add_all(triggers)
    db_session.flush()
    polled: list[str] = []

    def observe(*, trigger_id, previous, **_kwargs):
        polled.append(trigger_id)
        return [], previous

    monkeypatch.setattr(trigger_source_worker, "local_triggers_enabled", lambda: True)
    monkeypatch.setattr(trigger_source_worker, "_observe_trigger", observe)
    for now in (100, 101, 102):
        result = trigger_source_worker.poll_local_trigger_sources(
            {"max_triggers_per_poll": 1},
            session=db_session,
            now=now,
        )
        db_session.flush()
        assert result["processed"] == 1
        assert result["deferred"] == 2

    assert polled == ["file-trigger-a", "file-trigger-b", "file-trigger-c"]
    assert all(trigger.runtime_state_json.get("_poll") for trigger in triggers)


def test_source_poller_is_disabled_in_server_profile(db_session, tmp_path: Path) -> None:
    settings = Settings(
        RUNTIME_PROFILE="server",
        RUNTIME_DATA_DIR=tmp_path,
        DATABASE_URL=f"sqlite+pysqlite:///{tmp_path / 'server.sqlite3'}",
        API_BASE_URL="http://127.0.0.1:8000",
        TRIGGER_AUTOMATION_ENABLED=True,
    )
    install_runtime_settings(settings)
    try:
        result = trigger_source_worker.poll_local_trigger_sources({}, session=db_session, now=100)
    finally:
        clear_runtime_settings()
    assert result == {"status": "disabled", "observed": 0, "enqueued": 0}


def test_schedule_poller_creates_one_persisted_invocation_and_planned_run(
    db_session, tmp_path: Path
) -> None:
    settings = Settings(
        RUNTIME_PROFILE="local",
        RUNTIME_DATA_DIR=tmp_path,
        DATABASE_URL=f"sqlite+pysqlite:///{tmp_path / 'local.sqlite3'}",
        API_BASE_URL="http://127.0.0.1:8000",
        TRIGGER_AUTOMATION_ENABLED=True,
    )
    install_runtime_settings(settings)
    agent = Agent(
        id="scheduled-agent",
        organization_id="local-org",
        name="Scheduled Agent",
        description="",
        role="generalist",
        model_provider="mock",
        model_name="mock-model",
        system_prompt="Handle scheduled work.",
    )
    trigger = Trigger(
        id="persisted-schedule-trigger",
        organization_id="local-org",
        agent_id=agent.id,
        type="schedule",
        name="Scheduled work",
        config_json={"interval_seconds": 10, "goal": "Run scheduled work"},
        runtime_state_json={},
        enabled=True,
    )
    db_session.add_all([agent, trigger])
    db_session.flush()
    try:
        first = trigger_source_worker.poll_local_trigger_sources(
            {}, session=db_session, now=100
        )
        db_session.commit()
        due = trigger_source_worker.poll_local_trigger_sources(
            {}, session=db_session, now=110
        )
        db_session.flush()
    finally:
        clear_runtime_settings()

    invocations = list(db_session.execute(select(TriggerInvocation)).scalars())
    runs = list(db_session.execute(select(Task)).scalars())
    jobs = list(
        db_session.execute(
            select(RuntimeJob).where(RuntimeJob.kind == "trigger_invocation")
        ).scalars()
    )
    assert first["enqueued"] == 0
    assert due["enqueued"] == 1
    assert len(invocations) == len(runs) == len(jobs) == 1
    assert invocations[0].run_id == runs[0].id
    assert invocations[0].payload_summary_json == {
        "scheduled_at": 110.0,
        "interval_seconds": 10.0,
    }
    assert runs[0].status == "PLANNED"
    assert runs[0].goal == (
        'Run scheduled work\n\nTrigger source: '
        '{"interval_seconds":10.0,"scheduled_at":110.0}'
    )
    assert jobs[0].payload["invocation_id"] == invocations[0].id
    assert jobs[0].payload["expires_at"]


def test_git_poller_supports_repo_root_contract_and_initial_snapshot_is_silent(
    db_session, tmp_path: Path
) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=tmp_path, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Trigger Test"], cwd=tmp_path, check=True
    )
    (tmp_path / "a.txt").write_text("one")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "one"], cwd=tmp_path, check=True)
    settings = Settings(
        RUNTIME_PROFILE="local",
        RUNTIME_DATA_DIR=tmp_path / "runtime",
        DATABASE_URL=f"sqlite+pysqlite:///{tmp_path / 'local.sqlite3'}",
        API_BASE_URL="http://127.0.0.1:8000",
        TRIGGER_AUTOMATION_ENABLED=True,
    )
    install_runtime_settings(settings)
    agent = Agent(
        id="git-agent",
        organization_id="local-org",
        name="Git Agent",
        description="",
        role="generalist",
        model_provider="mock",
        model_name="mock-model",
        system_prompt="Handle Git changes.",
    )
    trigger = Trigger(
        id="git-trigger",
        organization_id="local-org",
        agent_id=agent.id,
        type="git",
        name="Git changes",
        config_json={"repo_root": str(tmp_path)},
        runtime_state_json={},
        enabled=True,
    )
    db_session.add_all([agent, trigger])
    db_session.flush()
    try:
        initial = trigger_source_worker.poll_local_trigger_sources(
            {}, session=db_session, now=100
        )
        db_session.commit()
        (tmp_path / "a.txt").write_text("two")
        subprocess.run(["git", "commit", "-qam", "two"], cwd=tmp_path, check=True)
        changed = trigger_source_worker.poll_local_trigger_sources(
            {}, session=db_session, now=101
        )
    finally:
        clear_runtime_settings()

    assert initial["enqueued"] == 0
    assert changed["enqueued"] == 1
    assert db_session.execute(select(TriggerInvocation)).scalar_one().run_id is not None


def test_execution_handler_rechecks_disabled_trigger(db_session, tmp_path: Path) -> None:
    settings = Settings(
        RUNTIME_PROFILE="local",
        RUNTIME_DATA_DIR=tmp_path,
        DATABASE_URL=f"sqlite+pysqlite:///{tmp_path / 'local.sqlite3'}",
        API_BASE_URL="http://127.0.0.1:8000",
        TRIGGER_AUTOMATION_ENABLED=True,
    )
    install_runtime_settings(settings)
    trigger = Trigger(
        id="disabled-trigger",
        organization_id="local-org",
        agent_id="default",
        type="schedule",
        config_json={"interval_seconds": 10},
        enabled=False,
    )
    run = Task(
        id="disabled-run",
        organization_id="local-org",
        agent_id="default",
        title="Disabled trigger run",
        goal="Must not execute",
        status="PLANNED",
        model_provider="mock",
        model_name="mock",
    )
    invocation = TriggerInvocation(
        id="disabled-invocation",
        trigger_id=trigger.id,
        organization_id="local-org",
        idempotency_key="due-slot",
        status="PLANNED",
        run_id=run.id,
    )
    db_session.add_all([trigger, run, invocation])
    db_session.flush()
    try:
        result = runtime_job_handlers.execute_trigger_invocation(
            {"invocation_id": invocation.id}, db_session
        )
    finally:
        clear_runtime_settings()
    assert result["status"] == "DISABLED"
    assert result["invocation_id"] == invocation.id
    assert invocation.status == "DISABLED"
    assert invocation.error == "Trigger automation is disabled"
    assert invocation.completed_at is not None
    assert run.status == "CANCELLED"
    assert run.completed_at is not None


def test_kill_switch_defers_invocation_without_consuming_attempt(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'paused-trigger.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        RUNTIME_PROFILE="local",
        RUNTIME_DATA_DIR=tmp_path,
        DATABASE_URL=f"sqlite+pysqlite:///{tmp_path / 'paused-trigger.sqlite3'}",
        API_BASE_URL="http://127.0.0.1:8000",
        TRIGGER_AUTOMATION_ENABLED=False,
    )
    install_runtime_settings(settings)
    try:
        with sessions.begin() as session:
            trigger = Trigger(
                id="paused-trigger",
                organization_id="local-org",
                agent_id="default",
                type="schedule",
                config_json={"interval_seconds": 10},
                enabled=True,
            )
            invocation = TriggerInvocation(
                id="paused-invocation",
                trigger_id=trigger.id,
                organization_id="local-org",
                status="PLANNED",
                attempt=1,
            )
            session.add_all([trigger, invocation])
            job = RuntimeJobRepository(session).enqueue(
                kind="trigger_invocation",
                payload={"invocation_id": invocation.id},
                max_attempts=2,
            )
        coordinator = RuntimeJobCoordinator(
            engine=engine,
            handlers={"trigger_invocation": runtime_job_handlers.execute_trigger_invocation},
        )
        claim = RuntimeJobRepository.claim_next(
            engine,
            lease_owner=coordinator.owner,
            lease_seconds=30,
        )
        assert claim is not None
        asyncio.run(coordinator._execute(claim))
    finally:
        clear_runtime_settings()

    with sessions() as session:
        deferred = session.get(RuntimeJob, job.id)
        invocation = session.get(TriggerInvocation, "paused-invocation")
        assert deferred is not None and deferred.status == "queued"
        assert deferred.attempt == 0
        assert deferred.error == "Trigger automation is paused"
        assert invocation is not None and invocation.status == "PLANNED"
        assert invocation.attempt == 1
        assert invocation.completed_at is None


def test_default_coordinator_registers_trigger_poll_and_execution(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'runtime.sqlite3'}")
    coordinator = RuntimeJobCoordinator(engine=engine)
    assert "trigger_source_poll" in coordinator.handlers
    assert "trigger_invocation" in coordinator.handlers
    assert any(job.kind == "trigger_source_poll" for job in coordinator._periodic_jobs)


def test_trigger_job_retry_updates_same_invocation_and_exhaustion_fails(
    tmp_path: Path,
) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'trigger-retry.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    run = Task(
        id="same-run",
        title="Scheduled run",
        goal="Run once",
        model_provider="mock",
        model_name="mock",
    )
    retrying = TriggerInvocation(
        id="retrying-invocation",
        trigger_id="retry-trigger",
        organization_id="local-org",
        idempotency_key="one-slot",
        status="PLANNED",
        run_id=run.id,
    )
    exhausted = TriggerInvocation(
        id="exhausted-invocation",
        trigger_id="retry-trigger",
        organization_id="local-org",
        idempotency_key="another-slot",
        status="PLANNED",
        run_id=run.id,
    )
    with sessions.begin() as session:
        session.add_all([run, retrying, exhausted])
        repository = RuntimeJobRepository(session)
        repository.enqueue(
            kind="trigger_invocation",
            payload={"invocation_id": retrying.id},
            max_attempts=2,
        )

    seen: list[tuple[str, int]] = []

    def succeeds_on_retry(payload, session):
        invocation = session.get(TriggerInvocation, payload["invocation_id"])
        checkpointed_run = session.get(Task, run.id)
        assert invocation is not None
        assert checkpointed_run is not None
        seen.append((invocation.id, payload["_runtime_attempt"]))
        if payload["_runtime_attempt"] == 1:
            checkpointed_run.title = "checkpointed once"
            session.info["runtime_job_step_checkpoint"]()
            raise RuntimeError("temporary executor outage")
        assert checkpointed_run.title == "checkpointed once"
        invocation.status = "SUCCEEDED"
        return {"status": "SUCCEEDED"}

    coordinator = RuntimeJobCoordinator(
        engine=engine,
        handlers={"trigger_invocation": succeeds_on_retry},
    )
    first = RuntimeJobRepository.claim_next(
        engine, lease_owner=coordinator.owner, lease_seconds=30
    )
    assert first is not None
    asyncio.run(coordinator._execute(first))
    with sessions() as session:
        job = session.get(RuntimeJob, first.id)
        invocation = session.get(TriggerInvocation, retrying.id)
        assert job is not None and job.status == "queued"
        assert invocation is not None and invocation.status == "PLANNED"
        assert invocation.attempt == 1
        assert invocation.error == "Trigger execution attempt 1 failed"
        assert invocation.run_id == run.id
        assert job.error == "temporary executor outage"

    second = RuntimeJobRepository.claim_next(
        engine,
        lease_owner=coordinator.owner,
        lease_seconds=30,
        now=utc_now() + timedelta(seconds=2),
    )
    assert second is not None and second.id == first.id
    asyncio.run(coordinator._execute(second))
    with sessions.begin() as session:
        job = session.get(RuntimeJob, first.id)
        invocation = session.get(TriggerInvocation, retrying.id)
        assert job is not None and job.status == "succeeded"
        assert invocation is not None and invocation.status == "SUCCEEDED"
        assert invocation.run_id == run.id
        RuntimeJobRepository(session).enqueue(
            kind="trigger_invocation",
            payload={"invocation_id": exhausted.id},
            max_attempts=2,
        )

    def always_fails(_payload, _session):
        raise RuntimeError("permanent executor outage")

    failing = RuntimeJobCoordinator(
        engine=engine,
        handlers={"trigger_invocation": always_fails},
    )
    exhausted_first = RuntimeJobRepository.claim_next(
        engine, lease_owner=failing.owner, lease_seconds=30
    )
    assert exhausted_first is not None
    asyncio.run(failing._execute(exhausted_first))
    exhausted_second = RuntimeJobRepository.claim_next(
        engine,
        lease_owner=failing.owner,
        lease_seconds=30,
        now=utc_now() + timedelta(seconds=2),
    )
    assert exhausted_second is not None
    asyncio.run(failing._execute(exhausted_second))
    with sessions() as session:
        job = session.get(RuntimeJob, exhausted_first.id)
        invocation = session.get(TriggerInvocation, exhausted.id)
        assert job is not None and job.status == "failed"
        assert invocation is not None and invocation.status == "FAILED"
        assert invocation.attempt == 2
        assert invocation.completed_at is not None
        assert invocation.error == "Trigger execution attempt 2 failed"
        assert job.error == "permanent executor outage"

    assert seen == [(retrying.id, 1), (retrying.id, 2)]


@pytest.mark.parametrize("safety_action", ["disable", "cancel"])
def test_slow_trigger_step_does_not_block_safety_write_and_never_starts_next_step(
    tmp_path: Path,
    monkeypatch,
    safety_action: str,
) -> None:
    from app.triggers import service as trigger_service

    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / f'slow-{safety_action}.sqlite3'}",
        connect_args={"check_same_thread": False, "timeout": 1},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        RUNTIME_PROFILE="local",
        RUNTIME_DATA_DIR=tmp_path,
        DATABASE_URL=str(engine.url),
        API_BASE_URL="http://127.0.0.1:8000",
        TRIGGER_AUTOMATION_ENABLED=True,
    )
    install_runtime_settings(settings)
    with sessions.begin() as session:
        run = Task(
            id=f"slow-{safety_action}-run",
            organization_id="local-org",
            agent_id="default",
            title="Slow trigger run",
            goal="Execute one slow step",
            status="PLANNED",
            model_provider="mock",
            model_name="mock",
            max_runtime_seconds=300,
        )
        trigger = Trigger(
            id=f"slow-{safety_action}-trigger",
            organization_id="local-org",
            agent_id="default",
            type="schedule",
            name="Slow trigger",
            config_json={"interval_seconds": 60},
            enabled=True,
        )
        invocation = TriggerInvocation(
            id=f"slow-{safety_action}-invocation",
            trigger_id=trigger.id,
            organization_id="local-org",
            status="PLANNED",
            run_id=run.id,
        )
        session.add_all([run, trigger, invocation])

    step_started = threading.Event()
    release_step = threading.Event()
    mutation_done = threading.Event()
    executed_steps: list[str] = []
    worker_errors: list[BaseException] = []

    class SlowExecutor:
        def __init__(self, session, *, step_checkpoint=None, step_guard=None, **_kwargs) -> None:
            self.session = session
            self.step_checkpoint = step_checkpoint
            self.step_guard = step_guard
            self.workspace_root = tmp_path

        def execute_existing_plan(self, task):
            assert self.step_guard is not None and self.step_checkpoint is not None
            self.step_guard()
            step_started.set()
            assert release_step.wait(3)
            executed_steps.append("first")
            self.step_checkpoint()
            self.step_guard()
            executed_steps.append("second")
            task.status = "COMPLETED"
            return task

    monkeypatch.setattr(trigger_service, "Executor", SlowExecutor)

    def execute() -> None:
        try:
            with sessions() as session:
                trigger_service.execute_trigger_invocation(
                    invocation_id=invocation.id,
                    session=session,
                    lease_owner="slow-worker",
                )
                session.commit()
        except BaseException as exc:  # pragma: no cover - surfaced by assertion below
            worker_errors.append(exc)

    def apply_safety_action() -> None:
        with sessions.begin() as session:
            if safety_action == "disable":
                current_trigger = session.get(Trigger, trigger.id)
                assert current_trigger is not None
                current_trigger.enabled = False
            else:
                current_run = session.get(Task, run.id)
                assert current_run is not None
                current_run.status = "CANCELLED"
                current_run.completed_at = utc_now()
        mutation_done.set()

    worker = threading.Thread(target=execute)
    worker.start()
    try:
        assert step_started.wait(3)
        mutator = threading.Thread(target=apply_safety_action)
        mutator.start()
        assert mutation_done.wait(1), "safety write was blocked by a slow Trigger step"
        release_step.set()
        mutator.join(timeout=3)
        worker.join(timeout=5)
    finally:
        release_step.set()
        clear_runtime_settings()

    assert not worker.is_alive()
    assert worker_errors == []
    assert executed_steps == ["first"]
    with sessions() as session:
        stored_run = session.get(Task, run.id)
        stored_invocation = session.get(TriggerInvocation, invocation.id)
        assert stored_run is not None and stored_run.status == "CANCELLED"
        assert stored_invocation is not None
        assert stored_invocation.status == ("DISABLED" if safety_action == "disable" else "FAILED")
