from __future__ import annotations

from datetime import datetime, timedelta

from app.db.models import utc_now

DEFAULT_SUBAGENT_TIMEOUT_SECONDS = 900


def timeout_at_from_now(
    timeout_seconds: int = DEFAULT_SUBAGENT_TIMEOUT_SECONDS,
) -> datetime:
    return utc_now() + timedelta(seconds=timeout_seconds)
