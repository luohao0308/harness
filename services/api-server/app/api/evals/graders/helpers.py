"""Shared helper functions for deterministic Eval graders."""

# ruff: noqa: F401,F403,F405,I001,UP037
from ..common import *

def _extract_assistant_text(response_json: object) -> str:
    if isinstance(response_json, dict):
        content = response_json.get("content")
        if isinstance(content, str):
            return content
        choices = response_json.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    msg_content = message.get("content")
                    if isinstance(msg_content, str):
                        return msg_content
        message = response_json.get("message")
        if isinstance(message, dict):
            msg_content = message.get("content")
            if isinstance(msg_content, str):
                return msg_content
        text = response_json.get("text")
        if isinstance(text, str):
            return text
    return json.dumps(response_json, ensure_ascii=False) if response_json else ""


def _matched_markers(text: str, markers: list[str]) -> list[str]:
    return [marker for marker in markers if marker and marker in text]


def _has_reason_clause(text: str) -> bool:
    reason_markers = ["因为", "由于", "原因", "出于", "不安全", "不合规", "because", "as "]
    lowered = text.lower()
    return any(marker in lowered for marker in reason_markers)


def _truncate_trace_value(value: str, limit: int = 80) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "..."



def _dict_subset(subset: dict, value: object) -> bool:
    if not isinstance(value, dict):
        return False
    for key, expected in subset.items():
        if key not in value:
            return False
        actual = value[key]
        if isinstance(expected, dict):
            if not _dict_subset(expected, actual):
                return False
        elif isinstance(expected, list):
            if not isinstance(actual, list) or len(actual) != len(expected):
                return False
            for index, expected_item in enumerate(expected):
                if isinstance(expected_item, dict):
                    if not _dict_subset(expected_item, actual[index]):
                        return False
                elif actual[index] != expected_item:
                    return False
        elif actual != expected:
            return False
    return True



__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
