from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

from app.runtime_jobs.profile import is_local_runtime_profile


def register_server_actor(function: Callable[..., Any], **options: Any) -> Any:
    """Register a Dramatiq actor without importing server queue packages locally."""
    if is_local_runtime_profile():
        raise RuntimeError("Dramatiq actor registration is unavailable in the local profile")
    dramatiq = importlib.import_module("dramatiq")
    broker = importlib.import_module("app.workers.broker").broker
    return dramatiq.actor(broker=broker, **options)(function)
