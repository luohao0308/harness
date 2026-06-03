"""Text normalization, chunking, embeddings, and scoring helpers."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *

def _normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _grounding_outcome(
    *,
    local_status: str,
    web_sources: list[WebResearchSource],
    connector_hit_count: int = 0,
    connector_provider: str | None = None,
) -> dict:
    if local_status == "sufficient":
        return {
            "grounding_provider": GROUNDING_PROVIDER_LOCAL_KNOWLEDGE,
            "fixture_grounded": False,
            "verified_grounded": True,
            "grounding_verification_reason": GROUNDING_REASON_LOCAL_SUFFICIENT,
        }
    if connector_hit_count > 0:
        provider = (connector_provider or "dify").strip().lower()
        return {
            "grounding_provider": (
                GROUNDING_PROVIDER_COZE_CONNECTOR
                if provider == "coze"
                else GROUNDING_PROVIDER_DIFY_CONNECTOR
            ),
            "fixture_grounded": False,
            "verified_grounded": True,
            "grounding_verification_reason": GROUNDING_REASON_CONNECTOR_SOURCE_BOUND,
            "verified_grounded_semantics": (
                "external_connector_source_bound_not_factual_verification"
            ),
        }
    if web_sources:
        provider = str(
            (
                web_sources[0].metadata_json
                if isinstance(web_sources[0].metadata_json, dict)
                else {}
            ).get("provider")
            or WEB_RESEARCH_PROVIDER_FAKE
        )
        if provider != WEB_RESEARCH_PROVIDER_FAKE:
            return {
                "grounding_provider": (
                    GROUNDING_PROVIDER_TAVILY_SEARCH
                    if provider == WEB_RESEARCH_PROVIDER_TAVILY
                    else provider
                ),
                "fixture_grounded": False,
                "verified_grounded": True,
                "grounding_verification_reason": GROUNDING_REASON_REAL_SOURCE_BOUND,
                "verified_grounded_semantics": "real_source_bound_not_factual_verification",
            }
        return {
            "grounding_provider": GROUNDING_PROVIDER_FAKE_WEB_FIXTURE,
            "fixture_grounded": True,
            "verified_grounded": False,
            "grounding_verification_reason": GROUNDING_REASON_FIXTURE_NOT_VERIFIED,
        }
    return {
        "grounding_provider": GROUNDING_PROVIDER_NONE,
        "fixture_grounded": False,
        "verified_grounded": False,
        "grounding_verification_reason": GROUNDING_REASON_NO_VERIFIED_EVIDENCE,
    }


def _policy_decision_for_text(value: str) -> str:
    if POLICY_DENY_MARKER in value:
        return POLICY_DECISION_DENIED
    if POLICY_REDACT_MARKER in value:
        return POLICY_DECISION_REDACTED
    return POLICY_DECISION_ALLOWED


def _redact_policy_marked_text(value: str) -> tuple[str, int]:
    redacted, count = re.subn(
        rf"{re.escape(POLICY_REDACT_MARKER)}[^\n]*",
        POLICY_REDACTION_TOKEN,
        value,
    )
    return redacted, count


def _tokenize(value: str) -> list[str]:
    normalized = _normalize_text(value)
    tokens = [token.lower() for token in ASCII_TOKEN_RE.findall(normalized)]
    cjk_tokens = [
        token for token in CJK_TOKEN_RE.findall(normalized) if token not in CJK_STOP_CHARS
    ]
    tokens.extend(cjk_tokens)
    return tokens


def _has_cjk_signal(value: str) -> bool:
    return sum(1 for token in _tokenize(value) if CJK_TOKEN_RE.fullmatch(token)) >= 2


def _is_single_cjk_strong_match(
    *,
    query: str,
    top_candidates: list[
        tuple[float, KnowledgeChunk, KnowledgeEmbedding, KnowledgeDocument, KnowledgeSource]
    ],
) -> bool:
    return len(top_candidates) == 1 and top_candidates[0][0] >= 0.95 and _has_cjk_signal(query)


def _fake_embedding(value: str, *, dimensions: int = 24) -> list[float]:
    vec = [0.0] * dimensions
    for token in _tokenize(value):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        for index in range(dimensions):
            byte = digest[index % len(digest)]
            vec[index] += (byte / 255.0) - 0.5
    norm = math.sqrt(sum(component * component for component in vec)) or 1.0
    return [component / norm for component in vec]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    length = min(len(left), len(right))
    if length == 0:
        return 0.0
    numerator = sum(left[index] * right[index] for index in range(length))
    left_norm = math.sqrt(sum(left[index] * left[index] for index in range(length))) or 1.0
    right_norm = math.sqrt(sum(right[index] * right[index] for index in range(length))) or 1.0
    return max(0.0, min(1.0, numerator / (left_norm * right_norm)))


def _lexical_similarity(query: str, text: str) -> float:
    query_terms = set(_tokenize(query))
    if not query_terms:
        return 0.0
    text_terms = set(_tokenize(text))
    if not text_terms:
        return 0.0
    overlap = query_terms & text_terms
    return min(1.0, len(overlap) / max(1, len(query_terms)))


def _chunk_text(text: str) -> list[tuple[int, int, str]]:
    normalized = _normalize_text(text).strip()
    if not normalized:
        return []
    chunks: list[tuple[int, int, str]] = []
    cursor = 0
    while cursor < len(normalized):
        end = min(len(normalized), cursor + CHUNK_TARGET_CHARS)
        if end < len(normalized):
            split = normalized.rfind("\n", cursor, end)
            if split > cursor + 100:
                end = split + 1
        chunk = normalized[cursor:end].strip()
        if chunk:
            chunks.append((cursor, end, chunk))
        if end >= len(normalized):
            break
        next_cursor = max(end - CHUNK_OVERLAP_CHARS, cursor + 1)
        cursor = next_cursor if next_cursor < end else end
    return chunks

__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
