from __future__ import annotations

import re
from dataclasses import dataclass

PermissionMode = str

READ_TOOLS = {"read_file", "list_files", "search_files"}
WRITE_TOOLS = {"write_file", "apply_patch"}
PREVIEW_TOOLS = {"preview_write_file", "preview_apply_patch"}
COMMIT_TOOLS = {"commit_write_file", "commit_apply_patch"}
SHELL_TOOLS = {"run_shell", "run_tests", "git"}

DANGEROUS_COMMAND_PATTERNS = [
    re.compile(r"\brm\s+(-[^\s]*r[^\s]*f|-f[^\s]*r)\s+/(?:\s|$)"),
    re.compile(r"\bsudo\b"),
    re.compile(r"\bsu\s+-?\b"),
    re.compile(r"\bmkfs(?:\.[a-z0-9]+)?\b"),
    re.compile(r"\bdd\s+if=.*\bof=/dev/", re.IGNORECASE),
    re.compile(r":\(\)\s*\{\s*:\|:\s*&\s*\};:"),
    re.compile(r"\bshutdown\b|\breboot\b|\bhalt\b"),
    re.compile(r"\bdiskutil\b|\bmount\b|\bumount\b"),
    re.compile(r"\bchmod\s+-R\s+777\s+/"),
    re.compile(r"\bchown\s+-R\s+[^;&|]+\s+/"),
    re.compile(r">\s*(/etc|/bin|/sbin|/usr|/System|/Library|/var|~/.ssh)(?:/|\b)"),
    re.compile(r"\bcurl\b[^|;&]+[|]\s*(?:sh|bash)\b"),
    re.compile(r"\bwget\b[^|;&]+[|]\s*(?:sh|bash)\b"),
]

SAFE_COMMAND_PREFIXES = (
    "pwd",
    "ls",
    "find .",
    "rg ",
    "grep ",
    "cat ",
    "sed -n",
    "git status",
    "git diff",
    "git log",
    "git show",
    "git branch",
    "git rev-parse",
    "git ls-files",
    "python -m pytest",
    "python3 -m pytest",
    "pytest",
    "uv run pytest",
    "uv run ruff check",
    "ruff check",
    "npm test",
    "npm run lint",
    "npm run build",
)


@dataclass(frozen=True)
class PermissionDecision:
    action: str
    risk_level: str
    reason: str

    @property
    def allowed(self) -> bool:
        return self.action == "allow"

    @property
    def requires_confirmation(self) -> bool:
        return self.action == "confirm"

    @property
    def denied(self) -> bool:
        return self.action == "deny"


def command_is_dangerous(command: str) -> bool:
    normalized = " ".join(command.strip().split())
    return any(pattern.search(normalized) for pattern in DANGEROUS_COMMAND_PATTERNS)


def command_is_safe_for_full_auto(command: str) -> bool:
    normalized = " ".join(command.strip().split())
    if command_is_dangerous(normalized):
        return False
    return any(
        normalized == prefix or normalized.startswith(prefix + " ")
        for prefix in SAFE_COMMAND_PREFIXES
    )


class PermissionEngine:
    def __init__(self, mode: PermissionMode) -> None:
        if mode not in {"confirm", "auto-edit", "full-auto"}:
            raise ValueError(f"unsupported permission mode: {mode}")
        self.mode = mode

    def decide(
        self,
        tool_name: str,
        input_json: dict,
        *,
        target: str = "host",
    ) -> PermissionDecision:
        if target == "sandbox":
            return PermissionDecision("allow", "high", "sandbox target delegates policy to Harness")
        if tool_name in READ_TOOLS:
            return PermissionDecision("allow", "low", "read-only workspace tool")
        if tool_name in PREVIEW_TOOLS:
            return PermissionDecision("allow", "high", "non-mutating diff preview")
        if tool_name in WRITE_TOOLS:
            if self.mode == "confirm":
                return PermissionDecision("confirm", "high", "file write requires confirmation")
            return PermissionDecision("allow", "high", f"file write allowed by {self.mode}")
        if tool_name in COMMIT_TOOLS:
            if self.mode == "confirm":
                return PermissionDecision(
                    "confirm",
                    "high",
                    "pending change commit requires confirmation",
                )
            return PermissionDecision(
                "allow",
                "high",
                f"pending change commit allowed by {self.mode}",
            )
        if tool_name in SHELL_TOOLS:
            command = str(input_json.get("command") or input_json.get("cmd") or "").strip()
            if tool_name == "git" and not command:
                command = "git " + " ".join(map(str, input_json.get("args") or []))
            if command_is_dangerous(command):
                return PermissionDecision("deny", "critical", "dangerous command blocked")
            if self.mode in {"confirm", "auto-edit"}:
                return PermissionDecision("confirm", "high", "shell command requires confirmation")
            if command_is_safe_for_full_auto(command):
                return PermissionDecision("allow", "high", "safe full-auto shell command")
            return PermissionDecision(
                "confirm",
                "high",
                "unclassified shell command requires confirmation",
            )
        return PermissionDecision("confirm", "unknown", "unknown tool requires confirmation")
