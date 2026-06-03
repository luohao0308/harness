from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

PricingVerificationStatus = Literal[
    "verified",
    "price_unverified",
    "sku_ambiguous",
    "currency_conversion_required",
    "stale",
]

BLOCKING_PRICING_STATUSES = {
    "missing_pricing",
    "price_unverified",
    "sku_ambiguous",
    "currency_conversion_required",
    "stale",
    "invalid_pricing",
}
SOURCE_BLOCKING_STATUSES = BLOCKING_PRICING_STATUSES - {"missing_pricing", "invalid_pricing"}
VERIFIED_USD_STATUS = "verified"


class ModelPricingSourceRow(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    mapped_provider: str = Field(min_length=1)
    mapped_model: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    official_url: str = Field(min_length=1)
    retrieved_at: datetime
    unit: Literal["per_1m_tokens"]
    currency: str = Field(min_length=3, max_length=8)
    input_per_1m: str | None = None
    cached_input_per_1m: str | None = None
    output_per_1m: str | None = None
    prompt_per_1k_usd: str | None = None
    cache_prompt_per_1k_usd: str | None = None
    completion_per_1k_usd: str | None = None
    verification_status: PricingVerificationStatus
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    region: str | None = None
    token_tier: str | None = None
    mode: str | None = None
    context_window_tokens: int | None = None
    max_output_tokens: int | None = None
    source_hash: str = Field(min_length=64, max_length=64)
    source_excerpt: str = Field(min_length=1)
    notes: str | None = None

    @field_validator("currency")
    @classmethod
    def _normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("provider", "model", "mapped_provider", "mapped_model")
    @classmethod
    def _normalize_key(cls, value: str) -> str:
        return value.strip()

    @field_validator(
        "input_per_1m",
        "cached_input_per_1m",
        "output_per_1m",
        "prompt_per_1k_usd",
        "cache_prompt_per_1k_usd",
        "completion_per_1k_usd",
    )
    @classmethod
    def _validate_decimal_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("price fields must be decimal strings") from exc
        return value

    @property
    def source_key(self) -> str:
        return f"{self.mapped_provider}/{self.mapped_model}"

    def current_status(self, *, now: datetime | None = None) -> PricingVerificationStatus:
        reference = now or datetime.now(UTC)
        if (
            self.verification_status == "verified"
            and self.valid_until
            and self.valid_until <= reference
        ):
            return "stale"
        return self.verification_status

    def blocks_usd_rollup(self, *, now: datetime | None = None) -> bool:
        return self.current_status(now=now) != VERIFIED_USD_STATUS or self.currency != "USD"


class ModelPricingSourceDocument(BaseModel):
    schema_version: str
    retrieved_at: datetime
    parser_version: str
    rows: list[ModelPricingSourceRow]


class ModelPricingSourceStatus(BaseModel):
    model: str
    status: str
    reason: str
    source_status: str | None = None


_SOURCE_PATH = Path(__file__).with_name("model_pricing_sources.json")


@lru_cache(maxsize=1)
def load_model_pricing_source_document() -> ModelPricingSourceDocument:
    with _SOURCE_PATH.open(encoding="utf-8") as handle:
        return ModelPricingSourceDocument.model_validate(json.load(handle))


def list_model_pricing_sources(*, now: datetime | None = None) -> list[ModelPricingSourceRow]:
    document = load_model_pricing_source_document()
    rows: list[ModelPricingSourceRow] = []
    for row in document.rows:
        status = row.current_status(now=now)
        rows.append(row.model_copy(update={"verification_status": status}))
    return rows


def model_pricing_source_index(
    *, now: datetime | None = None,
) -> dict[tuple[str, str], ModelPricingSourceRow]:
    return {
        (row.mapped_provider, row.mapped_model): row
        for row in list_model_pricing_sources(now=now)
    }


def lookup_model_pricing_source(
    provider: str,
    model: str,
    *,
    now: datetime | None = None,
) -> ModelPricingSourceRow | None:
    return model_pricing_source_index(now=now).get((provider, model))


def source_status_for_model(
    provider: str,
    model: str,
    *,
    now: datetime | None = None,
) -> ModelPricingSourceStatus:
    row = lookup_model_pricing_source(provider, model, now=now)
    key = f"{provider}/{model}"
    if row is None:
        return ModelPricingSourceStatus(
            model=key,
            status="missing_pricing",
            reason="No official-source pricing row is registered for this model.",
            source_status=None,
        )
    status = row.current_status(now=now)
    if status != "verified":
        return ModelPricingSourceStatus(
            model=key,
            status=status,
            reason=f"Official source row is {status}.",
            source_status=status,
        )
    if row.currency != "USD":
        return ModelPricingSourceStatus(
            model=key,
            status="currency_conversion_required",
            reason=f"Official source is {row.currency}; no FX source is recorded for USD rollup.",
            source_status=status,
        )
    return ModelPricingSourceStatus(
        model=key,
        status="verified",
        reason="Official USD source row is verified.",
        source_status=status,
    )


def pricing_row_matches_source(row: object, source: ModelPricingSourceRow) -> bool:
    prompt_price = str(getattr(row, "prompt_per_1k_usd", "") or "")
    completion_price = str(getattr(row, "completion_per_1k_usd", "") or "")
    cache_prompt_price = str(getattr(row, "cache_prompt_per_1k_usd", "") or "0")
    source_cache_prompt_price = str(source.cache_prompt_per_1k_usd or "0")
    return (
        getattr(row, "provider", None) == source.mapped_provider
        and getattr(row, "model", None) == source.mapped_model
        and str(getattr(row, "currency", "USD") or "USD").upper() == source.currency
        and prompt_price == str(source.prompt_per_1k_usd or "")
        and completion_price == str(source.completion_per_1k_usd or "")
        and cache_prompt_price == source_cache_prompt_price
    )


def per_1m_to_per_1k(value: str | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(value) / Decimal(1000)
