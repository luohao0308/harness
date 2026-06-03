"""Eval regression metric delta helpers."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
from .graders.cost import _format_cost

def _metric_delta(current_metrics: dict, baseline_metrics: dict, key: str) -> float:
    return round(float(current_metrics.get(key, 0)) - float(baseline_metrics.get(key, 0)), 4)


def _cost_metric_delta(current_metrics: dict, baseline_metrics: dict, key: str) -> str:
    try:
        current = Decimal(str(current_metrics.get(key, "0")))
        baseline = Decimal(str(baseline_metrics.get(key, "0")))
    except (InvalidOperation, ValueError):
        return "0"
    return _format_cost(current - baseline)



__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
