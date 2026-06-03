from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

CONNECTOR_PROVIDER_COZE = "coze"

DEFAULT_COZE_TIMEOUT_SECONDS = 8
DEFAULT_COZE_MAX_RESULTS = 3
DEFAULT_COZE_MAX_CONTENT_BYTES = 1200
DEFAULT_COZE_QUERY_MAX_CHARS = 250
DEFAULT_COZE_MAX_DOCUMENTS = 5
DEFAULT_COZE_MAX_DOCUMENT_BYTES = 200_000
DEFAULT_COZE_CHUNK_CHARS = 900
DEFAULT_COZE_DOCUMENT_MIN_SCORE = 0.45
COZE_REQUEST_USER_AGENT = "AgentHarness/0.1"
COZE_ERROR_DETAIL_MAX_CHARS = 300
COZE_CJK_STOP_CHARS = set("的了什么吗呢啊呀吧请看查找一下里面里写有是我你他她它们这那哪与和及或")


class CozeConnectorError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class CozeRetrievalResult:
    content: str
    rank: int
    score: float
    dataset_id: str
    segment_id: str | None = None
    document_id: str | None = None
    document_name: str | None = None

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


class CozeRetrievalAdapter(Protocol):
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
    ) -> list[CozeRetrievalResult]: ...


def _request_json(
    *,
    url: str,
    api_key: str,
    method: str = "POST",
    payload: dict[str, Any] | None = None,
    timeout_seconds: int,
) -> dict[str, Any]:
    token = api_key.strip()
    if not token:
        raise CozeConnectorError("coze api key is missing")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": COZE_REQUEST_USER_AGENT,
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        retryable = exc.code in {408, 429, 500, 502, 503, 504}
        detail = _coze_error_detail(exc.read())
        message = f"coze retrieval failed with HTTP {exc.code}"
        if detail:
            message = f"{message}: {detail}"
        raise CozeConnectorError(message, retryable=retryable) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise CozeConnectorError("coze retrieval failed", retryable=True) from exc


def _coze_retrieve_url(endpoint: str, dataset_id: str) -> str:
    base = endpoint.strip().rstrip("/")
    if not base:
        raise CozeConnectorError("coze endpoint is missing")
    parsed = urllib.parse.urlsplit(base)
    if parsed.username or parsed.password:
        raise CozeConnectorError("coze endpoint must not include credentials")
    if not parsed.scheme or not parsed.netloc:
        raise CozeConnectorError("coze endpoint must be an absolute URL")
    path = parsed.path.rstrip("/")
    if _path_looks_like_retrieve_endpoint(path):
        return urllib.parse.urlunsplit(parsed)
    if path.endswith(f"/datasets/{dataset_id}"):
        path = f"{path}/retrieve"
    elif path.endswith("/v1"):
        path = f"{path}/datasets/{urllib.parse.quote(dataset_id, safe='')}/retrieve"
    elif path == "":
        path = f"/v1/datasets/{urllib.parse.quote(dataset_id, safe='')}/retrieve"
    else:
        path = f"{path}/v1/datasets/{urllib.parse.quote(dataset_id, safe='')}/retrieve"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _coze_document_list_url(endpoint: str) -> str:
    base = endpoint.strip().rstrip("/")
    if not base:
        raise CozeConnectorError("coze endpoint is missing")
    parsed = urllib.parse.urlsplit(base)
    if parsed.username or parsed.password:
        raise CozeConnectorError("coze endpoint must not include credentials")
    if not parsed.scheme or not parsed.netloc:
        raise CozeConnectorError("coze endpoint must be an absolute URL")
    path = parsed.path.rstrip("/")
    if path.endswith("/open_api/knowledge/document/list"):
        return urllib.parse.urlunsplit(parsed)
    if path.endswith("/open_api"):
        path = f"{path}/knowledge/document/list"
    elif path == "/v1":
        path = "/open_api/knowledge/document/list"
    elif path == "":
        path = "/open_api/knowledge/document/list"
    else:
        path = f"{path}/open_api/knowledge/document/list"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _path_looks_like_retrieve_endpoint(path: str) -> bool:
    normalized = path.rstrip("/").lower()
    return normalized.endswith(("/retrieve", "/retrieval", "/search"))


def _coze_retrieve_payload(*, dataset_id: str, query: str, max_results: int) -> dict[str, Any]:
    bounded_query = query.strip()[:DEFAULT_COZE_QUERY_MAX_CHARS]
    bounded_limit = max(1, min(max_results, DEFAULT_COZE_MAX_RESULTS))
    return {
        "dataset_id": dataset_id,
        "query": bounded_query,
        "top_k": bounded_limit,
        "limit": bounded_limit,
    }


def _coze_document_list_payload(*, dataset_id: str) -> dict[str, Any]:
    normalized_dataset_id = dataset_id.strip()
    payload_dataset_id: str | int = normalized_dataset_id
    if normalized_dataset_id.isdigit():
        payload_dataset_id = int(normalized_dataset_id)
    return {
        "dataset_id": payload_dataset_id,
        "page": 1,
        "size": DEFAULT_COZE_MAX_DOCUMENTS,
    }


def _candidate_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: Any = payload
    if isinstance(payload.get("data"), dict):
        candidates = payload["data"]
    if isinstance(candidates, dict):
        for key in (
            "records",
            "chunks",
            "slices",
            "segments",
            "results",
            "document_chunks",
            "items",
        ):
            value = candidates.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    for key in ("records", "chunks", "slices", "segments", "results", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _document_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    for container in (payload, data):
        for key in ("document_infos", "documents", "items", "data"):
            value = container.get(key) if isinstance(container, dict) else None
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _document_content_url(record: dict[str, Any]) -> str:
    for key in (
        "preview_tos_url",
        "tos_url",
        "url",
        "doc_tree_tos_url",
        "document_url",
    ):
        value = str(record.get(key) or "").strip()
        if value:
            return value
    return ""


def _document_id(record: dict[str, Any]) -> str | None:
    for key in ("document_id_new", "document_id", "id"):
        value = str(record.get(key) or "").strip()
        if value:
            return value
    return None


def _document_name(record: dict[str, Any]) -> str:
    return str(record.get("name") or record.get("document_name") or "Coze document")[:300]


def _request_text_url(*, url: str, timeout_seconds: int) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CozeConnectorError("coze document content URL is invalid")
    if parsed.username or parsed.password:
        raise CozeConnectorError("coze document content URL must not include credentials")
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/plain,text/markdown,application/json,*/*",
            "User-Agent": COZE_REQUEST_USER_AGENT,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return response.read(DEFAULT_COZE_MAX_DOCUMENT_BYTES).decode(
                "utf-8",
                errors="replace",
            )
    except urllib.error.HTTPError as exc:
        retryable = exc.code in {408, 429, 500, 502, 503, 504}
        raise CozeConnectorError(
            f"coze document content fetch failed with HTTP {exc.code}",
            retryable=retryable,
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise CozeConnectorError("coze document content fetch failed", retryable=True) from exc


def _document_text(record: dict[str, Any], *, timeout_seconds: int) -> str:
    for key in ("content", "text", "markdown"):
        value = str(record.get(key) or "").strip()
        if value:
            return value[:DEFAULT_COZE_MAX_DOCUMENT_BYTES]
    content_url = _document_content_url(record)
    if not content_url:
        return ""
    raw = _request_text_url(url=content_url, timeout_seconds=timeout_seconds).strip()
    if not raw:
        return ""
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:DEFAULT_COZE_MAX_DOCUMENT_BYTES]
    chunks = decoded.get("chunks") if isinstance(decoded, dict) else None
    if not isinstance(chunks, list):
        return raw[:DEFAULT_COZE_MAX_DOCUMENT_BYTES]
    parts = [
        str(chunk.get("text") or "").strip()
        for chunk in chunks
        if isinstance(chunk, dict) and str(chunk.get("text") or "").strip()
    ]
    return "\n\n".join(parts)[:DEFAULT_COZE_MAX_DOCUMENT_BYTES]


def _split_document_text(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", normalized) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > DEFAULT_COZE_CHUNK_CHARS:
            if current:
                chunks.append(current)
                current = ""
            for start in range(0, len(paragraph), DEFAULT_COZE_CHUNK_CHARS):
                piece = paragraph[start : start + DEFAULT_COZE_CHUNK_CHARS].strip()
                if piece:
                    chunks.append(piece)
            continue
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) > DEFAULT_COZE_CHUNK_CHARS and current:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _query_tokens(value: str) -> list[str]:
    normalized = value.lower()
    word_tokens = re.findall(r"[a-z0-9]{2,}", normalized)
    cjk_tokens = [
        token
        for token in re.findall(r"[\u4e00-\u9fff]", normalized)
        if token not in COZE_CJK_STOP_CHARS
    ]
    return word_tokens + cjk_tokens


def _cjk_core_terms(value: str) -> list[str]:
    terms: list[str] = []
    stop_chars = "".join(re.escape(char) for char in sorted(COZE_CJK_STOP_CHARS))
    for sequence in re.findall(r"[\u4e00-\u9fff]+", value.lower()):
        for part in re.split(f"[{stop_chars}]+", sequence):
            if len(part) < 2:
                continue
            terms.append(part)
    return list(dict.fromkeys(terms))


def _cjk_strong_terms(value: str) -> list[str]:
    terms: list[str] = []
    for part in _cjk_core_terms(value):
        terms.append(part)
        if len(part) <= 2:
            continue
            terms.extend(part[index : index + 2] for index in range(0, len(part) - 1))
    return list(dict.fromkeys(terms))


def _strong_query_terms(value: str) -> list[str]:
    normalized = value.lower()
    ascii_terms = re.findall(r"[a-z0-9]{2,}", normalized)
    return list(dict.fromkeys([*ascii_terms, *_cjk_strong_terms(normalized)]))


def _score_document_chunk(query: str, chunk: str) -> float:
    normalized_query = query.strip().lower()
    normalized_chunk = chunk.lower()
    if not normalized_query or not normalized_chunk:
        return 0.0
    if normalized_query in normalized_chunk:
        return 1.0
    core_terms = _cjk_core_terms(normalized_query)
    if core_terms and not any(token in normalized_chunk for token in core_terms):
        return 0.0
    strong_terms = _strong_query_terms(normalized_query)
    if strong_terms:
        strong_overlap = sum(1 for token in strong_terms if token in normalized_chunk)
        if strong_overlap == 0:
            return 0.0
    else:
        strong_overlap = 0
    query_tokens = _query_tokens(normalized_query)
    if not query_tokens:
        return 0.0
    chunk_tokens = set(_query_tokens(normalized_chunk))
    if not chunk_tokens:
        return 0.0
    overlap = sum(1 for token in query_tokens if token in chunk_tokens)
    token_score = overlap / max(len(query_tokens), 1)
    strong_score = strong_overlap / max(len(strong_terms), 1) if strong_terms else 0.0
    score = max(token_score * 0.7, strong_score)
    if any(token in normalized_chunk for token in _cjk_strong_terms(normalized_query)):
        score += 0.1
    return max(0.0, min(1.0, score))


def _retrieve_from_document_list(
    *,
    endpoint: str,
    dataset_id: str,
    api_key: str,
    query: str,
    max_results: int,
    timeout_seconds: int,
) -> list[CozeRetrievalResult]:
    payload = _coze_document_list_payload(dataset_id=dataset_id)
    response_payload = _request_json(
        url=_coze_document_list_url(endpoint),
        api_key=api_key,
        method="POST",
        payload=payload,
        timeout_seconds=timeout_seconds,
    )
    scored: list[tuple[float, str, dict[str, Any]]] = []
    for record in _document_records(response_payload):
        document_text = _document_text(record, timeout_seconds=timeout_seconds)
        for chunk in _split_document_text(document_text):
            score = _score_document_chunk(query, chunk)
            if score < DEFAULT_COZE_DOCUMENT_MIN_SCORE:
                continue
            scored.append((score, chunk, record))
    scored.sort(key=lambda item: item[0], reverse=True)
    results: list[CozeRetrievalResult] = []
    normalized_dataset_id = dataset_id.strip()
    bounded_max_results = max(1, min(max_results, DEFAULT_COZE_MAX_RESULTS))
    for index, (score, chunk, record) in enumerate(scored[:bounded_max_results], start=1):
        results.append(
            CozeRetrievalResult(
                content=chunk[:DEFAULT_COZE_MAX_CONTENT_BYTES],
                rank=index,
                score=score,
                dataset_id=normalized_dataset_id,
                segment_id=None,
                document_id=_document_id(record),
                document_name=_document_name(record),
            )
        )
    return results


def _record_content(record: dict[str, Any]) -> str:
    nested_candidates = [
        record,
        record.get("segment") if isinstance(record.get("segment"), dict) else {},
        record.get("slice") if isinstance(record.get("slice"), dict) else {},
        record.get("chunk") if isinstance(record.get("chunk"), dict) else {},
    ]
    for candidate in nested_candidates:
        if not isinstance(candidate, dict):
            continue
        for key in ("content", "text", "answer", "snippet"):
            value = str(candidate.get(key) or "").strip()
            if value:
                return value
    return ""


def _record_score(record: dict[str, Any]) -> float:
    for key in ("score", "similarity", "distance_score", "rank_score"):
        if key in record:
            return _float_score(record.get(key))
    return 1.0


def _record_document(record: dict[str, Any]) -> dict[str, Any]:
    for key in ("document", "document_info", "file", "source"):
        value = record.get(key)
        if isinstance(value, dict):
            return value
    segment = record.get("segment") if isinstance(record.get("segment"), dict) else {}
    value = segment.get("document") if isinstance(segment.get("document"), dict) else {}
    return value if isinstance(value, dict) else {}


def _float_score(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _coze_error_detail(payload: bytes) -> str:
    text = payload.decode("utf-8", errors="replace").strip()
    if not text:
        return ""
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return text[:COZE_ERROR_DETAIL_MAX_CHARS]
    if isinstance(decoded, dict):
        parts = [
            str(decoded.get(key) or "").strip()
            for key in ("code", "msg", "message", "error")
            if str(decoded.get(key) or "").strip()
        ]
        if parts:
            return ": ".join(parts)[:COZE_ERROR_DETAIL_MAX_CHARS]
    return text[:COZE_ERROR_DETAIL_MAX_CHARS]


class CozeKnowledgeBaseAdapter:
    provider = CONNECTOR_PROVIDER_COZE

    def retrieve(
        self,
        *,
        endpoint: str,
        dataset_id: str,
        api_key: str,
        query: str,
        max_results: int,
        timeout_seconds: int,
    ) -> list[CozeRetrievalResult]:
        token = api_key.strip()
        if not token:
            raise CozeConnectorError("coze api key is missing")
        normalized_dataset_id = dataset_id.strip()
        if not normalized_dataset_id:
            raise CozeConnectorError("coze dataset_id is missing")
        bounded_max_results = max(1, min(max_results, DEFAULT_COZE_MAX_RESULTS))
        if not _path_looks_like_retrieve_endpoint(
            urllib.parse.urlsplit(endpoint.strip().rstrip("/")).path
        ):
            return _retrieve_from_document_list(
                endpoint=endpoint,
                dataset_id=normalized_dataset_id,
                api_key=token,
                query=query,
                max_results=bounded_max_results,
                timeout_seconds=timeout_seconds,
            )
        payload = _coze_retrieve_payload(
            dataset_id=normalized_dataset_id,
            query=query,
            max_results=bounded_max_results,
        )
        response_payload = _request_json(
            url=_coze_retrieve_url(endpoint, normalized_dataset_id),
            api_key=token,
            method="POST",
            payload=payload,
            timeout_seconds=timeout_seconds,
        )
        results: list[CozeRetrievalResult] = []
        for index, record in enumerate(
            _candidate_records(response_payload)[:bounded_max_results],
            start=1,
        ):
            content = _record_content(record)
            if not content:
                continue
            document = _record_document(record)
            segment = record.get("segment") if isinstance(record.get("segment"), dict) else {}
            results.append(
                CozeRetrievalResult(
                    content=content[:DEFAULT_COZE_MAX_CONTENT_BYTES],
                    rank=index,
                    score=_record_score(record),
                    dataset_id=normalized_dataset_id,
                    segment_id=str(
                        record.get("segment_id")
                        or record.get("slice_id")
                        or record.get("chunk_id")
                        or segment.get("id")
                        or ""
                    )
                    or None,
                    document_id=str(
                        record.get("document_id")
                        or record.get("doc_id")
                        or document.get("document_id")
                        or document.get("id")
                        or ""
                    )
                    or None,
                    document_name=str(
                        record.get("document_name")
                        or document.get("name")
                        or document.get("document_name")
                        or "Coze document"
                    )[:300],
                )
            )
        return results


def get_coze_retrieval_adapter(provider: str) -> CozeRetrievalAdapter | None:
    if provider.strip().lower() == CONNECTOR_PROVIDER_COZE:
        return CozeKnowledgeBaseAdapter()
    return None
