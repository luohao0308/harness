import base64
import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.pagination import decode_cursor, encode_cursor
from app.db.models import Task
from app.main import app
from tests.conftest import AUTH_HEADERS


def test_agent_runs_cursor_pagination_has_no_duplicates(db_session: Session) -> None:
    base = datetime(2026, 5, 29, 8, 0, tzinfo=UTC)
    for index in range(25):
        db_session.add(
            Task(
                id=f"run-{index:02d}",
                organization_id="dev-org",
                agent_id="default",
                created_by="dev-engineer",
                title=f"Run {index:02d}",
                goal="cursor pagination proof",
                status="COMPLETED",
                model_provider="default",
                model_name="default",
                created_at=base + timedelta(minutes=index),
                updated_at=base + timedelta(minutes=index),
            )
        )
    db_session.commit()

    client = TestClient(app)
    seen: list[str] = []
    cursor: str | None = None
    for _page in range(3):
        params = {"limit": "10"}
        if cursor is not None:
            params["cursor"] = cursor
        response = client.get("/api/agents/runs", headers=AUTH_HEADERS, params=params)
        assert response.status_code == 200
        payload = response.json()
        seen.extend(item["id"] for item in payload["items"])
        cursor = payload["next_cursor"]

    assert len(seen) == 25
    assert len(set(seen)) == 25
    assert seen[:3] == ["run-24", "run-23", "run-22"]
    assert cursor is None


def test_invalid_cursor_returns_400() -> None:
    response = TestClient(app).get(
        "/api/agents/runs",
        headers=AUTH_HEADERS,
        params={"cursor": "not-valid"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid pagination cursor"


def test_cursor_round_trip_encodes_position() -> None:
    encoded = encode_cursor(last_id="run-1", last_created_at="2026-05-29T08:00:00+00:00")

    assert decode_cursor(encoded) == {
        "last_id": "run-1",
        "last_created_at": "2026-05-29T08:00:00+00:00",
    }


def test_tampered_cursor_returns_400() -> None:
    encoded = encode_cursor(last_id="run-1", last_created_at="2026-05-29T08:00:00+00:00")
    padded = encoded + "=" * (-len(encoded) % 4)
    envelope = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    envelope["p"]["last_id"] = "run-2"
    tampered = (
        base64.urlsafe_b64encode(json.dumps(envelope).encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )

    response = TestClient(app).get(
        "/api/agents/runs",
        headers=AUTH_HEADERS,
        params={"cursor": tampered},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid pagination cursor"
