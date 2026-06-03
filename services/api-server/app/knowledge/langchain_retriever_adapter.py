from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import (
    CitationRecord,
    PromptAssemblyManifest,
    RetrievalHit,
    RetrievalSession,
    utc_now,
)

LANGCHAIN_CONNECTOR_SOURCE_KIND = "langchain_connector"


@dataclass(frozen=True)
class LangChainRetrieverDocument:
    page_content: str
    metadata: dict[str, Any]
    score: float = 0.0


def normalize_langchain_documents(documents: list[Any]) -> list[LangChainRetrieverDocument]:
    normalized: list[LangChainRetrieverDocument] = []
    for item in documents:
        if isinstance(item, dict):
            content = str(item.get("page_content") or item.get("content") or "")
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            score = float(item.get("score") or metadata.get("score") or 0)
        else:
            content = str(getattr(item, "page_content", "") or getattr(item, "content", "") or "")
            metadata = getattr(item, "metadata", {})
            metadata = metadata if isinstance(metadata, dict) else {}
            score = float(getattr(item, "score", metadata.get("score", 0)) or 0)
        if content.strip():
            normalized.append(
                LangChainRetrieverDocument(
                    page_content=content,
                    metadata=metadata,
                    score=score,
                )
            )
    return normalized


def persist_langchain_grounding(
    *,
    session: Session,
    organization_id: str | None,
    agent_id: str,
    run_id: str | None,
    query: str,
    documents: list[Any],
    grounding_correlation_id: str,
) -> tuple[RetrievalSession, list[RetrievalHit], list[CitationRecord], PromptAssemblyManifest]:
    normalized = normalize_langchain_documents(documents)
    retrieval_session = RetrievalSession(
        organization_id=organization_id,
        agent_id=agent_id,
        run_id=run_id,
        query=query,
        mode="langchain_connector",
        local_status="sufficient" if normalized else "insufficient",
        vector_capability="external_connector",
        strategy="langchain_retriever",
        min_hits=1,
        min_score=0,
        max_local_chunks=len(normalized),
        max_web_results=0,
        metadata_json={
            "connector_provider": "langchain",
            "source_kind": LANGCHAIN_CONNECTOR_SOURCE_KIND,
            "connector_hit_count": len(normalized),
        },
        created_at=utc_now(),
    )
    session.add(retrieval_session)
    session.flush()
    hits: list[RetrievalHit] = []
    citations: list[CitationRecord] = []
    for index, document in enumerate(normalized, start=1):
        hit = RetrievalHit(
            retrieval_session_id=retrieval_session.id,
            chunk_id=None,
            web_source_id=None,
            rank=index,
            score=document.score,
            source_kind=LANGCHAIN_CONNECTOR_SOURCE_KIND,
            document_id=None,
            document_version=None,
            snippet=document.page_content[:1200],
            metadata_json={
                "connector_provider": "langchain",
                "document_metadata": document.metadata,
                "content_sha256": _sha256(document.page_content),
            },
            created_at=utc_now(),
        )
        session.add(hit)
        session.flush()
        citation = CitationRecord(
            retrieval_session_id=retrieval_session.id,
            retrieval_hit_id=hit.id,
            run_id=run_id,
            citation_key=f"[L{index}]",
            source_kind=LANGCHAIN_CONNECTOR_SOURCE_KIND,
            chunk_id=None,
            web_source_id=None,
            claim_text=None,
            quoted_text=document.page_content[:500],
            confidence=max(0.0, min(document.score, 1.0)),
            metadata_json={"connector_provider": "langchain"},
            created_at=utc_now(),
        )
        session.add(citation)
        hits.append(hit)
        citations.append(citation)
    session.flush()
    evidence_text = "\n".join(hit.snippet for hit in hits)
    manifest = PromptAssemblyManifest(
        retrieval_session_id=retrieval_session.id,
        run_id=run_id,
        organization_id=organization_id,
        agent_id=agent_id,
        grounding_correlation_id=grounding_correlation_id,
        query=query,
        included_retrieval_hit_ids_json=[hit.id for hit in hits],
        omitted_candidates_json=[],
        source_snapshots_json=[
            {
                "source_kind": LANGCHAIN_CONNECTOR_SOURCE_KIND,
                "retrieval_hit_id": hit.id,
                "content_sha256": hit.metadata_json.get("content_sha256"),
            }
            for hit in hits
        ],
        token_budget_json={"source": "langchain_connector", "hit_count": len(hits)},
        prompt_sections_json=[
            {"citation_key": citation.citation_key, "retrieval_hit_id": citation.retrieval_hit_id}
            for citation in citations
        ],
        evidence_text_sha256=_sha256(evidence_text),
        metadata_json={
            "grounding_provider": LANGCHAIN_CONNECTOR_SOURCE_KIND,
            "connector_provider": "langchain",
        },
        created_at=utc_now(),
    )
    session.add(manifest)
    session.flush()
    return retrieval_session, hits, citations, manifest


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_document_json(documents: list[Any]) -> str:
    normalized = [
        {"page_content": item.page_content, "metadata": item.metadata, "score": item.score}
        for item in normalize_langchain_documents(documents)
    ]
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
