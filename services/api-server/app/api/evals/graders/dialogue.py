"""Dialogue contract grader."""

# ruff: noqa: F401,F403,F405,I001,UP037
from ..common import *
from ..helpers import *
from .helpers import *

def _grade_dialogue_contract(model_calls: list[ModelCall], expected_json: dict) -> dict:
    contract = expected_json.get("dialogue_contract")
    if not isinstance(contract, dict):
        return {
            "configured": False,
            "passed": True,
            "turn_results": [],
        }
    turns_raw = contract.get("turns") or []
    turn_specs = [spec for spec in turns_raw if isinstance(spec, dict)]
    min_turns = contract.get("min_turns")
    max_turns = contract.get("max_turns")
    actual_turn_count = len(model_calls)

    failures: list[str] = []
    if isinstance(min_turns, int) and actual_turn_count < min_turns:
        failures.append(f"turn_count_below_min:{actual_turn_count}<{min_turns}")
    if isinstance(max_turns, int) and actual_turn_count > max_turns:
        failures.append(f"turn_count_above_max:{actual_turn_count}>{max_turns}")

    turn_results: list[dict] = []
    for index, spec in enumerate(turn_specs):
        model_call = model_calls[index] if index < len(model_calls) else None
        assistant_text = _extract_assistant_text(model_call.response_json) if model_call else ""
        contains_required = _as_string_list(spec.get("contains"))
        not_contains_required = _as_string_list(spec.get("not_contains"))
        missing_contains = [
            phrase for phrase in contains_required if phrase and phrase not in assistant_text
        ]
        found_not_contains = [
            phrase
            for phrase in not_contains_required
            if phrase and phrase in assistant_text
        ]
        min_length = spec.get("min_length")
        max_length = spec.get("max_length")
        length_violations: list[str] = []
        if isinstance(min_length, int) and len(assistant_text) < min_length:
            length_violations.append(f"below_min_length:{len(assistant_text)}<{min_length}")
        if isinstance(max_length, int) and len(assistant_text) > max_length:
            length_violations.append(f"above_max_length:{len(assistant_text)}>{max_length}")
        turn_failures: list[str] = []
        if model_call is None:
            turn_failures.append("missing_turn")
        turn_failures.extend(f"missing_contains:{phrase}" for phrase in missing_contains)
        turn_failures.extend(f"unexpected_phrase:{phrase}" for phrase in found_not_contains)
        turn_failures.extend(length_violations)
        turn_results.append(
            {
                "turn_index": index,
                "passed": not turn_failures,
                "missing_contains": missing_contains,
                "found_not_contains": found_not_contains,
                "length_violations": length_violations,
                "assistant_length": len(assistant_text),
                "model_call_id": model_call.id if model_call is not None else None,
            }
        )
        if turn_failures:
            failures.extend(f"turn[{index}].{tag}" for tag in turn_failures)

    return {
        "configured": True,
        "passed": not failures,
        "failures": failures,
        "turn_results": turn_results,
        "expected_turn_count": len(turn_specs),
        "actual_turn_count": actual_turn_count,
    }



__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
