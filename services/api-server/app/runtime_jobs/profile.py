from __future__ import annotations

import os
from typing import Any

LOCAL_RUNTIME_PROFILE = "local"


def is_local_runtime_profile(settings: Any | None = None) -> bool:
    if settings is None:
        try:
            from app.core.config import get_settings

            settings = get_settings()
        except Exception:
            settings = None
    configured = getattr(settings, "runtime_profile", None)
    if configured is None:
        configured = os.getenv("RUNTIME_PROFILE", os.getenv("HARNESS_RUNTIME_PROFILE", ""))
    return str(configured).strip().lower() == LOCAL_RUNTIME_PROFILE
