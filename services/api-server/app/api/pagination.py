from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import Select, and_, or_
from sqlalchemy.orm.attributes import InstrumentedAttribute

from app.core.config import get_settings


@dataclass(frozen=True)
class CursorPage:
    items: list[Any]
    next_cursor: str | None


def encode_cursor(*, last_id: str, last_created_at: datetime | str) -> str:
    timestamp = (
        last_created_at.isoformat()
        if isinstance(last_created_at, datetime)
        else str(last_created_at)
    )
    payload = {"last_id": last_id, "last_created_at": timestamp}
    envelope = {"v": 1, "p": payload, "sig": _sign_payload(payload)}
    encoded = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
    return base64.urlsafe_b64encode(encoded.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(cursor: str | None) -> dict[str, str] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw_payload = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        envelope = json.loads(raw_payload)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination cursor") from exc
    if not isinstance(envelope, dict) or envelope.get("v") != 1:
        raise HTTPException(status_code=400, detail="Invalid pagination cursor")
    data = envelope.get("p")
    signature = envelope.get("sig")
    if (
        not isinstance(data, dict)
        or not isinstance(signature, str)
        or not data.get("last_id")
        or not data.get("last_created_at")
        or not hmac.compare_digest(signature, _sign_payload(data))
    ):
        raise HTTPException(status_code=400, detail="Invalid pagination cursor")
    return {"last_id": str(data["last_id"]), "last_created_at": str(data["last_created_at"])}


def cursor_paginate(
    *,
    session,
    statement: Select,
    model,
    cursor: str | None,
    limit: int,
    created_at_attr: str = "created_at",
    id_attr: str = "id",
    descending: bool = True,
) -> CursorPage:
    created_at_col: InstrumentedAttribute = getattr(model, created_at_attr)
    id_col: InstrumentedAttribute = getattr(model, id_attr)
    decoded = decode_cursor(cursor)
    if decoded is not None:
        last_created_at = _parse_datetime(decoded["last_created_at"])
        last_id = decoded["last_id"]
        if descending:
            statement = statement.where(
                or_(
                    created_at_col < last_created_at,
                    and_(created_at_col == last_created_at, id_col > last_id),
                )
            )
        else:
            statement = statement.where(
                or_(
                    created_at_col > last_created_at,
                    and_(created_at_col == last_created_at, id_col > last_id),
                )
            )
    order = created_at_col.desc() if descending else created_at_col.asc()
    rows = list(session.execute(statement.order_by(order, id_col.asc()).limit(limit + 1)).scalars())
    visible = rows[:limit]
    next_cursor = None
    if len(rows) > limit and visible:
        last = visible[-1]
        next_cursor = encode_cursor(
            last_id=str(getattr(last, id_attr)),
            last_created_at=getattr(last, created_at_attr),
        )
    return CursorPage(items=visible, next_cursor=next_cursor)


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination cursor") from exc


def _sign_payload(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    secret = get_settings().auth_jwt_secret.encode("utf-8")
    return hmac.new(secret, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
