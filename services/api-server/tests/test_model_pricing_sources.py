import hashlib
import importlib.util
import re
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.db.models import ModelPricing
from app.main import app
from app.settings.model_pricing_sources import (
    BLOCKING_PRICING_STATUSES,
    list_model_pricing_sources,
    load_model_pricing_source_document,
    per_1m_to_per_1k,
    pricing_row_matches_source,
    source_status_for_model,
)
from tests.conftest import AUTH_HEADERS

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_model_pricing_source_document_covers_builtin_presets() -> None:
    document = load_model_pricing_source_document()
    rows = list_model_pricing_sources(now=datetime(2026, 5, 30, tzinfo=UTC))

    assert document.schema_version == "model_pricing_sources.v1"
    assert document.parser_version == "manual-official-source-2026-05-30"
    assert {
        f"{row.mapped_provider}/{row.mapped_model}"
        for row in rows
    } == {
        "deepseek-flash/deepseek-v4-flash",
        "deepseek-pro/deepseek-v4-pro",
        "openai-compatible/gpt-5.5",
        "kimi/kimi-k2.6",
        "z-ai/glm-5.1",
    }
    assert all(re.fullmatch(r"[0-9a-f]{64}", row.source_hash) for row in rows)
    for row in rows:
        assert row.source_hash == hashlib.sha256(row.source_excerpt.encode()).hexdigest()


def test_verified_usd_rows_convert_per_1m_to_backend_per_1k() -> None:
    rows = {
        row.source_key: row
        for row in list_model_pricing_sources(now=datetime(2026, 5, 30, tzinfo=UTC))
    }

    flash = rows["deepseek-flash/deepseek-v4-flash"]
    assert flash.currency == "USD"
    assert flash.verification_status == "verified"
    assert per_1m_to_per_1k(flash.input_per_1m) == Decimal(flash.prompt_per_1k_usd)
    assert per_1m_to_per_1k(flash.cached_input_per_1m) == Decimal(
        flash.cache_prompt_per_1k_usd
    )
    assert per_1m_to_per_1k(flash.output_per_1m) == Decimal(
        flash.completion_per_1k_usd
    )

    latest_openai = rows["openai-compatible/gpt-5.5"]
    assert latest_openai.currency == "USD"
    assert latest_openai.verification_status == "verified"
    assert per_1m_to_per_1k(latest_openai.input_per_1m) == Decimal("0.005")
    assert per_1m_to_per_1k(latest_openai.cached_input_per_1m) == Decimal("0.0005")
    assert per_1m_to_per_1k(latest_openai.output_per_1m) == Decimal("0.030")

    kimi = rows["kimi/kimi-k2.6"]
    assert kimi.currency == "USD"
    assert kimi.verification_status == "verified"
    assert per_1m_to_per_1k(kimi.input_per_1m) == Decimal("0.00095")
    assert per_1m_to_per_1k(kimi.cached_input_per_1m) == Decimal("0.00016")
    assert per_1m_to_per_1k(kimi.output_per_1m) == Decimal("0.00400")

    glm = rows["z-ai/glm-5.1"]
    assert glm.currency == "USD"
    assert glm.verification_status == "verified"
    assert per_1m_to_per_1k(glm.input_per_1m) == Decimal("0.0014")
    assert per_1m_to_per_1k(glm.cached_input_per_1m) == Decimal("0.00026")
    assert per_1m_to_per_1k(glm.output_per_1m) == Decimal("0.0044")


def test_missing_pricing_blocks_usd_rollup() -> None:
    missing = source_status_for_model("unknown", "unknown-model")

    assert missing.status == "missing_pricing"
    assert missing.status in BLOCKING_PRICING_STATUSES


def test_deepseek_pro_current_price_remains_verified_without_validity_window() -> None:
    current = source_status_for_model(
        "deepseek-pro",
        "deepseek-v4-pro",
        now=datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )
    future = source_status_for_model(
        "deepseek-pro",
        "deepseek-v4-pro",
        now=datetime(2026, 12, 31, 12, 0, tzinfo=UTC),
    )
    rows = {
        row.source_key: row
        for row in list_model_pricing_sources(now=datetime(2026, 12, 31, 12, 0, tzinfo=UTC))
    }
    deepseek_pro = rows["deepseek-pro/deepseek-v4-pro"]

    assert current.status == "verified"
    assert future.status == "verified"
    assert deepseek_pro.valid_until is None
    assert deepseek_pro.token_tier == "all"
    assert deepseek_pro.blocks_usd_rollup(now=datetime(2026, 12, 31, 12, 0, tzinfo=UTC)) is False


def test_verified_usd_source_rows_have_exact_seed_projection() -> None:
    sources = list_model_pricing_sources(now=datetime(2026, 5, 30, tzinfo=UTC))
    seed_rows = _load_official_pricing_seed_rows()
    seed_by_model = {
        f"{row['provider']}/{row['model']}": row
        for row in seed_rows
    }

    assert set(seed_by_model) == {source.source_key for source in sources}
    seeded = {
        key:
        ModelPricing(
            organization_id=None,
            provider=str(row["provider"]),
            model=str(row["model"]),
            prompt_per_1k_usd=str(row["prompt_per_1k_usd"]),
            completion_per_1k_usd=str(row["completion_per_1k_usd"]),
            cache_prompt_per_1k_usd=str(row["cache_prompt_per_1k_usd"]),
            currency=str(row["currency"]),
            active=bool(row["active"]),
            source=str(row["source"]),
        )
        for key, row in seed_by_model.items()
    }

    for source in sources:
        assert source.verification_status == "verified"
        assert source.currency == "USD"
        assert pricing_row_matches_source(seeded[source.source_key], source)


def _load_official_pricing_seed_rows() -> list[dict[str, Any]]:
    path = (
        REPO_ROOT
        / "services/api-server/alembic/versions/20260606_0033_seed_builtin_model_pricing_sources.py"
    )
    spec = importlib.util.spec_from_file_location("seed_builtin_model_pricing_sources_0033", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["seed_builtin_model_pricing_sources_0033"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    rows = module._BUILTIN_PRICING_ROWS
    assert isinstance(rows, list)
    return rows


def test_model_pricing_sources_api_requires_auth_and_returns_statuses() -> None:
    client = TestClient(app)

    unauthenticated = client.get("/api/settings/models/pricing-sources")
    assert unauthenticated.status_code == 401

    response = client.get(
        "/api/settings/models/pricing-sources",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["schema_version"] == "model_pricing_sources.v1"
    assert len(payload["items"]) == 5
    by_model = {
        f"{item['mapped_provider']}/{item['mapped_model']}": item
        for item in payload["items"]
    }
    assert by_model["deepseek-flash/deepseek-v4-flash"]["blocks_usd_rollup"] is False
    assert by_model["openai-compatible/gpt-5.5"]["verification_status"] == "verified"
    assert by_model["openai-compatible/gpt-5.5"]["blocks_usd_rollup"] is False
    assert by_model["kimi/kimi-k2.6"]["currency"] == "USD"
    assert by_model["kimi/kimi-k2.6"]["verification_status"] == "verified"
    assert by_model["kimi/kimi-k2.6"]["blocks_usd_rollup"] is False
    assert by_model["z-ai/glm-5.1"]["currency"] == "USD"
    assert by_model["z-ai/glm-5.1"]["verification_status"] == "verified"
    assert by_model["z-ai/glm-5.1"]["blocks_usd_rollup"] is False
