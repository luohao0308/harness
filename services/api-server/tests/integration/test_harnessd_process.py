from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Queue


def test_harnessd_process_ready_health_secret_redaction_and_sigterm(tmp_path: Path) -> None:
    canary = "harnessd-integration-model-secret-canary-123456789"
    bootstrap = {
        "runtime_data_dir": str(tmp_path),
        "session_signing_secret": "integration-session-secret-at-least-32-characters",
        "vault_encryption_secret": "integration-vault-secret-at-least-32-characters",
        "desktop_bootstrap_token": "integration-desktop-token-at-least-32-characters",
        "model_api_key": canary,
    }
    packaged_executable = os.environ.get("HARNESSD_TEST_EXECUTABLE")
    command = (
        [
            packaged_executable,
            "--static-dir",
            str(Path(__file__).resolve().parents[4] / "apps" / "agent-console" / "dist"),
        ]
        if packaged_executable
        else [sys.executable, "-m", "app.cli.harnessd"]
    )
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    process.stdin.write(json.dumps(bootstrap))
    process.stdin.close()
    process.stdin = None

    ready_lines: Queue[str] = Queue()
    reader = threading.Thread(
        target=lambda: ready_lines.put(process.stdout.readline()),
        daemon=True,
    )
    reader.start()
    reader.join(timeout=30)
    if reader.is_alive():
        process.kill()
        _, stderr = process.communicate(timeout=5)
        raise AssertionError(f"harnessd did not emit readiness within 30s: {stderr}")

    ready_line = ready_lines.get_nowait()
    if not ready_line:
        stderr = process.stderr.read()
        process.wait(timeout=5)
        raise AssertionError(
            f"harnessd exited before readiness (code={process.returncode}): {stderr}"
        )
    ready = json.loads(ready_line)
    assert ready["protocol_version"] == 1
    assert ready["origin"].startswith("http://127.0.0.1:")
    assert ready["health_path"] == "/api/health/readiness"
    assert ready["desktop_session_path"] == "/api/local-runtime/desktop-session"
    assert ready["renderer_path"] == "/desktop/"

    with urllib.request.urlopen(f"{ready['origin']}/health", timeout=10) as response:
        assert response.status == 200
        assert json.loads(response.read())["status"] == "ok"
    with urllib.request.urlopen(
        f"{ready['origin']}{ready['health_path']}", timeout=10
    ) as response:
        readiness = json.loads(response.read())
        assert response.status == 200
        assert readiness["profile"] == "local"
        assert readiness["db"] == {"status": "ok"}
        assert readiness["runtime_ready"] is True
        assert readiness["ready"] is True

    session_request = urllib.request.Request(
        f"{ready['origin']}{ready['desktop_session_path']}",
        headers={
            "X-Harness-Desktop-Bootstrap": bootstrap["desktop_bootstrap_token"],
        },
        method="POST",
    )
    with urllib.request.urlopen(session_request, timeout=10) as response:
        assert response.status == 204
        cookie = response.headers["set-cookie"].split(";", 1)[0]

    concurrent_paths = (
        "/openapi.json",
        "/api/settings/models",
        "/api/settings/models/pricing-sources",
        "/api/teams",
        "/api/tools/registry",
        "/api/agents",
    )

    def fetch(path: str) -> tuple[int, dict | None]:
        request = urllib.request.Request(
            f"{ready['origin']}{path}",
            headers={"Cookie": cookie},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = response.read()
            parsed = json.loads(payload) if path.endswith("/pricing-sources") else None
            return response.status, parsed

    with ThreadPoolExecutor(max_workers=len(concurrent_paths)) as pool:
        results = list(pool.map(fetch, concurrent_paths))
    assert [status for status, _payload in results] == [200] * len(concurrent_paths)
    pricing_payload = results[concurrent_paths.index("/api/settings/models/pricing-sources")][1]
    assert pricing_payload is not None
    assert pricing_payload["schema_version"] == "model_pricing_sources.v1"
    assert pricing_payload["items"]

    with urllib.request.urlopen(f"{ready['origin']}/desktop/", timeout=10) as response:
        assert response.status == 200
        assert "default-src 'self'" in response.headers["Content-Security-Policy"]
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"

    for path in (
        "/api/agents",
        "/api/tasks",
        "/api/teams",
        "/api/tools/registry",
        "/api/tasks/route-probe/events",
        "/api/subagents",
        "/api/evals/datasets",
        "/api/observability/summary",
    ):
        try:
            urllib.request.urlopen(f"{ready['origin']}{path}", timeout=10)
        except urllib.error.HTTPError as exc:
            assert exc.code != 404, f"core local route is missing: {path}"

    foreign_origin_request = urllib.request.Request(
        f"{ready['origin']}/health",
        headers={"Origin": "https://attacker.invalid"},
    )
    try:
        urllib.request.urlopen(foreign_origin_request, timeout=10)
    except urllib.error.HTTPError as exc:
        assert exc.code == 404
    else:
        raise AssertionError("harnessd accepted a foreign Origin")

    if os.name == "nt":
        process.terminate()
    else:
        process.send_signal(signal.SIGTERM)
    stdout_tail, stderr = process.communicate(timeout=15)

    assert process.returncode == 0
    assert stdout_tail == ""
    evidence = stderr + (tmp_path / "logs" / "harnessd.jsonl").read_text(encoding="utf-8")
    for candidate in (tmp_path / "harness.sqlite3", tmp_path / "harness.sqlite3-wal"):
        if candidate.exists():
            evidence += candidate.read_bytes().decode("utf-8", errors="ignore")
    assert canary not in evidence
