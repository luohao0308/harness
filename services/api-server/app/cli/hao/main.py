from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import tomllib
import uuid
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

from .api_client import HarnessApiClient, SSEEvent
from .config import clear_persisted_token, format_status, load_config, save_auth
from .local_tools import SHELL_COMMAND_TOOLS, ToolExecutionResult, execute_local_tool
from .permissions import PermissionEngine
from .sandbox_tools import execute_sandbox_tool
from .session_store import SessionStore

GIT_STATUS_CONTEXT_LIMIT = 8
PACKAGE_DISTRIBUTION_NAME = "agent-harness-api-server"


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
        choices=["fake", "hao"],
        default="hao",
    )
    bridge_pair.add_argument("--display-name", default=None)
    bridge_pair.add_argument("--cwd", default=".")
    bridge_pair.add_argument("--daemon", action="store_true")
    bridge_pair.add_argument("--once", action="store_true")
    bridge_pair.add_argument("--interval", type=float, default=2.0)

    bridge_run = bridge_sub.add_parser("run", help="Run a previously paired local Agent bridge")
    bridge_run.add_argument("--api", "--api-url", dest="api_url", default=None)
    bridge_run.add_argument("--connection-id", default=None)
    bridge_run.add_argument("--device-token", default=None)
    bridge_run.add_argument(
        "--adapter",
        "--adapter-kind",
        dest="adapter_kind",
        choices=["fake", "hao"],
        default="hao",
    )
    bridge_run.add_argument("--cwd", default=".")
    bridge_run.add_argument("--once", action="store_true")
    bridge_run.add_argument("--interval", type=float, default=2.0)

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


def _bridge_version() -> str:
    return f"hao-{_hao_version()}"


def _bridge_capabilities(adapter_kind: str) -> dict[str, Any]:
    return {
        "adapter_kind": adapter_kind,
        "supports_resume": adapter_kind == "hao",
        "supports_streaming": True,
        "supports_cancel": False,
        "protocol_version": "local-agent-v1",
    }


def _bridge_risk_capabilities(adapter_kind: str) -> list[str]:
    if adapter_kind == "hao":
        return ["host_read", "host_write", "shell", "git", "network"]
    return []


def _save_bridge_state(config: Any, state: dict[str, Any]) -> None:
    config.home.mkdir(parents=True, exist_ok=True)
    path = _bridge_state_path(config)
    data = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True)
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
    return loaded if isinstance(loaded, dict) else {}


def _run_bridge_pair(args: argparse.Namespace) -> int:
    config = load_config()
    api_url = args.api_url or config.api_url
    cwd = Path(args.cwd).expanduser().resolve()
    client = HarnessApiClient(api_url, config.token)
    display_name = args.display_name or (
        "hao Local Agent" if args.adapter_kind == "hao" else "Fake Local Agent"
    )
    registered = client.register_local_agent_connection(
        pair_token=args.pair_token,
        pair_code=args.pair_code,
        adapter_kind=args.adapter_kind,
        display_name=display_name,
        workspace_root=str(cwd),
        capabilities=_bridge_capabilities(args.adapter_kind),
        risk_capabilities=_bridge_risk_capabilities(args.adapter_kind),
        bridge_version=_bridge_version(),
    )
    connection = registered["connection"]
    state = {
        "api_url": api_url,
        "connection_id": connection["id"],
        "device_token": registered["device_token"],
        "adapter_kind": args.adapter_kind,
        "cwd": str(cwd),
        "display_name": display_name,
    }
    _save_bridge_state(config, state)
    print(
        json.dumps(
            {
                "status": "paired",
                "connection_id": connection["id"],
                "adapter_kind": args.adapter_kind,
                "state_path": str(_bridge_state_path(config)),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    if args.daemon:
        return _spawn_bridge_daemon(args=args, state=state)
    if args.once:
        return _run_bridge_loop_from_state(
            config=config,
            state=state,
            once=True,
            interval=args.interval,
        )
    return 0


def _spawn_bridge_daemon(*, args: argparse.Namespace, state: dict[str, Any]) -> int:
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
        "--cwd",
        str(state["cwd"]),
        "--interval",
        str(args.interval),
    ]
    subprocess.Popen(  # noqa: S603
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    print(
        json.dumps(
            {
                "status": "daemon_started",
                "connection_id": state["connection_id"],
                "adapter_kind": state["adapter_kind"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _run_bridge(args: argparse.Namespace) -> int:
    config = load_config()
    state = _load_bridge_state(config)
    if args.api_url:
        state["api_url"] = args.api_url
    if args.connection_id:
        state["connection_id"] = args.connection_id
    if args.device_token:
        state["device_token"] = args.device_token
    state["adapter_kind"] = args.adapter_kind or state.get("adapter_kind") or "hao"
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
    capabilities = _bridge_capabilities(adapter_kind)
    while True:
        client.heartbeat_local_agent_connection(
            connection_id=connection_id,
            device_token=device_token,
            status="online",
            bridge_version=_bridge_version(),
            capabilities=capabilities,
        )
        page = client.pull_local_agent_bridge_tasks(device_token=device_token)
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
    _handle_hao_bridge_task(
        config=config,
        state=state,
        client=client,
        device_token=device_token,
        task=task,
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
    prompt = str(payload.get("message") or "").strip()
    run_id = str(payload.get("run_id") or "")
    agent_id = str(payload.get("agent_id") or "default")
    adapter_session_id = payload.get("adapter_session_id")
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
            cli_mode="act",
            target="host",
        )
    if run_id:
        store.update_run_id(local_session.id, run_id)
    try:
        result = run_headless_once(
            command="act",
            prompt=prompt,
            cwd=cwd,
            session_store=store,
            session_id=local_session.id,
            permission_mode="confirm",
            target="host",
            max_auto_turns=3,
            api_client=client,
            agent_id=agent_id,
            model_provider="default",
            model_name="default",
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
    client.report_local_agent_bridge_event(
        device_token=device_token,
        payload={
            "event_id": f"{task_id}:done:{uuid.uuid4().hex}",
            "bridge_task_id": task_id,
            "event_type": "assistant_done",
            "content": assistant or "hao completed without assistant text.",
            "sequence": 1,
            "metadata": {
                "local_session_id": local_session.id,
                "headless_status": result.status,
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
    max_auto_turns: int,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    workflow_metadata = _build_workflow_metadata(command)
    return {
        "mode": workflow_metadata["backend_mode"],
        "goal": goal,
        "run_id": run_id,
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
                assistant_chunks.append(str(event.data.get("content") or ""))
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
