"""Tool contract grader."""

# ruff: noqa: F401,F403,F405,I001,UP037
from ..common import *
from ..helpers import *
from .helpers import *

def _grade_tool_contract(tool_calls: list[ToolCall], expected_json: dict) -> dict:
    contract = expected_json.get("tool_contract")
    if not isinstance(contract, dict):
        return {
            "configured": False,
            "passed": True,
            "failures": [],
        }
    required_tools = _as_string_list(contract.get("required_tools"))
    forbidden_tools = _as_string_list(contract.get("forbidden_tools"))
    expected_calls_raw = contract.get("expected_calls") or []
    expected_calls = [call for call in expected_calls_raw if isinstance(call, dict)]
    ordered = bool(contract.get("ordered"))
    allow_extra_calls = contract.get("allow_extra_calls")
    allow_extra_calls = True if allow_extra_calls is None else bool(allow_extra_calls)

    realized_calls = [call for call in tool_calls if call.status not in {"BLOCKED", "DENIED"}]
    realized_names = [call.tool_name for call in realized_calls]

    failures: list[str] = []
    missing_required = [name for name in required_tools if name not in realized_names]
    forbidden_seen = [name for name in forbidden_tools if name in realized_names]
    if missing_required:
        failures.extend(f"missing_required_tool:{name}" for name in missing_required)
    if forbidden_seen:
        failures.extend(f"forbidden_tool_used:{name}" for name in forbidden_seen)

    expected_calls_matched = 0
    args_mismatches: list[str] = []
    if expected_calls:
        if ordered:
            cursor = 0
            for expected in expected_calls:
                tool_name = str(expected.get("tool_name") or "")
                args_value = expected.get("args_subset")
                args_subset = args_value if isinstance(args_value, dict) else None
                match_found = False
                for idx in range(cursor, len(realized_calls)):
                    candidate = realized_calls[idx]
                    if candidate.tool_name != tool_name:
                        continue
                    if args_subset is not None and not _dict_subset(
                        args_subset, candidate.input_json
                    ):
                        continue
                    cursor = idx + 1
                    expected_calls_matched += 1
                    match_found = True
                    break
                if not match_found:
                    if any(call.tool_name == tool_name for call in realized_calls):
                        args_mismatches.append(tool_name)
                        failures.append(f"args_mismatch:{tool_name}")
                    else:
                        failures.append(f"out_of_order_or_missing:{tool_name}")
        else:
            used_indices: set[int] = set()
            for expected in expected_calls:
                tool_name = str(expected.get("tool_name") or "")
                args_value = expected.get("args_subset")
                args_subset = args_value if isinstance(args_value, dict) else None
                match_found = False
                for idx, candidate in enumerate(realized_calls):
                    if idx in used_indices or candidate.tool_name != tool_name:
                        continue
                    if args_subset is not None and not _dict_subset(
                        args_subset, candidate.input_json
                    ):
                        continue
                    used_indices.add(idx)
                    expected_calls_matched += 1
                    match_found = True
                    break
                if not match_found:
                    if any(call.tool_name == tool_name for call in realized_calls):
                        args_mismatches.append(tool_name)
                        failures.append(f"args_mismatch:{tool_name}")
                    else:
                        failures.append(f"missing_expected_call:{tool_name}")

    if not allow_extra_calls:
        allowed = set(required_tools) | {
            str(call.get("tool_name") or "") for call in expected_calls if isinstance(call, dict)
        }
        extra = [name for name in realized_names if name not in allowed]
        if extra:
            failures.extend(f"unexpected_tool:{name}" for name in dict.fromkeys(extra))

    passed = not failures
    return {
        "configured": True,
        "passed": passed,
        "failures": failures,
        "required_calls_seen": [name for name in required_tools if name in realized_names],
        "forbidden_calls_seen": forbidden_seen,
        "expected_calls_total": len(expected_calls),
        "expected_calls_matched": expected_calls_matched,
        "args_mismatches": args_mismatches,
        "realized_tool_call_count": len(realized_calls),
        "ordered": ordered,
        "allow_extra_calls": allow_extra_calls,
    }



__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
