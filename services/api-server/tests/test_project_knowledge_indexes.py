from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.db.models import (
    AdminAuditEvent,
    CitationRecord,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
    ProjectKnowledgeFile,
    ProjectKnowledgeIndex,
    utc_now,
)
from app.knowledge import ground_query
from app.main import app
from tests.conftest import AUTH_HEADERS

OTHER_ORG_HEADERS = {"Authorization": "Bearer dev-other-org-token"}
ROOT_IDENTITY = "a" * 64


def _payload(**overrides) -> dict:
    payload = {
        "name": "Harness project",
        "description": "Local project knowledge",
        "desktop_profile_id": "profile-main",
        "root_identity": ROOT_IDENTITY,
        "ignore_patterns": ["coverage/**", "tmp/*.log", "coverage/**"],
        "idempotency_key": "project-index-main",
    }
    payload.update(overrides)
    return payload


def _snapshot_file(relative_path: str, content: str) -> dict:
    raw = content.encode("utf-8")
    return {
        "relative_path": relative_path,
        "status": "ready",
        "content": content,
        "content_sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "modified_at": "2026-08-18T12:00:00Z",
        "mime_type": "text/markdown",
        "skip_reason": None,
    }


def _snapshot_payload(
    *,
    cursor: str,
    files: list[dict],
    complete: bool = True,
    started_at: str = "2026-08-18T12:00:00Z",
    schema_version: str = "desktop-project-knowledge-snapshot-v1",
) -> dict:
    total_bytes = sum(item["size_bytes"] for item in files if item["status"] == "ready")
    return {
        "schema_version": schema_version,
        "default_ignore_version": "v1",
        "desktop_profile_id": "profile-main",
        "root_identity": ROOT_IDENTITY,
        "snapshot_cursor": cursor,
        "complete": complete,
        "truncated": not complete,
        "truncation_reason": None if complete else "scan_error",
        "files": files,
        "errors": [] if complete else [{"path": "nested", "reason": "directory_read_failed"}],
        "scanned_files": len(files),
        "indexed_files": sum(item["status"] == "ready" for item in files),
        "total_bytes": total_bytes,
        "started_at": started_at,
        "completed_at": started_at,
    }


def test_project_index_create_is_scoped_idempotent_and_path_free(
    db_session: Session,
) -> None:
    client = TestClient(app)

    created = client.post(
        "/api/agents/default/knowledge/project-indexes",
        headers=AUTH_HEADERS,
        json=_payload(),
    )

    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "ACTIVE"
    assert body["root_identity"] == ROOT_IDENTITY
    assert body["desktop_profile_id"] == "profile-main"
    assert body["ignore_patterns"] == ["coverage/**", "tmp/*.log"]
    assert body["file_count"] == 0
    assert "root_path" not in body
    assert "/Users/" not in created.text

    retried = client.post(
        "/api/agents/default/knowledge/project-indexes",
        headers=AUTH_HEADERS,
        json=_payload(),
    )
    assert retried.status_code == 201
    assert retried.json()["id"] == body["id"]
    assert retried.json()["knowledge_source_id"] == body["knowledge_source_id"]

    index = db_session.get(ProjectKnowledgeIndex, body["id"])
    source = db_session.get(KnowledgeSource, body["knowledge_source_id"])
    assert index is not None
    assert source is not None
    assert source.source_type == "project"
    assert source.metadata_json["project_index"] == {
        "index_id": index.id,
        "desktop_profile_id": "profile-main",
        "root_identity": ROOT_IDENTITY,
    }
    assert all(
        "path" not in column["name"]
        for column in inspect(db_session.bind).get_columns("project_knowledge_indexes")
    )

    other_org = client.get(
        f"/api/agents/default/knowledge/project-indexes/{index.id}",
        headers=OTHER_ORG_HEADERS,
    )
    assert other_org.status_code == 404
    assert client.get(
        "/api/agents/default/knowledge/project-indexes",
        headers=OTHER_ORG_HEADERS,
    ).json() == {"items": []}


def test_project_index_rejects_path_input_and_conflicting_idempotency() -> None:
    client = TestClient(app)

    with_path = client.post(
        "/api/agents/default/knowledge/project-indexes",
        headers=AUTH_HEADERS,
        json={**_payload(), "root_path": "/Users/example/private-project"},
    )
    assert with_path.status_code == 422

    invalid_identity = client.post(
        "/api/agents/default/knowledge/project-indexes",
        headers=AUTH_HEADERS,
        json=_payload(root_identity="/Users/example/private-project"),
    )
    assert invalid_identity.status_code == 422

    invalid_ignore = client.post(
        "/api/agents/default/knowledge/project-indexes",
        headers=AUTH_HEADERS,
        json=_payload(ignore_patterns=["../private/**"]),
    )
    assert invalid_ignore.status_code == 422

    assert (
        client.post(
            "/api/agents/default/knowledge/project-indexes",
            headers=AUTH_HEADERS,
            json=_payload(),
        ).status_code
        == 201
    )
    conflict = client.post(
        "/api/agents/default/knowledge/project-indexes",
        headers=AUTH_HEADERS,
        json=_payload(root_identity="b" * 64),
    )
    assert conflict.status_code == 409
    assert "another project root" in conflict.json()["detail"]


def test_project_index_lifecycle_archives_source_and_preserves_receipts(
    db_session: Session,
) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/knowledge/project-indexes",
        headers=AUTH_HEADERS,
        json=_payload(),
    )
    assert created.status_code == 201
    body = created.json()
    index_id = body["id"]
    source_id = body["knowledge_source_id"]

    file_receipt = ProjectKnowledgeFile(
        index_id=index_id,
        relative_path="docs/README.md",
        path_sha256=hashlib.sha256(b"docs/README.md").hexdigest(),
        content_sha256=hashlib.sha256(b"content").hexdigest(),
        size_bytes=7,
        mime_type="text/markdown",
        status="INDEXED",
        last_seen_generation=1,
        last_scanned_at=utc_now(),
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(file_receipt)
    db_session.commit()

    detail = client.get(
        f"/api/agents/default/knowledge/project-indexes/{index_id}",
        headers=AUTH_HEADERS,
    )
    assert detail.status_code == 200
    assert detail.json()["file_count"] == 1
    assert detail.json()["indexed_file_count"] == 1

    paused = client.post(
        f"/api/agents/default/knowledge/project-indexes/{index_id}/pause",
        headers=AUTH_HEADERS,
        json={"reason": "battery saver"},
    )
    assert paused.status_code == 200
    assert paused.json()["status"] == "PAUSED"
    assert db_session.get(KnowledgeSource, source_id).status == "DISABLED"

    resumed = client.post(
        f"/api/agents/default/knowledge/project-indexes/{index_id}/resume",
        headers=AUTH_HEADERS,
        json={"reason": "back online"},
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "ACTIVE"
    assert db_session.get(KnowledgeSource, source_id).status == "ACTIVE"

    generic_update = client.patch(
        f"/api/agents/default/knowledge/sources/{source_id}",
        headers=AUTH_HEADERS,
        json={"name": "bypass"},
    )
    assert generic_update.status_code == 409

    unbound = client.post(
        f"/api/agents/default/knowledge/project-indexes/{index_id}/unbind",
        headers=AUTH_HEADERS,
        json={"reason": "workspace removed"},
    )
    assert unbound.status_code == 200
    assert unbound.json()["status"] == "UNBOUND"
    assert unbound.json()["unbound_at"] is not None
    source = db_session.get(KnowledgeSource, source_id)
    assert source is not None
    assert source.status == "ARCHIVED"
    assert source.archived_at is not None
    assert db_session.get(ProjectKnowledgeFile, file_receipt.id) is not None

    resume_unbound = client.post(
        f"/api/agents/default/knowledge/project-indexes/{index_id}/resume",
        headers=AUTH_HEADERS,
        json={},
    )
    assert resume_unbound.status_code == 409

    generic_delete = client.delete(
        f"/api/agents/default/knowledge/sources/{source_id}",
        headers=AUTH_HEADERS,
    )
    assert generic_delete.status_code == 409

    actions = list(
        db_session.execute(
            select(AdminAuditEvent.action)
            .where(AdminAuditEvent.resource_id == index_id)
            .order_by(AdminAuditEvent.created_at.asc())
        ).scalars()
    )
    assert actions == ["created", "paused", "resumed", "unbound"]


def test_project_snapshot_sync_versions_tombstones_and_preserves_citations(
    db_session: Session,
) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/knowledge/project-indexes",
        headers=AUTH_HEADERS,
        json=_payload(),
    )
    assert created.status_code == 201
    index_id = created.json()["id"]
    source_id = created.json()["knowledge_source_id"]
    content_a_v1 = ("orion anchor local fact. " + "alpha " * 120 + "\n") * 2
    content_b = ("orion anchor secondary fact. " + "beta " * 120 + "\n") * 2
    files_v1 = [
        _snapshot_file("docs/a.md", content_a_v1),
        _snapshot_file("docs/b.md", content_b),
    ]

    first = client.post(
        f"/api/agents/default/knowledge/project-indexes/{index_id}/sync",
        headers=AUTH_HEADERS,
        json=_snapshot_payload(cursor="1" * 64, files=files_v1),
    )
    assert first.status_code == 200
    assert first.json()["status"] == "ACTIVE"
    assert first.json()["indexed_file_count"] == 2
    assert first.json()["snapshot_generation"] == 1

    receipts = list(
        db_session.execute(
            select(ProjectKnowledgeFile)
            .where(ProjectKnowledgeFile.index_id == index_id)
            .order_by(ProjectKnowledgeFile.relative_path)
        ).scalars()
    )
    assert [receipt.status for receipt in receipts] == ["INDEXED", "INDEXED"]
    documents = list(
        db_session.execute(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.source_id == source_id)
            .order_by(KnowledgeDocument.uri)
        ).scalars()
    )
    assert [document.uri for document in documents] == [
        "project://docs/a.md",
        "project://docs/b.md",
    ]
    assert documents[0].metadata_json["relative_path"] == "docs/a.md"
    assert documents[0].metadata_json["file_content_sha256"] == files_v1[0]["content_sha256"]
    assert "/Users/" not in str(documents[0].metadata_json)

    idempotent = client.post(
        f"/api/agents/default/knowledge/project-indexes/{index_id}/sync",
        headers=AUTH_HEADERS,
        json=_snapshot_payload(cursor="1" * 64, files=files_v1),
    )
    assert idempotent.status_code == 200
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(KnowledgeDocument.source_id == source_id)
        )
        == 2
    )

    content_a_v2 = content_a_v1.replace("local fact", "updated local fact")
    files_v2 = [_snapshot_file("docs/a.md", content_a_v2), files_v1[1]]
    modified = client.post(
        f"/api/agents/default/knowledge/project-indexes/{index_id}/sync",
        headers=AUTH_HEADERS,
        json=_snapshot_payload(
            cursor="2" * 64,
            files=files_v2,
            started_at="2026-08-18T12:01:00Z",
        ),
    )
    assert modified.status_code == 200
    receipt_a = db_session.execute(
        select(ProjectKnowledgeFile).where(
            ProjectKnowledgeFile.index_id == index_id,
            ProjectKnowledgeFile.relative_path == "docs/a.md",
        )
    ).scalar_one()
    assert receipt_a.document_version == 2
    assert (
        db_session.scalar(
            select(func.count()).select_from(KnowledgeChunk).where(KnowledgeChunk.status == "STALE")
        )
        >= 1
    )

    grounding = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=None,
        query="orion anchor",
    )
    db_session.flush()
    assert grounding.citations
    citation = db_session.get(CitationRecord, grounding.citations[0].id)
    assert citation is not None
    source_snapshot = citation.metadata_json["source_snapshot"]
    assert source_snapshot["project_uri"].startswith("project://docs/")
    assert source_snapshot["project_relative_path"].startswith("docs/")
    assert len(source_snapshot["project_file_sha256"]) == 64
    assert source_snapshot["document_version"] in {1, 2}

    incomplete = client.post(
        f"/api/agents/default/knowledge/project-indexes/{index_id}/sync",
        headers=AUTH_HEADERS,
        json=_snapshot_payload(
            cursor="3" * 64,
            files=[_snapshot_file("docs/a.md", content_a_v2)],
            complete=False,
            started_at="2026-08-18T12:02:00Z",
        ),
    )
    assert incomplete.status_code == 200
    assert incomplete.json()["status"] == "ERROR"
    receipt_b = db_session.execute(
        select(ProjectKnowledgeFile).where(
            ProjectKnowledgeFile.index_id == index_id,
            ProjectKnowledgeFile.relative_path == "docs/b.md",
        )
    ).scalar_one()
    assert receipt_b.status == "INDEXED"

    complete_delete = client.post(
        f"/api/agents/default/knowledge/project-indexes/{index_id}/sync",
        headers=AUTH_HEADERS,
        json=_snapshot_payload(
            cursor="4" * 64,
            files=[_snapshot_file("docs/a.md", content_a_v2)],
            started_at="2026-08-18T12:03:00Z",
        ),
    )
    assert complete_delete.status_code == 200
    db_session.refresh(receipt_b)
    assert receipt_b.status == "TOMBSTONED"
    assert receipt_b.tombstoned_at is not None
    deleted_document = db_session.get(KnowledgeDocument, receipt_b.knowledge_document_id)
    assert deleted_document is not None
    assert deleted_document.status == "SUPERSEDED"
    assert db_session.get(CitationRecord, citation.id) is not None


def test_project_snapshot_sync_is_monotonic_and_keeps_last_complete_cursor(
    db_session: Session,
) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/knowledge/project-indexes",
        headers=AUTH_HEADERS,
        json=_payload(),
    )
    index_id = created.json()["id"]
    source_id = created.json()["knowledge_source_id"]
    current = client.post(
        f"/api/agents/default/knowledge/project-indexes/{index_id}/sync",
        headers=AUTH_HEADERS,
        json=_snapshot_payload(
            cursor="a" * 64,
            files=[_snapshot_file("README.md", "current")],
            started_at="2026-08-18T12:02:00Z",
            schema_version="desktop-project-knowledge-snapshot-v2",
        ),
    )
    assert current.status_code == 200

    stale = client.post(
        f"/api/agents/default/knowledge/project-indexes/{index_id}/sync",
        headers=AUTH_HEADERS,
        json=_snapshot_payload(
            cursor="b" * 64,
            files=[_snapshot_file("README.md", "stale")],
            started_at="2026-08-18T12:01:00Z",
        ),
    )
    assert stale.status_code == 200
    assert stale.json()["snapshot_cursor"] == "a" * 64

    conflict = client.post(
        f"/api/agents/default/knowledge/project-indexes/{index_id}/sync",
        headers=AUTH_HEADERS,
        json=_snapshot_payload(
            cursor="c" * 64,
            files=[_snapshot_file("README.md", "conflict")],
            started_at="2026-08-18T12:02:00Z",
        ),
    )
    assert conflict.status_code == 409

    incomplete = client.post(
        f"/api/agents/default/knowledge/project-indexes/{index_id}/sync",
        headers=AUTH_HEADERS,
        json=_snapshot_payload(
            cursor="d" * 64,
            files=[_snapshot_file("README.md", "current")],
            complete=False,
            started_at="2026-08-18T12:03:00Z",
        ),
    )
    assert incomplete.status_code == 200
    assert incomplete.json()["snapshot_cursor"] == "a" * 64
    assert incomplete.json()["snapshot_generation"] == 1
    source = db_session.get(KnowledgeSource, source_id)
    assert source is not None
    metadata = source.metadata_json["project_index"]
    assert metadata["snapshot_cursor"] == "a" * 64
    assert metadata["snapshot_generation"] == 1


def test_project_snapshot_sync_rejects_binding_mismatch_and_path_traversal() -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/knowledge/project-indexes",
        headers=AUTH_HEADERS,
        json=_payload(),
    )
    index_id = created.json()["id"]
    valid_file = _snapshot_file("README.md", "project facts")

    mismatch = client.post(
        f"/api/agents/default/knowledge/project-indexes/{index_id}/sync",
        headers=AUTH_HEADERS,
        json={
            **_snapshot_payload(cursor="5" * 64, files=[valid_file]),
            "desktop_profile_id": "profile-other",
        },
    )
    assert mismatch.status_code == 409

    traversal_file = {**valid_file, "relative_path": "../outside.md"}
    traversal = client.post(
        f"/api/agents/default/knowledge/project-indexes/{index_id}/sync",
        headers=AUTH_HEADERS,
        json=_snapshot_payload(cursor="6" * 64, files=[traversal_file]),
    )
    assert traversal.status_code == 422
