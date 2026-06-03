"""Cost contract grader and pricing helpers."""

# ruff: noqa: F401,F403,F405,I001,UP037
from ..common import *

def _grade_cost_contract(
    *,
    session: Session,
    organization_id: str | None,
    model_calls: list[ModelCall],
    expected_json: dict,
) -> dict:
    contract = expected_json.get("cost_contract")
    configured = isinstance(contract, dict)
    aggregate = _aggregate_cost(session, organization_id, model_calls)
    failures: list[str] = []
    limit_exceeded: list[str] = []
    if configured:
        assert isinstance(contract, dict)
        max_cost = contract.get("max_cost_usd")
        if max_cost is not None:
            try:
                max_cost_decimal = Decimal(str(max_cost))
                if aggregate["cost_decimal"] > max_cost_decimal:
                    limit_exceeded.append("max_cost_usd")
                    failures.append(
                        f"max_cost_usd_exceeded:{aggregate['actual_cost_usd']}>{max_cost_decimal}"
                    )
            except (InvalidOperation, ValueError):
                failures.append("invalid_max_cost_usd")
        max_prompt = contract.get("max_prompt_tokens")
        if isinstance(max_prompt, int) and aggregate["prompt_tokens"] > max_prompt:
            limit_exceeded.append("max_prompt_tokens")
            failures.append(f"max_prompt_tokens_exceeded:{aggregate['prompt_tokens']}>{max_prompt}")
        max_completion = contract.get("max_completion_tokens")
        if isinstance(max_completion, int) and aggregate["completion_tokens"] > max_completion:
            limit_exceeded.append("max_completion_tokens")
            failures.append(
                f"max_completion_tokens_exceeded:{aggregate['completion_tokens']}>{max_completion}"
            )
        max_total = contract.get("max_total_tokens")
        total_tokens = aggregate["prompt_tokens"] + aggregate["completion_tokens"]
        if isinstance(max_total, int) and total_tokens > max_total:
            limit_exceeded.append("max_total_tokens")
            failures.append(f"max_total_tokens_exceeded:{total_tokens}>{max_total}")
    return {
        "configured": configured,
        "passed": not failures,
        "failures": failures,
        "limit_exceeded": limit_exceeded,
        "actual_cost_usd": aggregate["actual_cost_usd"],
        "prompt_tokens": aggregate["prompt_tokens"],
        "completion_tokens": aggregate["completion_tokens"],
        "model_call_count": len(model_calls),
        "missing_pricing": aggregate["missing_pricing"],
        "pricing_breakdown": aggregate["pricing_breakdown"],
    }


def _aggregate_cost(
    session: Session,
    organization_id: str | None,
    model_calls: list[ModelCall],
) -> dict:
    total_cost = Decimal("0")
    prompt_tokens_total = 0
    completion_tokens_total = 0
    missing_pricing: list[str] = []
    pricing_breakdown: dict[str, dict[str, object]] = {}
    pricing_cache: dict[tuple[str, str], ModelPricing | None] = {}
    for call in model_calls:
        prompt_tokens = max(0, int(call.prompt_tokens or 0))
        completion_tokens = max(0, int(call.completion_tokens or 0))
        prompt_tokens_total += prompt_tokens
        completion_tokens_total += completion_tokens
        provider = (call.model_provider or "default").strip() or "default"
        model = (call.model_name or "default").strip() or "default"
        cache_key = (provider, model)
        if cache_key not in pricing_cache:
            pricing_cache[cache_key] = _lookup_pricing(session, organization_id, provider, model)
        pricing = pricing_cache[cache_key]
        if pricing is None:
            missing_pricing.append(f"{provider}/{model}")
            continue
        try:
            prompt_per_1k = Decimal(pricing.prompt_per_1k_usd or "0")
            completion_per_1k = Decimal(pricing.completion_per_1k_usd or "0")
        except (InvalidOperation, ValueError):
            missing_pricing.append(f"{provider}/{model}")
            continue
        line_cost = (
            (Decimal(prompt_tokens) / Decimal(1000)) * prompt_per_1k
            + (Decimal(completion_tokens) / Decimal(1000)) * completion_per_1k
        )
        total_cost += line_cost
        bucket_key = f"{provider}/{model}"
        bucket = pricing_breakdown.setdefault(
            bucket_key,
            {
                "calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cost_usd": "0",
            },
        )
        bucket["calls"] = int(bucket["calls"]) + 1  # type: ignore[arg-type]
        bucket["prompt_tokens"] = int(bucket["prompt_tokens"]) + prompt_tokens  # type: ignore[arg-type]
        bucket["completion_tokens"] = int(bucket["completion_tokens"]) + completion_tokens  # type: ignore[arg-type]
        bucket["cost_usd"] = _format_cost(
            Decimal(str(bucket["cost_usd"])) + line_cost
        )
    return {
        "cost_decimal": total_cost,
        "actual_cost_usd": _format_cost(total_cost),
        "prompt_tokens": prompt_tokens_total,
        "completion_tokens": completion_tokens_total,
        "missing_pricing": sorted(set(missing_pricing)),
        "pricing_breakdown": pricing_breakdown,
    }


def _lookup_pricing(
    session: Session,
    organization_id: str | None,
    provider: str,
    model: str,
) -> ModelPricing | None:
    fallback_chain: list[tuple[str | None, str, str]] = []
    if organization_id:
        fallback_chain.append((organization_id, provider, model))
        fallback_chain.append((organization_id, provider, "default"))
    fallback_chain.append((None, provider, model))
    fallback_chain.append((None, provider, "default"))
    fallback_chain.append((None, "default", "default"))
    for org_id, prov, mdl in fallback_chain:
        if org_id is None:
            org_predicate = ModelPricing.organization_id.is_(None)
        else:
            org_predicate = ModelPricing.organization_id == org_id
        row = session.execute(
            select(ModelPricing).where(
                org_predicate,
                ModelPricing.provider == prov,
                ModelPricing.model == mdl,
                ModelPricing.active.is_(True),
            )
        ).scalar_one_or_none()
        if row is not None:
            return row
    return None


def _format_cost(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.000001"))
    return f"{quantized:.6f}"



__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
