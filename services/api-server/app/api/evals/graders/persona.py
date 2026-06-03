"""Persona contract grader."""

# ruff: noqa: F401,F403,F405,I001,UP037
from ..common import *
from ..helpers import *
from .helpers import *

def _grade_persona_contract(model_calls: list[ModelCall], expected_json: dict) -> dict:
    contract = expected_json.get("persona_contract")
    if not isinstance(contract, dict):
        return {
            "configured": False,
            "passed": True,
            "failures": [],
        }
    assistant_texts = [_extract_assistant_text(call.response_json) for call in model_calls]
    combined_text = "\n".join(text for text in assistant_texts if text)
    must_mention_role_as = contract.get("must_mention_role_as")
    role_drift_phrases = _as_string_list(contract.get("ban_role_drift_phrases"))
    tone_required_markers = _as_string_list(contract.get("tone_required_markers"))
    tone_banned_markers = _as_string_list(contract.get("tone_banned_markers"))
    out_of_scope_markers = _as_string_list(contract.get("out_of_scope_markers"))

    failures: list[str] = []
    if isinstance(must_mention_role_as, str) and must_mention_role_as:
        if must_mention_role_as not in combined_text:
            failures.append(f"role_missing:{must_mention_role_as}")

    role_drift_hits = _matched_markers(combined_text, role_drift_phrases)
    failures.extend(f"role_drift:{phrase}" for phrase in role_drift_hits)

    missing_tone = [
        marker for marker in tone_required_markers if marker and marker not in combined_text
    ]
    tone_banned_hits = _matched_markers(combined_text, tone_banned_markers)
    failures.extend(f"tone_violation:missing:{marker}" for marker in missing_tone)
    failures.extend(f"tone_violation:banned:{marker}" for marker in tone_banned_hits)

    first_person_drift_count = _first_person_drift_count(combined_text)
    max_first_person_drift_count = contract.get("max_first_person_drift_count")
    if (
        isinstance(max_first_person_drift_count, int)
        and first_person_drift_count > max_first_person_drift_count
    ):
        failures.append(
            "first_person_drift_exceeded:"
            f"{first_person_drift_count}>{max_first_person_drift_count}"
        )

    if contract.get("expect_out_of_scope_response") and out_of_scope_markers:
        matched_scope_markers = _matched_markers(combined_text, out_of_scope_markers)
        if not matched_scope_markers:
            failures.append("scope_breach:missing_out_of_scope_marker")
    else:
        matched_scope_markers = _matched_markers(combined_text, out_of_scope_markers)

    return {
        "configured": True,
        "passed": not failures,
        "failures": failures,
        "must_mention_role_as": must_mention_role_as,
        "role_drift_count": len(role_drift_hits),
        "role_drift_phrases": role_drift_hits,
        "tone_missing_markers": missing_tone,
        "tone_banned_markers": tone_banned_hits,
        "first_person_drift_count": first_person_drift_count,
        "max_first_person_drift_count": max_first_person_drift_count,
        "out_of_scope_markers_seen": matched_scope_markers,
        "model_call_count": len(model_calls),
    }



def _first_person_drift_count(text: str) -> int:
    return len(re.findall(r"(我是|\bI\s+am\b|\bI'm\b)", text, flags=re.IGNORECASE))



__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
