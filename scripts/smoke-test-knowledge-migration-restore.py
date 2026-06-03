#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_SERVER_DIR = REPO_ROOT / "services" / "api-server"
REQUIRED_TABLES = (
    "knowledge_sources",
    "knowledge_documents",
    "knowledge_chunks",
    "knowledge_embeddings",
    "retrieval_sessions",
    "retrieval_hits",
    "citation_records",
    "prompt_assembly_manifests",
    "knowledge_policy_audits",
    "admin_audit_events",
)

SMOKE_CODE = r"""
import hashlib
import json
import os

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.db.models import (
    Agent,
    CitationRecord,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
    RetrievalHit,
    RetrievalSession,
    Task,
    utc_now,
)

database_url = os.environ["DATABASE_URL"]
required_tables = json.loads(os.environ["P7_REQUIRED_TABLES"])
engine = create_engine(database_url)
inspector = inspect(engine)
tables = set(inspector.get_table_names())
missing = sorted(set(required_tables) - tables)
if missing:
    raise AssertionError(f"missing tables after alembic upgrade: {missing}")

ids = {
    "agent": "p7-smoke-agent",
    "task": "p7000000-0000-4000-8000-000000000001",
    "source": "p7000000-0000-4000-8000-000000000002",
    "document": "p7000000-0000-4000-8000-000000000003",
    "chunk": "p7000000-0000-4000-8000-000000000004",
    "retrieval": "p7000000-0000-4000-8000-000000000005",
    "hit": "p7000000-0000-4000-8000-000000000006",
    "citation": "p7000000-0000-4000-8000-000000000007",
}
now = utc_now()
content = "P7 migration restore smoke selector continuity beacon"
sha = hashlib.sha256(content.encode("utf-8")).hexdigest()

with Session(engine) as session:
    session.query(CitationRecord).filter(CitationRecord.id == ids["citation"]).delete()
    session.query(RetrievalHit).filter(RetrievalHit.id == ids["hit"]).delete()
    session.query(RetrievalSession).filter(RetrievalSession.id == ids["retrieval"]).delete()
    session.query(KnowledgeChunk).filter(KnowledgeChunk.id == ids["chunk"]).delete()
    session.query(KnowledgeDocument).filter(KnowledgeDocument.id == ids["document"]).delete()
    session.query(KnowledgeSource).filter(KnowledgeSource.id == ids["source"]).delete()
    session.query(Task).filter(Task.id == ids["task"]).delete()
    session.query(Agent).filter(Agent.id == ids["agent"]).delete()
    session.commit()

    session.add(
        Agent(
            id=ids["agent"],
            organization_id="dev-org",
            name="P7 Smoke Agent",
            description="Service-level migration smoke agent",
            role="verifier",
            status="ACTIVE",
            model_provider="default",
            model_name="default",
            system_prompt="Verify P7 migration smoke evidence.",
            tools_json=[],
            routing_tags=["p7-smoke"],
            max_parallel_assignments=1,
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        Task(
            id=ids["task"],
            organization_id="dev-org",
            agent_id=ids["agent"],
            created_by="p7-smoke",
            title="P7 Knowledge Migration Restore Smoke",
            goal="Verify selector continuity after migration and restore.",
            status="COMPLETED",
            model_provider="default",
            model_name="default",
            capability_snapshot_json={},
            created_at=now,
            updated_at=now,
            completed_at=now,
        )
    )
    session.add(
        KnowledgeSource(
            id=ids["source"],
            organization_id="dev-org",
            agent_id=ids["agent"],
            name="P7 Migration Smoke Source",
            description="DB-level service smoke fixture",
            source_type="markdown",
            status="ACTIVE",
            version=1,
            last_indexed_at=now,
            health_status="HEALTHY",
            settings_json={},
            metadata_json={},
            idempotency_key="p7-migration-smoke:source",
            created_by="p7-smoke",
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        KnowledgeDocument(
            id=ids["document"],
            source_id=ids["source"],
            organization_id="dev-org",
            agent_id=ids["agent"],
            title="P7 Migration Smoke Document",
            uri="seed-fixture://agent-knowledge-harness/p7/migration-smoke",
            content_sha256=sha,
            mime_type="text/markdown",
            status="INDEXED",
            version=1,
            logical_document_id=ids["document"],
            metadata_json={},
            idempotency_key="p7-migration-smoke:document",
            created_by="p7-smoke",
            created_at=now,
            updated_at=now,
            indexed_at=now,
        )
    )
    session.add(
        KnowledgeChunk(
            id=ids["chunk"],
            document_id=ids["document"],
            source_id=ids["source"],
            organization_id="dev-org",
            agent_id=ids["agent"],
            source_version=1,
            document_version=1,
            chunk_version=1,
            chunk_index=1,
            text=content,
            text_sha256=sha,
            start_offset=0,
            end_offset=len(content),
            status="ACTIVE",
            metadata_json={},
            created_at=now,
        )
    )
    session.add(
        RetrievalSession(
            id=ids["retrieval"],
            organization_id="dev-org",
            agent_id=ids["agent"],
            run_id=ids["task"],
            query="selector continuity beacon",
            mode="local",
            local_status="sufficient",
            vector_capability="available",
            strategy="lexical",
            min_hits=1,
            min_score=0.1,
            max_local_chunks=3,
            max_web_results=0,
            metadata_json={"schema_version": "p7-migration-restore-smoke-v1"},
            created_at=now,
        )
    )
    session.add(
        RetrievalHit(
            id=ids["hit"],
            retrieval_session_id=ids["retrieval"],
            chunk_id=ids["chunk"],
            rank=1,
            score=0.99,
            source_kind="knowledge_chunk",
            document_id=ids["document"],
            document_version=1,
            snippet=content,
            metadata_json={},
            created_at=now,
        )
    )
    session.add(
        CitationRecord(
            id=ids["citation"],
            retrieval_session_id=ids["retrieval"],
            retrieval_hit_id=ids["hit"],
            run_id=ids["task"],
            citation_key="[1]",
            source_kind="knowledge_chunk",
            chunk_id=ids["chunk"],
            claim_text="P7 migration smoke preserves selectors.",
            quoted_text=content,
            confidence=0.99,
            metadata_json={},
            created_at=now,
        )
    )
    session.commit()

engine.dispose()
engine = create_engine(database_url)
with Session(engine) as session:
    hit = session.execute(
        select(RetrievalHit).where(
            RetrievalHit.id == ids["hit"],
            RetrievalHit.retrieval_session_id == ids["retrieval"],
            RetrievalHit.document_id == ids["document"],
            RetrievalHit.chunk_id == ids["chunk"],
        )
    ).scalar_one()
    citation = session.execute(
        select(CitationRecord).where(
            CitationRecord.id == ids["citation"],
            CitationRecord.retrieval_hit_id == ids["hit"],
            CitationRecord.citation_key == "[1]",
        )
    ).scalar_one()
    print(json.dumps({
        "schema_version": "p7-migration-restore-smoke-v1",
        "required_tables": required_tables,
        "selector_continuity": {
            "retrieval_hit_id": hit.id,
            "citation_id": citation.id,
            "document_id": hit.document_id,
            "chunk_id": hit.chunk_id,
        },
    }, sort_keys=True))
"""


def run(command: list[str], *, env: dict[str, str]) -> None:
    print("$ " + " ".join(command))
    subprocess.run(command, cwd=API_SERVER_DIR, env=env, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run P7 service-level Knowledge/RAG migration and restore smoke.",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("HARNESS_P7_DATABASE_URL"),
        help=(
            "Database URL to smoke. Defaults to HARNESS_P7_DATABASE_URL when set, "
            "otherwise a temporary sqlite database. Ambient DATABASE_URL is ignored."
        ),
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Keep the temporary sqlite database file for local inspection.",
    )
    parser.add_argument(
        "--allow-service-db-mutation",
        action="store_true",
        help=(
            "Required when --database-url or HARNESS_P7_DATABASE_URL points at "
            "a service database."
        ),
    )
    parser.add_argument("--skip-alembic", action="store_true", help="Skip alembic upgrade head.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    temp_database_dir: Path | None = None
    database_url = args.database_url
    uses_provided_database = bool(database_url)
    if uses_provided_database and not args.allow_service_db_mutation:
        raise SystemExit(
            "Refusing to mutate a provided database URL without --allow-service-db-mutation. "
            "Omit --database-url/HARNESS_P7_DATABASE_URL for the temporary SQLite default."
        )
    if not database_url:
        temp_database_dir = Path(tempfile.mkdtemp(prefix="harness-p7-knowledge-smoke-"))
        database_path = temp_database_dir / "agent_harness.sqlite"
        database_url = f"sqlite+pysqlite:///{database_path}"

    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["P7_REQUIRED_TABLES"] = json.dumps(REQUIRED_TABLES)

    try:
        if not args.skip_alembic:
            run(["uv", "run", "alembic", "upgrade", "head"], env=env)
        result = subprocess.run(
            ["uv", "run", "python", "-c", SMOKE_CODE],
            cwd=API_SERVER_DIR,
            env=env,
            check=True,
            text=True,
            capture_output=True,
        )
        print(result.stdout.strip())
        print(
            json.dumps(
                {
                    "schema_version": "p7-migration-restore-smoke-summary-v1",
                    "database_url_kind": (
                        "provided" if uses_provided_database else "temporary-sqlite"
                    ),
                    "alembic": "skipped" if args.skip_alembic else "upgraded-to-head",
                    "cleanup": (
                        "provided database retained"
                        if uses_provided_database
                        else "temporary database kept"
                        if args.keep_db
                        else "temporary database removed"
                    ),
                },
                sort_keys=True,
            )
        )
    finally:
        if temp_database_dir is not None and args.keep_db:
            print(f"kept temporary database directory: {temp_database_dir}")
        elif temp_database_dir is not None:
            shutil.rmtree(temp_database_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
