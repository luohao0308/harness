from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]


def _run_import_probe(script: str, *, runtime_profile: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "RUNTIME_PROFILE": runtime_profile,
        "DATABASE_URL": "sqlite+pysqlite:///:memory:",
        "APP_ENV": "test",
        "AUTH_JWT_SECRET": "test-harness-jwt-secret-32-characters-min",
        "DEEPSEEK_API_KEY": "",
    }
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=SERVICE_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_local_core_routes_and_job_workers_import_without_server_queue_packages() -> None:
    completed = _run_import_probe(
        """
        import importlib
        import importlib.abc
        import sys

        from app.core.config import Settings, install_runtime_settings

        install_runtime_settings(Settings(
            RUNTIME_PROFILE="local",
            RUNTIME_DATA_DIR="/tmp/harness-local-import-probe",
            DATABASE_URL="sqlite+pysqlite:///:memory:",
            API_BASE_URL="http://127.0.0.1:8000",
        ))

        class RejectServerQueuePackages(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname.split(".", 1)[0] in {"dramatiq", "redis"}:
                    raise ModuleNotFoundError(fullname)
                return None

        sys.meta_path.insert(0, RejectServerQueuePackages())
        for module_name in (
            "app.api.agents",
            "app.api.tasks",
            "app.api.teams",
            "app.api.subagents",
            "app.runtime_jobs.handlers",
        ):
            importlib.import_module(module_name)

        assert "app.workers.subagent_worker" not in sys.modules
        for module_name in (
            "app.workers.agent_assignment_worker",
            "app.workers.subagent_worker",
            "app.workers.team_runtime_worker",
            "app.workers.alert_evaluator",
            "app.workers.subagent_recovery_worker",
            "app.workers.trigger_invocation_worker",
        ):
            importlib.import_module(module_name)

        from app.runtime_jobs.handlers import default_runtime_job_handlers
        assert set(default_runtime_job_handlers()) == {
            "agent_assignment",
            "subagent",
            "team_runtime_tick",
            "alert_evaluation",
                "subagent_recovery",
                "trigger_source_poll",
                "trigger_invocation",
        }
        assert not any(
            name.split(".", 1)[0] in {"dramatiq", "redis"}
            for name in sys.modules
        )
        """,
        runtime_profile="local",
    )

    assert completed.returncode == 0, completed.stderr


def test_server_worker_modules_still_register_dramatiq_actors() -> None:
    completed = _run_import_probe(
        """
        from app.workers.agent_assignment_worker import run_agent_assignment
        from app.workers.alert_evaluator import evaluate_alerts_actor
        from app.workers.subagent_recovery_worker import recover_stalled_subagents_actor
        from app.workers.subagent_worker import run_subagent
        from app.workers.trigger_invocation_worker import run_trigger_invocation

        actors = (
            (run_agent_assignment, "run_agent_assignment", "agent_assignments"),
            (run_subagent, "run_subagent", "subagents"),
            (evaluate_alerts_actor, "evaluate_alerts_actor", "observability"),
            (recover_stalled_subagents_actor, "recover_stalled_subagents_actor", "subagents"),
        )
        for actor, actor_name, queue_name in actors:
            assert hasattr(actor, "fn")
            assert hasattr(actor, "send")
            assert actor.actor_name == actor_name
            assert actor.queue_name == queue_name
            assert actor.options["max_retries"] == 0
        assert run_subagent.options["time_limit"] == 900_000
        assert hasattr(run_trigger_invocation, "fn")
        assert hasattr(run_trigger_invocation, "send")
        assert run_trigger_invocation.actor_name == "run_trigger_invocation"
        assert run_trigger_invocation.queue_name == "triggers"
        assert run_trigger_invocation.options["max_retries"] == 10_000
        """,
        runtime_profile="server",
    )

    assert completed.returncode == 0, completed.stderr
