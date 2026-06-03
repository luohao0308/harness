from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import SystemSetting, utc_now
from app.security.secrets import (
    SECRET_PURPOSE_KNOWLEDGE_CONNECTOR,
    SECRET_SCOPE_ORG,
    env_candidates_for_provider,
    resolve_secret,
    upsert_secret,
)

CONNECTOR_PROVIDER_DIFY = "dify"
CONNECTOR_PROVIDER_COZE = "coze"
GROUNDING_PROVIDER_DIFY_CONNECTOR = "dify_connector"
GROUNDING_PROVIDER_COZE_CONNECTOR = "coze_connector"

DEFAULT_DIFY_TIMEOUT_SECONDS = 8
DEFAULT_DIFY_MAX_RESULTS = 3
DEFAULT_DIFY_MAX_CONTENT_BYTES = 1200
DEFAULT_DIFY_QUERY_MAX_CHARS = 250
CONNECTOR_SECRET_SETTING_PREFIX = "secrets.connectors."
DIFY_REQUEST_USER_AGENT = "AgentHarness/0.1"
DIFY_ERROR_DETAIL_MAX_CHARS = 300


class DifyConnectorError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class DifyRetrievalResult:
    content: str
    rank: int
    score: float
    dataset_id: str
    segment_id: str | None = None
    document_id: str | None = None
    document_name: str | None = None
    position: int | None = None

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DifyDatasetDocumentStatus:
    document_count: int | None = None
    enabled_document_count: int | None = None
    disabled_document_count: int | None = None
    completed_document_count: int | None = None


class DifyRetrievalAdapter(Protocol):
    provider: str

    def retrieve(
        self,
        *,
        endpoint: str,
        dataset_id: str,
        api_key: str,
        query: str,
        max_results: int,
        timeout_seconds: int,
    ) -> list[DifyRetrievalResult]: ...


def _request_json(
    *,
    url: str,
    api_key: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout_seconds: int,
) -> dict[str, Any]:
    token = api_key.strip()
    if not token:
        raise DifyConnectorError("dify api key is missing")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": DIFY_REQUEST_USER_AGENT,
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        retryable = exc.code in {408, 429, 500, 502, 503, 504}
        detail = _dify_error_detail(exc.read())
        message = f"dify retrieval failed with HTTP {exc.code}"
        if detail:
            message = f"{message}: {detail}"
        raise DifyConnectorError(
            message,
            retryable=retryable,
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise DifyConnectorError("dify retrieval failed", retryable=True) from exc


def _dify_retrieve_payload(*, query: str) -> dict[str, Any]:
    # Let Dify use the dataset's own retrieval_model_dict. Overriding it can
    # diverge from Dify Console test retrieval and return empty results.
    return {
        "query": query.strip()[:DEFAULT_DIFY_QUERY_MAX_CHARS],
    }


def _secret_ref_slug(secret_ref: str) -> str:
    value = secret_ref.strip()
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme:
        slug = "/".join(part for part in (parsed.netloc, parsed.path.strip("/")) if part)
    else:
        slug = value
    return re.sub(r"[^A-Za-z0-9]+", "_", slug).strip("_").upper()


def connector_secret_setting_key(secret_ref: str) -> str:
    slug = _secret_ref_slug(secret_ref).lower()
    if not slug:
        raise ValueError("connector secret_ref is required")
    return f"{CONNECTOR_SECRET_SETTING_PREFIX}{slug}"


def secret_ref_looks_like_raw_secret(secret_ref: str) -> bool:
    value = secret_ref.strip()
    if not value:
        return False
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme in {"secret", "env"}:
        return False
    if re.fullmatch(r"[A-Z][A-Z0-9_]{2,}", value):
        return False
    if any(part in value.lower() for part in ("token", "secret", "apikey", "api_key")):
        return True
    return bool(len(value) >= 24 and re.fullmatch(r"[A-Za-z0-9._=-]+", value))


def store_connector_secret_ref(
    session: Session,
    *,
    organization_id: str | None,
    actor_id: str | None,
    secret_ref: str,
    provider: str,
    secret_value: str,
    owner_user_id: str | None = None,
    scope: str = SECRET_SCOPE_ORG,
    purpose: str = SECRET_PURPOSE_KNOWLEDGE_CONNECTOR,
) -> str:
    ref = secret_ref.strip()
    if not ref:
        raise ValueError("connector secret_ref is required")
    if secret_ref_looks_like_raw_secret(ref):
        raise ValueError("connector secret_ref must reference a server-side secret")
    value = secret_value.strip()
    if not value:
        raise ValueError("connector secret value is required")
    if len(value.encode("utf-8")) > 10_000:
        raise ValueError("connector secret value is too large")
    if not organization_id:
        raise ValueError("connector secret organization_id is required")
    upsert_secret(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        scope=scope,
        owner_user_id=owner_user_id or (actor_id if scope == "user" else None),
        provider=provider,
        purpose=purpose,
        secret_ref=ref,
        secret_value=value,
    )
    key = connector_secret_setting_key(ref)
    setting = session.execute(
        select(SystemSetting).where(
            SystemSetting.organization_id == organization_id,
            SystemSetting.key == key,
        )
    ).scalar_one_or_none()
    payload = {
        "schema_version": "connector-secret-v1",
        "provider": provider.strip().lower(),
        "secret_ref": ref,
        "secret_configured": True,
        "secret_storage": "stored_secrets",
        "updated_by": actor_id,
        "updated_at": utc_now().isoformat(),
    }
    if setting is None:
        setting = SystemSetting(
            organization_id=organization_id,
            key=key,
            value_json=payload,
            updated_by=actor_id,
            updated_at=utc_now(),
        )
        session.add(setting)
    else:
        setting.value_json = payload
        setting.updated_by = actor_id
        setting.updated_at = utc_now()
    session.flush()
    return key


def read_connector_secret_ref(
    session: Session,
    *,
    organization_id: str | None,
    secret_ref: str,
    provider: str | None = None,
    user_id: str | None = None,
    purpose: str = SECRET_PURPOSE_KNOWLEDGE_CONNECTOR,
) -> str:
    ref = secret_ref.strip()
    if not ref or secret_ref_looks_like_raw_secret(ref):
        return ""
    normalized_provider = (provider or _secret_ref_slug(ref).lower() or "connector").strip().lower()
    resolved = resolve_secret(
        session,
        organization_id=organization_id,
        user_id=user_id,
        provider=normalized_provider,
        purpose=purpose,
        env_candidates=[],
    )
    if resolved.found:
        return resolved.value
    key = connector_secret_setting_key(ref)
    setting = session.execute(
        select(SystemSetting).where(
            SystemSetting.organization_id == organization_id,
            SystemSetting.key == key,
        )
    ).scalar_one_or_none()
    if setting is None or not isinstance(setting.value_json, dict):
        return ""
    return str(setting.value_json.get("secret_value") or "").strip()


def resolve_connector_secret_ref(
    secret_ref: str,
    *,
    provider: str,
    session: Session | None = None,
    organization_id: str | None = None,
    user_id: str | None = None,
    purpose: str = SECRET_PURPOSE_KNOWLEDGE_CONNECTOR,
) -> str:
    ref = secret_ref.strip()
    if not ref:
        return ""
    if secret_ref_looks_like_raw_secret(ref):
        return ""
    normalized_provider = provider.strip().lower()
    if session is not None:
        stored = read_connector_secret_ref(
            session,
            organization_id=organization_id,
            secret_ref=ref,
            provider=normalized_provider,
            user_id=user_id,
            purpose=purpose,
        )
        if stored:
            return stored
    slug = _secret_ref_slug(ref)
    env_candidates: list[str] = []
    if ref.startswith("env://"):
        env_candidates.append(ref.removeprefix("env://").strip())
    if re.fullmatch(r"[A-Z][A-Z0-9_]{2,}", ref):
        env_candidates.append(ref)
    if slug:
        env_candidates.append(f"{slug}_API_KEY")
        env_candidates.append(f"{slug}_KEY")
    env_candidates.extend(env_candidates_for_provider(normalized_provider))
    if normalized_provider == CONNECTOR_PROVIDER_DIFY:
        env_candidates.extend(
            [
                "DIFY_API_KEY",
                "DIFY_CLOUD_API_KEY",
                "DIFY_KNOWLEDGE_API_KEY",
            ]
        )
    if normalized_provider == CONNECTOR_PROVIDER_COZE:
        env_candidates.extend(
            [
                "COZE_API_KEY",
                "COZE_PAT",
                "COZE_PERSONAL_ACCESS_TOKEN",
                "COZE_KNOWLEDGE_API_KEY",
            ]
        )
    seen: set[str] = set()
    for name in env_candidates:
        env_name = name.strip().upper()
        if not env_name or env_name in seen:
            continue
        seen.add(env_name)
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    if normalized_provider == CONNECTOR_PROVIDER_DIFY:
        return get_settings().dify_api_key.strip()
    return ""


def _dify_retrieve_url(endpoint: str, dataset_id: str) -> str:
    base = endpoint.strip().rstrip("/")
    if not base:
        raise DifyConnectorError("dify endpoint is missing")
    parsed = urllib.parse.urlsplit(base)
    if parsed.username or parsed.password:
        raise DifyConnectorError("dify endpoint must not include credentials")
    if not parsed.scheme or not parsed.netloc:
        raise DifyConnectorError("dify endpoint must be an absolute URL")
    path = parsed.path.rstrip("/")
    if path.endswith("/retrieve") and "/datasets/" in path:
        return urllib.parse.urlunsplit(parsed)
    if re.search(r"/datasets/[^/]+$", path):
        path = f"{path}/retrieve"
    else:
        path = f"{path}/datasets/{urllib.parse.quote(dataset_id, safe='')}/retrieve"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _dify_documents_url(endpoint: str, dataset_id: str) -> str:
    base = endpoint.strip().rstrip("/")
    if not base:
        raise DifyConnectorError("dify endpoint is missing")
    parsed = urllib.parse.urlsplit(base)
    if parsed.username or parsed.password:
        raise DifyConnectorError("dify endpoint must not include credentials")
    if not parsed.scheme or not parsed.netloc:
        raise DifyConnectorError("dify endpoint must be an absolute URL")
    path = parsed.path.rstrip("/")
    if re.search(r"/datasets/[^/]+/documents$", path):
        return urllib.parse.urlunsplit(parsed)
    if re.search(r"/datasets/[^/]+$", path):
        path = f"{path}/documents"
    else:
        path = f"{path}/datasets/{urllib.parse.quote(dataset_id, safe='')}/documents"
    query = urllib.parse.urlencode({"limit": "10"})
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, query, ""))


def _document_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = payload.get("data") or payload.get("documents") or payload.get("items") or []
    if not isinstance(candidates, list):
        return []
    return [item for item in candidates if isinstance(item, dict)]


def _document_status(payload: dict[str, Any]) -> DifyDatasetDocumentStatus:
    documents = _document_items(payload)
    if not documents:
        return DifyDatasetDocumentStatus()
    enabled = 0
    disabled = 0
    completed = 0
    for document in documents:
        if document.get("enabled") is True:
            enabled += 1
        elif document.get("enabled") is False:
            disabled += 1
        if str(document.get("indexing_status") or "").strip().lower() == "completed":
            completed += 1
    return DifyDatasetDocumentStatus(
        document_count=len(documents),
        enabled_document_count=enabled,
        disabled_document_count=disabled,
        completed_document_count=completed,
    )


def _segment_content(record: dict[str, Any]) -> str:
    segment = record.get("segment") if isinstance(record.get("segment"), dict) else {}
    content = str(segment.get("content") or segment.get("answer") or "").strip()
    if content:
        return content
    child_chunks = (
        record.get("child_chunks") if isinstance(record.get("child_chunks"), list) else []
    )
    parts: list[str] = []
    for child in child_chunks:
        if not isinstance(child, dict):
            continue
        value = str(child.get("content") or child.get("text") or "").strip()
        if value:
            parts.append(value)
    return "\n".join(parts).strip()


def _float_score(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _dify_error_detail(payload: bytes) -> str:
    text = payload.decode("utf-8", errors="replace").strip()
    if not text:
        return ""
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return text[:DIFY_ERROR_DETAIL_MAX_CHARS]
    if isinstance(decoded, dict):
        parts = [
            str(decoded.get(key) or "").strip()
            for key in ("code", "message", "error")
            if str(decoded.get(key) or "").strip()
        ]
        if parts:
            return ": ".join(parts)[:DIFY_ERROR_DETAIL_MAX_CHARS]
    return text[:DIFY_ERROR_DETAIL_MAX_CHARS]


class DifyKnowledgeBaseAdapter:
    provider = CONNECTOR_PROVIDER_DIFY

    def retrieve(
        self,
        *,
        endpoint: str,
        dataset_id: str,
        api_key: str,
        query: str,
        max_results: int,
        timeout_seconds: int,
    ) -> list[DifyRetrievalResult]:
        token = api_key.strip()
        if not token:
            raise DifyConnectorError("dify api key is missing")
        normalized_dataset_id = dataset_id.strip()
        if not normalized_dataset_id:
            raise DifyConnectorError("dify dataset_id is missing")
        bounded_max_results = max(1, min(max_results, DEFAULT_DIFY_MAX_RESULTS))
        payload = _dify_retrieve_payload(query=query)
        response_payload = _request_json(
            url=_dify_retrieve_url(endpoint, normalized_dataset_id),
            api_key=token,
            method="POST",
            payload=payload,
            timeout_seconds=timeout_seconds,
        )

        records = response_payload.get("records") if isinstance(response_payload, dict) else []
        if not isinstance(records, list):
            return []
        results: list[DifyRetrievalResult] = []
        for index, record in enumerate(records[:bounded_max_results], start=1):
            if not isinstance(record, dict):
                continue
            segment = record.get("segment") if isinstance(record.get("segment"), dict) else {}
            document = segment.get("document") if isinstance(segment.get("document"), dict) else {}
            content = _segment_content(record)
            if not content:
                continue
            try:
                position = int(segment.get("position")) if segment.get("position") else None
            except (TypeError, ValueError):
                position = None
            results.append(
                DifyRetrievalResult(
                    content=content[:DEFAULT_DIFY_MAX_CONTENT_BYTES],
                    rank=index,
                    score=_float_score(record.get("score")),
                    dataset_id=normalized_dataset_id,
                    segment_id=str(segment.get("id") or "") or None,
                    document_id=str(segment.get("document_id") or document.get("id") or "")
                    or None,
                    document_name=str(
                        document.get("name") or segment.get("name") or "Dify document"
                    )[:300],
                    position=position,
                )
            )
        return results

    def document_status(
        self,
        *,
        endpoint: str,
        dataset_id: str,
        api_key: str,
        timeout_seconds: int,
    ) -> DifyDatasetDocumentStatus:
        normalized_dataset_id = dataset_id.strip()
        if not normalized_dataset_id:
            raise DifyConnectorError("dify dataset_id is missing")
        response_payload = _request_json(
            url=_dify_documents_url(endpoint, normalized_dataset_id),
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
        return _document_status(response_payload)


def get_dify_retrieval_adapter(provider: str) -> DifyRetrievalAdapter | None:
    if provider.strip().lower() == CONNECTOR_PROVIDER_DIFY:
        return DifyKnowledgeBaseAdapter()
    return None
