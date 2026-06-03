import importlib.util
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_script(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


seed_demo = _load_script("p7_seed_knowledge_demo", REPO_ROOT / "scripts/seed-knowledge-demo.py")
restore_smoke = _load_script(
    "p7_smoke_test_knowledge_migration_restore",
    REPO_ROOT / "scripts/smoke-test-knowledge-migration-restore.py",
)


def _source_response(source: Any) -> dict[str, Any]:
    documents = [
        {
            "id": f"{source.scope}-document",
            "uri": source.uri,
            "idempotency_key": source.idempotency_key,
            "chunk_count": 1,
        }
    ]
    documents.extend(
        {
            "id": f"{source.scope}-{document.slug}-document",
            "uri": document.uri,
            "idempotency_key": document.idempotency_key,
            "chunk_count": 1,
        }
        for document in seed_demo.DEMO_DOCUMENTS
        if document.source_slug == source.slug
    )
    return {
        "id": f"{source.scope}-source",
        "name": source.name,
        "scope": source.scope,
        "health_status": "HEALTHY",
        "idempotency_key": source.idempotency_key,
        "latest_documents": documents,
    }


class ExistingSeedClient:
    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []

    def get_json(self, path: str) -> dict[str, Any]:
        assert path == "/api/agents/default/knowledge/sources"
        return {"items": [_source_response(source) for source in seed_demo.DEMO_SOURCES]}

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.posts.append({"path": path, "payload": payload})
        raise AssertionError("existing valid seed must not be posted again")


def test_seed_reuses_existing_sources_without_posting() -> None:
    client = ExistingSeedClient()

    evidence = seed_demo.create_or_verify(client, agent_id="default")

    assert client.posts == []
    assert evidence["agent_source_id"] == "agent-source"
    assert evidence["org_source_id"] == "org-source"
    assert evidence["agent_grounding-evidence_document_id"] == (
        "agent-grounding-evidence-document"
    )


def test_restore_smoke_ignores_ambient_database_url(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/service")
    monkeypatch.delenv("HARNESS_P7_DATABASE_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["smoke-test-knowledge-migration-restore.py"])

    args = restore_smoke.parse_args()

    assert args.database_url is None
