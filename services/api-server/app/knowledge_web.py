from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings

WEB_RESEARCH_PROVIDER_DISABLED = "disabled"
WEB_RESEARCH_PROVIDER_FAKE = "fake"
WEB_RESEARCH_PROVIDER_TAVILY = "tavily"

GROUNDING_PROVIDER_REAL_WEB_RESEARCH = "real_web_research"
GROUNDING_PROVIDER_TAVILY_SEARCH = "tavily_search"

DEFAULT_WEB_RESEARCH_TIMEOUT_SECONDS = 8
DEFAULT_WEB_RESEARCH_MAX_RESULTS = 2
DEFAULT_WEB_RESEARCH_MAX_CONTENT_BYTES = 1200
TAVILY_SEARCH_ENDPOINT = "https://api.tavily.com/search"

SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password)\s*[:=]\s*[^\s]+"),
    re.compile(r"\b[A-Za-z0-9_]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
)


class WebResearchProviderError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class WebResearchResult:
    title: str
    url: str
    snippet: str
    rank: int
    score: float
    published_at: str | None = None
    provider_request_id: str | None = None
    usage_credits: float | None = None
    response_time_ms: int | None = None
    raw_content_available: bool = False

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.snippet.encode("utf-8")).hexdigest()


class WebResearchAdapter(Protocol):
    provider: str

    def search(
        self,
        *,
        query: str,
        max_results: int,
        timeout_seconds: int,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[WebResearchResult]: ...


def redacted_query_preview(query: str, *, max_chars: int = 160) -> str:
    value = query
    for pattern in SECRET_PATTERNS:
        value = pattern.sub("[REDACTED:secret-pattern]", value)
    value = " ".join(value.split())
    return value[:max_chars]


def query_has_secret_pattern(query: str) -> bool:
    return any(pattern.search(query) for pattern in SECRET_PATTERNS)


def resolve_web_research_api_key(provider: str) -> str:
    if provider == WEB_RESEARCH_PROVIDER_TAVILY:
        return get_settings().tavily_api_key.strip()
    return ""


def fake_web_research_allowed() -> bool:
    return get_settings().app_env.lower() in {"test", "development"}


def web_research_health(
    *,
    provider: str,
    policy_enabled: bool,
    mode: str = "local_config_only",
) -> dict:
    if provider == WEB_RESEARCH_PROVIDER_DISABLED:
        return {"status": "policy_disabled", "mode": mode, "network": False}
    if provider == WEB_RESEARCH_PROVIDER_FAKE and not fake_web_research_allowed():
        return {"status": "fake_not_allowed", "mode": mode, "network": False}
    if provider == WEB_RESEARCH_PROVIDER_FAKE:
        return {"status": "configured_no_live_check", "mode": mode, "network": False}
    if provider != WEB_RESEARCH_PROVIDER_TAVILY:
        return {"status": "not_supported_in_environment", "mode": mode, "network": False}
    if not policy_enabled:
        return {"status": "policy_disabled", "mode": mode, "network": False}
    if not resolve_web_research_api_key(provider):
        return {"status": "missing_key", "mode": mode, "network": False}
    return {"status": "configured_no_live_check", "mode": mode, "network": False}


class TavilySearchAdapter:
    provider = WEB_RESEARCH_PROVIDER_TAVILY

    def __init__(self, *, api_key: str | None = None) -> None:
        self.api_key = (api_key or resolve_web_research_api_key(self.provider)).strip()

    def search(
        self,
        *,
        query: str,
        max_results: int,
        timeout_seconds: int,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[WebResearchResult]:
        if not self.api_key:
            raise WebResearchProviderError("tavily api key is missing")
        payload = {
            "query": query,
            "max_results": max(1, min(max_results, DEFAULT_WEB_RESEARCH_MAX_RESULTS)),
            "search_depth": "basic",
            "include_raw_content": False,
            "include_usage": True,
        }
        if include_domains:
            payload["include_domains"] = include_domains
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            TAVILY_SEARCH_ENDPOINT,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            retryable = exc.code in {408, 429, 500, 502, 503, 504}
            raise WebResearchProviderError(
                f"tavily search failed with HTTP {exc.code}",
                retryable=retryable,
            ) from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise WebResearchProviderError("tavily search failed", retryable=True) from exc

        request_id = str(response_payload.get("request_id") or "") or None
        usage = response_payload.get("usage") if isinstance(response_payload, dict) else {}
        usage_credits = None
        if isinstance(usage, dict) and usage.get("credits") is not None:
            try:
                usage_credits = float(usage["credits"])
            except (TypeError, ValueError):
                usage_credits = None
        results = response_payload.get("results") if isinstance(response_payload, dict) else []
        if not isinstance(results, list):
            return []
        normalized: list[WebResearchResult] = []
        for index, item in enumerate(results[:max_results], start=1):
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            snippet = str(item.get("content") or item.get("snippet") or "").strip()
            title = str(item.get("title") or url or "Untitled web source").strip()
            if not url or not snippet:
                continue
            try:
                score = float(item.get("score") or 0.0)
            except (TypeError, ValueError):
                score = 0.0
            normalized.append(
                WebResearchResult(
                    title=title[:300],
                    url=url,
                    snippet=snippet[:DEFAULT_WEB_RESEARCH_MAX_CONTENT_BYTES],
                    rank=index,
                    score=max(0.0, min(1.0, score)),
                    published_at=item.get("published_date") or item.get("published_at"),
                    provider_request_id=request_id,
                    usage_credits=usage_credits,
                    response_time_ms=None,
                    raw_content_available=bool(item.get("raw_content")),
                )
            )
        return normalized


class FakeWebResearchAdapter:
    provider = WEB_RESEARCH_PROVIDER_FAKE

    def search(
        self,
        *,
        query: str,
        max_results: int,
        timeout_seconds: int,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[WebResearchResult]:
        del timeout_seconds, include_domains, exclude_domains
        normalized_query = " ".join(query.split()) or "knowledge"
        results = []
        for index in range(1, max_results + 1):
            snippet = (
                f"Controlled fake web result {index} for {normalized_query}. "
                "This deterministic fixture is used for no-network grounding tests."
            )
            results.append(
                WebResearchResult(
                    title=f"Fake web source {index}",
                    url=f"https://example.test/knowledge/{index}",
                    snippet=snippet,
                    rank=index,
                    score=1.0,
                )
            )
        return results


def get_web_research_adapter(provider: str) -> WebResearchAdapter | None:
    if provider == WEB_RESEARCH_PROVIDER_TAVILY:
        return TavilySearchAdapter()
    if provider == WEB_RESEARCH_PROVIDER_FAKE:
        return FakeWebResearchAdapter()
    return None
