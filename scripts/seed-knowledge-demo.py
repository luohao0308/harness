#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any
from urllib import error, request

DEFAULT_BASE_URL = os.environ.get("HARNESS_API_BASE_URL", "http://127.0.0.1:8000")
DEFAULT_AGENT_ID = os.environ.get("HARNESS_DEMO_AGENT_ID", "default")
DEFAULT_TOKEN = os.environ.get("HARNESS_ADMIN_TOKEN", "dev-admin-token")
HTTP_TIMEOUT_SECONDS = 60
SEED_PREFIX = "p7-seed-fixture"
SEED_URI_PREFIX = "seed-fixture://agent-knowledge-harness/p7"
DEMO_QUESTION = "What evidence proves the Agent Knowledge Harness demo is grounded?"


@dataclass(frozen=True)
class DemoSource:
    slug: str
    scope: str
    name: str
    title: str
    content: str

    @property
    def idempotency_key(self) -> str:
        return f"{SEED_PREFIX}:{self.scope}:{self.slug}"

    @property
    def uri(self) -> str:
        return f"{SEED_URI_PREFIX}/{self.slug}"

    @property
    def description(self) -> str:
        return (
            "P7 deterministic local demo seed. Fixture evidence only; "
            "not provider-backed web verification."
        )

    def payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "scope": self.scope,
            "source_type": "markdown",
            "title": self.title,
            "content": self.content,
            "uri": self.uri,
            "mime_type": "text/markdown",
            "idempotency_key": self.idempotency_key,
        }


@dataclass(frozen=True)
class DemoDocument:
    source_slug: str
    slug: str
    title: str
    content: str

    @property
    def idempotency_key(self) -> str:
        return f"{SEED_PREFIX}:document:{self.slug}"

    @property
    def uri(self) -> str:
        return f"{SEED_URI_PREFIX}/{self.slug}"

    def payload(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content,
            "uri": self.uri,
            "mime_type": "text/markdown",
            "idempotency_key": self.idempotency_key,
        }


DEMO_SOURCES = (
    DemoSource(
        slug="agent-runbook",
        scope="agent",
        name="P7 Demo Agent Runbook",
        title="P7 Demo Agent Runbook",
        content=(
            "# P7 Demo Agent Runbook\n\n"
            f"The demo question is: {DEMO_QUESTION}\n\n"
            "The deterministic answer must cite the local runbook source, retrieval hit, "
            "prompt manifest, and Run Detail evidence. The seed is fixture evidence only."
        ),
    ),
    DemoSource(
        slug="org-handoff",
        scope="org",
        name="P7 Demo Org Handoff",
        title="P7 Demo Org Handoff",
        content=(
            "# P7 Demo Org Handoff\n\n"
            "Private release handoff requires deterministic local seed data, a service-level "
            "migration and restore smoke, mocked browser release smoke, and runbook evidence.\n\n"
            "Provider-backed live web validation is optional and credential-gated."
        ),
    ),
)


DEMO_DOCUMENTS = (
    DemoDocument(
        source_slug="agent-runbook",
        slug="grounding-evidence",
        title="P7 Demo Grounding Evidence",
        content=(
            "# P7 Demo Grounding Evidence\n\n"
            "What evidence proves the Agent Knowledge Harness demo is grounded? "
            "The evidence is local Knowledge/RAG fixture grounding from the P7 Demo Agent "
            "Runbook, retrieval hit selectors, citation records, prompt manifest records, "
            "and Run Detail evidence. The Agent Knowledge Harness demo is grounded by "
            "these deterministic local seed documents, not by provider-backed web research."
        ),
    ),
)


class ApiClient:
    def __init__(self, *, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def get_json(self, path: str) -> Any:
        return self.request_json("GET", path)

    def post_json(self, path: str, payload: dict[str, Any]) -> Any:
        return self.request_json("POST", path, payload=payload)

    def request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            self.base_url + path,
            data=data,
            headers=self.headers,
            method=method,
        )
        try:
            with request.urlopen(http_request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise AssertionError(f"{method} {path} -> {exc.code}: {body}") from exc


def find_seed_source(items: list[dict[str, Any]], expected: DemoSource) -> dict[str, Any]:
    for item in items:
        if item.get("idempotency_key") == expected.idempotency_key:
            return item
    raise AssertionError(f"seed source missing from readback: {expected.idempotency_key}")


def maybe_find_seed_source(
    items: list[dict[str, Any]], expected: DemoSource
) -> dict[str, Any] | None:
    for item in items:
        if item.get("idempotency_key") == expected.idempotency_key:
            return item
    return None


def validate_source(source: dict[str, Any], expected: DemoSource) -> None:
    if source.get("name") != expected.name:
        raise AssertionError(f"{expected.slug}: name mismatch")
    if source.get("scope") != expected.scope:
        raise AssertionError(f"{expected.slug}: scope mismatch")
    if source.get("idempotency_key") != expected.idempotency_key:
        raise AssertionError(f"{expected.slug}: idempotency_key mismatch")
    if source.get("health_status") != "HEALTHY":
        raise AssertionError(f"{expected.slug}: health_status is not HEALTHY")
    documents = source.get("latest_documents") or []
    document = find_document(documents, uri=expected.uri, idempotency_key=expected.idempotency_key)
    if int(document.get("chunk_count") or 0) < 1:
        raise AssertionError(f"{expected.slug}: indexed chunk missing")


def find_document(
    documents: list[dict[str, Any]],
    *,
    uri: str,
    idempotency_key: str,
) -> dict[str, Any]:
    for document in documents:
        if document.get("uri") == uri and document.get("idempotency_key") == idempotency_key:
            return document
    raise AssertionError(f"seed document missing from readback: {idempotency_key}")


def support_documents_for(source: DemoSource) -> list[DemoDocument]:
    return [document for document in DEMO_DOCUMENTS if document.source_slug == source.slug]


def ensure_support_documents(
    client: ApiClient,
    *,
    agent_id: str,
    source: dict[str, Any],
    expected: DemoSource,
) -> dict[str, Any]:
    documents = list(source.get("latest_documents") or [])
    for document in support_documents_for(expected):
        existing = next(
            (
                item
                for item in documents
                if item.get("uri") == document.uri
                and item.get("idempotency_key") == document.idempotency_key
            ),
            None,
        )
        if existing is None or int(existing.get("chunk_count") or 0) < 1:
            source = client.post_json(
                f"/api/agents/{agent_id}/knowledge/sources/{source['id']}/documents",
                document.payload(),
            )
            documents = list(source.get("latest_documents") or [])
        created = find_document(
            documents,
            uri=document.uri,
            idempotency_key=document.idempotency_key,
        )
        if int(created.get("chunk_count") or 0) < 1:
            raise AssertionError(f"{document.slug}: indexed chunk missing")
    return source


def create_or_verify(client: ApiClient, *, agent_id: str) -> dict[str, str]:
    evidence: dict[str, str] = {}
    readback = client.get_json(f"/api/agents/{agent_id}/knowledge/sources")
    items = list(readback.get("items") or [])
    for expected in DEMO_SOURCES:
        source = maybe_find_seed_source(items, expected)
        if source is None:
            source = client.post_json(
                f"/api/agents/{agent_id}/knowledge/sources",
                expected.payload(),
            )
        validate_source(source, expected)
        source = ensure_support_documents(
            client,
            agent_id=agent_id,
            source=source,
            expected=expected,
        )
        evidence[f"{expected.scope}_source_id"] = str(source["id"])
        documents = list(source.get("latest_documents") or [])
        primary = find_document(
            documents,
            uri=expected.uri,
            idempotency_key=expected.idempotency_key,
        )
        evidence[f"{expected.scope}_document_id"] = str(primary["id"])
        for document in support_documents_for(expected):
            support = find_document(
                documents,
                uri=document.uri,
                idempotency_key=document.idempotency_key,
            )
            evidence[f"{expected.scope}_{document.slug}_document_id"] = str(support["id"])

    readback = client.get_json(f"/api/agents/{agent_id}/knowledge/sources")
    items = list(readback.get("items") or [])
    for expected in DEMO_SOURCES:
        source = find_seed_source(items, expected)
        validate_source(source, expected)
        source = ensure_support_documents(
            client,
            agent_id=agent_id,
            source=source,
            expected=expected,
        )
        evidence[f"{expected.scope}_readback_id"] = str(source["id"])
    return evidence


def assert_idempotent(first: dict[str, str], second: dict[str, str]) -> None:
    for key in ("agent_source_id", "agent_document_id", "org_source_id", "org_document_id"):
        if first.get(key) != second.get(key):
            raise AssertionError(
                f"idempotency mismatch for {key}: {first.get(key)} != {second.get(key)}"
            )


def print_seed_plan() -> None:
    print(
        json.dumps(
            {
                "schema_version": "p7-knowledge-demo-seed-v1",
                "demo_question": DEMO_QUESTION,
                "sources": [source.payload() for source in DEMO_SOURCES],
                "evidence_class": "deterministic local fixture; not provider-backed web evidence",
            },
            indent=2,
            sort_keys=True,
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed deterministic P7 Knowledge/RAG demo data through public APIs.",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--agent-id", default=DEFAULT_AGENT_ID)
    parser.add_argument("--token", default=DEFAULT_TOKEN)
    parser.add_argument(
        "--print-plan",
        action="store_true",
        help="Print seed payloads without API calls.",
    )
    parser.add_argument(
        "--verify-readback",
        action="store_true",
        help="Accepted for explicit runbooks; API readback is always verified.",
    )
    parser.add_argument(
        "--check-idempotent",
        action="store_true",
        help="Seed twice and compare IDs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.print_plan:
        print_seed_plan()
        return 0

    client = ApiClient(base_url=args.base_url, token=args.token)
    first = create_or_verify(client, agent_id=args.agent_id)
    idempotent_checked = False
    if args.check_idempotent:
        second = create_or_verify(client, agent_id=args.agent_id)
        assert_idempotent(first, second)
        idempotent_checked = True

    print(
        json.dumps(
            {
                "schema_version": "p7-knowledge-demo-seed-v1",
                "base_url": args.base_url,
                "agent_id": args.agent_id,
                "demo_question": DEMO_QUESTION,
                "evidence_class": "deterministic local fixture; not provider-backed web evidence",
                "idempotent_checked": idempotent_checked,
                "readback_verified": True,
                "evidence": first,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
