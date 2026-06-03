"""Connector and web provider routing helpers for grounding."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
from .chunking import *
from .connectors import *
from .lifecycle import *
from .prompt_assembly import *
from .retrieval_events import *
from .web_routing import *
from ._provider_fallback import *
import app.knowledge as knowledge_api


def _connector_source_rows(
    *,
    session: Session,
    organization_id: str | None,
    agent_id: str,
) -> list[KnowledgeSource]:
    now = utc_now()
    return list(
        session.execute(
            select(KnowledgeSource)
            .where(
                KnowledgeSource.organization_id == organization_id,
                or_(KnowledgeSource.agent_id == None, KnowledgeSource.agent_id == agent_id),  # noqa: E711
                KnowledgeSource.status == SOURCE_STATUS_ACTIVE,
                KnowledgeSource.source_type == "connector",
                or_(KnowledgeSource.expires_at == None, KnowledgeSource.expires_at > now),  # noqa: E711
            )
            .order_by(KnowledgeSource.created_at.desc(), KnowledgeSource.id.asc())
            .limit(20)
        ).scalars()
    )


def _connector_snapshot_hash(sources: list[KnowledgeSource]) -> str:
    payload = []
    for source in sources:
        settings = source.settings_json if isinstance(source.settings_json, dict) else {}
        provider = connector_provider_key(settings, source_type=source.source_type)
        if provider not in {"coze", "dify"}:
            continue
        endpoint = str(settings.get("endpoint") or settings.get("uri") or "").strip()
        dataset_id = str(settings.get("dataset_id") or "").strip()
        payload.append(
            {
                "source_id": source.id,
                "source_version": source.version,
                "source_status": source.status,
                "source_agent_id": source.agent_id,
                "provider": provider,
                "release_state": connector_release_state(settings, source_type=source.source_type),
                "counts_as_usable": connector_counts_toward_complete_usable(
                    settings,
                    source_type=source.source_type,
                ),
                "endpoint_sha256": _sha256(endpoint) if endpoint else None,
                "dataset_id_sha256": _sha256(dataset_id) if dataset_id else None,
                "secret_ref_present": bool(
                    settings.get("secret_ref") or settings.get("auth_secret_ref")
                ),
            }
        )
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256(raw)

__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
