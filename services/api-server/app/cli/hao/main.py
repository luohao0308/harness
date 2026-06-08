from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from hashlib import sha256
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from queue import Empty, Queue
from typing import Any

import httpx

from .api_client import HarnessApiClient, SSEEvent
from .config import clear_persisted_token, format_status, load_config, save_auth
from .local_tools import SHELL_COMMAND_TOOLS, ToolExecutionResult, execute_local_tool
from .permissions import PermissionEngine
from .sandbox_tools import execute_sandbox_tool
from .session_store import SessionStore

GIT_STATUS_CONTEXT_LIMIT = 8
PACKAGE_DISTRIBUTION_NAME = "agent-harness-api-server"
BRIDGE_DEVICE_TOKEN_REF = "bridge.device-token"
BRIDGE_WORKSPACE_ROOT_REF = "bridge.workspace-root"
BRIDGE_AUTO_PAIR_ADAPTERS = ("hao", "codex", "claude_code")
BRIDGE_FULL_RISK_CAPABILITIES = ["host_read", "host_write", "shell", "git", "network"]
BRIDGE_UNCONFIRMED_STATUS_PHRASE = "has not been confirmed"
CODEX_SUBPROCESS_TIMEOUT_SECONDS = 120
CODEX_OUTPUT_LIMIT_BYTES = 64_000
CODEX_PROMPT_CONTEXT_MESSAGE_LIMIT = 4000
CODEX_WORKSPACE_HASH_PREFIX = "harness-local-agent-codex-v4:"
CODEX_SECRET_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9_-]{12,}|sat-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._-]{12,})",
    re.IGNORECASE,
)
CODEX_CONFIG_SCALAR_ALLOWLIST = {
    "disable_response_storage",
    "model",
    "model_context_window",
    "model_provider",
    "model_reasoning_effort",
    "model_verbosity",
}
CODEX_PROVIDER_CONFIG_ALLOWLIST = {
    "base_url",
    "experimental_bearer_token",
    "name",
    "requires_openai_auth",
    "wire_api",
}
CODEX_SENSITIVE_CONFIG_KEYS = {
    "access_token",
    "api_key",
    "experimental_bearer_token",
    "id_token",
    "refresh_token",
    "secret",
    "token",
}
CLAUDE_SUBPROCESS_TIMEOUT_SECONDS = 120
CLAUDE_OUTPUT_LIMIT_BYTES = 64_000
CLAUDE_WORKSPACE_HASH_PREFIX = "harness-local-agent-claude-code-v5:"
CLAUDE_PERMISSION_BRIDGE_VERSION = "harness_local_tool_request_v1"
CLAUDE_PERMISSION_BRIDGE_MODE_NONE = "none"
CLAUDE_PERMISSION_BRIDGE_MODE_SDK = "sdk"
CLAUDE_PERMISSION_DECISION_POLL_SECONDS = 2.0
CLAUDE_PERMISSION_DECISION_TIMEOUT_SECONDS = 1800.0
CLAUDE_SECRET_PATTERN = re.compile(
    r"(sk-ant-[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9_-]{12,}|sat-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._-]{12,})",
    re.IGNORECASE,
)
CLAUDE_READ_TOOLS = {"Read", "Glob", "Grep", "LS"}
CLAUDE_DENIED_TOOLS = {
    "WebFetch",
    "WebSearch",
    "Task",
    "AskUserQuestion",
    "NotebookEdit",
    "TodoWrite",
}
CLAUDE_SIDE_EFFECT_TOOLS = {"Bash", "Write", "Edit", "MultiEdit"}
CLAUDE_SAFE_SDK_TOOLS: list[str] = []
CLAUDE_SETTINGS_ENV_ALLOWLIST = {
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_MODEL",
}
CLAUDE_SENSITIVE_ENV_KEYS = {
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
}
CLAUDE_AGENT_SDK_REQUIRED_SYMBOLS = (
    "ClaudeSDKClient",
    "ClaudeAgentOptions",
    "PermissionResultAllow",
    "PermissionResultDeny",
    "HookMatcher",
    "AssistantMessage",
)


def _hao_version() -> str:
    try:
        return package_version(PACKAGE_DISTRIBUTION_NAME)
    except PackageNotFoundError:
        pass

    pyproject_path = Path(__file__).resolve().parents[3] / "pyproject.toml"
    try:
        pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        return str(pyproject["project"]["version"])
    except (KeyError, OSError, tomllib.TOMLDecodeError):
        return "unknown"


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("--max-auto-turns must be positive (>= 1)")
    return parsed


@dataclass(frozen=True)
class HeadlessRunResult:
    exit_code: int
    status: str
    stdout_json: dict[str, Any]
    stderr: str = ""


@dataclass(frozen=True)
class BridgeToolContext:
    bridge_task_id: str
    device_token: str
    harness_stream_token: str = ""


@dataclass(frozen=True)
class BridgeToolHandlingResult:
    status: str
    result: ToolExecutionResult | None = None
    backend_tool_call_id: str | None = None
    pending_tool: dict[str, Any] | None = None
    error_message: str = ""


@dataclass(frozen=True)
class CodexCliProbe:
    installed: bool
    executable: str = ""
    version: str = ""
    exec_help: str = ""
    resume_help: str = ""
    error_message: str = ""

    @property
    def supports_json(self) -> bool:
        return "--json" in self.exec_help

    @property
    def supports_output_last_message(self) -> bool:
        return "--output-last-message" in self.exec_help

    @property
    def supports_cd(self) -> bool:
        return "-C" in self.exec_help or "--cd" in self.exec_help

    @property
    def supports_read_only_sandbox(self) -> bool:
        return "--sandbox" in self.exec_help and "read-only" in self.exec_help

    @property
    def supports_skip_git_repo_check(self) -> bool:
        return "--skip-git-repo-check" in self.exec_help

    @property
    def supports_resume(self) -> bool:
        return "resume" in self.resume_help

    @property
    def resume_supports_read_only_sandbox(self) -> bool:
        return "--sandbox" in self.resume_help and "read-only" in self.resume_help

    @property
    def resume_supports_config(self) -> bool:
        return "-c" in self.resume_help or "--config" in self.resume_help


@dataclass(frozen=True)
class CodexRunResult:
    status: str
    content: str = ""
    error_message: str = ""
    session_id: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ClaudeCodeCliProbe:
    installed: bool
    executable: str = ""
    version: str = ""
    help_text: str = ""
    print_help: str = ""
    error_message: str = ""

    @property
    def supports_bare(self) -> bool:
        return "--bare" in self.help_text or "--bare" in self.print_help

    @property
    def supports_print(self) -> bool:
        return "-p" in self.help_text or "--print" in self.help_text or "-p" in self.print_help

    @property
    def supports_stream_json(self) -> bool:
        text = f"{self.help_text}\n{self.print_help}"
        return "--output-format" in text and "stream-json" in text

    @property
    def supports_include_partial_messages(self) -> bool:
        text = f"{self.help_text}\n{self.print_help}"
        return "--include-partial-messages" in text

    @property
    def supports_no_session_persistence(self) -> bool:
        text = f"{self.help_text}\n{self.print_help}"
        return "--no-session-persistence" in text

    @property
    def supports_permission_mode(self) -> bool:
        text = f"{self.help_text}\n{self.print_help}"
        return "--permission-mode" in text

    @property
    def supports_tools(self) -> bool:
        text = f"{self.help_text}\n{self.print_help}"
        return "--tools" in text


@dataclass(frozen=True)
class ClaudeCodeRunResult:
    status: str
    content: str = ""
    error_message: str = ""
    session_id: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ClaudeAgentSdkProbe:
    installed: bool
    version: str = ""
    error_message: str = ""
    symbols: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClaudePermissionBridgeResult:
    status: str
    content: str = ""
    error_message: str = ""
    session_id: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ClaudeToolMapping:
    allowed: bool
    tool_name: str
    input_json: dict[str, Any]
    target_paths: list[str]
    requires_network: bool = False
    requires_secret_read: bool = False
    reason: str = ""


def _store() -> SessionStore:
    config = load_config()
    return SessionStore(config.session_db_path, config.sessions_dir)


def _add_common_run_args(
    parser: argparse.ArgumentParser,
    *,
    suppress_defaults: bool = False,
) -> None:
    def arg_default(value: Any) -> Any:
        return argparse.SUPPRESS if suppress_defaults else value

    parser.add_argument("--agent-id", default=arg_default("default"), help="Harness Agent ID")
    parser.add_argument("--cwd", default=arg_default("."), help="Local workspace root")
    parser.add_argument(
        "--model-provider",
        default=arg_default("default"),
        help="Model provider recorded on the run",
    )
    parser.add_argument(
        "--model-name",
        default=arg_default("default"),
        help="Model name recorded on the run",
    )
    parser.add_argument(
        "--mode",
        choices=["confirm", "auto-edit", "full-auto"],
        default=arg_default("confirm"),
        help="Local permission mode",
    )
    parser.add_argument(
        "--target",
        choices=["host", "sandbox"],
        default=arg_default("host"),
        help="Execute tools on the host workspace or Harness sandbox",
    )
    parser.add_argument(
        "--max-auto-turns",
        type=_positive_int,
        default=arg_default(3),
        help="Maximum automatic local-tool continuation turns",
    )
    parser.add_argument(
        "--api-url",
        default=arg_default(None),
        help="Override Harness API URL",
    )
    parser.add_argument(
        "--token",
        default=arg_default(None),
        help="Override Harness API bearer token",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hao",
        description="Local Agent CLI for AI Harness workspaces.",
    )
    parser.add_argument(
        "-V",
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {_hao_version()}",
    )
    _add_common_run_args(parser)
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("version", help="Output current hao version")

    login = subparsers.add_parser("login", help="Save API URL and token")
    login.add_argument("--api-url", required=True)
    login.add_argument("--token", required=True)

    subparsers.add_parser("status", help="Show credential status")
    subparsers.add_parser("logout", help="Clear the persisted API token")

    auth = subparsers.add_parser("auth", help="Manage API credentials")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    auth_set = auth_sub.add_parser("set", help="Save API URL and token")
    auth_set.add_argument("--api-url", required=True)
    auth_set.add_argument("--token", required=True)
    auth_sub.add_parser("status", help="Show credential status")

    subparsers.add_parser("sessions", help="List local sessions")

    bridge = subparsers.add_parser("bridge", help="Run the Harness local Agent bridge")
    bridge_sub = bridge.add_subparsers(dest="bridge_command", required=True)
    bridge_pair = bridge_sub.add_parser("pair", help="Pair and optionally run a local Agent bridge")
    bridge_pair.add_argument("--api", "--api-url", dest="api_url", default=None)
    bridge_pair.add_argument("--pair-token", required=True)
    bridge_pair.add_argument("--pair-code", required=True)
    bridge_pair.add_argument(
        "--adapter",
        "--adapter-kind",
        dest="adapter_kind",
        choices=["fake", "hao", "codex", "claude_code"],
        default=None,
    )
    bridge_pair.add_argument("--display-name", default=None)
    bridge_pair.add_argument("--cwd", default=".")
    bridge_pair.add_argument("--daemon", action="store_true")
    bridge_pair.add_argument("--once", action="store_true")
    bridge_pair.add_argument("--interval", type=float, default=2.0)
    bridge_pair.add_argument(
        "--permission-bridge",
        choices=[CLAUDE_PERMISSION_BRIDGE_MODE_NONE, CLAUDE_PERMISSION_BRIDGE_MODE_SDK],
        default=CLAUDE_PERMISSION_BRIDGE_MODE_NONE,
        help="Claude Code permission bridge mode",
    )

    bridge_run = bridge_sub.add_parser("run", help="Run a previously paired local Agent bridge")
    bridge_run.add_argument("--api", "--api-url", dest="api_url", default=None)
    bridge_run.add_argument("--connection-id", default=None)
    bridge_run.add_argument("--device-token", default=None)
    bridge_run.add_argument(
        "--adapter",
        "--adapter-kind",
        dest="adapter_kind",
        choices=["fake", "hao", "codex", "claude_code"],
        default=None,
    )
    bridge_run.add_argument("--cwd", default=None)
    bridge_run.add_argument("--once", action="store_true")
    bridge_run.add_argument("--interval", type=float, default=2.0)
    bridge_run.add_argument(
        "--permission-bridge",
        choices=[CLAUDE_PERMISSION_BRIDGE_MODE_NONE, CLAUDE_PERMISSION_BRIDGE_MODE_SDK],
        default=None,
        help="Claude Code permission bridge mode",
    )

    resume = subparsers.add_parser("resume", help="Resume a local session")
    resume.add_argument("session_id", nargs="?")

    subparsers.add_parser("doctor", help="Check local CLI setup")

    for command in ("chat", "plan", "act"):
        run = subparsers.add_parser(command, help=f"Run a one-shot {command} prompt")
        _add_common_run_args(run, suppress_defaults=True)
        run.add_argument("prompt", nargs="+")
        run.add_argument("--resume", dest="resume_session_id", default=None)
    return parser


def _print_sessions() -> int:
    sessions = _store().list_sessions(limit=50)
    if not sessions:
        print("no local hao sessions")
        return 0
    for session in sessions:
        run = session.run_id or "-"
        print(
            f"{session.id}  {session.updated_at}  agent={session.agent_id} "
            f"mode={session.mode} workflow={session.cli_mode} "
            f"target={session.target} run={run} cwd={session.cwd}"
        )
    return 0


def _doctor() -> int:
    config = load_config()
    print(format_status(config), end="")
    ok = True
    for package in ("httpx", "rich", "textual"):
        try:
            __import__(package)
        except Exception as exc:
            ok = False
            print(f"{package}=missing ({exc})")
        else:
            print(f"{package}=ok")
    if config.token:
        try:
            from .api_client import HarnessApiClient

            health = HarnessApiClient(config.api_url, config.token).health()
            print(f"api_health={health}")
        except Exception as exc:
            ok = False
            print(f"api_health=failed ({exc})")
    else:
        print("api_health=skipped (missing token)")
    return 0 if ok else 1


def _print_version() -> int:
    print(f"hao {_hao_version()}")
    return 0


def _save_login(args: argparse.Namespace) -> int:
    config = load_config()
    save_auth(config, api_url=args.api_url, token=args.token)
    print(f"saved auth config to {config.config_path}")
    return 0


def _print_auth_status() -> int:
    print(format_status(load_config()), end="")
    return 0


def _logout() -> int:
    config = load_config()
    cleared = clear_persisted_token(config)
    if cleared:
        print(f"cleared persisted token at {config.config_path}")
    else:
        print(f"no persisted auth config at {config.config_path}")
    return 0


def _run_tui(args: argparse.Namespace, *, resume_session_id: str | None = None) -> int:
    config = load_config()
    api_url = args.api_url or config.api_url
    token = args.token or config.token
    from .tui import HaoApp

    app = HaoApp(
        api_url=api_url,
        token=token,
        agent_id=args.agent_id,
        cwd=Path(args.cwd).expanduser().resolve(),
        model_provider=args.model_provider,
        model_name=args.model_name,
        permission_mode=args.mode,
        target=args.target,
        resume_session_id=resume_session_id,
        max_auto_turns=args.max_auto_turns,
    )
    return _run_terminal_tui(app)


def _run_terminal_tui(app: Any) -> int:
    from rich.console import Console

    from .tui import HaoApp

    console = Console()

    def print_chat(message: str) -> None:
        console.print(message)

    def begin_assistant_stream() -> None:
        console.print("[bold green]hao[/bold green] ", end="")

    def append_assistant_stream(content: str) -> None:
        if content:
            console.print(content, end="")

    def print_tool(label: str, message: str) -> None:
        print_chat(f"[dim]{label}[/dim] {message}")

    def print_side_panel() -> None:
        app.workbench_open = True
        header, entries = app._side_panel_entries()
        console.print(f"[bold #d97757]{header}[/bold #d97757] [dim](/clear hides)[/dim]")
        if not entries:
            console.print("[dim]No entries yet.[/dim]")
            return
        for entry in entries:
            console.print(entry)

    def refresh_side_panel() -> None:
        if app.workbench_open:
            print_side_panel()

    def clear_screen() -> None:
        app.workbench_open = False
        console.clear()
        console.print(app._welcome_card())

    app._chat = print_chat
    app._stream_assistant_begin = begin_assistant_stream
    app._stream_assistant_append = append_assistant_stream
    last_status_block: str | None = None

    def print_status() -> None:
        nonlocal last_status_block
        footer_block = getattr(app, "_footer_status_block", None)
        if callable(footer_block):
            block = footer_block()
        else:
            status_text = getattr(app, "_status_text", None)
            workbench_status = getattr(app, "_workbench_status", None)
            if not callable(status_text) or not callable(workbench_status):
                return
            block = status_text(workbench_status())
        if block == last_status_block:
            return
        last_status_block = block
        console.print(block)

    app._status = print_status
    app._render_side_panel = print_side_panel
    app._refresh_workbench = refresh_side_panel
    app._close_workbench = lambda: setattr(app, "workbench_open", False)
    app.action_clear = clear_screen
    app._tool_log = lambda message: (
        app.tool_entries.append(message),
        print_tool("tool", message),
    )
    app._diff_log = lambda message: (
        app.diff_entries.append(message),
        print_tool("diff", message),
    )
    app._approval_log = lambda message: (
        app.approval_entries.append(message),
        print_tool("approval", message),
    )
    app.run_turn_worker = (
        lambda goal, append_user, depth, interaction_mode: app._run_turn_sync(
            goal,
            depth,
            interaction_mode,
        )
    )
    app.approve_tool_worker = (
        lambda pending_id: HaoApp.approve_tool_worker.__wrapped__(app, pending_id)
    )
    app.approve_change_worker = (
        lambda change_id: HaoApp.approve_change_worker.__wrapped__(app, change_id)
    )
    app.retry_command_worker = (
        lambda command_id: HaoApp.retry_command_worker.__wrapped__(app, command_id)
    )

    if app.resume_session_id:
        session = app.store.get_session(app.resume_session_id)
        if session is None:
            console.print(f"[red]session not found:[/red] {app.resume_session_id}")
            session = app._new_session()
        else:
            app.agent_id = session.agent_id
            app.cwd = Path(session.cwd).expanduser().resolve()
            app.permission_mode = session.mode
            app.interaction_mode = session.cli_mode
            app.target = session.target
    else:
        session = app._new_session()
    app._load_session_state(session)
    console.print(app._welcome_card())
    for message in app.messages[-12:]:
        console.print(app._format_transcript_line(message["role"], message["content"]))
    app._status()

    exit_armed = False
    while True:
        try:
            value = _read_terminal_input(console, "[bold #d97757]›[/bold #d97757] ")
        except EOFError:
            break
        except KeyboardInterrupt:
            if exit_armed:
                break
            exit_armed = True
            console.print("[dim]Press Ctrl-C again to exit[/dim]")
            continue
        exit_armed = False
        value = value.strip()
        if not value:
            continue
        command = value.split(maxsplit=1)[0].lower()
        if command in {"/quit", "/exit"}:
            break
        if value.startswith("/"):
            app._handle_command(value)
            continue
        workflow_metadata = app._workflow_metadata(app.interaction_mode)
        app._record_message_ui("user", value, metadata=workflow_metadata)
        app._run_turn_sync(value, 0, app.interaction_mode)
    return 0


def _decode_terminal_input(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace").rstrip("\r\n")


def _read_terminal_input(console: Any, prompt: str) -> str:
    console.print(prompt, end="")
    stdin_is_tty = bool(getattr(sys.stdin, "isatty", lambda: False)())
    stream = getattr(sys.stdin, "buffer", None)
    if stream is None:
        line = sys.stdin.readline()
        if line == "":
            raise EOFError
        if not stdin_is_tty:
            console.print("")
        return line.rstrip("\r\n")
    raw = stream.readline()
    if raw == b"":
        raise EOFError
    if not stdin_is_tty:
        console.print("")
    return _decode_terminal_input(raw)


def _normalize_headless_args(args: argparse.Namespace) -> None:
    if isinstance(args.prompt, list):
        args.prompt = " ".join(args.prompt).strip()
    if not getattr(args, "resume_session_id", None):
        args.resume_session_id = None


def _bridge_state_path(config: Any) -> Path:
    return config.home / "bridge.json"


def _bridge_device_token_path(config: Any, token_ref: str | None = None) -> Path:
    ref = Path(str(token_ref or BRIDGE_DEVICE_TOKEN_REF)).name
    return config.home / ref


def _bridge_workspace_root_path(config: Any, root_ref: str | None = None) -> Path:
    ref = Path(str(root_ref or BRIDGE_WORKSPACE_ROOT_REF)).name
    return config.home / ref


def _bridge_version() -> str:
    return f"hao-{_hao_version()}"


def _permission_bridge_for_adapter(adapter_kind: str, value: str | None) -> str:
    mode = str(value or CLAUDE_PERMISSION_BRIDGE_MODE_NONE).strip()
    if mode not in {CLAUDE_PERMISSION_BRIDGE_MODE_NONE, CLAUDE_PERMISSION_BRIDGE_MODE_SDK}:
        return CLAUDE_PERMISSION_BRIDGE_MODE_NONE
    if adapter_kind != "claude_code":
        return CLAUDE_PERMISSION_BRIDGE_MODE_NONE
    return mode


def _bridge_capabilities(
    adapter_kind: str,
    *,
    permission_bridge: str = CLAUDE_PERMISSION_BRIDGE_MODE_NONE,
) -> dict[str, Any]:
    if adapter_kind == "codex":
        probe = _probe_codex_cli()
        model_provider, model_name = _codex_detected_model()
        return _with_detected_model_capabilities(
            _codex_bridge_capabilities(probe),
            model_provider=model_provider,
            model_name=model_name,
        )
    if adapter_kind == "claude_code":
        probe = _probe_claude_code_cli()
        sdk_probe = (
            _probe_claude_agent_sdk()
            if permission_bridge == CLAUDE_PERMISSION_BRIDGE_MODE_SDK
            else None
        )
        model_provider, model_name = _claude_code_detected_model()
        return _with_detected_model_capabilities(
            _claude_code_bridge_capabilities(
                probe,
                permission_bridge=permission_bridge,
                sdk_probe=sdk_probe,
            ),
            model_provider=model_provider,
            model_name=model_name,
        )
    return {
        "adapter_kind": adapter_kind,
        "supports_resume": adapter_kind == "hao",
        "supports_streaming": True,
        "supports_cancel": adapter_kind == "hao",
        "protocol_version": "local-agent-v1",
    }


def _with_detected_model_capabilities(
    capabilities: dict[str, Any],
    *,
    model_provider: str | None,
    model_name: str | None,
) -> dict[str, Any]:
    provider = str(model_provider or "").strip()
    model = str(model_name or "").strip()
    if not provider or not model:
        return capabilities
    return {
        **capabilities,
        "model_provider": provider,
        "model_name": model,
        "default_model_provider": provider,
        "default_model": model,
    }


def _codex_detected_model() -> tuple[str | None, str | None]:
    config = _minimal_codex_config(Path.home() / ".codex" / "config.toml")
    model_provider = config.get("model_provider")
    model_name = config.get("model")
    return (
        model_provider if isinstance(model_provider, str) else None,
        model_name if isinstance(model_name, str) else None,
    )


def _claude_code_detected_model(
    source: Mapping[str, str] | None = None,
) -> tuple[str | None, str | None]:
    env = _claude_code_allowed_source_env(source or os.environ)
    model = str(env.get("ANTHROPIC_MODEL") or "").strip()
    return ("anthropic", model) if model else (None, None)


def _bridge_risk_capabilities(
    adapter_kind: str,
    *,
    permission_bridge: str = CLAUDE_PERMISSION_BRIDGE_MODE_NONE,
) -> list[str]:
    del permission_bridge
    if adapter_kind in {"hao", "codex", "claude_code"}:
        return list(BRIDGE_FULL_RISK_CAPABILITIES)
    return []


def _codex_safe_env(*, executable: str, temp_dir: Path | None = None) -> dict[str, str]:
    source = os.environ
    path_parts = [
        str(Path(executable).resolve().parent),
        "/usr/local/bin",
        "/opt/homebrew/bin",
        "/usr/bin",
        "/bin",
    ]
    env: dict[str, str] = {
        "PATH": os.pathsep.join(dict.fromkeys(path_parts)),
    }
    if temp_dir is not None:
        env["TMPDIR"] = str(temp_dir)
        isolated_home = temp_dir / "home"
        isolated_codex_home = temp_dir / "codex-home"
        isolated_home.mkdir(mode=0o700, parents=True, exist_ok=True)
        isolated_codex_home.mkdir(mode=0o700, parents=True, exist_ok=True)
        env["HOME"] = str(isolated_home)
        env["CODEX_HOME"] = str(isolated_codex_home)
        _copy_codex_runtime_config(source=source, destination=isolated_codex_home)
    for key in ("LANG", "LC_ALL", "LC_CTYPE", "TERM"):
        value = source.get(key)
        if value:
            env[key] = value
    return env


def _codex_source_home(source: Mapping[str, str]) -> Path:
    codex_home = source.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser()
    home = source.get("HOME")
    return (Path(home).expanduser() if home else Path.home()) / ".codex"


def _copy_codex_runtime_config(*, source: Mapping[str, str], destination: Path) -> None:
    source_home = _codex_source_home(source)
    auth_path = source_home / "auth.json"
    if auth_path.is_file():
        try:
            shutil.copyfile(auth_path, destination / "auth.json")
            os.chmod(destination / "auth.json", 0o600)
        except OSError:
            pass
    minimal_config = _minimal_codex_config(source_home / "config.toml")
    if minimal_config:
        try:
            config_path = destination / "config.toml"
            config_path.write_text(_dump_minimal_toml(minimal_config), encoding="utf-8")
            os.chmod(config_path, 0o600)
        except OSError:
            pass


def _minimal_codex_config(config_path: Path) -> dict[str, Any]:
    try:
        raw_config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    if not isinstance(raw_config, dict):
        return {}
    config: dict[str, Any] = {}
    for key in sorted(CODEX_CONFIG_SCALAR_ALLOWLIST):
        value = raw_config.get(key)
        if isinstance(value, str | bool | int | float):
            config[key] = value
    provider_name = config.get("model_provider")
    raw_providers = raw_config.get("model_providers")
    if isinstance(provider_name, str) and isinstance(raw_providers, dict):
        raw_provider = raw_providers.get(provider_name)
        if isinstance(raw_provider, dict):
            provider_config: dict[str, Any] = {}
            for key in sorted(CODEX_PROVIDER_CONFIG_ALLOWLIST):
                value = raw_provider.get(key)
                if isinstance(value, str | bool | int | float):
                    provider_config[key] = value
            if provider_config:
                config["model_providers"] = {provider_name: provider_config}
    return config


def _dump_minimal_toml(config: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in config.items():
        if key == "model_providers" or isinstance(value, dict):
            continue
        lines.append(f"{key} = {_toml_scalar(value)}\n")
    providers = config.get("model_providers")
    if isinstance(providers, dict):
        for provider_name, provider_config in providers.items():
            if not isinstance(provider_name, str) or not isinstance(provider_config, dict):
                continue
            lines.append(f"\n[model_providers.{_toml_key(provider_name)}]\n")
            for key, value in provider_config.items():
                if isinstance(value, str | bool | int | float):
                    lines.append(f"{key} = {_toml_scalar(value)}\n")
    return "".join(lines)


def _toml_key(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _toml_scalar(value: str | bool | int | float) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _codex_sensitive_source_values(source: Mapping[str, str]) -> list[str]:
    source_home = _codex_source_home(source)
    values: set[str] = set()
    try:
        raw_auth = json.loads((source_home / "auth.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw_auth = {}
    _collect_sensitive_config_values(raw_auth, values)
    _collect_sensitive_config_values(_minimal_codex_config(source_home / "config.toml"), values)
    return sorted(values, key=len, reverse=True)


def _collect_sensitive_config_values(value: Any, values: set[str], key: str = "") -> None:
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            _collect_sensitive_config_values(child_value, values, str(child_key))
        return
    if isinstance(value, list):
        for child_value in value:
            _collect_sensitive_config_values(child_value, values, key)
        return
    if not isinstance(value, str) or len(value) < 8:
        return
    key_lower = key.lower()
    if (
        key_lower in CODEX_SENSITIVE_CONFIG_KEYS
        or "token" in key_lower
        or "secret" in key_lower
        or "password" in key_lower
        or key_lower.endswith("key")
    ):
        values.add(value)


def _run_probe_command(command: list[str], *, timeout: float = 5.0) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        env=_codex_safe_env(executable=command[0]),
    )


def _probe_codex_cli() -> CodexCliProbe:
    executable = shutil.which("codex")
    if not executable:
        return CodexCliProbe(installed=False, error_message="codex executable not found")
    try:
        version_result = _run_probe_command([executable, "--version"])
        exec_help_result = _run_probe_command([executable, "exec", "--help"])
        resume_help_result = _run_probe_command([executable, "exec", "resume", "--help"])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CodexCliProbe(
            installed=False,
            executable=executable,
            error_message=f"codex probe failed: {exc}",
        )
    exec_help = f"{exec_help_result.stdout}\n{exec_help_result.stderr}"
    resume_help = f"{resume_help_result.stdout}\n{resume_help_result.stderr}"
    probe = CodexCliProbe(
        installed=True,
        executable=executable,
        version=(version_result.stdout or version_result.stderr).strip(),
        exec_help=exec_help,
        resume_help=resume_help,
    )
    if not (
        probe.supports_json
        and probe.supports_output_last_message
        and probe.supports_cd
        and probe.supports_read_only_sandbox
    ):
        return CodexCliProbe(
            installed=False,
            executable=executable,
            version=probe.version,
            exec_help=exec_help,
            resume_help=resume_help,
            error_message="codex exec lacks required --json/output/-C/read-only sandbox support",
        )
    return probe


def _codex_bridge_capabilities(probe: CodexCliProbe) -> dict[str, Any]:
    return {
        "adapter_kind": "codex",
        "installed": probe.installed,
        "version": probe.version,
        "supports_streaming": probe.installed and probe.supports_json,
        "supports_resume": False,
        "supports_cancel": True,
        "host_tools_authorized": True,
        "permission_defer_supported": True,
        "tool_execution_authority": "harness_approved_local_bridge",
        "resume_mode": "context_replay_new_session",
        "protocol_version": "local-agent-v1",
        "enabled_in_v4": True,
        "deterministic_session_id": False,
        "resume_sandbox_read_only": False,
        "resume_config_read_only_smoke_passed": False,
        "probe_error": probe.error_message,
    }


def _probe_claude_agent_sdk() -> ClaudeAgentSdkProbe:
    try:
        module = importlib.import_module("claude_agent_sdk")
    except Exception as exc:
        return ClaudeAgentSdkProbe(
            installed=False,
            error_message=_redact_claude_text(f"claude_agent_sdk import failed: {exc}"),
        )
    try:
        types_module = importlib.import_module("claude_agent_sdk.types")
    except Exception:
        types_module = None
    missing = [
        name
        for name in CLAUDE_AGENT_SDK_REQUIRED_SYMBOLS
        if not _claude_agent_sdk_has_symbol(module, types_module, name)
    ]
    if missing:
        return ClaudeAgentSdkProbe(
            installed=False,
            error_message=f"claude_agent_sdk missing required symbols: {', '.join(missing)}",
            symbols=tuple(
                name
                for name in CLAUDE_AGENT_SDK_REQUIRED_SYMBOLS
                if _claude_agent_sdk_has_symbol(module, types_module, name)
            ),
        )
    options_symbol = _claude_agent_sdk_symbol(module, types_module, "ClaudeAgentOptions")
    missing_options = [
        keyword
        for keyword in ("can_use_tool", "hooks")
        if not _callable_accepts_keyword(options_symbol, keyword)
    ]
    if missing_options:
        return ClaudeAgentSdkProbe(
            installed=False,
            error_message=(
                "claude_agent_sdk ClaudeAgentOptions missing required parameters: "
                + ", ".join(missing_options)
            ),
            symbols=CLAUDE_AGENT_SDK_REQUIRED_SYMBOLS,
        )
    version = str(getattr(module, "__version__", "") or "")
    if not version:
        try:
            version = package_version("claude-agent-sdk")
        except PackageNotFoundError:
            version = "unknown"
    return ClaudeAgentSdkProbe(
        installed=True,
        version=version,
        symbols=CLAUDE_AGENT_SDK_REQUIRED_SYMBOLS,
    )


def _claude_agent_sdk_has_symbol(module: Any, types_module: Any, name: str) -> bool:
    return hasattr(module, name) or (types_module is not None and hasattr(types_module, name))


def _claude_agent_sdk_symbol(module: Any, types_module: Any, name: str) -> Any:
    if hasattr(module, name):
        return getattr(module, name)
    if types_module is not None and hasattr(types_module, name):
        return getattr(types_module, name)
    raise AttributeError(name)


def _callable_accepts_keyword(target: Any, keyword: str) -> bool:
    try:
        signature = inspect.signature(target)
    except (TypeError, ValueError):
        return True
    if keyword in signature.parameters:
        return True
    return any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


def _claude_code_bridge_capabilities(
    probe: ClaudeCodeCliProbe,
    *,
    permission_bridge: str = CLAUDE_PERMISSION_BRIDGE_MODE_NONE,
    sdk_probe: ClaudeAgentSdkProbe | None = None,
) -> dict[str, Any]:
    base = {
        "adapter_kind": "claude_code",
        "installed": probe.installed,
        "version": probe.version,
        "supports_streaming": probe.installed and probe.supports_stream_json,
        "supports_resume": False,
        "supports_cancel": True,
        "host_tools_authorized": True,
        "permission_defer_supported": True,
        "tool_execution_authority": "harness_approved_local_bridge",
        "resume_mode": "context_replay_new_session",
        "protocol_version": "local-agent-v1",
        "enabled_in_v5": True,
        "execution_mode": "headless_harness_tool_bridge",
        "probe_error": probe.error_message,
    }
    if permission_bridge != CLAUDE_PERMISSION_BRIDGE_MODE_SDK:
        return base
    sdk_probe = sdk_probe or _probe_claude_agent_sdk()
    if not (probe.installed and sdk_probe.installed):
        return {
            **base,
            "permission_bridge_mode": "sdk",
            "sdk_available": sdk_probe.installed,
            "sdk_version": sdk_probe.version,
            "sdk_probe_error": sdk_probe.error_message,
        }
    return {
        **base,
        "supports_cancel": True,
        "host_tools_authorized": True,
        "enabled_in_v6": True,
        "claude_permission_bridge_v1": True,
        "permission_bridge": CLAUDE_PERMISSION_BRIDGE_VERSION,
        "permission_bridge_mode": "sdk",
        "execution_mode": "agent_sdk_intent_capture_harness_executor",
        "permission_bridge_execution": "harness_owned_executor",
        "sdk_native_tool_execution_enabled": False,
        "sdk_available": True,
        "sdk_version": sdk_probe.version,
        "sdk_required_symbols": list(sdk_probe.symbols),
        "sdk_allowed_tools_preapproved": False,
        "allowed_tools": [],
        "permission_bridge_callback_configured": True,
        "permission_bridge_pre_tool_hook_configured": True,
        "permission_bridge_dummy_hook_only": True,
        "side_effect_tools_preapproval_disabled": True,
        "forbidden_permission_modes_disabled": True,
        "unmanaged_settings_disabled": True,
        "mcp_enabled": False,
        "plugins_enabled": False,
        "hooks_enabled": False,
        "subagents_enabled": False,
        "browser_enabled": False,
        "computer_use_enabled": False,
        "remote_control_enabled": False,
        "native_resume_enabled": False,
        "background_sessions_enabled": False,
        "web_sessions_enabled": False,
        "cloud_sessions_enabled": False,
    }


def _redact_local_path_text(value: str) -> str:
    def redact(match: re.Match[str]) -> str:
        parts = match.group(0).replace("\\", "/").split("/")
        safe_tail = [part for part in parts[3:] if part]
        return f".../{'/'.join(safe_tail[-2:])}" if safe_tail else "..."

    return re.sub(r"(?<!\.)/(?:Users|home)/[^\s'\";:&|`]+", redact, value)


def _redact_codex_text(value: str, *, limit: int = CODEX_OUTPUT_LIMIT_BYTES) -> str:
    if not value:
        return ""
    bounded = value.encode("utf-8", errors="replace")[:limit].decode(
        "utf-8",
        errors="replace",
    )
    redacted = bounded
    for secret_value in _codex_sensitive_source_values(os.environ):
        redacted = re.sub(re.escape(secret_value), "[REDACTED]", redacted)
    redacted = CODEX_SECRET_PATTERN.sub("[REDACTED]", redacted)
    redacted = re.sub(
        r"(?i)(api[_-]?key|token|secret|password)=\S+",
        r"\1=[REDACTED]",
        redacted,
    )
    return _redact_local_path_text(redacted)


def _redact_claude_text(value: str, *, limit: int = CLAUDE_OUTPUT_LIMIT_BYTES) -> str:
    if not value:
        return ""
    bounded = value.encode("utf-8", errors="replace")[:limit].decode(
        "utf-8",
        errors="replace",
    )
    redacted = bounded
    for secret_value in _claude_code_sensitive_source_env_values(os.environ):
        redacted = re.sub(re.escape(secret_value), "[REDACTED]", redacted)
    redacted = CLAUDE_SECRET_PATTERN.sub("[REDACTED]", redacted)
    redacted = re.sub(
        r"(?i)(api[_-]?key|token|secret|password)=\S+",
        r"\1=[REDACTED]",
        redacted,
    )
    return _redact_local_path_text(redacted)


def _safe_codex_metadata(value: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for index, (key, item) in enumerate(value.items()):
        if index >= 20:
            safe["truncated"] = True
            break
        key_text = str(key)
        if any(marker in key_text.lower() for marker in ("token", "secret", "key", "password")):
            safe[key_text] = "[REDACTED]"
        elif isinstance(item, str):
            safe[key_text] = _redact_codex_text(item, limit=4000)
        elif isinstance(item, bool | int | float):
            safe[key_text] = item
        elif item is None:
            safe[key_text] = None
        else:
            safe[key_text] = _redact_codex_text(json.dumps(item, ensure_ascii=False), limit=4000)
    return safe


def _safe_claude_metadata(value: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for index, (key, item) in enumerate(value.items()):
        if index >= 20:
            safe["truncated"] = True
            break
        key_text = str(key)
        if any(marker in key_text.lower() for marker in ("token", "secret", "key", "password")):
            safe[key_text] = "[REDACTED]"
        elif isinstance(item, str):
            safe[key_text] = _redact_claude_text(item, limit=4000)
        elif isinstance(item, bool | int | float):
            safe[key_text] = item
        elif item is None:
            safe[key_text] = None
        else:
            safe[key_text] = _redact_claude_text(json.dumps(item, ensure_ascii=False), limit=4000)
    return safe


def _bridge_workspace_context_prompt(payload: dict[str, Any], *, redactor) -> str:
    lines: list[str] = []
    model_provider = str(payload.get("model_provider") or "default").strip() or "default"
    model_name = str(payload.get("model_name") or "default").strip() or "default"
    lines.append(f"Harness selected model: provider={model_provider}, model={model_name}.")

    tool_names = _bridge_payload_tool_names(payload.get("tool_mentions"))
    if tool_names:
        lines.append("Harness requested tools: " + ", ".join(tool_names) + ".")

    attachment_names = _bridge_payload_attachment_names(payload)
    if attachment_names:
        lines.append("Harness attachments: " + ", ".join(attachment_names) + ".")

    compressed = payload.get("compressed_context")
    if isinstance(compressed, dict):
        summary = str(compressed.get("summary") or "").strip()
        if summary:
            lines.append("Compressed workspace context: " + redactor(summary, limit=3000))

    attachment_snippets = _bridge_payload_attachment_snippets(
        payload.get("attachments"),
        redactor=redactor,
    )
    lines.extend(attachment_snippets)

    if len(lines) == 1 and model_provider == "default" and model_name == "default":
        return ""
    return (
        "Harness Workspace request metadata:\n"
        + "\n".join(f"- {line}" for line in lines)
        + "\n\n"
    )


def _bridge_payload_tool_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value[:12]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        source = str(item.get("source") or "").strip()
        if not name:
            continue
        names.append(f"{source}:{name}" if source else name)
    return names


def _bridge_payload_attachment_names(payload: dict[str, Any]) -> list[str]:
    names: list[str] = []
    raw_names = payload.get("attachment_names")
    if isinstance(raw_names, list):
        names.extend(str(item).strip() for item in raw_names[:12] if str(item).strip())
    raw_attachments = payload.get("attachments")
    if isinstance(raw_attachments, list):
        for attachment in raw_attachments[:12]:
            if not isinstance(attachment, dict):
                continue
            name = str(attachment.get("name") or attachment.get("filename") or "").strip()
            if name and name not in names:
                names.append(name)
    return names


def _bridge_payload_attachment_snippets(value: Any, *, redactor) -> list[str]:
    if not isinstance(value, list):
        return []
    snippets: list[str] = []
    for attachment in value[:3]:
        if not isinstance(attachment, dict):
            continue
        name = str(attachment.get("name") or attachment.get("filename") or "attachment").strip()
        text = str(
            attachment.get("content_text")
            or attachment.get("text")
            or attachment.get("content")
            or ""
        ).strip()
        if not text:
            continue
        snippets.append(f"Attachment {name}: {redactor(text, limit=1200)}")
    return snippets


def _bridge_conversation_context_block(payload: dict[str, Any], *, redactor) -> str:
    context_lines: list[str] = []
    context = payload.get("conversation_context")
    if isinstance(context, list):
        for item in context:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            if role not in {"user", "assistant"}:
                continue
            content = redactor(
                str(item.get("content") or "").strip(),
                limit=CODEX_PROMPT_CONTEXT_MESSAGE_LIMIT,
            )
            if content:
                context_lines.append(f"{role}: {content}")
    return (
        "Harness conversation context from prior turns:\n"
        + "\n".join(context_lines)
        + "\n\n"
        if context_lines
        else ""
    )


def _hao_prompt_for_task(payload: dict[str, Any]) -> str:
    message = _redact_codex_text(str(payload.get("message") or "").strip(), limit=4000)
    resume_mode = str(payload.get("resume_mode") or "native_resume")
    harness_context = _bridge_workspace_context_prompt(payload, redactor=_redact_codex_text)
    context_block = _bridge_conversation_context_block(payload, redactor=_redact_codex_text)
    return (
        "You are running under the AI Harness local-agent bridge as the hao adapter.\n"
        "Harness owns the conversation, run, events, approvals, model selection, tools, "
        "attachments, context routing, and audit records.\n"
        f"Resume mode: {resume_mode}.\n\n"
        f"{harness_context}"
        f"{context_block}"
        "User message:\n"
        f"{message}\n"
    )


def _codex_prompt_for_task(payload: dict[str, Any]) -> str:
    message = _redact_codex_text(str(payload.get("message") or "").strip(), limit=4000)
    resume_mode = str(payload.get("resume_mode") or "context_replay_new_session")
    harness_context = _bridge_workspace_context_prompt(payload, redactor=_redact_codex_text)
    context_block = _bridge_conversation_context_block(payload, redactor=_redact_codex_text)
    return (
        "You are running under the AI Harness local-agent bridge as the Codex CLI adapter.\n"
        "Harness owns the conversation, run, events, approvals, and audit records.\n"
        "You have the same Harness-managed local capability surface as hao: read, write, "
        "shell, test, git, and network intent may be requested. Host side effects must go "
        "through Harness approval and audit; never bypass the Harness bridge.\n"
        f"Resume mode: {resume_mode}.\n\n"
        f"{harness_context}"
        f"{context_block}"
        "User message:\n"
        f"{message}\n"
    )


def _claude_code_prompt_for_task(payload: dict[str, Any]) -> str:
    message = _redact_claude_text(str(payload.get("message") or "").strip(), limit=4000)
    resume_mode = str(payload.get("resume_mode") or "context_replay_new_session")
    harness_context = _bridge_workspace_context_prompt(payload, redactor=_redact_claude_text)
    context_block = _bridge_conversation_context_block(payload, redactor=_redact_claude_text)
    return (
        "You are running under the AI Harness local-agent bridge as the Claude Code adapter.\n"
        "Harness owns the conversation, run, events, approvals, and audit records.\n"
        "You have the same Harness-managed local capability surface as hao: read, write, "
        "shell, test, git, and network intent may be requested. Host side effects must go "
        "through Harness approval and audit; never bypass the Harness bridge.\n"
        f"Resume mode: {resume_mode}.\n\n"
        f"{harness_context}"
        f"{context_block}"
        "User message:\n"
        f"{message}\n"
    )


def _claude_code_permission_bridge_prompt_for_task(payload: dict[str, Any]) -> str:
    base = _claude_code_prompt_for_task(payload)
    return (
        base
        + "\nV6 permission bridge is active. Harness owns all local tool approvals. "
        "When you need Bash, Write, Edit, MultiEdit, git, network, env, or secret-like "
        "host access, request the tool normally and wait for Harness approval. "
        "The approved input may be modified by policy; do not assume the original "
        "request was executed.\n"
    )


async def _claude_agent_sdk_prompt_stream(prompt: str):
    yield {
        "type": "user",
        "message": {
            "role": "user",
            "content": prompt,
        },
    }


def _codex_subprocess_env(*, executable: str, temp_dir: Path) -> dict[str, str]:
    return _codex_safe_env(executable=executable, temp_dir=temp_dir)


def _claude_code_settings_env(source_home: str | None) -> dict[str, str]:
    home = Path(source_home).expanduser() if source_home else Path.home()
    settings_path = home / ".claude" / "settings.json"
    try:
        raw_settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw_settings, dict):
        return {}
    raw_env = raw_settings.get("env")
    if not isinstance(raw_env, dict):
        return {}
    env: dict[str, str] = {}
    for key in sorted(CLAUDE_SETTINGS_ENV_ALLOWLIST):
        value = raw_env.get(key)
        if isinstance(value, str) and value:
            env[key] = value
    return env


def _claude_code_allowed_source_env(source: Mapping[str, str]) -> dict[str, str]:
    env = _claude_code_settings_env(source.get("HOME"))
    for key in sorted(CLAUDE_SETTINGS_ENV_ALLOWLIST):
        value = source.get(key)
        if value:
            env[key] = str(value)
    if source.get("HAO_CLAUDE_CODE_ALLOW_ANTHROPIC_API_KEY") == "1":
        api_key = source.get("ANTHROPIC_API_KEY")
        if api_key:
            env["ANTHROPIC_API_KEY"] = str(api_key)
    return env


def _claude_code_sensitive_source_env_values(source: Mapping[str, str]) -> list[str]:
    env = _claude_code_allowed_source_env(source)
    return [
        value
        for key, value in env.items()
        if key in CLAUDE_SENSITIVE_ENV_KEYS and isinstance(value, str) and value
    ]


def _claude_code_safe_env(*, executable: str, temp_dir: Path | None = None) -> dict[str, str]:
    source = os.environ
    path_parts = [
        str(Path(executable).resolve().parent),
        "/usr/local/bin",
        "/opt/homebrew/bin",
        "/usr/bin",
        "/bin",
    ]
    env: dict[str, str] = {
        "PATH": os.pathsep.join(dict.fromkeys(path_parts)),
    }
    if temp_dir is not None:
        env["TMPDIR"] = str(temp_dir)
        isolated_home = temp_dir / "home"
        isolated_config = temp_dir / "claude-config"
        isolated_home.mkdir(mode=0o700, parents=True, exist_ok=True)
        isolated_config.mkdir(mode=0o700, parents=True, exist_ok=True)
        env["HOME"] = str(isolated_home)
        env["CLAUDE_CONFIG_DIR"] = str(isolated_config)
        env["CLAUDE_CODE_SKIP_PROMPT_HISTORY"] = "1"
        env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
        env["CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS"] = "1"
        env.update(_claude_code_allowed_source_env(source))
    for key in ("LANG", "LC_ALL", "LC_CTYPE", "TERM"):
        value = source.get(key)
        if value:
            env[key] = value
    return env


def _run_claude_probe_command(
    command: list[str],
    *,
    timeout: float = 5.0,
) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        env=_claude_code_safe_env(executable=command[0]),
    )


def _probe_claude_code_cli() -> ClaudeCodeCliProbe:
    executable = shutil.which("claude")
    if not executable:
        return ClaudeCodeCliProbe(installed=False, error_message="claude executable not found")
    try:
        version_result = _run_claude_probe_command([executable, "--version"])
        help_result = _run_claude_probe_command([executable, "--help"])
        print_help_result = _run_claude_probe_command([executable, "-p", "--help"])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ClaudeCodeCliProbe(
            installed=False,
            executable=executable,
            error_message=f"claude probe failed: {exc}",
        )
    help_text = f"{help_result.stdout}\n{help_result.stderr}"
    print_help = f"{print_help_result.stdout}\n{print_help_result.stderr}"
    probe = ClaudeCodeCliProbe(
        installed=True,
        executable=executable,
        version=(version_result.stdout or version_result.stderr).strip(),
        help_text=help_text,
        print_help=print_help,
    )
    if not (
        probe.supports_bare
        and probe.supports_print
        and probe.supports_stream_json
        and probe.supports_include_partial_messages
        and probe.supports_no_session_persistence
        and probe.supports_permission_mode
        and probe.supports_tools
    ):
        return ClaudeCodeCliProbe(
            installed=False,
            executable=executable,
            version=probe.version,
            help_text=help_text,
            print_help=print_help,
            error_message=(
                "claude lacks required "
                "--bare/-p/stream-json/partial/no-session/permission/tools support"
            ),
        )
    return probe


def _claude_code_subprocess_env(*, executable: str, temp_dir: Path) -> dict[str, str]:
    return _claude_code_safe_env(executable=executable, temp_dir=temp_dir)


def _codex_command(
    *,
    probe: CodexCliProbe,
    workspace_root: Path,
    output_last_message: Path,
) -> list[str]:
    command = [
        probe.executable,
        "exec",
        "--json",
        "--output-last-message",
        str(output_last_message),
        "-C",
        str(workspace_root),
        "--sandbox",
        "read-only",
    ]
    if probe.supports_skip_git_repo_check:
        command.append("--skip-git-repo-check")
    command.append("-")
    forbidden = {
        "--dangerously-bypass-approvals-and-sandbox",
        "danger-full-access",
        "--last",
    }
    if any(item in forbidden for item in command):
        raise ValueError("unsafe codex command generated")
    return command


def _claude_code_command(*, probe: ClaudeCodeCliProbe) -> list[str]:
    command = [
        probe.executable,
        "--bare",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--no-session-persistence",
        "--permission-mode",
        "default",
        "--tools",
        "",
    ]
    forbidden = {
        "--dangerously-skip-permissions",
        "--dangerously-bypass-approvals-and-sandbox",
        "--continue",
        "-c",
        "--resume",
        "-r",
        "--session-id",
        "--add-dir",
        "--remote",
        "--remote-control",
        "--mcp-config",
        "--plugin-dir",
        "--plugin-url",
        "--agents",
        "--allowedTools",
        "--settings",
        "--setting-sources",
        "--include-hook-events",
        "bypassPermissions",
        "acceptEdits",
        "auto",
        "dontAsk",
    }
    if any(item in forbidden for item in command):
        raise ValueError("unsafe claude command generated")
    try:
        tools_index = command.index("--tools")
    except ValueError as exc:
        raise ValueError("claude command must disable tools") from exc
    if tools_index + 1 >= len(command) or command[tools_index + 1] != "":
        raise ValueError("claude command must use empty tools")
    return command


def _extract_codex_session_id(record: dict[str, Any]) -> str | None:
    for key in ("session_id", "sessionId", "conversation_id", "conversationId"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    session = record.get("session")
    if isinstance(session, dict):
        value = session.get("id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_claude_session_id(record: dict[str, Any]) -> str | None:
    for key in ("session_id", "sessionId", "conversation_id", "conversationId"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    session = record.get("session")
    if isinstance(session, dict):
        value = session.get("id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    message = record.get("message")
    if isinstance(message, dict):
        return _extract_claude_session_id(message)
    return None


def _extract_codex_text(record: dict[str, Any]) -> str:
    record_type = str(record.get("type") or record.get("event") or "").lower()
    role = str(record.get("role") or "").lower()
    if role and role != "assistant":
        return ""
    assistant_record = role == "assistant" or any(
        marker in record_type for marker in ("assistant", "agent_message")
    )
    for nested_key in ("message", "item", "data"):
        nested = record.get(nested_key)
        if isinstance(nested, dict):
            text = _extract_codex_text(nested)
            if text:
                return text
    candidate_keys = ("delta", "content", "text", "message", "output")
    if assistant_record or record_type in {"delta", "message_delta"}:
        for key in candidate_keys:
            value = record.get(key)
            if isinstance(value, str):
                return value
    elif any(key in record for key in candidate_keys):
        return ""
    content = record.get("content")
    if assistant_record and isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    chunks.append(text)
            elif isinstance(item, str):
                chunks.append(item)
        return "".join(chunks)
    return ""


def _extract_claude_text(record: dict[str, Any]) -> str:
    record_type = str(record.get("type") or record.get("event") or "").lower()
    role = str(record.get("role") or "").lower()
    if role and role not in {"assistant", "model"}:
        return ""
    assistant_record = role in {"assistant", "model"} or record_type in {
        "assistant",
        "assistant_message",
        "assistant_delta",
        "message_delta",
        "content_block_delta",
        "text_delta",
    }
    if record_type == "result" and isinstance(record.get("result"), str):
        return str(record["result"])
    delta = record.get("delta")
    if isinstance(delta, dict):
        text = delta.get("text") or delta.get("content")
        if isinstance(text, str):
            return text
    elif isinstance(delta, str) and assistant_record:
        return delta
    for nested_key in ("message", "item", "data"):
        nested = record.get(nested_key)
        if isinstance(nested, dict):
            text = _extract_claude_text(nested)
            if text:
                return text
    content = record.get("content")
    if isinstance(content, str) and assistant_record:
        return content
    if assistant_record and isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    chunks.append(text)
                elif isinstance(item.get("delta"), dict):
                    delta_text = item["delta"].get("text")
                    if isinstance(delta_text, str):
                        chunks.append(delta_text)
            elif isinstance(item, str):
                chunks.append(item)
        return "".join(chunks)
    for key in ("text", "output"):
        value = record.get(key)
        if isinstance(value, str) and assistant_record:
            return value
    return ""


def _claude_result_text(record: dict[str, Any]) -> str:
    record_type = str(record.get("type") or record.get("event") or "").lower()
    if record_type == "result" and isinstance(record.get("result"), str):
        return str(record["result"])
    return ""


def _claude_record_indicates_init(record: dict[str, Any]) -> bool:
    record_type = str(record.get("type") or record.get("event") or "").lower()
    subtype = str(record.get("subtype") or record.get("kind") or "").lower()
    return (
        record_type in {"system", "system/init", "init"}
        and (not subtype or subtype == "init")
    ) or record_type == "system_init"


def _nonempty_capability_value(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list | tuple | set | dict):
        return bool(value)
    return bool(value)


def _claude_init_safety_error(record: dict[str, Any]) -> str | None:
    unsafe_keys = (
        "tools",
        "available_tools",
        "availableTools",
        "mcp_servers",
        "mcpServers",
        "plugins",
        "loaded_plugins",
        "loadedPlugins",
        "hooks",
        "hook_events",
        "hookEvents",
        "agents",
        "subagents",
        "sub_agents",
        "custom_agents",
        "customAgents",
        "browser",
        "remote_control",
        "remoteControl",
        "session_path",
        "sessionPath",
        "transcript_path",
        "transcriptPath",
    )
    for key in unsafe_keys:
        if _nonempty_capability_value(record.get(key)):
            return f"claude unsafe system/init capability surface: {key}"
    return None


def _claude_record_safety_error(record: dict[str, Any]) -> str | None:
    record_type = str(record.get("type") or record.get("event") or "").lower()
    if any(
        marker in record_type
        for marker in (
            "tool",
            "mcp",
            "plugin",
            "hook",
            "subagent",
            "browser",
            "remote",
        )
    ):
        return f"claude unsafe stream event: {record_type or 'unknown'}"
    if _claude_record_indicates_init(record):
        return _claude_init_safety_error(record)
    for key in ("tools", "mcp_servers", "plugins", "hooks", "agents", "subagents"):
        if _nonempty_capability_value(record.get(key)):
            return f"claude unsafe stream field: {key}"
    return None


def _parse_codex_output(stdout: str, final_message: str) -> CodexRunResult:
    deltas: list[str] = []
    session_id: str | None = None
    malformed = False
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            malformed = True
            continue
        if not isinstance(record, dict):
            continue
        session_id = _extract_codex_session_id(record) or session_id
        text = _extract_codex_text(record)
        if text:
            deltas.append(_redact_codex_text(text))
    fallback = _redact_codex_text(final_message.strip())
    content = fallback or "".join(deltas).strip()
    if malformed and not content:
        return CodexRunResult(status="error", error_message="codex emitted malformed JSONL")
    if not content:
        return CodexRunResult(status="error", error_message="codex returned empty assistant output")
    return CodexRunResult(
        status="completed",
        content=content,
        session_id=session_id,
        metadata={"delta_count": len(deltas), "used_fallback": bool(fallback)},
    )


def _parse_claude_code_output(stdout: str) -> ClaudeCodeRunResult:
    deltas: list[str] = []
    result_text = ""
    session_id: str | None = None
    malformed = False
    safety_proven = False
    safety_metadata: dict[str, Any] = {}
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            malformed = True
            continue
        if not isinstance(record, dict):
            continue
        safety_error = _claude_record_safety_error(record)
        if safety_error:
            return ClaudeCodeRunResult(status="error", error_message=safety_error)
        if _claude_record_indicates_init(record):
            safety_proven = True
            safety_metadata = {
                "system_init_safe": True,
                "tools_count": len(record.get("tools") or []),
                "mcp_servers_count": len(
                    record.get("mcp_servers") or record.get("mcpServers") or []
                ),
            }
        session_id = _extract_claude_session_id(record) or session_id
        result_candidate = _claude_result_text(record)
        if result_candidate:
            result_text = _redact_claude_text(result_candidate)
            continue
        text = _extract_claude_text(record)
        if text:
            deltas.append(_redact_claude_text(text))
    if malformed and not deltas:
        return ClaudeCodeRunResult(status="error", error_message="claude emitted malformed JSONL")
    if not safety_proven:
        return ClaudeCodeRunResult(
            status="error",
            error_message="claude output missing empty-tool system/init safety proof",
        )
    delta_content = "".join(deltas)
    if result_text:
        if not delta_content:
            content = result_text.strip()
        elif result_text == delta_content or result_text.startswith(delta_content):
            content = result_text.strip()
        elif delta_content.endswith(result_text):
            content = delta_content.strip()
        else:
            content = f"{delta_content}{result_text}".strip()
    else:
        content = delta_content.strip()
    if not content:
        return ClaudeCodeRunResult(
            status="error",
            error_message="claude returned empty assistant output",
            metadata=safety_metadata,
        )
    return ClaudeCodeRunResult(
        status="completed",
        content=content,
        session_id=session_id,
        metadata={
            **safety_metadata,
            "delta_count": len(deltas),
            "result_text_present": bool(result_text),
            "used_fallback": False,
        },
    )


def _run_subprocess_with_stdout_stream(
    command: list[str],
    *,
    input_text: str,
    timeout_seconds: float,
    cwd: str,
    env: dict[str, str],
    on_stdout_line: Callable[[str], None],
) -> subprocess.CompletedProcess[str]:
    stdout_queue: Queue[str | None] = Queue()
    stdout_lines: list[str] = []
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stderr_file:
        process = subprocess.Popen(  # noqa: S603
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr_file,
            text=True,
            cwd=cwd,
            env=env,
        )
        if process.stdout is None:
            process.kill()
            raise OSError("subprocess stdout pipe was unavailable")

        def read_stdout() -> None:
            try:
                for line in process.stdout:
                    stdout_queue.put(line)
            finally:
                stdout_queue.put(None)

        reader = threading.Thread(target=read_stdout, daemon=True)
        reader.start()
        stdin_errors: list[BaseException] = []

        def write_stdin() -> None:
            if process.stdin is None:
                return
            try:
                process.stdin.write(input_text)
                process.stdin.close()
            except BrokenPipeError:
                pass
            except BaseException as exc:  # pragma: no cover - defensive pipe failure path
                stdin_errors.append(exc)

        writer = threading.Thread(target=write_stdin, daemon=True)
        writer.start()
        deadline = time.monotonic() + timeout_seconds
        stdout_done = False
        while not stdout_done:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                process.wait()
                writer.join(timeout=1)
                reader.join(timeout=1)
                stderr_file.seek(0)
                raise subprocess.TimeoutExpired(
                    command,
                    timeout_seconds,
                    output="".join(stdout_lines),
                    stderr=stderr_file.read(),
                )
            try:
                item = stdout_queue.get(timeout=min(0.1, remaining))
            except Empty:
                continue
            if item is None:
                stdout_done = True
                continue
            stdout_lines.append(item)
            on_stdout_line(item)
        remaining = max(0.0, deadline - time.monotonic())
        try:
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            writer.join(timeout=1)
            reader.join(timeout=1)
            stderr_file.seek(0)
            raise subprocess.TimeoutExpired(
                command,
                timeout_seconds,
                output="".join(stdout_lines),
                stderr=stderr_file.read(),
            ) from None
        writer.join(timeout=1)
        reader.join(timeout=1)
        if stdin_errors:
            raise OSError(f"subprocess stdin pipe failed: {stdin_errors[0]}")
        stderr_file.seek(0)
        return subprocess.CompletedProcess(
            command,
            returncode,
            stdout="".join(stdout_lines),
            stderr=stderr_file.read(),
        )


def _run_codex_cli(
    *,
    config: Any,
    state: dict[str, Any],
    payload: dict[str, Any],
    on_delta: Callable[[str], None] | None = None,
) -> CodexRunResult:
    probe = _probe_codex_cli()
    if not probe.installed:
        return CodexRunResult(status="error", error_message=probe.error_message)
    workspace_root = _load_bridge_workspace_root(config, state)
    if workspace_root is None:
        return CodexRunResult(
            status="error",
            error_message="codex workspace root sidecar missing or mismatched",
        )
    if not workspace_root.exists() or not workspace_root.is_dir():
        return CodexRunResult(status="error", error_message="codex workspace root is unavailable")
    actual_workspace_hash = _workspace_identity_hash(workspace_root, adapter_kind="codex")
    server_workspace_hash = str(payload.get("workspace_identity_hash") or "")
    if not server_workspace_hash or server_workspace_hash != actual_workspace_hash:
        return CodexRunResult(
            status="error",
            error_message="codex workspace identity does not match server task",
            metadata={"workspace_identity_hash": actual_workspace_hash},
        )
    prompt = _codex_prompt_for_task(payload)
    with tempfile.TemporaryDirectory(prefix="harness-codex-") as temp_name:
        temp_dir = Path(temp_name)
        output_last_message = temp_dir / "last-message.txt"
        try:
            command = _codex_command(
                probe=probe,
                workspace_root=workspace_root,
                output_last_message=output_last_message,
            )
        except ValueError as exc:
            return CodexRunResult(status="error", error_message=str(exc))
        try:
            env = _codex_subprocess_env(executable=probe.executable, temp_dir=temp_dir)
            streamed_delta_count = 0
            if on_delta is None:
                completed = subprocess.run(  # noqa: S603
                    command,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=CODEX_SUBPROCESS_TIMEOUT_SECONDS,
                    cwd=str(workspace_root),
                    env=env,
                )
            else:

                def stream_codex_line(raw_line: str) -> None:
                    nonlocal streamed_delta_count
                    line = raw_line.strip()
                    if not line:
                        return
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        return
                    if not isinstance(record, dict):
                        return
                    text = _extract_codex_text(record)
                    if not text:
                        return
                    on_delta(_redact_codex_text(text))
                    streamed_delta_count += 1

                completed = _run_subprocess_with_stdout_stream(
                    command,
                    input_text=prompt,
                    timeout_seconds=CODEX_SUBPROCESS_TIMEOUT_SECONDS,
                    cwd=str(workspace_root),
                    env=env,
                    on_stdout_line=stream_codex_line,
                )
        except subprocess.TimeoutExpired:
            return CodexRunResult(status="error", error_message="codex subprocess timed out")
        except OSError as exc:
            return CodexRunResult(status="error", error_message=f"codex subprocess failed: {exc}")
        try:
            final_message = output_last_message.read_text(encoding="utf-8")
        except OSError:
            final_message = ""
        if completed.returncode != 0:
            error_text = _redact_codex_text(completed.stderr or completed.stdout)
            return CodexRunResult(
                status="error",
                error_message=error_text or f"codex exited with {completed.returncode}",
                metadata={"exit_code": completed.returncode},
            )
        result = _parse_codex_output(completed.stdout, final_message)
        metadata = dict(result.metadata or {})
        metadata["exit_code"] = completed.returncode
        metadata["workspace_identity_hash"] = actual_workspace_hash
        if on_delta is not None:
            metadata["streamed_delta_count"] = streamed_delta_count
        return CodexRunResult(
            status=result.status,
            content=result.content,
            error_message=result.error_message,
            session_id=result.session_id,
            metadata=metadata,
        )


def _run_claude_code_cli(
    *,
    config: Any,
    state: dict[str, Any],
    payload: dict[str, Any],
    on_delta: Callable[[str], None] | None = None,
) -> ClaudeCodeRunResult:
    probe = _probe_claude_code_cli()
    if not probe.installed:
        return ClaudeCodeRunResult(status="error", error_message=probe.error_message)
    workspace_root = _load_bridge_workspace_root(config, state)
    if workspace_root is None:
        return ClaudeCodeRunResult(
            status="error",
            error_message="claude workspace root sidecar missing or mismatched",
        )
    if not workspace_root.exists() or not workspace_root.is_dir():
        return ClaudeCodeRunResult(
            status="error",
            error_message="claude workspace root is unavailable",
        )
    actual_workspace_hash = _workspace_identity_hash(workspace_root, adapter_kind="claude_code")
    server_workspace_hash = str(payload.get("workspace_identity_hash") or "")
    if not server_workspace_hash or server_workspace_hash != actual_workspace_hash:
        return ClaudeCodeRunResult(
            status="error",
            error_message="claude workspace identity does not match server task",
            metadata={"workspace_identity_hash": actual_workspace_hash},
        )
    prompt = _claude_code_prompt_for_task(payload)
    with tempfile.TemporaryDirectory(prefix="harness-claude-code-") as temp_name:
        temp_dir = Path(temp_name)
        private_cwd = temp_dir / "cwd"
        private_cwd.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            command = _claude_code_command(probe=probe)
        except ValueError as exc:
            return ClaudeCodeRunResult(status="error", error_message=str(exc))
        try:
            env = _claude_code_subprocess_env(executable=probe.executable, temp_dir=temp_dir)
            streamed_delta_count = 0
            if on_delta is None:
                completed = subprocess.run(  # noqa: S603
                    command,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=CLAUDE_SUBPROCESS_TIMEOUT_SECONDS,
                    cwd=str(private_cwd),
                    env=env,
                )
            else:
                safety_proven = False
                pending_deltas: list[str] = []

                def stream_claude_line(raw_line: str) -> None:
                    nonlocal safety_proven, streamed_delta_count
                    line = raw_line.strip()
                    if not line:
                        return
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        return
                    if not isinstance(record, dict):
                        return
                    if _claude_record_safety_error(record):
                        return
                    if _claude_record_indicates_init(record):
                        safety_proven = True
                        for pending in pending_deltas:
                            on_delta(pending)
                            streamed_delta_count += 1
                        pending_deltas.clear()
                        return
                    if _claude_result_text(record):
                        return
                    text = _extract_claude_text(record)
                    if not text:
                        return
                    redacted = _redact_claude_text(text)
                    if safety_proven:
                        on_delta(redacted)
                        streamed_delta_count += 1
                    else:
                        pending_deltas.append(redacted)

                completed = _run_subprocess_with_stdout_stream(
                    command,
                    input_text=prompt,
                    timeout_seconds=CLAUDE_SUBPROCESS_TIMEOUT_SECONDS,
                    cwd=str(private_cwd),
                    env=env,
                    on_stdout_line=stream_claude_line,
                )
        except subprocess.TimeoutExpired:
            return ClaudeCodeRunResult(status="error", error_message="claude subprocess timed out")
        except OSError as exc:
            return ClaudeCodeRunResult(
                status="error",
                error_message=f"claude subprocess failed: {exc}",
            )
        if completed.returncode != 0:
            error_text = _redact_claude_text(completed.stderr or completed.stdout)
            return ClaudeCodeRunResult(
                status="error",
                error_message=error_text or f"claude exited with {completed.returncode}",
                metadata={"exit_code": completed.returncode},
            )
        result = _parse_claude_code_output(completed.stdout)
        metadata = dict(result.metadata or {})
        metadata["exit_code"] = completed.returncode
        metadata["workspace_identity_hash"] = actual_workspace_hash
        if on_delta is not None:
            metadata["streamed_delta_count"] = streamed_delta_count
        return ClaudeCodeRunResult(
            status=result.status,
            content=result.content,
            error_message=result.error_message,
            session_id=result.session_id,
            metadata=metadata,
        )


def _claude_permission_bridge_safety_metadata(
    *,
    sdk_version: str = "",
    fake_sdk: bool = False,
) -> dict[str, Any]:
    safety = {
        "permission_bridge_callback_configured": True,
        "side_effect_tools_preapproval_disabled": True,
        "forbidden_permission_modes_disabled": True,
        "unmanaged_settings_disabled": True,
        "mcp_disabled": True,
        "plugins_disabled": True,
        "hooks_disabled": True,
        "subagents_disabled": True,
        "browser_disabled": True,
        "computer_use_disabled": True,
        "remote_control_disabled": True,
        "permission_mode": "default",
        "allowed_tools": [],
        "forbidden_surfaces": [],
        "permission_bridge_pre_tool_hook_configured": True,
        "permission_bridge_dummy_hook_only": True,
    }
    return {
        **safety,
        "permission_bridge_active": True,
        "permission_bridge_version": CLAUDE_PERMISSION_BRIDGE_VERSION,
        "permission_bridge_mode": "sdk",
        "permission_bridge_execution": "harness_owned_executor",
        "sdk_native_tool_execution_enabled": False,
        "sdk_version": sdk_version,
        "fake_sdk": fake_sdk,
        "supports_resume": False,
        "resume_mode": "context_replay_new_session",
        "safety": safety,
    }


def _validate_claude_permission_bridge_workspace(
    *,
    config: Any,
    state: dict[str, Any],
    payload: dict[str, Any],
) -> tuple[Path | None, ClaudePermissionBridgeResult | None]:
    workspace_root = _load_bridge_workspace_root(config, state)
    if workspace_root is None:
        return None, ClaudePermissionBridgeResult(
            status="error",
            error_message="claude workspace root sidecar missing or mismatched",
        )
    if not workspace_root.exists() or not workspace_root.is_dir():
        return None, ClaudePermissionBridgeResult(
            status="error",
            error_message="claude workspace root is unavailable",
        )
    actual_workspace_hash = _workspace_identity_hash(workspace_root, adapter_kind="claude_code")
    server_workspace_hash = str(payload.get("workspace_identity_hash") or "")
    if not server_workspace_hash or server_workspace_hash != actual_workspace_hash:
        return None, ClaudePermissionBridgeResult(
            status="error",
            error_message="claude workspace identity does not match server task",
            metadata={"workspace_identity_hash": actual_workspace_hash},
        )
    return workspace_root, None


def _fake_claude_sdk_events_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    fake = payload.get("fake_sdk_events")
    if isinstance(fake, list):
        return [item for item in fake if isinstance(item, dict)]
    return []


def _claude_permission_bridge_fake_sdk_enabled() -> bool:
    return str(os.environ.get("HAO_CLAUDE_PERMISSION_BRIDGE_FAKE_SDK") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _claude_permission_bridge_fake_sdk_requested(payload: dict[str, Any]) -> bool:
    return (
        payload.get("test_fixture_mode") == "claude_permission_bridge_fake_sdk"
        and payload.get("fake_sdk_events") is not None
    )


def _run_claude_permission_bridge_fake_sdk(
    *,
    client: HarnessApiClient,
    device_token: str,
    bridge_task_id: str,
    config: Any,
    state: dict[str, Any],
    payload: dict[str, Any],
) -> ClaudePermissionBridgeResult:
    if not _claude_permission_bridge_fake_sdk_enabled():
        return ClaudePermissionBridgeResult(
            status="error",
            error_message="Claude permission bridge fake SDK mode is disabled",
            metadata=_claude_permission_bridge_safety_metadata(fake_sdk=True),
        )
    workspace_root, failure = _validate_claude_permission_bridge_workspace(
        config=config,
        state=state,
        payload=payload,
    )
    if failure is not None:
        return failure
    assert workspace_root is not None
    store = SessionStore(config.session_db_path, config.sessions_dir)
    local_session = store.create_session(
        cwd=str(workspace_root),
        agent_id=str(payload.get("agent_id") or "default"),
        mode="confirm",
        cli_mode="claude_code",
        target="host",
    )
    run_id = str(payload.get("run_id") or "")
    if run_id:
        store.update_run_id(local_session.id, run_id)
    model_provider = str(payload.get("model_provider") or "default")
    model_name = str(payload.get("model_name") or "default")
    assistant_chunks: list[str] = []
    sequence = 0
    for event in _fake_claude_sdk_events_from_payload(payload):
        sequence += 1
        event_type = str(event.get("type") or "")
        if event_type == "tool_request":
            ok, message, _approved_input = _handle_claude_permission_tool_request(
                client=client,
                device_token=device_token,
                bridge_task_id=bridge_task_id,
                store=store,
                local_session_id=local_session.id,
                run_id=run_id,
                agent_id=str(payload.get("agent_id") or "default"),
                model_provider=model_provider,
                model_name=model_name,
                cwd=workspace_root,
                claude_tool_name=str(event.get("tool_name") or ""),
                claude_input=event.get("input") if isinstance(event.get("input"), dict) else {},
                tool_use_id=str(event.get("tool_use_id") or ""),
                sequence=sequence,
            )
            if not ok:
                return ClaudePermissionBridgeResult(
                    status="error",
                    error_message=message,
                    metadata=_claude_permission_bridge_safety_metadata(fake_sdk=True),
                )
            assistant_chunks.append(message)
        elif event_type in {"assistant", "assistant_delta"}:
            assistant_chunks.append(_redact_claude_text(str(event.get("content") or "")))
        elif event_type == "crash":
            return ClaudePermissionBridgeResult(
                status="error",
                error_message=_redact_claude_text(str(event.get("error") or "fake SDK crashed")),
                metadata=_claude_permission_bridge_safety_metadata(fake_sdk=True),
            )
    content = "\n".join(chunk for chunk in assistant_chunks if chunk).strip()
    if not content:
        content = "Claude Code permission bridge completed."
    return ClaudePermissionBridgeResult(
        status="completed",
        content=content,
        session_id=local_session.id,
        metadata=_claude_permission_bridge_safety_metadata(fake_sdk=True),
    )


def _extract_claude_sdk_text(message: Any) -> str:
    if isinstance(message, str):
        return _redact_claude_text(message)
    if isinstance(message, dict):
        return _extract_claude_text(message)
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return _redact_claude_text(content)
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            text = getattr(item, "text", None)
            if isinstance(text, str):
                chunks.append(text)
            elif isinstance(item, dict):
                value = item.get("text") or item.get("content")
                if isinstance(value, str):
                    chunks.append(value)
        return _redact_claude_text("".join(chunks))
    return ""


def _claude_sdk_tool_name(
    tool_name: Any,
    input_json: Any,
) -> tuple[str, dict[str, Any], str | None]:
    if isinstance(tool_name, dict):
        payload = tool_name
        inferred_name = str(payload.get("name") or payload.get("tool_name") or "")
        inferred_input = payload.get("input") if isinstance(payload.get("input"), dict) else {}
        tool_use_id = payload.get("id") or payload.get("tool_use_id")
        return inferred_name, inferred_input, str(tool_use_id) if tool_use_id else None
    if isinstance(input_json, dict):
        tool_use_id = input_json.get("id") or input_json.get("tool_use_id")
        return str(tool_name or ""), input_json, str(tool_use_id) if tool_use_id else None
    return str(tool_name or ""), {}, None


async def _run_claude_permission_bridge_sdk_async(
    *,
    client: HarnessApiClient,
    device_token: str,
    bridge_task_id: str,
    config: Any,
    state: dict[str, Any],
    payload: dict[str, Any],
) -> ClaudePermissionBridgeResult:
    workspace_root, failure = _validate_claude_permission_bridge_workspace(
        config=config,
        state=state,
        payload=payload,
    )
    if failure is not None:
        return failure
    assert workspace_root is not None
    sdk_probe = _probe_claude_agent_sdk()
    if not sdk_probe.installed:
        return ClaudePermissionBridgeResult(
            status="error",
            error_message=sdk_probe.error_message or "claude_agent_sdk unavailable",
            metadata=_claude_permission_bridge_safety_metadata(
                sdk_version=sdk_probe.version,
                fake_sdk=False,
            ),
        )
    sdk = importlib.import_module("claude_agent_sdk")
    try:
        sdk_types = importlib.import_module("claude_agent_sdk.types")
    except Exception:
        sdk_types = None
    HookMatcher = _claude_agent_sdk_symbol(sdk, sdk_types, "HookMatcher")
    PermissionResultDeny = _claude_agent_sdk_symbol(sdk, sdk_types, "PermissionResultDeny")
    store = SessionStore(config.session_db_path, config.sessions_dir)
    local_session = store.create_session(
        cwd=str(workspace_root),
        agent_id=str(payload.get("agent_id") or "default"),
        mode="confirm",
        cli_mode="claude_code",
        target="host",
    )
    run_id = str(payload.get("run_id") or "")
    if run_id:
        store.update_run_id(local_session.id, run_id)
    model_provider = str(payload.get("model_provider") or "default")
    model_name = str(payload.get("model_name") or "default")
    sequence_counter = {"value": 0}

    async def can_use_tool(tool_name: Any, input_json: Any, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        sequence_counter["value"] += 1
        mapped_name, mapped_input, tool_use_id = _claude_sdk_tool_name(tool_name, input_json)
        ok, message, _approved_input = _handle_claude_permission_tool_request(
            client=client,
            device_token=device_token,
            bridge_task_id=bridge_task_id,
            store=store,
            local_session_id=local_session.id,
            run_id=run_id,
            agent_id=str(payload.get("agent_id") or "default"),
            model_provider=model_provider,
            model_name=model_name,
            cwd=workspace_root,
            claude_tool_name=mapped_name,
            claude_input=mapped_input,
            tool_use_id=tool_use_id,
            sequence=sequence_counter["value"],
        )
        if ok:
            # Harness already executed and audited the side effect. Deny SDK-native execution
            # so Claude Code cannot perform the same host mutation a second time.
            return PermissionResultDeny(message=message)
        return PermissionResultDeny(message=_redact_claude_text(message))

    async def permission_bridge_pre_tool_hook(
        input_data: Any,
        tool_use_id: Any,
        context: Any,
    ) -> dict[str, bool]:
        del input_data, tool_use_id, context
        return {"continue_": True}

    options_kwargs = {
        "permission_mode": "default",
        "allowed_tools": CLAUDE_SAFE_SDK_TOOLS,
        "can_use_tool": can_use_tool,
    }
    options_signature = inspect.signature(sdk.ClaudeAgentOptions)
    if _callable_accepts_keyword(sdk.ClaudeAgentOptions, "hooks"):
        options_kwargs["hooks"] = {
            "PreToolUse": [
                HookMatcher(
                    matcher=None,
                    hooks=[permission_bridge_pre_tool_hook],
                )
            ]
        }
    if "setting_sources" in options_signature.parameters:
        options_kwargs["setting_sources"] = []
    if "disallowed_tools" in options_signature.parameters:
        options_kwargs["disallowed_tools"] = sorted(CLAUDE_DENIED_TOOLS)
    for disabled_keyword, disabled_value in (
        ("mcp_servers", {}),
        ("strict_mcp_config", True),
        ("agents", {}),
        ("plugins", []),
        ("skills", []),
        ("include_hook_events", False),
    ):
        if disabled_keyword in options_signature.parameters:
            options_kwargs[disabled_keyword] = disabled_value
    if "cwd" in options_signature.parameters:
        options_kwargs["cwd"] = str(workspace_root)
    try:
        options = sdk.ClaudeAgentOptions(**options_kwargs)
    except Exception as exc:
        return ClaudePermissionBridgeResult(
            status="error",
            error_message=_redact_claude_text(f"Claude Agent SDK options failed: {exc}"),
            metadata=_claude_permission_bridge_safety_metadata(
                sdk_version=sdk_probe.version,
                fake_sdk=False,
            ),
        )
    prompt = _claude_code_permission_bridge_prompt_for_task(payload)
    assistant_chunks: list[str] = []
    try:
        async with sdk.ClaudeSDKClient(options=options) as claude_client:
            await claude_client.query(_claude_agent_sdk_prompt_stream(prompt))
            async for message in claude_client.receive_response():
                text = _extract_claude_sdk_text(message)
                if text:
                    assistant_chunks.append(text)
    except Exception as exc:
        return ClaudePermissionBridgeResult(
            status="error",
            error_message=_redact_claude_text(f"Claude Agent SDK run failed: {exc}"),
            metadata=_claude_permission_bridge_safety_metadata(
                sdk_version=sdk_probe.version,
                fake_sdk=False,
            ),
        )
    content = "".join(assistant_chunks).strip()
    if not content:
        return ClaudePermissionBridgeResult(
            status="error",
            error_message="Claude Agent SDK returned empty assistant output",
            metadata=_claude_permission_bridge_safety_metadata(
                sdk_version=sdk_probe.version,
                fake_sdk=False,
            ),
        )
    return ClaudePermissionBridgeResult(
        status="completed",
        content=content,
        session_id=local_session.id,
        metadata=_claude_permission_bridge_safety_metadata(
            sdk_version=sdk_probe.version,
            fake_sdk=False,
        ),
    )


def _run_claude_permission_bridge_sdk(
    *,
    client: HarnessApiClient,
    device_token: str,
    bridge_task_id: str,
    config: Any,
    state: dict[str, Any],
    payload: dict[str, Any],
) -> ClaudePermissionBridgeResult:
    fake_requested = _claude_permission_bridge_fake_sdk_requested(payload)
    if fake_requested and _claude_permission_bridge_fake_sdk_enabled():
        return _run_claude_permission_bridge_fake_sdk(
            client=client,
            device_token=device_token,
            bridge_task_id=bridge_task_id,
            config=config,
            state=state,
            payload=payload,
        )
    if fake_requested:
        return ClaudePermissionBridgeResult(
            status="error",
            error_message="Claude permission bridge fake SDK mode is disabled",
            metadata=_claude_permission_bridge_safety_metadata(fake_sdk=True),
        )
    return asyncio.run(
        _run_claude_permission_bridge_sdk_async(
            client=client,
            device_token=device_token,
            bridge_task_id=bridge_task_id,
            config=config,
            state=state,
            payload=payload,
        )
    )


def _save_bridge_device_token(config: Any, device_token: str) -> str:
    config.home.mkdir(parents=True, exist_ok=True)
    token_ref = BRIDGE_DEVICE_TOKEN_REF
    path = _bridge_device_token_path(config, token_ref)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(device_token)
    os.chmod(path, 0o600)
    return token_ref


def _load_bridge_device_token(config: Any, state: dict[str, Any]) -> str:
    token_ref = str(state.get("device_token_ref") or BRIDGE_DEVICE_TOKEN_REF)
    try:
        return _bridge_device_token_path(config, token_ref).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _workspace_identity_hash(cwd: Path, *, adapter_kind: str = "codex") -> str:
    canonical = str(cwd.expanduser().resolve())
    prefix = (
        CLAUDE_WORKSPACE_HASH_PREFIX
        if adapter_kind == "claude_code"
        else CODEX_WORKSPACE_HASH_PREFIX
    )
    return sha256(f"{prefix}{canonical}".encode()).hexdigest()


def _save_bridge_workspace_root(config: Any, cwd: Path) -> str:
    config.home.mkdir(parents=True, exist_ok=True)
    root_ref = BRIDGE_WORKSPACE_ROOT_REF
    path = _bridge_workspace_root_path(config, root_ref)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(str(cwd.expanduser().resolve()))
    os.chmod(path, 0o600)
    return root_ref


def _load_bridge_workspace_root(config: Any, state: dict[str, Any]) -> Path | None:
    root_ref = str(state.get("workspace_root_ref") or BRIDGE_WORKSPACE_ROOT_REF)
    try:
        raw = _bridge_workspace_root_path(config, root_ref).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    cwd = Path(raw).expanduser().resolve()
    expected_hash = str(state.get("workspace_identity_hash") or "")
    adapter_kind = str(state.get("adapter_kind") or "codex")
    if expected_hash and _workspace_identity_hash(cwd, adapter_kind=adapter_kind) != expected_hash:
        return None
    return cwd


def _bridge_state_for_disk(state: dict[str, Any]) -> dict[str, Any]:
    allowed_scalar_keys = {
        "api_url",
        "connection_id",
        "device_token_ref",
        "adapter_kind",
        "display_name",
        "permission_bridge",
        "workspace_root_ref",
        "workspace_identity_hash",
    }
    safe = {
        key: str(state[key])
        for key in allowed_scalar_keys
        if state.get(key) not in (None, "")
    }
    pending = [
        item
        for item in (
            _safe_bridge_pending_tool_state(candidate)
            for candidate in _bridge_pending_tools(state)
        )
        if item
    ]
    if pending:
        safe["pending_tool_requests"] = pending
    return safe


def _save_bridge_state(config: Any, state: dict[str, Any]) -> None:
    config.home.mkdir(parents=True, exist_ok=True)
    if state.get("device_token"):
        state["device_token_ref"] = _save_bridge_device_token(config, str(state["device_token"]))
    path = _bridge_state_path(config)
    data = json.dumps(_bridge_state_for_disk(state), ensure_ascii=False, indent=2, sort_keys=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(data)
    os.chmod(path, 0o600)


def _load_bridge_state(config: Any) -> dict[str, Any]:
    path = _bridge_state_path(config)
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    if loaded.get("device_token"):
        loaded["device_token_ref"] = _save_bridge_device_token(config, str(loaded["device_token"]))
        _save_bridge_state(config, loaded)
    else:
        token = _load_bridge_device_token(config, loaded)
        if token:
            loaded["device_token"] = token
    return loaded


def _bridge_pending_tools(state: dict[str, Any]) -> list[dict[str, Any]]:
    items = state.get("pending_tool_requests")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _safe_bridge_command_mode(value: Any) -> str:
    command = str(value or "act").strip()
    return command if command in {"act", "chat,plan", "chat", "plan"} else "act"


def _safe_bridge_pending_tool_state(pending: dict[str, Any]) -> dict[str, Any]:
    tool_request_id = str(pending.get("tool_request_id") or "")
    bridge_task_id = str(pending.get("bridge_task_id") or "")
    if not tool_request_id or not bridge_task_id:
        return {}
    safe: dict[str, Any] = {
        "tool_request_id": tool_request_id,
        "bridge_task_id": bridge_task_id,
        "command": _safe_bridge_command_mode(pending.get("command")),
    }
    for key in (
        "tool_name",
        "tool_call_id",
        "backend_tool_call_id",
        "approval_id",
        "local_session_id",
        "run_id",
        "agent_id",
        "model_provider",
        "model_name",
        "harness_stream_token",
        "bridge_delta_count",
        "risk_level",
        "permission_mode",
        "change_id",
        "diff_sha256",
    ):
        value = pending.get(key)
        if value not in (None, ""):
            safe[key] = str(value)
    return safe


def _upsert_bridge_pending_tool(
    *,
    config: Any,
    state: dict[str, Any],
    pending: dict[str, Any],
) -> None:
    pending_state = _safe_bridge_pending_tool_state(pending)
    tool_request_id = str(pending_state.get("tool_request_id") or "")
    if not tool_request_id:
        return
    items = [
        item
        for item in _bridge_pending_tools(state)
        if str(item.get("tool_request_id") or "") != tool_request_id
    ]
    items.append(pending_state)
    state["pending_tool_requests"] = items
    _save_bridge_state(config, state)


def _remove_bridge_pending_tool(
    *,
    config: Any,
    state: dict[str, Any],
    tool_request_id: str,
) -> None:
    state["pending_tool_requests"] = [
        item
        for item in _bridge_pending_tools(state)
        if str(item.get("tool_request_id") or "") != tool_request_id
    ]
    _save_bridge_state(config, state)


def _bridge_tool_request_id(
    *,
    bridge_task_id: str,
    tool_call_id: str | None,
    tool_name: str,
) -> str:
    raw = f"{bridge_task_id}:{tool_call_id or tool_name}".strip(":")
    if 1 <= len(raw) <= 150:
        return raw
    return f"{bridge_task_id}:tool:{sha256(raw.encode('utf-8')).hexdigest()[:24]}"


def _sha256_text(value: str) -> str:
    return sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _tool_target_paths(
    tool_name: str,
    input_json: dict[str, Any],
    output_json: dict | None,
) -> list[str]:
    if output_json is not None and isinstance(output_json.get("target_paths"), list):
        return [str(path) for path in output_json["target_paths"]]
    if tool_name in {"write_file", "read_file"} and input_json.get("path"):
        return [str(input_json["path"])]
    return []


def _requires_network(tool_name: str, input_json: dict[str, Any]) -> bool:
    command = str(input_json.get("command") or input_json.get("cmd") or "")
    lowered = command.lower()
    return tool_name == "network" or any(
        pattern in lowered
        for pattern in (
            "curl ",
            "wget ",
            "ssh ",
            "scp ",
            "git remote",
            "npm install",
            "pnpm install",
            "yarn add",
            "pip install",
        )
    )


def _requires_secret_read(tool_name: str, input_json: dict[str, Any]) -> bool:
    command = str(input_json.get("command") or input_json.get("cmd") or "")
    lowered = command.lower()
    return tool_name in {"env_read", "secret_read"} or any(
        pattern in lowered
        for pattern in ("printenv", "cat .env", "token", "secret", "api_key")
    )


def _claude_tool_text(input_json: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = input_json.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _map_claude_tool_request(tool_name: str, input_json: dict[str, Any]) -> ClaudeToolMapping:
    normalized_tool = str(tool_name or "").strip()
    if normalized_tool == "Bash":
        command = _claude_tool_text(input_json, "command", "cmd")
        if not command:
            return ClaudeToolMapping(False, "run_shell", {}, [], reason="Bash command is missing")
        return ClaudeToolMapping(
            True,
            "run_shell",
            {
                "command": command,
                "description": _claude_tool_text(input_json, "description"),
                "timeout_seconds": input_json.get("timeout_seconds", input_json.get("timeout")),
            },
            [],
            requires_network=_requires_network("run_shell", {"command": command}),
            requires_secret_read=_requires_secret_read("run_shell", {"command": command}),
        )
    if normalized_tool == "Write":
        path = _claude_tool_text(input_json, "file_path", "path")
        content = str(input_json.get("content") or "")
        if not path:
            return ClaudeToolMapping(False, "write_file", {}, [], reason="Write path is missing")
        return ClaudeToolMapping(True, "write_file", {"path": path, "content": content}, [path])
    if normalized_tool in {"Edit", "MultiEdit"}:
        patch = _claude_tool_text(input_json, "patch", "diff")
        path = _claude_tool_text(input_json, "file_path", "path")
        if patch:
            return ClaudeToolMapping(True, "apply_patch", {"patch": patch}, [path] if path else [])
        return ClaudeToolMapping(
            False,
            "apply_patch",
            {},
            [path] if path else [],
            reason=f"{normalized_tool} requires diff-first patch input in V6",
        )
    if normalized_tool == "Read":
        path = _claude_tool_text(input_json, "file_path", "path")
        if not path:
            return ClaudeToolMapping(False, "read_file", {}, [], reason="Read path is missing")
        return ClaudeToolMapping(True, "read_file", {"path": path}, [path])
    if normalized_tool == "LS":
        root = _claude_tool_text(input_json, "path", "root") or "."
        return ClaudeToolMapping(True, "list_files", {"root": root}, [root])
    if normalized_tool == "Glob":
        root = _claude_tool_text(input_json, "path", "root") or "."
        glob = _claude_tool_text(input_json, "pattern", "glob") or "**/*"
        return ClaudeToolMapping(True, "list_files", {"root": root, "glob": glob}, [root])
    if normalized_tool == "Grep":
        query = _claude_tool_text(input_json, "pattern", "query")
        root = _claude_tool_text(input_json, "path", "root") or "."
        glob = _claude_tool_text(input_json, "glob") or "**/*"
        if not query:
            return ClaudeToolMapping(
                False,
                "search_files",
                {},
                [root],
                reason="Grep query is missing",
            )
        return ClaudeToolMapping(
            True,
            "search_files",
            {"root": root, "query": query, "glob": glob},
            [root],
        )
    if normalized_tool in CLAUDE_DENIED_TOOLS or normalized_tool.startswith("mcp__"):
        return ClaudeToolMapping(
            False,
            normalized_tool or "unknown",
            {},
            [],
            reason=f"Claude tool {normalized_tool or 'unknown'} is not mapped in V6",
        )
    return ClaudeToolMapping(
        False,
        normalized_tool or "unknown",
        {},
        [],
        reason=f"unknown Claude tool {normalized_tool or 'unknown'} is denied by default",
    )


def _claude_tool_request_id(
    *,
    bridge_task_id: str,
    tool_use_id: str | None,
    tool_name: str,
    sequence: int,
) -> str:
    return _bridge_tool_request_id(
        bridge_task_id=bridge_task_id,
        tool_call_id=f"claude:{tool_use_id or f'{tool_name}:{sequence}'}",
        tool_name=tool_name,
    )


def _claude_permission_result_message(result: ToolExecutionResult) -> str:
    output = result.output_json if isinstance(result.output_json, dict) else {}
    safe_output = _redact_claude_text(json.dumps(output, ensure_ascii=False), limit=4000)
    if result.status == "SUCCESS":
        return f"Harness approved and executed the local tool. Result: {safe_output}"
    reason = result.error_message or str(output.get("error") or result.status)
    return f"Harness did not execute the local tool successfully: {_redact_claude_text(reason)}"


def _poll_local_tool_decision_for_claude(
    *,
    client: HarnessApiClient,
    device_token: str,
    tool_request_id: str,
    timeout_seconds: float = CLAUDE_PERMISSION_DECISION_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(0.1, timeout_seconds)
    last_decision: dict[str, Any] = {}
    while time.monotonic() <= deadline:
        decision = client.get_local_agent_tool_decision(
            device_token=device_token,
            tool_request_id=tool_request_id,
        )
        if isinstance(decision, dict):
            last_decision = decision
        terminal_decision = str(decision.get("decision") or decision.get("status") or "").strip()
        if terminal_decision == "approval_required":
            time.sleep(CLAUDE_PERMISSION_DECISION_POLL_SECONDS)
            continue
        if terminal_decision == "cancelled" and not decision.get("reason"):
            return {
                **decision,
                "executable": False,
                "reason": "Claude Code permission bridge request was cancelled",
            }
        if terminal_decision == "expired" and not decision.get("reason"):
            return {
                **decision,
                "executable": False,
                "reason": "Claude Code permission bridge approval expired",
            }
        if terminal_decision in {"denied", "failed", "revoked"} and not decision.get("reason"):
            return {
                **decision,
                "executable": False,
                "reason": f"Claude Code permission bridge request {terminal_decision}",
            }
        if terminal_decision:
            return decision
        return {
            **decision,
            "decision": "denied",
            "executable": False,
            "reason": "Claude Code permission bridge returned an invalid decision",
        }
    return {
        **last_decision,
        "decision": "denied",
        "executable": False,
        "reason": "Claude Code permission bridge approval timed out",
    }


def _handle_claude_permission_tool_request(
    *,
    client: HarnessApiClient,
    device_token: str,
    bridge_task_id: str,
    store: SessionStore,
    local_session_id: str,
    run_id: str | None,
    agent_id: str,
    model_provider: str,
    model_name: str,
    cwd: Path,
    claude_tool_name: str,
    claude_input: dict[str, Any],
    tool_use_id: str | None,
    sequence: int,
) -> tuple[bool, str, dict[str, Any] | None]:
    mapping = _map_claude_tool_request(claude_tool_name, claude_input)
    if not mapping.allowed:
        return False, mapping.reason or "Claude tool denied by Harness", None
    tool_request_id = _claude_tool_request_id(
        bridge_task_id=bridge_task_id,
        tool_use_id=tool_use_id,
        tool_name=claude_tool_name,
        sequence=sequence,
    )
    try:
        handled = _handle_bridge_host_tool_request(
            client=client,
            bridge_context=BridgeToolContext(
                bridge_task_id=bridge_task_id,
                device_token=device_token,
            ),
            store=store,
            session_id=local_session_id,
            run_id=run_id,
            agent_id=agent_id,
            command="claude_code",
            cwd=cwd,
            tool_name=mapping.tool_name,
            tool_call_id=tool_request_id,
            input_json=mapping.input_json,
            risk_level="critical"
            if (mapping.requires_network or mapping.requires_secret_read)
            else "high",
            permission_mode="confirm",
            model_provider=model_provider,
            model_name=model_name,
            tool_request_id_override=tool_request_id,
        )
    except Exception as exc:
        return False, _redact_claude_text(f"Harness tool request failed: {exc}"), None
    if handled.status == "pending_approval":
        pending = handled.pending_tool
        if not isinstance(pending, dict):
            return False, "Harness approval state is missing", None
        try:
            decision = _poll_local_tool_decision_for_claude(
                client=client,
                device_token=device_token,
                tool_request_id=tool_request_id,
            )
        except Exception as exc:
            return False, _redact_claude_text(f"Harness approval polling failed: {exc}"), None
        if not decision.get("executable"):
            return False, str(decision.get("reason") or decision.get("decision") or "denied"), None
        handled = _execute_approved_bridge_pending_tool(
            pending={**pending, "input_json": decision.get("input_json")},
            decision=decision,
            client=client,
            device_token=device_token,
            store=store,
            local_session_id=local_session_id,
            cwd=cwd,
        )
    if handled.result is None:
        return False, handled.error_message or handled.status, None
    if handled.status != "executed" or handled.result.status != "SUCCESS":
        return (
            False,
            handled.error_message or _claude_permission_result_message(handled.result),
            None,
        )
    executable_input = (
        handled.result.input_json
        if isinstance(handled.result.input_json, dict)
        else mapping.input_json
    )
    return True, _claude_permission_result_message(handled.result), executable_input


def _bridge_pending_tool_from_decision(decision: dict[str, Any]) -> dict[str, Any] | None:
    tool_request_id = str(decision.get("tool_request_id") or "")
    bridge_task_id = str(decision.get("bridge_task_id") or "")
    if not tool_request_id or not bridge_task_id:
        return None
    decision_json = (
        decision.get("decision_json") if isinstance(decision.get("decision_json"), dict) else {}
    )
    metadata = (
        decision_json.get("metadata") if isinstance(decision_json.get("metadata"), dict) else {}
    )
    preview = (
        decision_json.get("pending_change_preview")
        if isinstance(decision_json.get("pending_change_preview"), dict)
        else {}
    )
    return {
        "tool_request_id": tool_request_id,
        "bridge_task_id": bridge_task_id,
        "tool_call_id": metadata.get("tool_call_id") or decision.get("tool_call_id"),
        "backend_tool_call_id": decision.get("tool_call_id"),
        "approval_id": decision.get("approval_id"),
        "tool_name": decision.get("tool_name") or metadata.get("tool_name") or "tool",
        "local_session_id": metadata.get("local_session_id"),
        "run_id": metadata.get("run_id"),
        "agent_id": metadata.get("agent_id"),
        "model_provider": metadata.get("model_provider"),
        "model_name": metadata.get("model_name"),
        "harness_stream_token": metadata.get("harness_stream_token"),
        "bridge_delta_count": metadata.get("bridge_delta_count"),
        "command": metadata.get("command") or "act",
        "risk_level": metadata.get("risk_level") or "high",
        "permission_mode": metadata.get("permission_mode") or "confirm",
        "change_id": preview.get("change_id"),
        "diff_sha256": preview.get("diff_sha256") or preview.get("diff_hash"),
    }


def _sync_bridge_pending_tools_from_api(
    *,
    config: Any,
    state: dict[str, Any],
    client: HarnessApiClient,
    device_token: str,
) -> None:
    list_pending = getattr(client, "list_pending_local_agent_tool_requests", None)
    if not callable(list_pending):
        return
    page = list_pending(device_token=device_token)
    items = page.get("items") if isinstance(page, dict) else []
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        pending = _bridge_pending_tool_from_decision(item)
        if pending is None:
            continue
        existing = {
            str(candidate.get("tool_request_id") or ""): candidate
            for candidate in _bridge_pending_tools(state)
        }.get(str(pending["tool_request_id"]))
        if existing is not None:
            for key in (
                "local_session_id",
                "run_id",
                "agent_id",
                "model_provider",
                "model_name",
                "harness_stream_token",
                "bridge_delta_count",
                "command",
                "risk_level",
                "permission_mode",
                "change_id",
                "diff_sha256",
            ):
                if pending.get(key) in (None, "") and existing.get(key) not in (None, ""):
                    pending[key] = existing[key]
        _upsert_bridge_pending_tool(config=config, state=state, pending=pending)


def _bridge_command_cancel_check(
    *,
    client: HarnessApiClient,
    device_token: str,
) -> Any:
    get_status = getattr(client, "get_local_agent_command_status", None)
    if not callable(get_status):
        return None
    last_poll: dict[str, float] = {}
    cached: dict[str, bool] = {}

    def _check(command_id: str) -> bool:
        now = time.monotonic()
        if now - last_poll.get(command_id, 0.0) < 0.25:
            return cached.get(command_id, False)
        last_poll[command_id] = now
        try:
            status_payload = get_status(
                device_token=device_token,
                command_id=command_id,
            )
        except Exception:
            return cached.get(command_id, False)
        cancel_requested = bool(
            isinstance(status_payload, dict) and status_payload.get("cancel_requested")
        )
        cached[command_id] = cancel_requested
        return cancel_requested

    return _check


def _bridge_tool_result_status(result: ToolExecutionResult) -> str:
    command_status = ""
    if isinstance(result.output_json, dict):
        command_status = str(result.output_json.get("command_status") or "").lower()
    if command_status == "cancelled":
        return "CANCELLED"
    return result.status


def _ack_bridge_command_cancel_if_needed(
    *,
    client: HarnessApiClient,
    device_token: str,
    result: ToolExecutionResult,
) -> None:
    if _bridge_tool_result_status(result) != "CANCELLED":
        return
    output = result.output_json if isinstance(result.output_json, dict) else {}
    command_id = str(output.get("command_id") or "")
    if not command_id:
        return
    ack_cancel = getattr(client, "ack_local_agent_command_cancel", None)
    if not callable(ack_cancel):
        return
    ack_cancel(
        device_token=device_token,
        command_id=command_id,
        payload={
            "status": "cancelled",
            "error_message": result.error_message or str(output.get("error") or "cancelled"),
        },
    )


class BridgeReportingSessionStore:
    def __init__(
        self,
        *,
        delegate: SessionStore,
        client: HarnessApiClient,
        device_token: str,
        tool_request_id: str,
    ) -> None:
        self._delegate = delegate
        self._client = client
        self._device_token = device_token
        self._tool_request_id = tool_request_id
        self._output_counters: dict[str, int] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    def start_command(self, command_id: str) -> dict[str, Any]:
        command = self._delegate.start_command(command_id)
        self._report_command_event(
            command_id=command_id,
            payload={
                "event_id": f"{self._tool_request_id}:{command_id}:started",
                "tool_request_id": self._tool_request_id,
                "event_type": "started",
                "tool_name": command["tool_name"],
                "command": command["command"],
            },
        )
        return command

    def record_command_output(self, command_id: str, *, stream: str, chunk: str) -> None:
        self._delegate.record_command_output(command_id, stream=stream, chunk=chunk)
        counter = self._output_counters.get(command_id, 0) + 1
        self._output_counters[command_id] = counter
        payload: dict[str, Any] = {
            "event_id": f"{self._tool_request_id}:{command_id}:output:{counter}",
            "tool_request_id": self._tool_request_id,
            "event_type": "output",
        }
        if stream == "stderr":
            payload["stderr"] = chunk
        else:
            payload["stdout"] = chunk
        self._report_command_event(command_id=command_id, payload=payload)

    def record_command_output_truncated(
        self,
        command_id: str,
        *,
        stream: str,
        limit_bytes: int,
    ) -> None:
        self._delegate.record_command_output_truncated(
            command_id,
            stream=stream,
            limit_bytes=limit_bytes,
        )
        counter = self._output_counters.get(command_id, 0) + 1
        self._output_counters[command_id] = counter
        self._report_command_event(
            command_id=command_id,
            payload={
                "event_id": f"{self._tool_request_id}:{command_id}:output:{counter}",
                "tool_request_id": self._tool_request_id,
                "event_type": "output",
                "metadata": {
                    "stream": stream,
                    "truncated": True,
                    "limit_bytes": limit_bytes,
                },
            },
        )

    def finish_command(
        self,
        command_id: str,
        *,
        status: str,
        exit_code: int | None,
        stdout_truncated: bool,
        stderr_truncated: bool,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        command = self._delegate.finish_command(
            command_id,
            status=status,
            exit_code=exit_code,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            error_message=error_message,
        )
        event_type = {
            "timeout": "timeout",
            "cancelled": "cancelled",
        }.get(status, "finished")
        self._report_command_event(
            command_id=command_id,
            payload={
                "event_id": f"{self._tool_request_id}:{command_id}:{event_type}",
                "tool_request_id": self._tool_request_id,
                "event_type": event_type,
                "status": status,
                "exit_code": exit_code,
                "error_message": error_message,
            },
        )
        return command

    def _report_command_event(self, *, command_id: str, payload: dict[str, Any]) -> None:
        self._client.report_local_agent_command_event(
            device_token=self._device_token,
            command_id=command_id,
            payload=payload,
        )


def _run_bridge_pair(args: argparse.Namespace) -> int:
    config = load_config()
    api_url = args.api_url or config.api_url
    cwd = Path(args.cwd).expanduser().resolve()
    if args.adapter_kind:
        result = _pair_bridge_adapter(
            args=args,
            config=config,
            api_url=api_url,
            cwd=cwd,
            adapter_kind=str(args.adapter_kind),
            explicit=True,
        )
        return 0 if result == "paired" else 1

    results = [
        _pair_bridge_adapter(
            args=args,
            config=replace(config, home=config.home / "bridges" / adapter_kind),
            api_url=api_url,
            cwd=cwd,
            adapter_kind=adapter_kind,
            explicit=False,
        )
        for adapter_kind in BRIDGE_AUTO_PAIR_ADAPTERS
    ]
    return 0 if "paired" in results else 1


def _pair_bridge_adapter(
    *,
    args: argparse.Namespace,
    config: Any,
    api_url: str,
    cwd: Path,
    adapter_kind: str,
    explicit: bool,
) -> str:
    permission_bridge = _permission_bridge_for_adapter(adapter_kind, args.permission_bridge)
    unavailable = _bridge_pair_unavailable_reason(
        adapter_kind,
        permission_bridge=permission_bridge,
    )
    if unavailable:
        _print_bridge_pair_status(
            status_value="failed" if explicit else "skipped",
            adapter_kind=adapter_kind,
            permission_bridge=permission_bridge,
            error=unavailable,
            stderr=explicit,
        )
        return "failed" if explicit else "skipped"

    client = HarnessApiClient(api_url, config.token)
    display_name = args.display_name or _bridge_pair_display_name(adapter_kind)
    workspace_identity_hash = (
        _workspace_identity_hash(cwd, adapter_kind=adapter_kind)
        if adapter_kind in {"codex", "claude_code"}
        else ""
    )
    try:
        registered = client.register_local_agent_connection(
            pair_token=args.pair_token,
            pair_code=args.pair_code,
            adapter_kind=adapter_kind,
            display_name=display_name,
            workspace_root=str(cwd),
            capabilities=_bridge_capabilities(
                adapter_kind,
                permission_bridge=permission_bridge,
            ),
            risk_capabilities=_bridge_risk_capabilities(
                adapter_kind,
                permission_bridge=permission_bridge,
            ),
            bridge_version=_bridge_version(),
            metadata={
                "workspace_identity_hash": workspace_identity_hash,
                "workspace_root_ref": BRIDGE_WORKSPACE_ROOT_REF,
            }
            if adapter_kind in {"codex", "claude_code"}
            else {},
        )
    except Exception as exc:
        _print_bridge_pair_status(
            status_value="failed",
            adapter_kind=adapter_kind,
            permission_bridge=permission_bridge,
            error=str(exc),
            stderr=True,
        )
        return "failed"

    connection = registered["connection"]
    state = {
        "api_url": api_url,
        "connection_id": connection["id"],
        "device_token": registered["device_token"],
        "adapter_kind": adapter_kind,
        "display_name": display_name,
        "permission_bridge": permission_bridge,
    }
    if adapter_kind in {"codex", "claude_code"}:
        state["workspace_root_ref"] = _save_bridge_workspace_root(config, cwd)
        state["workspace_identity_hash"] = workspace_identity_hash
    else:
        state["cwd"] = str(cwd)
    _save_bridge_state(config, state)
    _print_bridge_pair_status(
        status_value="paired",
        adapter_kind=adapter_kind,
        permission_bridge=permission_bridge,
        connection_id=connection["id"],
        state_path=str(_bridge_state_path(config)),
    )
    if args.daemon:
        _spawn_bridge_daemon(config=config, args=args, state=state)
    elif args.once:
        _run_bridge_loop_from_state(
            config=config,
            state=state,
            once=True,
            interval=args.interval,
        )
    return "paired"


def _bridge_pair_unavailable_reason(
    adapter_kind: str,
    *,
    permission_bridge: str,
) -> str:
    if adapter_kind == "codex":
        probe = _probe_codex_cli()
        return "" if probe.installed else probe.error_message or "codex unavailable"
    if adapter_kind == "claude_code":
        probe = _probe_claude_code_cli()
        if not probe.installed:
            return probe.error_message or "claude unavailable"
        if permission_bridge == CLAUDE_PERMISSION_BRIDGE_MODE_SDK:
            sdk_probe = _probe_claude_agent_sdk()
            if not sdk_probe.installed:
                return sdk_probe.error_message or "claude_agent_sdk unavailable"
    return ""


def _bridge_pair_display_name(adapter_kind: str) -> str:
    return {
        "hao": "hao Local Agent",
        "codex": "Codex CLI",
        "claude_code": "Claude Code",
        "fake": "Fake Local Agent",
    }.get(adapter_kind, adapter_kind)


def _print_bridge_pair_status(
    *,
    status_value: str,
    adapter_kind: str,
    permission_bridge: str,
    connection_id: str | None = None,
    state_path: str | None = None,
    error: str | None = None,
    stderr: bool = False,
) -> None:
    payload = {
        "status": status_value,
        "adapter_kind": adapter_kind,
        "permission_bridge": permission_bridge,
    }
    if connection_id:
        payload["connection_id"] = connection_id
    if state_path:
        payload["state_path"] = state_path
    if error:
        payload["error"] = error
    if status_value == "paired":
        payload["next_step"] = "return_to_platform_refresh_discovery"
        payload["message"] = (
            "已发现本地 Agent，请返回 Harness 平台点击“我已执行，刷新识别”，"
            "勾选确认后才会接入。"
        )
    print(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        file=sys.stderr if stderr else sys.stdout,
    )


def _spawn_bridge_daemon(
    *,
    config: Any,
    args: argparse.Namespace,
    state: dict[str, Any],
) -> int:
    command = [
        sys.executable,
        "-m",
        "app.cli.hao.main",
        "bridge",
        "run",
        "--api",
        str(state["api_url"]),
        "--connection-id",
        str(state["connection_id"]),
        "--adapter",
        str(state["adapter_kind"]),
        "--interval",
        str(args.interval),
    ]
    permission_bridge = str(state.get("permission_bridge") or CLAUDE_PERMISSION_BRIDGE_MODE_NONE)
    if (
        state.get("adapter_kind") == "claude_code"
        and permission_bridge != CLAUDE_PERMISSION_BRIDGE_MODE_NONE
    ):
        command.extend(["--permission-bridge", permission_bridge])
    if state.get("adapter_kind") not in {"codex", "claude_code"}:
        command.extend(["--cwd", str(state["cwd"])])
    popen_kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "start_new_session": True,
        "env": {**os.environ, "HAO_HOME": str(config.home)},
    }
    if state.get("adapter_kind") in {"codex", "claude_code"}:
        popen_kwargs["cwd"] = str(Path(__file__).resolve().parents[3])
    subprocess.Popen(  # noqa: S603
        command,
        **popen_kwargs,
    )
    print(
        json.dumps(
            {
                "status": "daemon_started",
                "connection_id": state["connection_id"],
                "adapter_kind": state["adapter_kind"],
                "next_step": "return_to_platform_refresh_discovery",
                "message": "后台 bridge 已启动，请返回到 Harness 平台上点击“我已执行，刷新识别”。",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _run_bridge(args: argparse.Namespace) -> int:
    config = load_config()
    state = _load_bridge_state(config)
    saved_adapter_kind = str(state.get("adapter_kind") or "")
    if args.api_url:
        state["api_url"] = args.api_url
    if args.connection_id:
        state["connection_id"] = args.connection_id
    if args.device_token:
        state["device_token"] = args.device_token
    if args.adapter_kind and saved_adapter_kind and args.adapter_kind != saved_adapter_kind:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": "bridge adapter does not match paired adapter identity",
                    "state_path": str(_bridge_state_path(config)),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    state["adapter_kind"] = args.adapter_kind or saved_adapter_kind or "hao"
    saved_permission_bridge = str(state.get("permission_bridge") or "")
    requested_permission_bridge = (
        _permission_bridge_for_adapter(str(state["adapter_kind"]), args.permission_bridge)
        if args.permission_bridge is not None
        else saved_permission_bridge or CLAUDE_PERMISSION_BRIDGE_MODE_NONE
    )
    if (
        args.permission_bridge is not None
        and saved_permission_bridge
        and requested_permission_bridge != saved_permission_bridge
    ):
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": "bridge permission mode does not match paired adapter identity",
                    "state_path": str(_bridge_state_path(config)),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    state["permission_bridge"] = _permission_bridge_for_adapter(
        str(state["adapter_kind"]),
        requested_permission_bridge,
    )
    if state["adapter_kind"] in {"codex", "claude_code"}:
        if args.cwd:
            cwd = Path(args.cwd).expanduser().resolve()
            workspace_identity_hash = _workspace_identity_hash(
                cwd,
                adapter_kind=str(state["adapter_kind"]),
            )
            existing_workspace_hash = str(state.get("workspace_identity_hash") or "")
            if existing_workspace_hash and existing_workspace_hash != workspace_identity_hash:
                print(
                    json.dumps(
                        {
                            "status": "failed",
                            "error": (
                                f"{state['adapter_kind']} cwd does not match "
                                "paired workspace identity"
                            ),
                            "state_path": str(_bridge_state_path(config)),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    file=sys.stderr,
                )
                return 1
            state["workspace_root_ref"] = _save_bridge_workspace_root(config, cwd)
            state["workspace_identity_hash"] = workspace_identity_hash
    else:
        state["cwd"] = str(Path(args.cwd or state.get("cwd") or ".").expanduser().resolve())
    missing = [key for key in ("api_url", "connection_id", "device_token") if not state.get(key)]
    if missing:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": f"missing bridge state: {', '.join(missing)}",
                    "state_path": str(_bridge_state_path(config)),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    return _run_bridge_loop_from_state(
        config=config,
        state=state,
        once=args.once,
        interval=args.interval,
    )


def _run_bridge_loop_from_state(
    *,
    config: Any,
    state: dict[str, Any],
    once: bool,
    interval: float,
) -> int:
    client = HarnessApiClient(str(state["api_url"]), config.token, timeout=30.0)
    adapter_kind = str(state.get("adapter_kind") or "hao")
    device_token = str(state["device_token"])
    connection_id = str(state["connection_id"])
    permission_bridge = _permission_bridge_for_adapter(
        adapter_kind,
        str(state.get("permission_bridge") or CLAUDE_PERMISSION_BRIDGE_MODE_NONE),
    )
    capabilities = _bridge_capabilities(adapter_kind, permission_bridge=permission_bridge)
    while True:
        heartbeat = client.heartbeat_local_agent_connection(
            connection_id=connection_id,
            device_token=device_token,
            status="online",
            bridge_version=_bridge_version(),
            capabilities=capabilities,
        )
        connection = heartbeat.get("connection") if isinstance(heartbeat, dict) else {}
        if isinstance(connection, dict) and connection.get("onboarding_confirmed") is False:
            if once:
                return 0
            time.sleep(max(0.5, interval))
            continue
        _resume_bridge_pending_tools(
            config=config,
            state=state,
            client=client,
            device_token=device_token,
        )
        try:
            page = client.pull_local_agent_bridge_tasks(device_token=device_token)
        except httpx.HTTPStatusError as exc:
            if _bridge_error_is_unconfirmed(exc):
                if once:
                    return 0
                time.sleep(max(0.5, interval))
                continue
            raise
        for task in page.get("items", []):
            _handle_bridge_task(
                config=config,
                state=state,
                client=client,
                device_token=device_token,
                adapter_kind=adapter_kind,
                task=task,
            )
        if once:
            return 0
        time.sleep(max(0.5, interval))


def _bridge_error_is_unconfirmed(exc: httpx.HTTPStatusError) -> bool:
    if exc.response.status_code not in {403, 409}:
        return False
    try:
        payload = exc.response.json()
    except ValueError:
        payload = {}
    detail = payload.get("detail") if isinstance(payload, dict) else ""
    return BRIDGE_UNCONFIRMED_STATUS_PHRASE in str(detail)


def _handle_bridge_task(
    *,
    config: Any,
    state: dict[str, Any],
    client: HarnessApiClient,
    device_token: str,
    adapter_kind: str,
    task: dict[str, Any],
) -> None:
    task_id = str(task["id"])
    client.ack_local_agent_bridge_task(
        bridge_task_id=task_id,
        device_token=device_token,
        status="running",
    )
    if adapter_kind == "fake":
        content = str(task.get("payload", {}).get("message") or "")
        reply = f"fake bridge received: {content}".strip()
        client.report_local_agent_bridge_event(
            device_token=device_token,
            payload={
                "event_id": f"{task_id}:delta:1",
                "bridge_task_id": task_id,
                "event_type": "assistant_delta",
                "content": reply,
                "sequence": 1,
            },
        )
        client.report_local_agent_bridge_event(
            device_token=device_token,
            payload={
                "event_id": f"{task_id}:done",
                "bridge_task_id": task_id,
                "event_type": "assistant_done",
                "content": reply,
                "sequence": 2,
            },
        )
        return
    if adapter_kind == "codex":
        _handle_codex_bridge_task(
            config=config,
            state=state,
            client=client,
            device_token=device_token,
            task=task,
        )
        return
    if adapter_kind == "claude_code":
        _handle_claude_code_bridge_task(
            config=config,
            state=state,
            client=client,
            device_token=device_token,
            task=task,
        )
        return
    _handle_hao_bridge_task(
        config=config,
        state=state,
        client=client,
        device_token=device_token,
        task=task,
    )


def _handle_codex_bridge_task(
    *,
    config: Any,
    state: dict[str, Any],
    client: HarnessApiClient,
    device_token: str,
    task: dict[str, Any],
) -> None:
    task_id = str(task["id"])
    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    client.report_local_agent_bridge_event(
        device_token=device_token,
        payload={
            "event_id": f"{task_id}:codex:started",
            "bridge_task_id": task_id,
            "event_type": "adapter_started",
            "sequence": 1,
            "metadata": {
                "adapter_kind": "codex",
                "command_mode": "exec_json_harness_tool_bridge",
                "supports_resume": False,
                "resume_mode": "context_replay_new_session",
                "workspace_identity_hash": state.get("workspace_identity_hash"),
            },
        },
    )
    next_sequence = 2
    streamed_delta_count = 0

    def report_delta(delta: str) -> None:
        nonlocal next_sequence, streamed_delta_count
        if delta == "":
            return
        client.report_local_agent_bridge_event(
            device_token=device_token,
            payload={
                "event_id": f"{task_id}:codex:delta:{next_sequence}",
                "bridge_task_id": task_id,
                "event_type": "assistant_delta",
                "content": delta,
                "sequence": next_sequence,
                "metadata": {"adapter_kind": "codex", "streaming_via": "subprocess_stdout"},
            },
        )
        next_sequence += 1
        streamed_delta_count += 1

    result = _run_codex_cli(config=config, state=state, payload=payload, on_delta=report_delta)
    if result.status != "completed":
        client.report_local_agent_bridge_event(
            device_token=device_token,
            payload={
                "event_id": f"{task_id}:codex:error",
                "bridge_task_id": task_id,
                "event_type": "assistant_error",
                "error_message": result.error_message or "codex adapter failed",
                "sequence": next_sequence,
                "metadata": {
                    "adapter_kind": "codex",
                    **_safe_codex_metadata(result.metadata or {}),
                },
            },
        )
        return
    content = result.content.strip()
    if streamed_delta_count == 0:
        report_delta(content)
    client.report_local_agent_bridge_event(
        device_token=device_token,
        payload={
            "event_id": f"{task_id}:codex:done",
            "bridge_task_id": task_id,
            "event_type": "assistant_done",
            "content": content,
            "sequence": next_sequence,
            "metadata": {
                "adapter_kind": "codex",
                "adapter_session_id": result.session_id,
                "resume_mode": "context_replay_new_session",
                **_safe_codex_metadata(result.metadata or {}),
            },
        },
    )


def _handle_claude_code_bridge_task(
    *,
    config: Any,
    state: dict[str, Any],
    client: HarnessApiClient,
    device_token: str,
    task: dict[str, Any],
) -> None:
    task_id = str(task["id"])
    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    next_sequence = 2
    streamed_delta_count = 0
    permission_bridge = _permission_bridge_for_adapter(
        "claude_code",
        str(state.get("permission_bridge") or CLAUDE_PERMISSION_BRIDGE_MODE_NONE),
    )
    command_mode = (
        "agent_sdk_intent_capture_harness_executor"
        if permission_bridge == CLAUDE_PERMISSION_BRIDGE_MODE_SDK
        else "headless_harness_tool_bridge"
    )
    client.report_local_agent_bridge_event(
        device_token=device_token,
        payload={
            "event_id": f"{task_id}:claude_code:started",
            "bridge_task_id": task_id,
            "event_type": "adapter_started",
            "sequence": 1,
            "metadata": {
                "adapter_kind": "claude_code",
                "command_mode": command_mode,
                "permission_bridge": permission_bridge,
                "supports_resume": False,
                "resume_mode": "context_replay_new_session",
                "workspace_identity_hash": state.get("workspace_identity_hash"),
            },
        },
    )
    result: ClaudeCodeRunResult | ClaudePermissionBridgeResult
    if permission_bridge == CLAUDE_PERMISSION_BRIDGE_MODE_SDK:
        result = _run_claude_permission_bridge_sdk(
            client=client,
            device_token=device_token,
            bridge_task_id=task_id,
            config=config,
            state=state,
            payload=payload,
        )
    else:
        def report_delta(delta: str) -> None:
            nonlocal next_sequence, streamed_delta_count
            if delta == "":
                return
            client.report_local_agent_bridge_event(
                device_token=device_token,
                payload={
                    "event_id": f"{task_id}:claude_code:delta:{next_sequence}",
                    "bridge_task_id": task_id,
                    "event_type": "assistant_delta",
                    "content": delta,
                    "sequence": next_sequence,
                    "metadata": {
                        "adapter_kind": "claude_code",
                        "streaming_via": "subprocess_stdout",
                    },
                },
            )
            next_sequence += 1
            streamed_delta_count += 1

        result = _run_claude_code_cli(
            config=config,
            state=state,
            payload=payload,
            on_delta=report_delta,
        )
    if result.status != "completed":
        client.report_local_agent_bridge_event(
            device_token=device_token,
            payload={
                "event_id": f"{task_id}:claude_code:error",
                "bridge_task_id": task_id,
                "event_type": "assistant_error",
                "error_message": result.error_message or "claude code adapter failed",
                "sequence": next_sequence,
                "metadata": {
                    "adapter_kind": "claude_code",
                    "permission_bridge": permission_bridge,
                    **_safe_claude_metadata(result.metadata or {}),
                },
            },
        )
        return
    content = result.content.strip()
    if streamed_delta_count == 0:
        client.report_local_agent_bridge_event(
            device_token=device_token,
            payload={
                "event_id": f"{task_id}:claude_code:delta:{next_sequence}",
                "bridge_task_id": task_id,
                "event_type": "assistant_delta",
                "content": content,
                "sequence": next_sequence,
                "metadata": {"adapter_kind": "claude_code"},
            },
        )
        next_sequence += 1
    client.report_local_agent_bridge_event(
        device_token=device_token,
        payload={
            "event_id": f"{task_id}:claude_code:done",
            "bridge_task_id": task_id,
            "event_type": "assistant_done",
            "content": content,
            "sequence": next_sequence,
            "metadata": {
                "adapter_kind": "claude_code",
                "permission_bridge": permission_bridge,
                "adapter_session_id": result.session_id,
                "resume_mode": "context_replay_new_session",
                **_safe_claude_metadata(result.metadata or {}),
            },
        },
    )


def _handle_hao_bridge_task(
    *,
    config: Any,
    state: dict[str, Any],
    client: HarnessApiClient,
    device_token: str,
    task: dict[str, Any],
) -> None:
    task_id = str(task["id"])
    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    prompt = _hao_prompt_for_task(payload)
    run_id = str(payload.get("run_id") or "")
    agent_id = str(payload.get("agent_id") or "default")
    adapter_session_id = payload.get("adapter_session_id")
    workspace_request = payload.get("workspace_request")
    workspace_mode = (
        str(workspace_request.get("mode") or "")
        if isinstance(workspace_request, dict)
        else ""
    )
    command = "plan" if workspace_mode in {"markdown_plan", "plan"} else "act"
    cwd = Path(str(state.get("cwd") or payload.get("workspace_root") or ".")).expanduser().resolve()
    store = SessionStore(config.session_db_path, config.sessions_dir)
    local_session = (
        store.get_session(str(adapter_session_id))
        if isinstance(adapter_session_id, str) and adapter_session_id.strip()
        else None
    )
    if local_session is None:
        local_session = store.create_session(
            cwd=str(cwd),
            agent_id=agent_id,
            mode="confirm",
            cli_mode=command,
            target="host",
        )
    if run_id:
        store.update_run_id(local_session.id, run_id)
    try:
        model_provider = str(payload.get("model_provider") or "default")
        model_name = str(payload.get("model_name") or "default")
        stream_token = str(payload.get("harness_stream_token") or "").strip()
        stream_client = (
            HarnessApiClient(
                str(state.get("api_url") or client.api_url),
                stream_token,
                timeout=30.0,
            )
            if stream_token
            else client
        )
        result = run_headless_once(
            command=command,
            prompt=prompt,
            cwd=cwd,
            session_store=store,
            session_id=local_session.id,
            permission_mode="confirm",
            target="host",
            max_auto_turns=3,
            api_client=stream_client,
            agent_id=agent_id,
            model_provider=model_provider,
            model_name=model_name,
            bridge_context=BridgeToolContext(
                bridge_task_id=task_id,
                device_token=device_token,
                harness_stream_token=stream_token,
            ),
        )
    except Exception as exc:
        client.report_local_agent_bridge_event(
            device_token=device_token,
            payload={
                "event_id": f"{task_id}:error:{uuid.uuid4().hex}",
                "bridge_task_id": task_id,
                "event_type": "assistant_error",
                "error_message": str(exc),
                "sequence": 1,
            },
        )
        return
    if result.exit_code != 0:
        if _finalize_pending_bridge_result(config=config, state=state, result=result):
            return
        client.report_local_agent_bridge_event(
            device_token=device_token,
            payload={
                "event_id": f"{task_id}:error:{uuid.uuid4().hex}",
                "bridge_task_id": task_id,
                "event_type": "assistant_error",
                "error_message": result.stderr or result.status,
                "sequence": 1,
            },
        )
        return
    assistant = str(result.stdout_json.get("assistant") or "").strip()
    _report_bridge_assistant_done(
        client=client,
        device_token=device_token,
        bridge_task_id=task_id,
        local_session_id=local_session.id,
        content=assistant or "hao completed without assistant text.",
        status=result.status,
        sequence=_bridge_done_sequence(result.stdout_json),
        model_call_id=(
            str(result.stdout_json.get("model_call_id"))
            if result.stdout_json.get("model_call_id")
            else None
        ),
        usage=(
            result.stdout_json.get("usage")
            if isinstance(result.stdout_json.get("usage"), dict)
            else None
        ),
    )


def _finalize_pending_bridge_result(
    *,
    config: Any,
    state: dict[str, Any],
    result: HeadlessRunResult,
) -> bool:
    pending_tool = result.stdout_json.get("pending_tool")
    if not isinstance(pending_tool, dict):
        return False
    _upsert_bridge_pending_tool(config=config, state=state, pending=pending_tool)
    return True


def _report_bridge_assistant_delta(
    *,
    client: Any,
    bridge_context: BridgeToolContext,
    content: str,
    sequence: int,
) -> None:
    client.report_local_agent_bridge_event(
        device_token=bridge_context.device_token,
        payload={
            "event_id": f"{bridge_context.bridge_task_id}:delta:{sequence}",
            "bridge_task_id": bridge_context.bridge_task_id,
            "event_type": "assistant_delta",
            "content": content,
            "sequence": sequence,
        },
    )


def _safe_bridge_delta_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _bridge_done_sequence(stdout_json: dict[str, Any]) -> int:
    delta_count = _safe_bridge_delta_count(stdout_json.get("bridge_delta_count"))
    return max(1, delta_count + 1)


def _report_bridge_assistant_done(
    *,
    client: HarnessApiClient,
    device_token: str,
    bridge_task_id: str,
    local_session_id: str,
    content: str,
    status: str,
    sequence: int = 1,
    model_call_id: str | None = None,
    usage: dict[str, Any] | None = None,
) -> None:
    metadata: dict[str, Any] = {
        "local_session_id": local_session_id,
        "headless_status": status,
    }
    if model_call_id:
        metadata["model_call_id"] = model_call_id
    if usage:
        metadata["usage"] = usage
    client.report_local_agent_bridge_event(
        device_token=device_token,
        payload={
            "event_id": f"{bridge_task_id}:done:{uuid.uuid4().hex}",
            "bridge_task_id": bridge_task_id,
            "event_type": "assistant_done",
            "content": content,
            "sequence": sequence,
            "metadata": metadata,
        },
    )


def _resume_bridge_pending_tools(
    *,
    config: Any,
    state: dict[str, Any],
    client: HarnessApiClient,
    device_token: str,
) -> None:
    _sync_bridge_pending_tools_from_api(
        config=config,
        state=state,
        client=client,
        device_token=device_token,
    )
    for pending in list(_bridge_pending_tools(state)):
        tool_request_id = str(pending.get("tool_request_id") or "")
        bridge_task_id = str(pending.get("bridge_task_id") or "")
        if not tool_request_id or not bridge_task_id:
            continue
        decision = client.get_local_agent_tool_decision(
            device_token=device_token,
            tool_request_id=tool_request_id,
        )
        if decision.get("decision") == "approval_required":
            continue
        if not decision.get("executable"):
            _remove_bridge_pending_tool(
                config=config,
                state=state,
                tool_request_id=tool_request_id,
            )
            client.report_local_agent_bridge_event(
                device_token=device_token,
                payload={
                    "event_id": f"{bridge_task_id}:error:{tool_request_id}:{uuid.uuid4().hex}",
                    "bridge_task_id": bridge_task_id,
                    "event_type": "assistant_error",
                    "error_message": decision.get("reason") or decision.get("decision") or "denied",
                    "sequence": 1,
                },
            )
            continue
        store = SessionStore(config.session_db_path, config.sessions_dir)
        session_id = str(pending.get("local_session_id") or "")
        local_session = store.get_session(session_id) if session_id else None
        if local_session is None:
            _remove_bridge_pending_tool(
                config=config,
                state=state,
                tool_request_id=tool_request_id,
            )
            client.report_local_agent_bridge_event(
                device_token=device_token,
                payload={
                    "event_id": f"{bridge_task_id}:error:{tool_request_id}:{uuid.uuid4().hex}",
                    "bridge_task_id": bridge_task_id,
                    "event_type": "assistant_error",
                    "error_message": f"local session not found for pending tool: {session_id}",
                    "sequence": 1,
                },
            )
            continue
        cwd = Path(str(pending.get("cwd") or local_session.cwd)).expanduser().resolve()
        executed = _execute_approved_bridge_pending_tool(
            pending=pending,
            decision=decision,
            client=client,
            device_token=device_token,
            store=store,
            local_session_id=local_session.id,
            cwd=cwd,
        )
        if executed.status != "executed":
            _remove_bridge_pending_tool(
                config=config,
                state=state,
                tool_request_id=tool_request_id,
            )
            client.report_local_agent_bridge_event(
                device_token=device_token,
                payload={
                    "event_id": f"{bridge_task_id}:error:{tool_request_id}:{uuid.uuid4().hex}",
                    "bridge_task_id": bridge_task_id,
                    "event_type": "assistant_error",
                    "error_message": executed.error_message or executed.status,
                    "sequence": 1,
                },
            )
            continue
        if executed.result is not None:
            _record_headless_tool_result(
                store=store,
                session_id=local_session.id,
                result=executed.result,
                run_id=str(pending.get("run_id") or local_session.run_id or ""),
                tool_call_id=str(pending.get("tool_call_id") or ""),
                api_client=client,
                risk_level=str(pending.get("risk_level") or "high"),
                command=str(pending.get("command") or "act"),
                cwd=cwd,
                target="host",
                permission_mode=str(pending.get("permission_mode") or "confirm"),
                backend_tool_call_id=executed.backend_tool_call_id,
                audit_host=False,
            )
        _remove_bridge_pending_tool(
            config=config,
            state=state,
            tool_request_id=tool_request_id,
        )
        followup_client = _bridge_stream_client_for_pending(
            client=client,
            state=state,
            pending=pending,
        )
        followup = run_headless_once(
            command=str(pending.get("command") or "act"),
            prompt="Continue using the approved local tool result.",
            cwd=cwd,
            session_store=store,
            session_id=local_session.id,
            permission_mode=str(pending.get("permission_mode") or "confirm"),
            target="host",
            max_auto_turns=3,
            api_client=followup_client,
            agent_id=str(pending.get("agent_id") or local_session.agent_id),
            model_provider=str(pending.get("model_provider") or "default"),
            model_name=str(pending.get("model_name") or "default"),
            bridge_context=BridgeToolContext(
                bridge_task_id=bridge_task_id,
                device_token=device_token,
                harness_stream_token=str(pending.get("harness_stream_token") or ""),
            ),
            bridge_delta_start=_safe_bridge_delta_count(pending.get("bridge_delta_count")),
        )
        if _finalize_pending_bridge_result(config=config, state=state, result=followup):
            continue
        if followup.exit_code != 0:
            client.report_local_agent_bridge_event(
                device_token=device_token,
                payload={
                    "event_id": f"{bridge_task_id}:error:{uuid.uuid4().hex}",
                    "bridge_task_id": bridge_task_id,
                    "event_type": "assistant_error",
                    "error_message": followup.stderr or followup.status,
                    "sequence": 1,
                },
            )
            continue
        assistant = str(followup.stdout_json.get("assistant") or "").strip()
        _report_bridge_assistant_done(
            client=client,
            device_token=device_token,
            bridge_task_id=bridge_task_id,
            local_session_id=local_session.id,
            content=assistant or "hao completed without assistant text.",
            status=followup.status,
            sequence=_bridge_done_sequence(followup.stdout_json),
            model_call_id=(
                str(followup.stdout_json.get("model_call_id"))
                if followup.stdout_json.get("model_call_id")
                else None
            ),
            usage=(
                followup.stdout_json.get("usage")
                if isinstance(followup.stdout_json.get("usage"), dict)
                else None
            ),
        )


def _bridge_stream_client_for_pending(
    *,
    client: HarnessApiClient,
    state: dict[str, Any],
    pending: dict[str, Any],
) -> HarnessApiClient:
    stream_token = str(pending.get("harness_stream_token") or "").strip()
    if not stream_token:
        return client
    api_url = str(state.get("api_url") or getattr(client, "api_url", "") or "").strip()
    if not api_url:
        return client
    return HarnessApiClient(api_url, stream_token, timeout=30.0)


def _handle_bridge_host_tool_request(
    *,
    client: HarnessApiClient,
    bridge_context: BridgeToolContext,
    store: SessionStore,
    session_id: str,
    run_id: str | None,
    agent_id: str,
    command: str,
    cwd: Path,
    tool_name: str,
    tool_call_id: str | None,
    input_json: dict[str, Any],
    risk_level: str,
    permission_mode: str,
    model_provider: str = "default",
    model_name: str = "default",
    bridge_delta_count: int = 0,
    tool_request_id_override: str | None = None,
) -> BridgeToolHandlingResult:
    tool_request_id = tool_request_id_override or _bridge_tool_request_id(
        bridge_task_id=bridge_context.bridge_task_id,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
    )
    preview_result: ToolExecutionResult | None = None
    pending_change_preview: dict[str, Any] | None = None
    target_paths = _tool_target_paths(tool_name, input_json, None)
    if tool_name in {"write_file", "apply_patch"}:
        preview_result = execute_local_tool(
            tool_name,
            input_json,
            cwd,
            session_store=store,
            session_id=session_id,
            pending_change_metadata={
                "source": "local_agent_bridge",
                "bridge_task_id": bridge_context.bridge_task_id,
                "tool_request_id": tool_request_id,
                "run_id": run_id,
                "permission_mode": permission_mode,
            },
        )
        if preview_result.status != "SUCCESS":
            return BridgeToolHandlingResult(
                status="failed",
                result=preview_result,
                error_message=preview_result.error_message or "pending change preview failed",
            )
        target_paths = _tool_target_paths(
            tool_name,
            input_json,
            preview_result.output_json,
        )
        diff = str(preview_result.output_json.get("diff") or "")
        pending_change_preview = {
            "change_id": preview_result.output_json.get("change_id"),
            "operation": tool_name,
            "target_paths": target_paths,
            "diff_sha256": _sha256_text(diff),
            "preview_bytes": len(diff.encode("utf-8", errors="replace")),
        }
    decision = client.create_local_agent_tool_request(
        device_token=bridge_context.device_token,
        payload={
            "tool_request_id": tool_request_id,
            "bridge_task_id": bridge_context.bridge_task_id,
            "tool_name": tool_name,
            "input_json": input_json,
            "execution_target": "host",
            "risk_level": risk_level,
            "permission_mode": permission_mode,
            "cwd": str(cwd),
            "target_paths": target_paths,
            "requires_network": _requires_network(tool_name, input_json),
            "requires_secret_read": _requires_secret_read(tool_name, input_json),
            "pending_change_preview": pending_change_preview,
            "metadata": {
                "run_id": run_id,
                "agent_id": agent_id,
                "model_provider": model_provider,
                "model_name": model_name,
                "bridge_delta_count": bridge_delta_count,
                "local_session_id": session_id,
                "tool_call_id": tool_call_id,
                "command": command,
                "cwd": str(cwd),
                "risk_level": risk_level,
                "permission_mode": permission_mode,
            },
        },
    )
    decision_json = decision.get("decision_json") if isinstance(decision, dict) else {}
    decision_metadata = (
        decision_json.get("metadata")
        if isinstance(decision_json, dict) and isinstance(decision_json.get("metadata"), dict)
        else {}
    )
    if decision.get("decision") == "approval_required":
        return BridgeToolHandlingResult(
            status="pending_approval",
            backend_tool_call_id=str(decision.get("tool_call_id") or ""),
            pending_tool=_safe_bridge_pending_tool_state(
                {
                    "tool_request_id": tool_request_id,
                    "bridge_task_id": bridge_context.bridge_task_id,
                    "tool_call_id": tool_call_id,
                    "backend_tool_call_id": decision.get("tool_call_id"),
                    "approval_id": decision.get("approval_id"),
                    "tool_name": tool_name,
                    "local_session_id": session_id,
                    "run_id": run_id,
                    "agent_id": agent_id,
                    "model_provider": model_provider,
                    "model_name": model_name,
                    "harness_stream_token": decision_metadata.get("harness_stream_token")
                    or bridge_context.harness_stream_token,
                    "bridge_delta_count": decision_metadata.get("bridge_delta_count")
                    or bridge_delta_count,
                    "command": command,
                    "risk_level": risk_level,
                    "permission_mode": permission_mode,
                    "change_id": pending_change_preview.get("change_id")
                    if pending_change_preview
                    else None,
                    "diff_sha256": pending_change_preview.get("diff_sha256")
                    if pending_change_preview
                    else None,
                }
            ),
        )
    if not decision.get("executable"):
        result = ToolExecutionResult(
            tool_name=tool_name,
            status="DENIED",
            input_json=input_json,
            output_json={
                "denied": True,
                "reason": decision.get("reason") or decision.get("decision") or "denied",
                "tool_request_id": tool_request_id,
            },
            duration_ms=0,
            error_message=str(decision.get("reason") or "denied"),
        )
        return BridgeToolHandlingResult(
            status="denied",
            result=result,
            backend_tool_call_id=str(decision.get("tool_call_id") or ""),
            error_message=result.error_message or "denied",
        )
    pending = {
        "tool_request_id": tool_request_id,
        "bridge_task_id": bridge_context.bridge_task_id,
        "tool_call_id": tool_call_id,
        "backend_tool_call_id": decision.get("tool_call_id"),
        "tool_name": tool_name,
        "input_json": (
            decision.get("input_json")
            if isinstance(decision.get("input_json"), dict)
            else input_json
        ),
        "local_session_id": session_id,
        "run_id": run_id,
        "agent_id": agent_id,
        "command": command,
        "cwd": str(cwd),
        "risk_level": risk_level,
        "permission_mode": permission_mode,
        "change_id": pending_change_preview.get("change_id") if pending_change_preview else None,
        "diff_sha256": (
            pending_change_preview.get("diff_sha256") if pending_change_preview else None
        ),
    }
    return _execute_approved_bridge_pending_tool(
        pending=pending,
        decision=decision,
        client=client,
        device_token=bridge_context.device_token,
        store=store,
        local_session_id=session_id,
        cwd=cwd,
    )


def _execute_approved_bridge_pending_tool(
    *,
    pending: dict[str, Any],
    decision: dict[str, Any],
    client: HarnessApiClient,
    device_token: str,
    store: SessionStore,
    local_session_id: str,
    cwd: Path,
) -> BridgeToolHandlingResult:
    tool_request_id = str(pending["tool_request_id"])
    tool_name = str(pending["tool_name"])
    input_json = (
        decision.get("input_json") if isinstance(decision.get("input_json"), dict) else None
    )
    if input_json is None:
        return BridgeToolHandlingResult(
            status="failed",
            error_message="approved local tool decision is missing executable input",
        )
    permission_mode = str(pending.get("permission_mode") or "confirm")
    local_decision = PermissionEngine(permission_mode).decide(
        tool_name,
        input_json,
        target="host",
    )
    if local_decision.denied:
        result = ToolExecutionResult(
            tool_name=tool_name,
            status="DENIED",
            input_json=input_json,
            output_json={"denied": True, "reason": local_decision.reason},
            duration_ms=0,
            error_message=local_decision.reason,
        )
    else:
        try:
            if tool_name in {"write_file", "apply_patch"}:
                refreshed_pending = _refresh_approved_bridge_pending_change(
                    pending=pending,
                    input_json=input_json,
                    client=client,
                    device_token=device_token,
                    store=store,
                    local_session_id=local_session_id,
                    cwd=cwd,
                )
                pending = refreshed_pending
                change_id = str(refreshed_pending.get("change_id") or "")
                commit_tool = _headless_commit_tool_name(tool_name)
                if not change_id or commit_tool is None:
                    raise ValueError("approved pending change is missing change_id")
                commit_result = execute_local_tool(
                    commit_tool,
                    {"change_id": change_id},
                    cwd,
                    session_store=store,
                    session_id=local_session_id,
                )
                result = ToolExecutionResult(
                    tool_name=tool_name,
                    status=commit_result.status,
                    input_json=input_json,
                    output_json=commit_result.output_json,
                    duration_ms=commit_result.duration_ms,
                    error_message=commit_result.error_message,
                )
            elif tool_name in SHELL_COMMAND_TOOLS:
                reporting_store = BridgeReportingSessionStore(
                    delegate=store,
                    client=client,
                    device_token=device_token,
                    tool_request_id=tool_request_id,
                )
                cancel_check = _bridge_command_cancel_check(
                    client=client,
                    device_token=device_token,
                )
                result = execute_local_tool(
                    tool_name,
                    input_json,
                    cwd,
                    session_store=reporting_store,
                    session_id=local_session_id,
                    cancel_check=cancel_check,
                )
            else:
                result = execute_local_tool(tool_name, input_json, cwd)
        except Exception as exc:
            result = ToolExecutionResult(
                tool_name=tool_name,
                status="FAILED",
                input_json=input_json,
                output_json={"error": str(exc)},
                duration_ms=0,
                error_message=str(exc),
            )
    try:
        response = _report_bridge_tool_result(
            client=client,
            device_token=device_token,
            tool_request_id=tool_request_id,
            result=result,
            pending=pending,
        )
        _ack_bridge_command_cancel_if_needed(
            client=client,
            device_token=device_token,
            result=result,
        )
    except Exception as exc:
        return BridgeToolHandlingResult(
            status="failed",
            result=result,
            error_message=f"local tool result audit failed: {exc}",
        )
    return BridgeToolHandlingResult(
        status="executed",
        result=result,
        backend_tool_call_id=str(
            response.get("tool_call_id") or pending.get("backend_tool_call_id") or ""
        ),
    )


def _report_bridge_tool_result(
    *,
    client: HarnessApiClient,
    device_token: str,
    tool_request_id: str,
    result: ToolExecutionResult,
    pending: dict[str, Any],
) -> dict:
    output = result.output_json if isinstance(result.output_json, dict) else {}
    return client.report_local_agent_tool_result(
        device_token=device_token,
        tool_request_id=tool_request_id,
        payload={
            "event_id": f"{tool_request_id}:result",
            "status": _bridge_tool_result_status(result),
            "output_json": output,
            "duration_ms": result.duration_ms,
            "error_message": result.error_message,
            "command_id": output.get("command_id"),
            "change_id": output.get("change_id") or pending.get("change_id"),
            "diff_sha256": pending.get("diff_sha256"),
            "metadata": {
                "local_session_id": pending.get("local_session_id"),
                "tool_call_id": pending.get("tool_call_id"),
            },
        },
    )


def _build_workflow_metadata(command: str) -> dict[str, Any]:
    return {
        "interaction_mode": command,
        "backend_mode": "markdown_plan" if command == "plan" else "cli_agent",
        "act_intent": {"source": "slash_command", "allow_local_tools": True}
        if command == "act"
        else None,
    }


def _git_output(cwd: Path, args: list[str]) -> str | None:
    if shutil.which("git") is None:
        return None
    try:
        completed = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _git_status_lines(cwd: Path, limit: int = GIT_STATUS_CONTEXT_LIMIT) -> list[str]:
    status = _git_output(cwd, ["status", "--short", "--untracked-files=all"])
    if status is None:
        return []
    return [line.strip() for line in status.splitlines() if line.strip()][:limit]


def _git_context_summary(cwd: Path) -> str:
    status_lines = _git_status_lines(cwd)
    if status_lines == []:
        return "none"
    branch = _git_output(cwd, ["branch", "--show-current"]) or "detached"
    sample = "; ".join(status_lines[:4]) or "clean"
    return f"branch={branch} dirty={len(status_lines)} sample={sample}"


def _recent_test_hint(store: SessionStore, session_id: str) -> str:
    for command in reversed(store.list_commands(session_id)):
        if command["tool_name"] != "run_tests":
            continue
        command_text = str(command["command"]).replace("\n", " ").strip()
        if len(command_text) > 120:
            command_text = command_text[:117] + "..."
        return f"{command['status']} exit={command['exit_code']} {command_text}"
    return "none"


def _local_context_message(
    *,
    store: SessionStore,
    session_id: str,
    cwd: Path,
    permission_mode: str,
    target: str,
    interaction_mode: str,
    max_auto_turns: int,
) -> dict[str, Any]:
    session = store.get_session(session_id)
    if session is None:
        raise ValueError(f"session not found: {session_id}")
    active_path = store.list_active_path(session_id)
    active_leaf = active_path[-1] if active_path else None
    branch_id = None if active_leaf is None else str(active_leaf["branch_id"])
    todos = store.list_todos(session_id, branch_id=branch_id)
    verifications = store.list_verifications(session_id, branch_id=branch_id)
    commands = store.list_commands(session_id)
    last_command = commands[-1] if commands else None
    pending_approval_count = sum(
        1
        for change in store.list_pending_changes(session_id)
        if change["status"] == "pending"
    )
    command_summary = "none"
    if last_command is not None:
        command_summary = (
            f"{last_command['tool_name']} {last_command['status']} "
            f"exit={last_command['exit_code']} {last_command['command']}"
        )
    todo_summary = "; ".join(f"{todo['status']}:{todo['title']}" for todo in todos[-8:])
    verification_summary = "; ".join(
        f"{verification['status']}:{verification['label']}"
        for verification in verifications[-8:]
    )
    active_command_count = sum(
        1 for command in commands if command["status"] in {"pending", "running"}
    )
    content = (
        "hao local context: "
        f"cwd={cwd} target={target} permission={permission_mode} "
        f"workflow={interaction_mode} session={session_id} run={session.run_id} "
        f"branch={branch_id} leaf={None if active_leaf is None else active_leaf['id']} "
        f"approvals={pending_approval_count} commands={active_command_count}/{len(commands)} "
        f"max_auto_turns={max_auto_turns}\n"
        f"todos: {todo_summary or 'none'}\n"
        f"verifications: {verification_summary or 'none'}\n"
        f"repo: {_git_context_summary(cwd)}\n"
        f"recent_diff: {'; '.join(_git_status_lines(cwd, limit=6)) or 'clean'}\n"
        f"recent_test: {_recent_test_hint(store, session_id)}\n"
        f"last_command: {command_summary}"
    )
    return {
        "id": "hao-local-context",
        "parent_id": None,
        "children_ids": [],
        "role": "system",
        "content": content,
        "state": "done",
        "run_id": session.run_id,
        "metadata": {"source": "hao_local_context"},
        "tool_calls": [],
        "artifacts": [],
    }


def _build_stream_payload(
    *,
    store: SessionStore,
    session_id: str,
    goal: str,
    command: str,
    model_provider: str,
    model_name: str,
    cwd: Path,
    permission_mode: str,
    target: str,
    run_id: str | None,
    local_bridge_task_id: str | None,
    max_auto_turns: int,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    workflow_metadata = _build_workflow_metadata(command)
    return {
        "mode": workflow_metadata["backend_mode"],
        "goal": goal,
        "run_id": run_id,
        "local_bridge_task_id": local_bridge_task_id,
        "model_provider": model_provider,
        "model_name": model_name,
        "messages": [
            _local_context_message(
                store=store,
                session_id=session_id,
                cwd=cwd,
                permission_mode=permission_mode,
                target=target,
                interaction_mode=workflow_metadata["interaction_mode"],
                max_auto_turns=max_auto_turns,
            ),
            *messages,
        ],
        "context_window_turns": 24,
        "interaction_mode": workflow_metadata["interaction_mode"],
        "turn_mode": workflow_metadata["interaction_mode"],
        "act_intent": workflow_metadata["act_intent"],
    }


def _headless_commit_tool_name(tool_name: str) -> str | None:
    if tool_name == "write_file":
        return "commit_write_file"
    if tool_name == "apply_patch":
        return "commit_apply_patch"
    return None


def _headless_preview_tool_name(tool_name: str) -> str | None:
    if tool_name == "write_file":
        return "preview_write_file"
    if tool_name == "apply_patch":
        return "preview_apply_patch"
    return None


def _reject_pending_change_safely(
    *,
    store: SessionStore,
    change_id: str,
    reason: str,
) -> None:
    if not change_id:
        return
    try:
        existing = store.get_pending_change(change_id)
        if existing is None or existing.get("status") != "pending":
            return
        store.update_pending_change_status(
            change_id,
            status="rejected",
            error_message=reason,
        )
    except Exception:
        return


def _refresh_approved_bridge_pending_change(
    *,
    pending: dict[str, Any],
    input_json: dict[str, Any],
    client: HarnessApiClient,
    device_token: str,
    store: SessionStore,
    local_session_id: str,
    cwd: Path,
) -> dict[str, Any]:
    tool_name = str(pending["tool_name"])
    preview_tool = _headless_preview_tool_name(tool_name)
    if preview_tool is None:
        return pending
    existing_change_id = str(pending.get("change_id") or "")
    if existing_change_id:
        existing_change = store.get_pending_change(existing_change_id)
        if (
            existing_change is not None
            and existing_change.get("tool_name") == tool_name
            and isinstance(existing_change.get("input_json"), dict)
            and existing_change.get("input_json") == input_json
        ):
            return pending
    refreshed_change_id = ""
    try:
        preview_result = execute_local_tool(
            preview_tool,
            input_json,
            cwd,
            session_store=store,
            session_id=local_session_id,
            pending_change_metadata={
                "source": "local_agent_bridge",
                "bridge_task_id": pending.get("bridge_task_id"),
                "tool_request_id": pending.get("tool_request_id"),
                "run_id": pending.get("run_id"),
                "permission_mode": pending.get("permission_mode"),
                "approved_refresh": True,
            },
        )
        if preview_result.status != "SUCCESS":
            raise ValueError(
                preview_result.error_message or "approved pending change preview failed"
            )
        output_json = (
            preview_result.output_json if isinstance(preview_result.output_json, dict) else {}
        )
        refreshed_change_id = str(output_json.get("change_id") or "").strip()
        if not refreshed_change_id:
            raise ValueError("approved pending change preview is missing change_id")
        target_paths = _tool_target_paths(tool_name, input_json, output_json)
        if not target_paths:
            raise ValueError("approved pending change preview is missing target paths")
        diff = str(output_json.get("diff") or "")
        diff_sha256 = _sha256_text(diff)
        refresh_payload = {
            "input_json": input_json,
            "target_paths": target_paths,
            "pending_change_preview": {
                "change_id": refreshed_change_id,
                "operation": tool_name,
                "target_paths": target_paths,
                "diff": diff,
                "diff_sha256": diff_sha256,
                "preview_bytes": len(diff.encode("utf-8", errors="replace")),
            },
        }
        client.refresh_local_agent_pending_change(
            device_token=device_token,
            tool_request_id=str(pending["tool_request_id"]),
            payload=refresh_payload,
        )
        previous_change_id = existing_change_id
        if previous_change_id and previous_change_id != refreshed_change_id:
            _reject_pending_change_safely(
                store=store,
                change_id=previous_change_id,
                reason="replaced by approved modified input",
            )
        return {
            **pending,
            "change_id": refreshed_change_id,
            "diff_sha256": diff_sha256,
        }
    except Exception:
        if refreshed_change_id:
            _reject_pending_change_safely(
                store=store,
                change_id=refreshed_change_id,
                reason="approved pending change refresh failed",
            )
        raise


def _verification_summary(result: ToolExecutionResult) -> str:
    output = result.output_json
    status = "passed" if result.status == "SUCCESS" else "failed"
    command = str(output.get("command") or result.input_json.get("command") or "run_tests")
    summary = f"{command} -> {status}"
    if output.get("exit_code") is not None:
        summary += f" exit={output['exit_code']}"
    stdout = str(output.get("stdout") or "").strip()
    stderr = str(output.get("stderr") or "").strip()
    if stdout:
        summary += f" stdout={stdout.splitlines()[0][:120]}"
    elif stderr:
        summary += f" stderr={stderr.splitlines()[0][:120]}"
    return summary


def _headless_audit_failure_reason(result: ToolExecutionResult) -> str | None:
    if result.status != "AUDIT_FAILED":
        return None
    return result.error_message or str(result.output_json.get("audit_error") or "audit failed")


def _record_headless_tool_result(
    *,
    store: SessionStore,
    session_id: str,
    result: ToolExecutionResult,
    run_id: str | None,
    tool_call_id: str | None,
    api_client: Any | None,
    risk_level: str,
    command: str,
    cwd: Path,
    target: str,
    permission_mode: str,
    backend_tool_call_id: str | None = None,
    audit_host: bool = True,
) -> tuple[str, ToolExecutionResult]:
    workflow_metadata = _build_workflow_metadata(command)
    backend_id = backend_tool_call_id or tool_call_id
    audit_error: str | None = None
    if audit_host and api_client is not None and run_id:
        try:
            response = api_client.record_local_tool_event(
                run_id,
                {
                    "tool_name": result.tool_name,
                    "input_json": result.input_json,
                    "output_json": result.output_json,
                    "status": result.status,
                    "risk_level": risk_level,
                    "requires_sandbox": False,
                    "duration_ms": result.duration_ms,
                    "error_message": result.error_message,
                    "execution_target": target,
                    "permission_mode": permission_mode,
                    "local_session_id": session_id,
                    "cwd": str(cwd),
                    "interaction_mode": workflow_metadata["interaction_mode"],
                    "act_intent": workflow_metadata["act_intent"],
                },
            )
            tool_call = response.get("tool_call", {}) if isinstance(response, dict) else {}
            if isinstance(tool_call, dict) and tool_call.get("id"):
                backend_id = str(tool_call["id"])
        except Exception as exc:
            audit_error = str(exc)
    stored_result = result
    if audit_error is not None:
        stored_result = ToolExecutionResult(
            tool_name=result.tool_name,
            status="AUDIT_FAILED",
            input_json=result.input_json,
            output_json={
                "audit_failed": True,
                "audit_error": audit_error,
                "original_status": result.status,
                "original_output_json": result.output_json,
            },
            duration_ms=result.duration_ms,
            error_message=audit_error,
        )
    tool_event_id = store.record_tool_event(
        session_id,
        run_id=run_id,
        tool_call_id=backend_id,
        tool_name=stored_result.tool_name,
        status=stored_result.status,
        input_json=stored_result.input_json,
        output_json=stored_result.output_json,
        duration_ms=stored_result.duration_ms,
    )
    output = stored_result.output_json
    command_id = output.get("command_id")
    if command_id:
        try:
            store.link_command_tool_event(str(command_id), tool_event_id)
        except Exception:
            pass
        if stored_result.tool_name == "run_tests":
            active_path = store.list_active_path(session_id)
            active_leaf = active_path[-1] if active_path else None
            status = "passed" if stored_result.status == "SUCCESS" else "failed"
            store.create_verification(
                session_id,
                label=str(output.get("command") or "run_tests"),
                status=status,
                branch_id=None if active_leaf is None else str(active_leaf["branch_id"]),
                leaf_id=None if active_leaf is None else str(active_leaf["id"]),
                command_id=str(command_id),
                tool_event_id=tool_event_id,
                evidence_summary=_verification_summary(stored_result),
                metadata={
                    "tool_name": stored_result.tool_name,
                    "tool_status": stored_result.status,
                },
            )
    change_id = output.get("change_id")
    if change_id:
        try:
            store.link_pending_change_tool_event(str(change_id), tool_event_id)
        except Exception:
            pass
    if audit_error is not None:
        return tool_event_id, stored_result
    message = (
        f"Local tool result {stored_result.tool_name} status={stored_result.status}: "
        f"{json.dumps(stored_result.output_json, ensure_ascii=False)[:4000]}"
    )
    store.append_message(
        session_id,
        role="tool",
        content=message,
        run_id=run_id,
        tool_event_id=tool_event_id,
        metadata={
            "tool_name": stored_result.tool_name,
            "status": stored_result.status,
            "tool_call_id": tool_call_id,
            "execution_target": target,
            "permission_mode": permission_mode,
            **workflow_metadata,
        },
    )
    return tool_event_id, stored_result


def run_headless_once(
    *,
    command: str,
    prompt: str,
    cwd: Path,
    session_store: SessionStore,
    session_id: str | None,
    permission_mode: str,
    target: str,
    max_auto_turns: int,
    fake_events: list[SSEEvent] | None = None,
    api_client: Any | None = None,
    agent_id: str = "default",
    model_provider: str = "default",
    model_name: str = "default",
    bridge_context: BridgeToolContext | None = None,
    bridge_delta_start: int = 0,
) -> HeadlessRunResult:
    session = session_store.get_session(session_id) if session_id else None
    if session_id is not None and session is None:
        raise ValueError(f"session not found: {session_id}")
    if session is None:
        session = session_store.create_session(
            cwd=str(cwd),
            agent_id=agent_id,
            mode=permission_mode,
            cli_mode=command,
            target=target,
        )
        session_id = session.id
    assert session_id is not None
    if not prompt.strip():
        raise ValueError("prompt is required")
    if fake_events is None and api_client is None:
        raise ValueError("api_client is required for live headless runs")
    store = session_store
    store.update_cli_mode(session.id, command)
    store.append_message(
        session.id,
        role="user",
        content=prompt,
        metadata=_build_workflow_metadata(command),
    )
    run_id: str | None = session.run_id
    assistant_outputs: list[str] = []
    tool_summaries: list[dict[str, Any]] = []
    pending_change_id: str | None = None
    pending_tool: dict[str, Any] | None = None
    status = "completed"
    stderr = ""
    depth = 0
    goal = prompt
    bridge_event_sequence = max(0, bridge_delta_start)
    latest_model_call_id: str | None = None
    latest_usage: dict[str, Any] = {}
    while True:
        assistant_chunks: list[str] = []
        executed_results: list[ToolExecutionResult] = []
        if fake_events is None:
            payload = _build_stream_payload(
                store=store,
                session_id=session.id,
                goal=goal,
                command=command,
                model_provider=model_provider,
                model_name=model_name,
                cwd=cwd,
                permission_mode=permission_mode,
                target=target,
                run_id=run_id,
                local_bridge_task_id=(
                    bridge_context.bridge_task_id if bridge_context is not None else None
                ),
                max_auto_turns=max_auto_turns,
                messages=store.list_active_path(session.id),
            )
            events = api_client.stream_chat(session.agent_id, payload)
        else:
            events = fake_events
        for event in events:
            store.record_stream_event(
                session.id,
                event=event.event,
                data=event.data,
                raw=event.raw,
            )
            if event.event == "run_created":
                run_id = str(event.data.get("run_id") or run_id or "")
                if run_id:
                    store.update_run_id(session.id, run_id)
            elif event.event == "delta":
                delta = str(event.data.get("content") or "")
                if not delta:
                    continue
                assistant_chunks.append(delta)
                if bridge_context is not None and api_client is not None:
                    bridge_event_sequence += 1
                    _report_bridge_assistant_delta(
                        client=api_client,
                        bridge_context=bridge_context,
                        content=delta,
                        sequence=bridge_event_sequence,
                    )
            elif event.event == "usage":
                latest_usage = event.data if isinstance(event.data, dict) else {}
                candidate_model_call_id = latest_usage.get("model_call_id")
                if isinstance(candidate_model_call_id, str) and candidate_model_call_id.strip():
                    latest_model_call_id = candidate_model_call_id.strip()
            elif event.event == "tool_call_requested":
                tool_name = str(event.data.get("tool_name") or "")
                input_json = event.data.get("input_json") if isinstance(event.data, dict) else {}
                if not isinstance(input_json, dict):
                    input_json = {}
                if command == "plan":
                    continue
                decision = PermissionEngine(permission_mode).decide(
                    tool_name,
                    input_json,
                    target=target,
                )
                tool_call_id = str(event.data.get("tool_call_id") or tool_name)
                if bridge_context is not None and target == "host":
                    handled = _handle_bridge_host_tool_request(
                        client=api_client,
                        bridge_context=bridge_context,
                        store=store,
                        session_id=session.id,
                        run_id=run_id,
                        agent_id=session.agent_id,
                        model_provider=model_provider,
                        model_name=model_name,
                        command=command,
                        cwd=cwd,
                        tool_name=tool_name,
                        tool_call_id=tool_call_id,
                        input_json=input_json,
                        risk_level=decision.risk_level,
                        permission_mode=permission_mode,
                        bridge_delta_count=bridge_event_sequence,
                    )
                    if handled.status == "pending_approval":
                        status = "pending_approval"
                        pending_tool = handled.pending_tool
                        break
                    if handled.result is not None:
                        tool_event_id, stored_result = _record_headless_tool_result(
                            store=store,
                            session_id=session.id,
                            result=handled.result,
                            run_id=run_id,
                            tool_call_id=tool_call_id,
                            api_client=api_client,
                            risk_level=decision.risk_level,
                            command=command,
                            cwd=cwd,
                            target=target,
                            permission_mode=permission_mode,
                            backend_tool_call_id=handled.backend_tool_call_id,
                            audit_host=False,
                        )
                        tool_summaries.append(
                            {
                                "tool_event_id": tool_event_id,
                                "tool_name": stored_result.tool_name,
                                "status": stored_result.status,
                            }
                        )
                        if handled.status != "executed" or stored_result.status == "DENIED":
                            status = "failed"
                            stderr = (
                                handled.error_message
                                or stored_result.error_message
                                or stored_result.status
                            )
                            break
                        executed_results.append(stored_result)
                        continue
                    status = "failed"
                    stderr = handled.error_message or handled.status
                    break
                if decision.denied:
                    result = ToolExecutionResult(
                        tool_name=tool_name,
                        status="DENIED",
                        input_json=input_json,
                        output_json={"denied": True, "reason": decision.reason},
                        duration_ms=0,
                        error_message=decision.reason,
                    )
                    tool_event_id, stored_result = _record_headless_tool_result(
                        store=store,
                        session_id=session.id,
                        result=result,
                        run_id=run_id,
                        tool_call_id=tool_call_id,
                        api_client=api_client,
                        risk_level=decision.risk_level,
                        command=command,
                        cwd=cwd,
                        target=target,
                        permission_mode=permission_mode,
                    )
                    tool_summaries.append(
                        {
                            "tool_event_id": tool_event_id,
                            "tool_name": stored_result.tool_name,
                            "status": stored_result.status,
                        }
                    )
                    audit_failure = _headless_audit_failure_reason(stored_result)
                    if audit_failure is not None:
                        status = "failed"
                        stderr = audit_failure
                        break
                    status = "failed"
                    stderr = decision.reason
                    break
                if target == "sandbox":
                    if run_id is None or api_client is None:
                        status = "failed"
                        stderr = "sandbox execution requires a live run"
                        break
                    try:
                        sandbox_result = execute_sandbox_tool(
                            api_client,
                            run_id=run_id,
                            tool_name=tool_name,
                            input_json=input_json,
                        )
                    except Exception as exc:
                        status = "failed"
                        stderr = str(exc)
                        break
                    result = ToolExecutionResult(
                        tool_name=tool_name,
                        status=sandbox_result.status,
                        input_json=input_json,
                        output_json=sandbox_result.output_json,
                        duration_ms=sandbox_result.duration_ms,
                        error_message=sandbox_result.error_message,
                    )
                    tool_event_id, stored_result = _record_headless_tool_result(
                        store=store,
                        session_id=session.id,
                        result=result,
                        run_id=run_id,
                        tool_call_id=tool_call_id,
                        api_client=api_client,
                        risk_level=decision.risk_level,
                        command=command,
                        cwd=cwd,
                        target=target,
                        permission_mode=permission_mode,
                        backend_tool_call_id=sandbox_result.tool_call_id,
                        audit_host=False,
                    )
                    tool_summaries.append(
                        {
                            "tool_event_id": tool_event_id,
                            "tool_name": stored_result.tool_name,
                            "status": stored_result.status,
                        }
                    )
                    audit_failure = _headless_audit_failure_reason(stored_result)
                    if audit_failure is not None:
                        status = "failed"
                        stderr = audit_failure
                        break
                    executed_results.append(stored_result)
                    continue
                if target == "host" and tool_name in {"write_file", "apply_patch"}:
                    result = execute_local_tool(
                        tool_name,
                        input_json,
                        cwd,
                        session_store=store,
                        session_id=session.id,
                        pending_change_metadata={
                            "workflow_metadata": _build_workflow_metadata(command),
                            "execution_target": target,
                            "permission_mode": permission_mode,
                            "risk_level": decision.risk_level,
                        },
                    )
                    tool_event_id, stored_result = _record_headless_tool_result(
                        store=store,
                        session_id=session.id,
                        result=result,
                        run_id=run_id,
                        tool_call_id=tool_call_id,
                        api_client=api_client,
                        risk_level=decision.risk_level,
                        command=command,
                        cwd=cwd,
                        target=target,
                        permission_mode=permission_mode,
                    )
                    tool_summaries.append(
                        {
                            "tool_event_id": tool_event_id,
                            "tool_name": stored_result.tool_name,
                            "status": stored_result.status,
                        }
                    )
                    audit_failure = _headless_audit_failure_reason(stored_result)
                    if audit_failure is not None:
                        failed_change_id = result.output_json.get("change_id")
                        if failed_change_id:
                            store.update_pending_change_status(
                                str(failed_change_id),
                                status="failed",
                                error_message=f"audit failed: {audit_failure}",
                                tool_event_id=tool_event_id,
                            )
                        status = "failed"
                        stderr = audit_failure
                        break
                    pending_change_id = str(result.output_json.get("change_id") or "")
                    if stored_result.status != "SUCCESS":
                        status = "failed"
                        stderr = stored_result.error_message or str(
                            stored_result.output_json.get("error") or ""
                        )
                        break
                    if decision.requires_confirmation and pending_change_id:
                        status = "pending_approval"
                        break
                    commit_tool = _headless_commit_tool_name(tool_name)
                    if commit_tool is not None and pending_change_id:
                        commit_result = execute_local_tool(
                            commit_tool,
                            {"change_id": pending_change_id},
                            cwd,
                            session_store=store,
                            session_id=session.id,
                        )
                        commit_event_id, stored_commit = _record_headless_tool_result(
                            store=store,
                            session_id=session.id,
                            result=commit_result,
                            run_id=run_id,
                            tool_call_id=tool_call_id,
                            api_client=api_client,
                            risk_level=decision.risk_level,
                            command=command,
                            cwd=cwd,
                            target=target,
                            permission_mode=permission_mode,
                            audit_host=False,
                        )
                        tool_summaries.append(
                            {
                                "tool_event_id": commit_event_id,
                                "tool_name": stored_commit.tool_name,
                                "status": stored_commit.status,
                            }
                        )
                        audit_failure = _headless_audit_failure_reason(stored_commit)
                        if audit_failure is not None:
                            status = "failed"
                            stderr = audit_failure
                            break
                        executed_results.append(stored_commit)
                    continue
                if decision.requires_confirmation:
                    status = "pending_approval"
                    pending_tool = {
                        "tool_name": tool_name,
                        "tool_call_id": tool_call_id,
                        "reason": decision.reason,
                    }
                    break
                tool_kwargs: dict[str, Any] = {}
                if target == "host" and tool_name in SHELL_COMMAND_TOOLS:
                    tool_kwargs = {"session_store": store, "session_id": session.id}
                result = execute_local_tool(
                    tool_name,
                    input_json,
                    cwd,
                    **tool_kwargs,
                )
                tool_event_id, stored_result = _record_headless_tool_result(
                    store=store,
                    session_id=session.id,
                    result=result,
                    run_id=run_id,
                    tool_call_id=tool_call_id,
                    api_client=api_client,
                    risk_level=decision.risk_level,
                    command=command,
                    cwd=cwd,
                    target=target,
                    permission_mode=permission_mode,
                )
                tool_summaries.append(
                    {
                        "tool_event_id": tool_event_id,
                        "tool_name": stored_result.tool_name,
                        "status": stored_result.status,
                    }
                )
                audit_failure = _headless_audit_failure_reason(stored_result)
                if audit_failure is not None:
                    status = "failed"
                    stderr = audit_failure
                    break
                executed_results.append(stored_result)
            elif event.event == "error":
                status = "failed"
                stderr = str(event.data.get("message") or "")
                break
            elif event.event == "done":
                break
        assistant_content = "".join(assistant_chunks).strip()
        if assistant_content:
            assistant_outputs.append(assistant_content)
            store.append_message(
                session.id,
                role="assistant",
                content=assistant_content,
                run_id=run_id,
                metadata=_build_workflow_metadata(command),
            )
        if status in {"failed", "pending_approval"}:
            break
        if fake_events is not None or not executed_results:
            break
        if depth >= max_auto_turns:
            status = "max_auto_turns_reached"
            stderr = "max auto turns reached"
            break
        depth += 1
        goal = "Continue using the local tool results."
    stdout_json: dict[str, Any] = {
        "status": status,
        "session_id": session.id,
        "run_id": run_id,
        "command": command,
        "turns": depth + 1,
    }
    if tool_summaries:
        stdout_json["tool_results"] = tool_summaries
    if pending_change_id:
        pending_change = store.get_pending_change(pending_change_id)
        if pending_change is not None:
            stdout_json["change_id"] = pending_change["id"]
            stdout_json["change_status"] = pending_change["status"]
            stdout_json["target_paths"] = pending_change["target_paths"]
    if pending_tool is not None:
        stdout_json["pending_tool"] = pending_tool
    if assistant_outputs:
        stdout_json["assistant"] = "\n".join(assistant_outputs)
    if latest_model_call_id is not None:
        stdout_json["model_call_id"] = latest_model_call_id
    if latest_usage:
        stdout_json["usage"] = latest_usage
    if bridge_event_sequence:
        stdout_json["bridge_delta_count"] = bridge_event_sequence
    exit_code = 0 if status == "completed" else 2 if status == "pending_approval" else 1
    return HeadlessRunResult(
        exit_code=exit_code,
        status=status,
        stdout_json=stdout_json,
        stderr=stderr,
    )


def _run_headless(args: argparse.Namespace) -> int:
    config = load_config()
    api_url = args.api_url or config.api_url
    token = args.token or config.token
    store = SessionStore(config.session_db_path, config.sessions_dir)
    try:
        result = run_headless_once(
            command=args.command,
            prompt=args.prompt,
            cwd=Path(args.cwd).expanduser().resolve(),
            session_store=store,
            session_id=args.resume_session_id,
            permission_mode=args.mode,
            target=args.target,
            max_auto_turns=args.max_auto_turns,
            api_client=HarnessApiClient(api_url, token),
            agent_id=args.agent_id,
            model_provider=args.model_provider,
            model_name=args.model_name,
        )
    except ValueError as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "command": args.command,
                    "resume_session_id": args.resume_session_id,
                    "error": str(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result.stdout_json, ensure_ascii=False, sort_keys=True))
    if result.stderr:
        print(
            json.dumps(
                {"status": result.status, "error": result.stderr},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
    return result.exit_code


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command in {"chat", "plan", "act"}:
        _normalize_headless_args(args)
        return _run_headless(args)
    if args.command == "version":
        return _print_version()
    if args.command == "login":
        return _save_login(args)
    if args.command == "status":
        return _print_auth_status()
    if args.command == "logout":
        return _logout()
    if args.command == "auth":
        if args.auth_command == "set":
            return _save_login(args)
        if args.auth_command == "status":
            return _print_auth_status()
    if args.command == "bridge":
        if args.bridge_command == "pair":
            return _run_bridge_pair(args)
        if args.bridge_command == "run":
            return _run_bridge(args)
    if args.command == "sessions":
        return _print_sessions()
    if args.command == "resume":
        if not args.session_id:
            sessions = _store().list_sessions(limit=1)
            if not sessions:
                print("no local hao sessions")
                return 1
            args.session_id = sessions[0].id
        return _run_tui(args, resume_session_id=args.session_id)
    if args.command == "doctor":
        return _doctor()
    return _run_tui(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
