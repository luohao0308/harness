from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from redis import Redis

from app.services.terminal_capability_store import (
    RedisTerminalCapabilityStore,
    TerminalSessionLimitReached,
)


@pytest.fixture(scope="module")
def redis_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    redis_server = shutil.which("redis-server")
    if redis_server is None:
        pytest.skip("redis-server is not installed")

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    data_dir = Path(tmp_path_factory.mktemp("terminal-capability-redis"))
    process = subprocess.Popen(
        [
            redis_server,
            "--bind",
            "127.0.0.1",
            "--port",
            str(port),
            "--save",
            "",
            "--appendonly",
            "no",
            "--dir",
            str(data_dir),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "LANG": "C", "LC_ALL": "C"},
    )
    url = f"redis://127.0.0.1:{port}/15"
    client = Redis.from_url(url)
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            if client.ping():
                break
        except Exception:
            time.sleep(0.05)
    else:
        process.terminate()
        process.wait(timeout=5)
        pytest.fail("temporary redis-server did not start")

    client.flushdb()
    try:
        yield url
    finally:
        client.flushdb()
        client.close()
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _store(redis_url: str, *, max_sessions: int = 4, lease_seconds: int = 60):
    return RedisTerminalCapabilityStore.from_url(
        redis_url,
        token_ttl_seconds=30,
        max_sessions=max_sessions,
        lease_seconds=lease_seconds,
    )


def test_redis_store_shares_one_time_tokens_across_instances(redis_url: str):
    issuer = _store(redis_url)
    consumer = _store(redis_url)
    record = issuer.issue_token(
        terminal_id="shared-terminal",
        user_id="user-1",
        organization_id="org-1",
        now=1000,
    )

    first = consumer.consume_and_reserve(
        token=record.token,
        terminal_id="shared-terminal",
        now=1001,
    )
    second = issuer.consume_and_reserve(
        token=record.token,
        terminal_id="shared-terminal",
        now=1001,
    )

    assert first is not None
    assert second is None
    consumer.release(first[1])


def test_redis_store_reserves_session_limit_atomically(redis_url: str):
    first_store = _store(redis_url, max_sessions=1)
    second_store = _store(redis_url, max_sessions=1)
    first_token = first_store.issue_token(
        terminal_id="terminal-1",
        user_id="user-2",
        organization_id="org-1",
        now=2000,
    )
    second_token = second_store.issue_token(
        terminal_id="terminal-2",
        user_id="user-2",
        organization_id="org-1",
        now=2000,
    )

    def consume(store, token, terminal_id):
        try:
            return store.consume_and_reserve(token=token, terminal_id=terminal_id, now=2001)
        except TerminalSessionLimitReached:
            return "limit"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda arguments: consume(*arguments),
                [
                    (first_store, first_token.token, first_token.terminal_id),
                    (second_store, second_token.token, second_token.terminal_id),
                ],
            )
        )

    reservations = [result for result in results if result != "limit"]
    assert len(reservations) == 1
    assert results.count("limit") == 1
    first_store.release(reservations[0][1])


def test_redis_store_reclaims_expired_session_lease(redis_url: str):
    store = _store(redis_url, max_sessions=1, lease_seconds=60)
    first_token = store.issue_token(
        terminal_id="terminal-1",
        user_id="user-3",
        organization_id="org-1",
        now=3000,
    )
    assert store.consume_and_reserve(
        token=first_token.token,
        terminal_id=first_token.terminal_id,
        now=3001,
    )

    with pytest.raises(TerminalSessionLimitReached):
        store.issue_token(
            terminal_id="terminal-2",
            user_id="user-3",
            organization_id="org-1",
            now=3050,
        )

    replacement = store.issue_token(
        terminal_id="terminal-2",
        user_id="user-3",
        organization_id="org-1",
        now=3062,
    )
    assert replacement.terminal_id == "terminal-2"


def test_redis_store_rejects_expired_or_terminal_mismatched_token(redis_url: str):
    store = _store(redis_url)
    expired = store.issue_token(
        terminal_id="terminal-1",
        user_id="user-4",
        organization_id="org-1",
        now=4000,
    )
    assert store.consume_and_reserve(
        token=expired.token,
        terminal_id="terminal-1",
        now=4031,
    ) is None

    mismatched = store.issue_token(
        terminal_id="terminal-1",
        user_id="user-4",
        organization_id="org-1",
        now=5000,
    )
    assert store.consume_and_reserve(
        token=mismatched.token,
        terminal_id="terminal-2",
        now=5001,
    ) is None
    assert store.consume_and_reserve(
        token=mismatched.token,
        terminal_id="terminal-1",
        now=5001,
    ) is None
