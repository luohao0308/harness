from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, RichLog, Static

from .api_client import HarnessApiClient, SSEEvent
from .config import load_config
from .local_tools import (
    COMMIT_COMMAND_TOOLS,
    PREVIEW_COMMAND_TOOLS,
    SHELL_COMMAND_TOOLS,
    WRITE_COMMAND_TOOLS,
    ToolExecutionResult,
    cancel_local_command,
    execute_local_tool,
    retry_local_command_tool,
)
from .main import _hao_version
from .permissions import PermissionDecision, PermissionEngine
from .sandbox_tools import execute_sandbox_tool
from .session_store import SessionStore, StoredSession

GIT_STATUS_CONTEXT_LIMIT = 8
OUTPUT_STYLES = {
    "default": "Use the default hao response style.",
    "concise": "Be terse. Lead with the result, commands, diffs, and next action.",
    "explanatory": "Explain important decisions and tradeoffs while staying practical.",
    "review": "Lead with findings, risks, missing tests, and concrete file references.",
}
HAO_INIT_TEMPLATE = """# HAO.md

Guidance for hao in this workspace.

## Project Notes

- Work from this repository root unless the user gives a narrower path.
- Prefer small, reviewable changes and preserve existing project patterns.
- Run the most relevant verification before reporting completion.

## hao Hints

- Use `/help` for the local slash command list.
- Use `/permissions` and `/target` before changing tool execution behavior.
- Use `/tools`, `/diff`, `/tasks`, and `/outputs` to inspect local work.
"""


@dataclass
class PendingTool:
    pending_id: str
    run_id: str
    tool_name: str
    input_json: dict[str, Any]
    decision: PermissionDecision
    workflow_metadata: dict[str, Any]
    execution_target: str
    permission_mode: str


@dataclass(frozen=True)
class SlashCommandSpec:
    name: str
    usage: str
    description: str
    category: str
    aliases: tuple[str, ...] = ()


SLASH_COMMANDS: tuple[SlashCommandSpec, ...] = (
    SlashCommandSpec(
        "/help",
        "/help [query]",
        "Show the slash command menu.",
        "core",
        aliases=("/commands", "/"),
    ),
    SlashCommandSpec(
        "/init",
        "/init",
        "Create a HAO.md workspace instruction file.",
        "core",
    ),
    SlashCommandSpec(
        "/release-notes",
        "/release-notes",
        "Show the latest hao CLI changes.",
        "core",
        aliases=("/whats-new",),
    ),
    SlashCommandSpec(
        "/chat",
        "/chat",
        "Switch to normal chat workflow.",
        "workflow",
    ),
    SlashCommandSpec(
        "/plan",
        "/plan",
        "Switch to plan-only workflow.",
        "workflow",
    ),
    SlashCommandSpec(
        "/act",
        "/act",
        "Switch to executable local-agent workflow.",
        "workflow",
        aliases=("/run", "/execute"),
    ),
    SlashCommandSpec(
        "/continue",
        "/continue",
        "Continue from the active branch without adding a user turn.",
        "workflow",
    ),
    SlashCommandSpec(
        "/branch",
        "/branch <message_id>",
        "Move the active path to a prior message leaf.",
        "workflow",
    ),
    SlashCommandSpec(
        "/compact",
        "/compact [instructions]",
        "Summarize older active-path context and keep the latest turns.",
        "workflow",
        aliases=("/compress",),
    ),
    SlashCommandSpec(
        "/resume",
        "/resume [session_id]",
        "List sessions or load a session in this TUI.",
        "workflow",
    ),
    SlashCommandSpec(
        "/config",
        "/config",
        "Show local runtime configuration.",
        "config",
        aliases=("/settings",),
    ),
    SlashCommandSpec(
        "/model",
        "/model [provider/model|provider model]",
        "Show or change the model recorded on new stream payloads.",
        "config",
    ),
    SlashCommandSpec(
        "/permissions",
        "/permissions [confirm|auto-edit|full-auto]",
        "Show or change local permission mode.",
        "config",
        aliases=("/mode", "/allowed-tools"),
    ),
    SlashCommandSpec(
        "/output-style",
        "/output-style [default|concise|explanatory|review]",
        "Show or change the response style hint sent with model turns.",
        "config",
    ),
    SlashCommandSpec(
        "/target",
        "/target host|sandbox",
        "Switch tool execution target.",
        "config",
    ),
    SlashCommandSpec(
        "/max-turns",
        "/max-turns <n>",
        "Set maximum automatic local-tool continuation turns.",
        "config",
    ),
    SlashCommandSpec(
        "/status",
        "/status",
        "Show current session, branch, approval, and command status.",
        "inspect",
    ),
    SlashCommandSpec(
        "/usage",
        "/usage",
        "Show local message, tool, approval, and command counts.",
        "inspect",
        aliases=("/cost", "/stats"),
    ),
    SlashCommandSpec(
        "/context",
        "/context",
        "Show the local context card sent with the next model turn.",
        "inspect",
    ),
    SlashCommandSpec(
        "/view",
        "/view tools|diff|files|approvals|commands|plan|outputs|todos|verify",
        "Open a named workbench view.",
        "views",
    ),
    SlashCommandSpec(
        "/diff",
        "/diff",
        "Open the diff workbench view.",
        "views",
    ),
    SlashCommandSpec(
        "/tools",
        "/tools",
        "Open the tool-event workbench view.",
        "views",
    ),
    SlashCommandSpec(
        "/files",
        "/files",
        "Open the file and git context view.",
        "views",
    ),
    SlashCommandSpec(
        "/approvals",
        "/approvals",
        "Open pending tool and change approvals.",
        "views",
    ),
    SlashCommandSpec(
        "/outputs",
        "/outputs",
        "Open command stdout/stderr summaries.",
        "views",
    ),
    SlashCommandSpec(
        "/tasks",
        "/tasks",
        "Open running and historical command tasks.",
        "views",
        aliases=("/bashes",),
    ),
    SlashCommandSpec(
        "/todo",
        "/todo [add|done|fail]",
        "List or update branch-scoped todos.",
        "work",
        aliases=("/todos",),
    ),
    SlashCommandSpec(
        "/verify",
        "/verify [pass|fail]",
        "List or record branch-scoped verification evidence.",
        "work",
    ),
    SlashCommandSpec(
        "/approve",
        "/approve <id>",
        "Approve a pending tool or change.",
        "approvals",
    ),
    SlashCommandSpec(
        "/reject",
        "/reject <id>",
        "Reject a pending tool or change.",
        "approvals",
    ),
    SlashCommandSpec(
        "/cancel",
        "/cancel <command_id>",
        "Request cancellation for a running local command.",
        "commands",
    ),
    SlashCommandSpec(
        "/retry",
        "/retry <command_id>",
        "Retry a terminal local command.",
        "commands",
    ),
    SlashCommandSpec(
        "/sessions",
        "/sessions",
        "List recent local sessions.",
        "sessions",
    ),
    SlashCommandSpec(
        "/clear",
        "/clear",
        "Clear visible chat and workbench panes.",
        "core",
    ),
    SlashCommandSpec(
        "/quit",
        "/quit",
        "Exit hao.",
        "core",
        aliases=("/exit",),
    ),
)

COMMAND_ALIAS_MAP = {
    alias: command.name
    for command in SLASH_COMMANDS
    for alias in (command.name, *command.aliases)
}

VIEW_COMMANDS = {
    "/tools": "tools",
    "/diff": "diff",
    "/files": "files",
    "/approvals": "approvals",
    "/outputs": "outputs",
    "/tasks": "commands",
}


class HaoApp(App):
    TITLE = "hao"
    SUB_TITLE = "local Agent CLI-style local Agent CLI"
    CSS = """
    Screen { layout: vertical; }
    #chat { height: 1fr; padding: 1 2 0 2; }
    #tools {
        display: none;
        height: 0;
        max-height: 12;
        border-top: solid $secondary;
        padding: 0 2;
        color: $text-muted;
    }
    #tools.open {
        display: block;
        height: 12;
    }
    #composer { height: auto; padding: 0 1; }
    #command_hint {
        height: auto;
        max-height: 8;
        padding: 0 1;
        color: $text-muted;
    }
    #composer_line { height: 3; }
    #prompt_marker {
        width: 2;
        content-align: center middle;
        color: $accent;
        text-style: bold;
    }
    #input {
        width: 1fr;
        border: none;
        padding: 0 1;
        background: transparent;
    }
    #status {
        height: auto;
        min-height: 2;
        padding: 0 2;
        color: $text-muted;
        background: $surface;
    }
    """
    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear", "Clear"),
    ]

    def __init__(
        self,
        *,
        api_url: str,
        token: str,
        agent_id: str,
        cwd: Path,
        model_provider: str,
        model_name: str,
        permission_mode: str,
        target: str,
        resume_session_id: str | None = None,
        max_auto_turns: int = 3,
    ) -> None:
        super().__init__()
        config = load_config()
        self.api_client = HarnessApiClient(api_url, token)
        self.store = SessionStore(config.session_db_path, config.sessions_dir)
        self.agent_id = agent_id
        self.cwd = cwd
        self.model_provider = model_provider
        self.model_name = model_name
        self.permission_mode = permission_mode
        self.interaction_mode = "chat"
        self.target = target
        self.resume_session_id = resume_session_id
        self.max_auto_turns = max(1, int(max_auto_turns))
        self.session: StoredSession | None = None
        self.messages: list[dict[str, Any]] = []
        self.run_id: str | None = None
        self.pending_tools: dict[str, PendingTool] = {}
        self.side_view: str = "tools"
        self.tool_entries: list[str] = []
        self.diff_entries: list[str] = []
        self.approval_entries: list[str] = []
        self.plan_entries: list[str] = []
        self.output_style = "default"
        self.workbench_open = False
        self._compact_summary: str | None = None
        self._compact_keep_from_index = 0
        self._last_tool_audit_failed = False

    def compose(self) -> ComposeResult:
        yield RichLog(id="chat", wrap=True, markup=True, highlight=True)
        yield RichLog(id="tools", wrap=True, markup=True, highlight=True)
        with Vertical(id="composer"):
            yield Static("", id="command_hint")
            with Horizontal(id="composer_line"):
                yield Static("›", id="prompt_marker")
                yield Input(
                    placeholder='Try "explain this repo" or type / for commands',
                    id="input",
                )
        yield Static(id="status")

    def on_mount(self) -> None:
        if self.resume_session_id:
            session = self.store.get_session(self.resume_session_id)
            if session is None:
                self._chat(f"[red]session not found:[/red] {self.resume_session_id}")
                session = self._new_session()
            else:
                self.agent_id = session.agent_id
                self.cwd = Path(session.cwd).expanduser().resolve()
                self.permission_mode = session.mode
                self.interaction_mode = session.cli_mode
                self.target = session.target
        else:
            session = self._new_session()
        self._load_session_state(session)
        self._status()
        self._chat(self._welcome_card())
        for message in self.messages[-12:]:
            self._chat(self._format_transcript_line(message["role"], message["content"]))

    def _new_session(self) -> StoredSession:
        return self.store.create_session(
            cwd=str(self.cwd),
            agent_id=self.agent_id,
            mode=self.permission_mode,
            cli_mode=self.interaction_mode,
            target=self.target,
            title=f"hao {self.cwd.name}",
        )

    def _load_session_state(self, session: StoredSession) -> None:
        self.session = session
        self.run_id = session.run_id
        self.messages = self.store.list_active_path(session.id)
        self.tool_entries = []
        self.diff_entries = []
        self.approval_entries = []
        self._compact_summary = None
        self._compact_keep_from_index = 0
        self.pending_tools.clear()
        for event in self.store.list_tool_events(session.id):
            self.tool_entries.append(
                f"[bold]{event['tool_name']}[/bold] {event['status']} {event['duration_ms']}ms"
            )
            diff = event["output_json"].get("diff")
            if isinstance(diff, str) and diff.strip():
                self.diff_entries.append(
                    f"[bold]{event['tool_name']}[/bold] {event['status']}\n{diff}"
                )
        self._rebuild_plan_entries()

    def _canonical_command(self, command: str) -> str:
        return COMMAND_ALIAS_MAP.get(command, command)

    def _slash_candidates(self, query: str = "") -> list[SlashCommandSpec]:
        normalized = query.strip().lower()
        if normalized.startswith("/"):
            normalized = normalized[1:]
        if not normalized:
            return list(SLASH_COMMANDS)
        matches: list[SlashCommandSpec] = []
        for command in SLASH_COMMANDS:
            haystack = " ".join(
                (
                    command.name,
                    command.usage,
                    command.description,
                    command.category,
                    *command.aliases,
                )
            ).lower()
            if normalized in haystack:
                matches.append(command)
        return matches

    def _format_command_menu(self, query: str = "", *, limit: int = 24) -> str:
        candidates = self._slash_candidates(query)[:limit]
        title = "[bold]hao commands[/bold]"
        if query.strip():
            title += f" matching {query.strip()}"
        if not candidates:
            return f"{title}\n[yellow]No matching commands.[/yellow]"
        lines = [title]
        category = ""
        for command in candidates:
            if command.category != category:
                category = command.category
                lines.append(f"[dim]{category}[/dim]")
            aliases = ""
            if command.aliases:
                aliases = f" aliases: {', '.join(command.aliases)}"
            lines.append(f"  [cyan]{command.usage}[/cyan]  {command.description}{aliases}")
        if len(candidates) == limit:
            lines.append("[dim]Type more after / to narrow the list.[/dim]")
        return "\n".join(lines)

    def _slash_hint_text(self, value: str, *, limit: int = 7) -> str:
        raw = value.strip()
        if not raw.startswith("/"):
            return ""
        token = raw.split(maxsplit=1)[0]
        if token in COMMAND_ALIAS_MAP and raw.endswith(" "):
            spec = next(
                command
                for command in SLASH_COMMANDS
                if command.name == COMMAND_ALIAS_MAP[token]
            )
            return f"{spec.usage} - {spec.description}"
        candidates = self._slash_candidates(token)
        if not candidates:
            return "No matching commands"
        return "\n".join(
            f"{command.usage} - {command.description}" for command in candidates[:limit]
        )

    @staticmethod
    def _clip_text(value: Any, limit: int = 62) -> str:
        text = str(value).replace("\n", " ").strip()
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 3)] + "..."

    def _model_strength_label(self) -> str:
        combined = f"{self.model_provider} {self.model_name}".lower()
        if any(marker in combined for marker in ("opus", "max", "ultra")):
            return "max"
        light_markers = ("flash", "mini", "haiku", "lite", "nano", "small")
        if any(marker in combined for marker in light_markers):
            return "light"
        if any(
            marker in combined
            for marker in (
                "pro",
                "sonnet",
                "gpt-5",
                "gpt-4.5",
                "gpt-4",
                "deepseek-v4-pro",
                "deepseek-pro",
            )
        ):
            return "strong"
        return "standard"

    @staticmethod
    def _compact_ring_for_ratio(ratio: float) -> str:
        if ratio <= 0:
            return "○"
        if ratio < 0.25:
            return "◔"
        if ratio < 0.5:
            return "◑"
        if ratio < 0.75:
            return "◕"
        if ratio < 1.0:
            return "◉"
        return "●"

    def _compact_status_summary(self) -> str:
        if self._compact_summary is None or not self.messages:
            return f"compact ○ 0% · {len(self.messages)} msgs · /compact"
        compacted = max(0, min(self._compact_keep_from_index, len(self.messages)))
        total = max(1, len(self.messages))
        ratio = compacted / total
        ring = self._compact_ring_for_ratio(ratio)
        percent = int(round(ratio * 100))
        kept = max(0, total - compacted)
        return f"compact {ring} {percent}% compacted · {kept} kept · /compact"

    def _footer_status_block(self) -> str:
        status = self._workbench_status()
        return "\n".join(
            (
                f"{status['model_provider']}/{status['model_name']} "
                f"· strength {status['model_strength']}",
                f"{self._compact_status_summary()} · "
                f"style {status['output_style']} · "
                f"approvals {status['pending_approval_count']} · "
                f"cmds {status['running_command_count']}/{status['total_command_count']}",
            )
        )

    def _welcome_card(self) -> str:
        status = self._workbench_status()
        terminal_width = shutil.get_terminal_size((80, 30)).columns
        width = max(72, min(terminal_width - 2, 154))
        inner_width = width - 2
        left_width = max(32, min(68, inner_width // 2 - 1))
        right_width = inner_width - left_width - 1
        title = f" hao Code v{_hao_version()} "
        title_prefix = "╭─"
        title_suffix_width = max(0, width - len(title_prefix) - len(title) - 1)
        top = f"{title_prefix}{title}{'─' * title_suffix_width}╮"
        bottom = f"╰{'─' * inner_width}╯"
        divider = "│"
        cwd = str(status["cwd"])
        if cwd.startswith(str(Path.home())):
            cwd = "~" + cwd[len(str(Path.home())) :]
        left_lines = [
            "",
            "Welcome back!",
            "",
            "        ▄▄▄▄▄▄▄",
            "      ▄█  ▄ ▄  █▄",
            "      ██▄▄▄▄▄▄▄██",
            "        ██   ██",
            "",
            f"{status['model_provider']} / {status['model_name']} "
            f"· strength {status['model_strength']}",
            cwd,
        ]
        right_lines = [
            "Tips for getting started",
            "Run /init to create a HAO.md file with instructions",
            "─" * max(8, right_width - 4),
            "What's new",
            "Model strength and compact ring now show in the footer",
            "Single-column terminal UI, no editor-style screen",
            "Slash commands, local tools, approvals, and audit trail",
            "Use /tools, /diff, /tasks, /config, /output-style",
            "Use /compact to summarize older turns",
            "/release-notes for more",
            "",
        ]

        def cell(text: str, width: int, *, align: str = "left") -> str:
            clipped = self._clip_text(text, width)
            if align == "center":
                return clipped.center(width)
            return f"{clipped:<{width}}"

        rows = [f"[#d97757]{top}[/]"]
        for index in range(max(len(left_lines), len(right_lines))):
            left = left_lines[index] if index < len(left_lines) else ""
            right = right_lines[index] if index < len(right_lines) else ""
            left_align = "center" if index in {1, 3, 4, 5, 6, 8, 9} else "left"
            rows.append(
                f"[#d97757]{divider}[/] "
                f"{cell(left, left_width - 2, align=left_align)} "
                f"[#d97757]{divider}[/] "
                f"{cell(right, right_width - 2)} "
                f"[#d97757]{divider}[/]"
            )
        rows.append(f"[#d97757]{bottom}[/]")
        return "\n".join(rows)

    def _format_transcript_line(self, role: str, content: Any) -> str:
        text = str(content).strip()
        if role == "user":
            return f"[bold cyan]›[/bold cyan] {text}"
        if role == "assistant":
            return f"[bold green]hao[/bold green] {text}"
        if role == "tool":
            return f"[bold magenta]tool[/bold magenta] {text}"
        return f"[dim]{role}[/dim] {text}"

    def _active_leaf_message(self) -> dict[str, Any] | None:
        if self.messages:
            return self.messages[-1]
        if self.session is None:
            return None
        active_path = self.store.list_active_path(self.session.id)
        if not active_path:
            return None
        self.messages = active_path
        return active_path[-1]

    def _pending_change_count(self) -> int:
        if self.session is None:
            return 0
        return sum(
            1
            for change in self.store.list_pending_changes(self.session.id)
            if change["status"] == "pending"
        )

    def _pending_approval_count(self) -> int:
        return len(self.pending_tools) + self._pending_change_count()

    def _command_counts(self) -> tuple[int, int]:
        if self.session is None:
            return 0, 0
        commands = self.store.list_commands(self.session.id)
        active = sum(1 for command in commands if command["status"] in {"pending", "running"})
        return active, len(commands)

    def _workbench_status(self) -> dict[str, Any]:
        active_leaf = self._active_leaf_message()
        active_leaf_id = None if active_leaf is None else str(active_leaf["id"])
        active_branch_id = None if active_leaf is None else str(active_leaf["branch_id"])
        running_commands, total_commands = self._command_counts()
        return {
            "agent_id": self.agent_id,
            "session_id": self.session.id if self.session else None,
            "run_id": self.run_id,
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "target": self.target,
            "permission_mode": self.permission_mode,
            "interaction_mode": self.interaction_mode,
            "side_view": self.side_view,
            "model_strength": self._model_strength_label(),
            "active_leaf_id": active_leaf_id,
            "active_branch_id": active_branch_id,
            "pending_tool_count": len(self.pending_tools),
            "pending_change_count": self._pending_change_count(),
            "pending_approval_count": self._pending_approval_count(),
            "running_command_count": running_commands,
            "total_command_count": total_commands,
            "max_auto_turns": self.max_auto_turns,
            "output_style": self.output_style,
            "compact_active": self._compact_summary is not None,
            "compact_compacted_messages": self._compact_keep_from_index,
            "compact_percent": (
                int(round(self._compact_keep_from_index / len(self.messages) * 100))
                if self._compact_summary is not None and self.messages
                else 0
            ),
            "compact_ring": (
                self._compact_ring_for_ratio(self._compact_keep_from_index / len(self.messages))
                if self._compact_summary is not None and self.messages
                else "○"
            ),
            "compact_kept_messages": (
                max(0, len(self.messages) - self._compact_keep_from_index)
                if self._compact_summary is not None
                else len(self.messages)
            ),
            "cwd": str(self.cwd),
        }

    def _status_text(self, status: dict[str, Any]) -> str:
        session_id = status["session_id"] or "-"
        run_id = status["run_id"] or "-"
        leaf_id = status["active_leaf_id"] or "-"
        branch_id = status["active_branch_id"] or "-"
        return (
            f"/help agent={status['agent_id']} "
            f"{status['model_provider']}/{status['model_name']} "
            f"strength={status['model_strength']} "
            f"workflow={status['interaction_mode']} "
            f"target={status['target']} permission={status['permission_mode']} "
            f"view={status['side_view']} style={status['output_style']} "
            f"approvals={status['pending_approval_count']} "
            f"commands={status['running_command_count']}/{status['total_command_count']} "
            f"compact={'on' if status['compact_active'] else 'off'} "
            f"compact_ring={status['compact_ring']} "
            f"max_turns={status['max_auto_turns']} "
            f"leaf={leaf_id} branch={branch_id} session={session_id} run={run_id} "
            f"cwd={status['cwd']}"
        )

    def _status(self) -> None:
        self.query_one("#status", Static).update(self._footer_status_block())

    def _chat(self, message: str) -> None:
        self.query_one("#chat", RichLog).write(message)

    def _stream_assistant_begin(self) -> None:
        self._chat("[bold green]hao[/bold green] ")

    def _stream_assistant_append(self, content: str) -> None:
        if content:
            self._chat(content)

    def _chat_stream_end(self) -> None:
        return None

    def _tools_log_widget(self) -> RichLog | None:
        try:
            return self.query_one("#tools", RichLog)
        except Exception:
            return None

    def _inline_workbench_message(self, label: str, message: str) -> None:
        if self.workbench_open:
            return
        self._chat(f"[dim]{label}[/dim] {message}")

    def _close_workbench(self) -> None:
        self.workbench_open = False
        log = self._tools_log_widget()
        if log is None:
            return
        log.remove_class("open")
        log.clear()

    def _tool_log(self, message: str) -> None:
        self.tool_entries.append(message)
        if self.side_view == "tools" and self.workbench_open:
            self._write_side_panel()
        else:
            self._inline_workbench_message("tool", message)

    def _diff_log(self, message: str) -> None:
        self.diff_entries.append(message)
        if self.side_view == "diff" and self.workbench_open:
            self._write_side_panel()
        else:
            self._inline_workbench_message("diff", message)

    def _approval_log(self, message: str) -> None:
        self.approval_entries.append(message)
        if self.side_view == "approvals" and self.workbench_open:
            self._write_side_panel()
        else:
            self._inline_workbench_message("approval", message)

    def _side_panel_entries(self) -> tuple[str, list[str]]:
        if self.side_view == "tools":
            entries = self.tool_entries[-60:]
            header = "tools"
        elif self.side_view == "diff":
            entries = self.diff_entries[-40:]
            header = "diff"
        elif self.side_view == "approvals":
            entries = self._approval_entries()
            header = "approvals"
        elif self.side_view == "commands":
            entries = self._command_entries()
            header = "commands"
        elif self.side_view == "plan":
            entries = self.plan_entries[-60:]
            header = "plan"
        elif self.side_view == "outputs":
            entries = self._output_entries()
            header = "outputs"
        elif self.side_view == "todos":
            entries = self._todo_entries()
            header = "todos"
        elif self.side_view == "verify":
            entries = self._verification_entries()
            header = "verify"
        else:
            entries = self._file_tree_entries()
            header = "files"
        return header, entries

    def _write_side_panel(self) -> None:
        log = self._tools_log_widget()
        if log is None:
            return
        log.add_class("open")
        log.clear()
        header, entries = self._side_panel_entries()
        log.write(f"[bold]{header}[/bold] [dim](/clear hides)[/dim]")
        for entry in entries:
            log.write(entry)

    def _render_side_panel(self) -> None:
        self.workbench_open = True
        self._write_side_panel()

    def _refresh_workbench(self) -> None:
        if self.workbench_open:
            self._write_side_panel()

    def _rebuild_plan_entries(self) -> None:
        self.plan_entries = []
        if self.session is None:
            return
        for message in self.store.list_messages(self.session.id):
            metadata = message.get("metadata") or {}
            if (
                message["role"] == "assistant"
                and metadata.get("interaction_mode") == "plan"
            ):
                self.plan_entries.append(str(message["content"]))

    def _output_entries(self) -> list[str]:
        if self.session is None:
            return []
        entries: list[str] = []
        for event in self.store.list_tool_events(self.session.id):
            output = event["output_json"]
            if "stdout" not in output and "stderr" not in output and "exit_code" not in output:
                continue
            parts = [f"> {event['tool_name']} {event['status']}"]
            if "exit_code" in output:
                parts.append(f"exit={output['exit_code']}")
            command = str(
                output.get("command")
                or event["input_json"].get("command")
                or event["tool_name"]
            ).strip()
            if command:
                parts.append(f"$ {command}")
            stdout = str(output.get("stdout") or "").strip()
            if stdout:
                parts.append(f"stdout: {stdout.splitlines()[0][:120]}")
            stderr = str(output.get("stderr") or "").strip()
            if stderr:
                parts.append(f"stderr: {stderr.splitlines()[0][:120]}")
            entries.append("\n".join(parts))
        for command in self.store.list_commands(self.session.id):
            if command["status"] not in {"success", "failed", "timeout", "cancelled"}:
                continue
            command_text = str(command["command"]).replace("\n", " ").strip()
            if len(command_text) > 120:
                command_text = command_text[:117] + "..."
            entries.append(
                f"> {command['tool_name']} {command['status']}\n"
                f"exit={command['exit_code']}\n$ {command_text}"
            )
        return entries

    def _approval_entries(self) -> list[str]:
        entries: list[str] = []
        for pending_id, pending in sorted(self.pending_tools.items()):
            tool_name = getattr(pending, "tool_name", "tool")
            decision = getattr(pending, "decision", None)
            reason = getattr(decision, "reason", "pending approval")
            entries.append(f"tool {pending_id} {tool_name}: {reason}")
        if self.session is not None:
            for change in self.store.list_pending_changes(self.session.id):
                if change["status"] != "pending":
                    continue
                paths = ", ".join(change["target_paths"]) or "-"
                entries.append(f"change {change['id']} {change['tool_name']}: {paths}")
        entries.extend(self.approval_entries[-40:])
        return entries[-60:]

    def _git_output(self, args: list[str]) -> str | None:
        if shutil.which("git") is None:
            return None
        try:
            completed = subprocess.run(
                ["git", "-C", str(self.cwd), *args],
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

    def _git_status_lines(self, limit: int = GIT_STATUS_CONTEXT_LIMIT) -> list[str]:
        status = self._git_output(["status", "--short", "--untracked-files=all"])
        if status is None:
            return []
        return [line.strip() for line in status.splitlines() if line.strip()][:limit]

    def _git_context_summary(self) -> str:
        status_lines = self._git_status_lines()
        if status_lines == []:
            return "none"
        branch = self._git_output(["branch", "--show-current"]) or "detached"
        sample = "; ".join(status_lines[:4]) or "clean"
        return f"branch={branch} dirty={len(status_lines)} sample={sample}"

    def _recent_test_hint(self) -> str:
        if self.session is None:
            return "none"
        for command in reversed(self.store.list_commands(self.session.id)):
            if command["tool_name"] != "run_tests":
                continue
            command_text = str(command["command"]).replace("\n", " ").strip()
            if len(command_text) > 120:
                command_text = command_text[:117] + "..."
            return f"{command['status']} exit={command['exit_code']} {command_text}"
        return "none"

    def _active_branch_leaf(self) -> tuple[str | None, str | None]:
        active_leaf = self._active_leaf_message()
        if active_leaf is None:
            return None, None
        return str(active_leaf["branch_id"]), str(active_leaf["id"])

    def _todo_entries(self) -> list[str]:
        if self.session is None:
            return []
        branch_id, _ = self._active_branch_leaf()
        todos = self.store.list_todos(self.session.id, branch_id=branch_id)
        return [
            f"{todo['id']} {todo['status']} {todo['title']}"
            for todo in todos[-60:]
        ]

    def _verification_entries(self) -> list[str]:
        if self.session is None:
            return []
        branch_id, _ = self._active_branch_leaf()
        verifications = self.store.list_verifications(
            self.session.id,
            branch_id=branch_id,
        )
        return [
            f"{verification['id']} {verification['status']} "
            f"{verification['label']} {verification['evidence_summary']}"
            for verification in verifications[-60:]
        ]

    def _command_entries(self) -> list[str]:
        if self.session is None:
            return []
        entries: list[str] = []
        for command in self.store.list_commands(self.session.id)[-40:]:
            command_text = str(command["command"]).replace("\n", " ").strip()
            if len(command_text) > 120:
                command_text = command_text[:117] + "..."
            retry_suffix = (
                f" retry_of={command['retry_of_id']}"
                if command["retry_of_id"]
                else ""
            )
            entries.append(
                f"> {command['id']} {command['status']} {command['tool_name']}"
                f"{retry_suffix}\nexit={command['exit_code']}\n$ {command_text}"
            )
        return entries

    def _file_tree_entries(self) -> list[str]:
        entries: list[str] = []
        git_summary = self._git_context_summary()
        if git_summary != "none":
            entries.append(f"git {git_summary}")
            entries.extend(f"git {line}" for line in self._git_status_lines(limit=12))
        ignored = {".git", ".venv", "__pycache__", "node_modules"}
        stack: list[tuple[Path, int]] = [(self.cwd, 0)]
        while stack and len(entries) < 80:
            path, depth = stack.pop(0)
            if not path.exists():
                continue
            try:
                children = sorted(
                    (child for child in path.iterdir() if child.name not in ignored),
                    key=lambda item: (not item.is_dir(), item.name.lower()),
                )
            except OSError:
                continue
            for child in children:
                try:
                    relative = child.relative_to(self.cwd)
                except ValueError:
                    continue
                prefix = "d" if child.is_dir() else "f"
                entries.append(f"{'  ' * depth}{prefix} {relative}")
                if child.is_dir() and depth < 1:
                    stack.append((child, depth + 1))
                if len(entries) >= 80:
                    break
        return entries

    def _safe_call(self, callback, *args) -> None:
        try:
            self.call_from_thread(callback, *args)
        except RuntimeError:
            callback(*args)

    def action_clear(self) -> None:
        self.query_one("#chat", RichLog).clear()
        self._close_workbench()
        self.query_one("#command_hint", Static).update("")

    async def on_input_changed(self, event: Input.Changed) -> None:
        hint = self._slash_hint_text(event.value)
        self.query_one("#command_hint", Static).update(hint)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        event.input.value = ""
        self.query_one("#command_hint", Static).update("")
        if not value:
            return
        if value.startswith("/"):
            self._handle_command(value)
            return
        interaction_mode = self.interaction_mode
        workflow_metadata = self._workflow_metadata(interaction_mode)
        self._record_message_ui(
            "user",
            value,
            metadata=workflow_metadata,
        )
        self._chat(self._format_transcript_line("user", value))
        self.run_turn_worker(value, True, 0, interaction_mode)

    def _handle_command(self, value: str) -> None:
        parts = value.split()
        raw_command = parts[0].lower()
        command = self._canonical_command(raw_command)
        if command in {"/quit", "/exit"}:
            self.exit()
            return
        if command == "/help":
            self._chat(self._format_command_menu(" ".join(parts[1:])))
            return
        if command == "/init":
            self._handle_init_command()
            return
        if command == "/release-notes":
            self._chat(self._release_notes_text())
            return
        if command == "/clear":
            self.action_clear()
            return
        if command in VIEW_COMMANDS:
            self._set_side_view(VIEW_COMMANDS[command])
            return
        if command == "/compact":
            self._handle_compact_command(parts)
            return
        if command in {"/chat", "/plan", "/act"}:
            self._set_interaction_mode(command.removeprefix("/"))
            return
        if command == "/config":
            self._chat(self._config_text())
            return
        if command == "/view" and len(parts) == 2 and parts[1] in {
            "tools",
            "diff",
            "files",
            "approvals",
            "commands",
            "plan",
            "outputs",
            "todos",
            "verify",
        }:
            self._set_side_view(parts[1])
            return
        if command == "/model":
            self._handle_model_command(parts)
            return
        if command == "/output-style":
            self._handle_output_style_command(parts)
            return
        if command == "/permissions" and len(parts) == 1:
            self._chat(f"[dim]permissions[/dim] {self.permission_mode}")
            return
        if command == "/permissions" and len(parts) == 2 and parts[1] in {
            "confirm",
            "auto-edit",
            "full-auto",
        }:
            self.permission_mode = parts[1]
            if self.session:
                self.store.update_mode_target(
                    self.session.id,
                    mode=self.permission_mode,
                    target=self.target,
                )
            self._status()
            return
        if command == "/permissions":
            self._tool_log(
                "[yellow]usage[/yellow] /permissions [confirm|auto-edit|full-auto]"
            )
            return
        if command == "/target" and len(parts) == 2 and parts[1] in {"host", "sandbox"}:
            self.target = parts[1]
            if self.session:
                self.store.update_mode_target(
                    self.session.id,
                    mode=self.permission_mode,
                    target=self.target,
                )
            self._status()
            return
        if command == "/target":
            self._tool_log("[yellow]usage[/yellow] /target host|sandbox")
            return
        if command == "/sessions":
            for session in self.store.list_sessions(limit=20):
                self._chat(
                    f"{session.id} {session.updated_at} {session.cwd} "
                    f"permission={session.mode} workflow={session.cli_mode}"
                )
            return
        if command == "/resume":
            if len(parts) == 1:
                self._handle_command("/sessions")
            elif len(parts) == 2:
                self._resume_session(parts[1])
            else:
                self._tool_log("[yellow]usage[/yellow] /resume [session_id]")
            return
        if command == "/continue":
            self._continue_current_workflow()
            return
        if command == "/branch" and len(parts) == 2:
            self._branch_to_message(parts[1])
            return
        if command == "/approve" and len(parts) == 2:
            self._approval_log(f"[green]approve[/green] {parts[1]}")
            if parts[1] in self.pending_tools:
                self.approve_tool_worker(parts[1])
            else:
                self.approve_change_worker(parts[1])
            return
        if command == "/reject" and len(parts) == 2:
            self._approval_log(f"[red]reject[/red] {parts[1]}")
            self.reject_tool(parts[1])
            return
        if command == "/cancel" and len(parts) == 2:
            if cancel_local_command(parts[1]):
                self._tool_log(f"[yellow]cancel requested[/yellow] {parts[1]}")
            else:
                self._tool_log(f"[red]unknown running command[/red] {parts[1]}")
            return
        if command == "/retry" and len(parts) == 2:
            self.retry_command_worker(parts[1])
            return
        if command == "/todo":
            self._handle_todo_command(parts)
            return
        if command == "/verify":
            self._handle_verify_command(parts)
            return
        if command == "/max-turns" and len(parts) == 2:
            self._handle_max_turns(parts[1])
            return
        if command == "/status":
            self._chat(self._status_text(self._workbench_status()))
            return
        if command == "/usage":
            self._chat(self._usage_text())
            return
        if command == "/context":
            self._chat(
                self._format_transcript_line(
                    "system",
                    self._local_context_message(self.interaction_mode)["content"],
                )
            )
            return
        self._chat(f"[yellow]unknown command[/yellow] {value}")

    def _handle_init_command(self) -> None:
        target = self.cwd / "HAO.md"
        if target.exists():
            self._tool_log(f"[yellow]exists[/yellow] {target}")
            return
        try:
            target.write_text(HAO_INIT_TEMPLATE, encoding="utf-8")
        except OSError as exc:
            self._tool_log(f"[red]init failed[/red] {exc}")
            return
        self._tool_log(f"[green]created[/green] {target}")

    def _release_notes_text(self) -> str:
        return "\n".join(
            (
                "[bold]hao release notes[/bold]",
                "v4.3: local Agent CLI-style footer shows model strength, compact ring, "
                "style, approvals, and commands.",
                "v4.3: /compress aliases /compact for local active-path context summarization.",
                "v4.2: inline local Agent CLI-style terminal page; no fullscreen editor screen.",
                "v4.2: two-column welcome card, bottom `>` composer, and hidden workbench drawer.",
                "v4.2: safe UTF-8 terminal input plus no duplicate user echo in real terminals.",
                "v4.1: /compact, /config, /usage, /output-style, /tasks, and command cards.",
                "v4: slash menu, /permissions, /model, /context, /resume, "
                "and branch-aware transcript.",
            )
        )

    def _handle_max_turns(self, raw_value: str) -> None:
        try:
            value = int(raw_value)
        except ValueError:
            self._tool_log(f"[red]invalid max turns[/red] {raw_value}")
            return
        if value < 1:
            self._tool_log("[red]max turns must be >= 1[/red]")
            return
        self.max_auto_turns = value
        self._status()
        self._tool_log(f"[cyan]max turns[/cyan] {value}")

    def _set_side_view(self, side_view: str) -> None:
        self.side_view = side_view
        self._render_side_panel()
        self._status()

    def _usage_text(self) -> str:
        status = self._workbench_status()
        return (
            f"[dim]usage[/dim] messages={len(self.messages)} "
            f"tool_entries={len(self.tool_entries)} diff_entries={len(self.diff_entries)} "
            f"approvals={status['pending_approval_count']} "
            f"commands={status['running_command_count']}/{status['total_command_count']} "
            f"view={status['side_view']} style={status['output_style']} "
            f"compact={'on' if status['compact_active'] else 'off'} "
            f"ring={status['compact_ring']} "
            f"kept_messages={status['compact_kept_messages']} "
            f"max_turns={status['max_auto_turns']}"
        )

    def _config_text(self) -> str:
        status = self._workbench_status()
        return "\n".join(
            (
                "[bold]hao config[/bold]",
                f"model: {status['model_provider']}/{status['model_name']}",
                f"strength: {status['model_strength']}",
                f"workflow: {status['interaction_mode']}",
                f"target: {status['target']}",
                f"permissions: {status['permission_mode']}",
                f"output-style: {status['output_style']}",
                f"compact: {status['compact_ring']} kept={status['compact_kept_messages']}",
                f"session: {status['session_id'] or '-'}",
                f"run: {status['run_id'] or '-'}",
                f"cwd: {status['cwd']}",
                "[dim]Try /model, /permissions, /target, /output-style, /compact.[/dim]",
            )
        )

    def _handle_model_command(self, parts: list[str]) -> None:
        if len(parts) == 1:
            self._chat(f"[dim]model[/dim] {self.model_provider}/{self.model_name}")
            return
        if len(parts) == 2 and "/" in parts[1]:
            provider, model_name = parts[1].split("/", 1)
        elif len(parts) >= 3:
            provider = parts[1]
            model_name = " ".join(parts[2:])
        else:
            self._tool_log(
                "[yellow]usage[/yellow] /model [provider/model|provider model]"
            )
            return
        provider = provider.strip()
        model_name = model_name.strip()
        if not provider or not model_name:
            self._tool_log(
                "[yellow]usage[/yellow] /model [provider/model|provider model]"
            )
            return
        self.model_provider = provider
        self.model_name = model_name
        self._status()
        self._chat(f"[cyan]model[/cyan] {self.model_provider}/{self.model_name}")

    def _handle_output_style_command(self, parts: list[str]) -> None:
        if len(parts) == 1:
            styles = ", ".join(OUTPUT_STYLES)
            self._chat(f"[dim]output-style[/dim] {self.output_style} ({styles})")
            return
        if len(parts) != 2 or parts[1] not in OUTPUT_STYLES:
            styles = "|".join(OUTPUT_STYLES)
            self._tool_log(f"[yellow]usage[/yellow] /output-style [{styles}]")
            return
        self.output_style = parts[1]
        self._status()
        self._chat(f"[cyan]output-style[/cyan] {self.output_style}")

    def _resume_session(self, session_id: str) -> None:
        session = self.store.get_session(session_id)
        if session is None:
            self._tool_log(f"[red]session not found[/red] {session_id}")
            return
        self.agent_id = session.agent_id
        self.cwd = Path(session.cwd).expanduser().resolve()
        self.permission_mode = session.mode
        self.interaction_mode = session.cli_mode
        self.target = session.target
        self._load_session_state(session)
        self._refresh_workbench()
        self._status()
        self._chat(
            f"[cyan]resumed[/cyan] {session.id} workflow={self.interaction_mode} "
            f"target={self.target} permission={self.permission_mode}"
        )

    def _handle_todo_command(self, parts: list[str]) -> None:
        if self.session is None:
            self._tool_log("[red]session missing[/red]")
            return
        branch_id, leaf_id = self._active_branch_leaf()
        if len(parts) == 1:
            for entry in self._todo_entries():
                self._tool_log(entry)
            return
        action = parts[1]
        if action == "add" and len(parts) >= 3:
            todo = self.store.create_todo(
                self.session.id,
                title=" ".join(parts[2:]),
                source="user",
                branch_id=branch_id,
                leaf_id=leaf_id,
            )
            self._tool_log(f"[green]todo[/green] {todo['id']} {todo['title']}")
            self._refresh_workbench()
            return
        if action in {"done", "fail"} and len(parts) == 3:
            todo_id = self._resolve_branch_item_id("todo", parts[2])
            if todo_id is None:
                self._tool_log(f"[red]unknown todo[/red] {parts[2]}")
                return
            status = "done" if action == "done" else "failed"
            todo = self.store.update_todo(todo_id, status=status)
            self._tool_log(f"[cyan]todo[/cyan] {todo['id']} {todo['status']}")
            self._refresh_workbench()
            return
        self._tool_log("[yellow]usage[/yellow] /todo [add <title>|done <id>|fail <id>]")

    def _handle_verify_command(self, parts: list[str]) -> None:
        if self.session is None:
            self._tool_log("[red]session missing[/red]")
            return
        branch_id, leaf_id = self._active_branch_leaf()
        if len(parts) == 1:
            for entry in self._verification_entries():
                self._tool_log(entry)
            return
        action = parts[1]
        if action in {"pass", "fail"} and len(parts) >= 3:
            status = "passed" if action == "pass" else "failed"
            label = " ".join(parts[2:])
            verification = self.store.create_verification(
                self.session.id,
                label=label,
                status=status,
                branch_id=branch_id,
                leaf_id=leaf_id,
                evidence_summary=f"user marked {status}: {label}",
            )
            self._tool_log(
                f"[cyan]verification[/cyan] {verification['id']} {verification['status']}"
            )
            self._refresh_workbench()
            return
        self._tool_log("[yellow]usage[/yellow] /verify [pass <label>|fail <label>]")

    def _resolve_branch_item_id(self, item_type: str, raw_id: str) -> str | None:
        if self.session is None:
            return None
        branch_id, _ = self._active_branch_leaf()
        if item_type == "todo":
            rows = self.store.list_todos(self.session.id, branch_id=branch_id)
        else:
            rows = self.store.list_verifications(self.session.id, branch_id=branch_id)
        matches = [str(row["id"]) for row in rows if str(row["id"]).startswith(raw_id)]
        if len(matches) == 1:
            return matches[0]
        if raw_id in matches:
            return raw_id
        return None

    def _set_interaction_mode(self, interaction_mode: str) -> None:
        self.interaction_mode = interaction_mode
        if self.session:
            self.store.update_cli_mode(self.session.id, interaction_mode)
        self._status()
        self._chat(self._format_transcript_line("system", f"workflow {interaction_mode}"))

    def _backend_mode_for_interaction(self, interaction_mode: str) -> str:
        return "markdown_plan" if interaction_mode == "plan" else "cli_agent"

    def _act_intent_for_interaction(self, interaction_mode: str) -> dict[str, Any] | None:
        if interaction_mode != "act":
            return None
        return {"source": "slash_command", "allow_local_tools": True}

    def _workflow_metadata(self, interaction_mode: str) -> dict[str, Any]:
        return {
            "interaction_mode": interaction_mode,
            "backend_mode": self._backend_mode_for_interaction(interaction_mode),
            "act_intent": self._act_intent_for_interaction(interaction_mode),
        }

    def _continue_current_workflow(self) -> None:
        self.run_turn_worker(
            "Continue from the active path.",
            False,
            0,
            self.interaction_mode,
        )

    def _handle_compact_command(self, parts: list[str]) -> None:
        instructions = " ".join(parts[1:]).strip()
        if len(self.messages) <= 6:
            self._compact_summary = None
            self._compact_keep_from_index = 0
            self._status()
            self._chat(
                f"[dim]compact[/dim] skipped; active path has {len(self.messages)} messages."
            )
            return
        keep_count = 6
        self._compact_keep_from_index = max(0, len(self.messages) - keep_count)
        self._compact_summary = self._build_compact_summary(instructions)
        self._status()
        self._chat(
            f"[cyan]compact[/cyan] summarized {self._compact_keep_from_index} messages; "
            f"keeping latest {keep_count}."
        )

    def _build_compact_summary(self, instructions: str = "") -> str:
        role_counts: dict[str, int] = {}
        for message in self.messages[: self._compact_keep_from_index]:
            role = str(message.get("role") or "unknown")
            role_counts[role] = role_counts.get(role, 0) + 1
        summarized = self.messages[: self._compact_keep_from_index]
        last_user = self._latest_message_excerpt(summarized, "user")
        last_assistant = self._latest_message_excerpt(summarized, "assistant")
        counts = ", ".join(f"{role}={count}" for role, count in sorted(role_counts.items()))
        lines = [
            "hao compacted context summary:",
            f"summarized_messages={len(summarized)} roles={counts or 'none'}",
            f"last_user={last_user or 'none'}",
            f"last_assistant={last_assistant or 'none'}",
        ]
        if instructions:
            lines.append(f"user_compact_instructions={instructions}")
        lines.append("Use this as the only representation of earlier compacted turns.")
        return "\n".join(lines)

    def _latest_message_excerpt(
        self,
        messages: list[dict[str, Any]],
        role: str,
        *,
        limit: int = 220,
    ) -> str | None:
        for message in reversed(messages):
            if str(message.get("role") or "") != role:
                continue
            content = str(message.get("content") or "").replace("\n", " ").strip()
            if len(content) > limit:
                content = content[: limit - 3] + "..."
            return content
        return None

    def _model_visible_messages(self) -> list[dict[str, Any]]:
        if self._compact_summary is None or self._compact_keep_from_index <= 0:
            return [self._conversation_node(message) for message in self.messages]
        compact_message = self._conversation_node(
            {
                "id": "hao-compact-context",
                "role": "system",
                "content": self._compact_summary,
                "metadata": {"source": "hao_compact_context"},
            }
        )
        return [
            compact_message,
            *[
                self._conversation_node(message)
                for message in self.messages[self._compact_keep_from_index :]
            ],
        ]

    def _conversation_node(self, message: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(message.get("id") or "hao-local-context"),
            "parent_id": message.get("parent_id"),
            "children_ids": list(message.get("children_ids") or []),
            "role": str(message.get("role") or "system"),
            "content": str(message.get("content") or ""),
            "state": str(message.get("state") or "done"),
            "run_id": message.get("run_id"),
            "metadata": dict(message.get("metadata") or {}),
            "tool_calls": list(message.get("tool_calls") or []),
            "artifacts": list(message.get("artifacts") or []),
            "created_at": message.get("created_at"),
        }

    def _local_context_message(self, interaction_mode: str) -> dict[str, Any]:
        status = self._workbench_status()
        branch_id = status["active_branch_id"]
        todos: list[dict[str, Any]] = []
        verifications: list[dict[str, Any]] = []
        last_command: dict[str, Any] | None = None
        if self.session is not None:
            todos = self.store.list_todos(self.session.id, branch_id=branch_id)
            verifications = self.store.list_verifications(
                self.session.id,
                branch_id=branch_id,
            )
            commands = self.store.list_commands(self.session.id)
            if commands:
                last_command = commands[-1]
        todo_summary = "; ".join(
            f"{todo['status']}:{todo['title']}" for todo in todos[-8:]
        ) or "none"
        verification_summary = "; ".join(
            f"{verification['status']}:{verification['label']}"
            for verification in verifications[-8:]
        ) or "none"
        command_summary = "none"
        if last_command is not None:
            command_summary = (
                f"{last_command['tool_name']} {last_command['status']} "
                f"exit={last_command['exit_code']} {last_command['command']}"
            )
        repo_summary = self._git_context_summary()
        recent_diff = "; ".join(self._git_status_lines(limit=6)) or "clean"
        recent_test = self._recent_test_hint()
        output_style_instruction = OUTPUT_STYLES[self.output_style]
        content = (
            "hao local context: "
            f"cwd={status['cwd']} target={status['target']} "
            f"permission={status['permission_mode']} workflow={interaction_mode} "
            f"output_style={self.output_style} "
            f"session={status['session_id']} run={status['run_id']} "
            f"branch={status['active_branch_id']} leaf={status['active_leaf_id']} "
            f"approvals={status['pending_approval_count']} "
            f"commands={status['running_command_count']}/{status['total_command_count']} "
            f"compact={'on' if status['compact_active'] else 'off'} "
            f"compact_kept_messages={status['compact_kept_messages']} "
            f"max_auto_turns={self.max_auto_turns}\n"
            f"output_style_instruction: {output_style_instruction}\n"
            f"todos: {todo_summary}\n"
            f"verifications: {verification_summary}\n"
            f"repo: {repo_summary}\n"
            f"recent_diff: {recent_diff}\n"
            f"recent_test: {recent_test}\n"
            f"last_command: {command_summary}"
        )
        return self._conversation_node(
            {
                "id": "hao-local-context",
                "role": "system",
                "content": content,
                "metadata": {"source": "hao_local_context"},
            }
        )

    def _branch_to_message(self, message_id: str) -> None:
        if self.session is None:
            self._safe_call(self._tool_log, "[red]session missing[/red]")
            return
        messages = {message["id"]: message for message in self.store.list_messages(self.session.id)}
        if message_id not in messages:
            self._safe_call(self._tool_log, f"[red]unknown branch leaf[/red] {message_id}")
            return
        try:
            self.store.set_active_leaf(self.session.id, message_id)
        except Exception as exc:
            self._safe_call(self._tool_log, f"[red]branch failed[/red] {exc}")
            return
        self.messages = self.store.list_active_path(self.session.id)
        self._rebuild_plan_entries()
        self._refresh_workbench()
        self._status()

    def _build_stream_payload(self, goal: str, interaction_mode: str) -> dict[str, Any]:
        workflow_metadata = self._workflow_metadata(interaction_mode)
        return {
            "mode": workflow_metadata["backend_mode"],
            "goal": goal,
            "run_id": self.run_id,
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "messages": [
                self._local_context_message(interaction_mode),
                *self._model_visible_messages(),
            ],
            "context_window_turns": 24,
            "interaction_mode": workflow_metadata["interaction_mode"],
            "turn_mode": workflow_metadata["interaction_mode"],
            "act_intent": workflow_metadata["act_intent"],
        }

    def _record_message_ui(
        self,
        role: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.session is None:
            raise RuntimeError("session not initialized")
        message = self.store.append_message(
            self.session.id,
            role=role,
            content=content,
            run_id=self.run_id,
            metadata=metadata,
        )
        self.messages.append(message)
        return message

    def _record_message_thread(
        self,
        role: str,
        content: str,
        *,
        tool_event_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.session is None:
            raise RuntimeError("session not initialized")
        message = self.store.append_message(
            self.session.id,
            role=role,
            content=content,
            run_id=self.run_id,
            tool_event_id=tool_event_id,
            metadata=metadata,
        )
        self.messages.append(message)
        return message

    @work(thread=True)
    def run_turn_worker(
        self,
        goal: str,
        append_user: bool,
        depth: int,
        interaction_mode: str,
    ) -> None:
        del append_user
        self._run_turn_sync(goal, depth, interaction_mode)

    def _run_turn_sync(self, goal: str, depth: int, interaction_mode: str) -> None:
        payload = self._build_stream_payload(goal, interaction_mode)
        assistant_chunks: list[str] = []
        executed_results: list[str] = []
        assistant_started = False
        try:
            for event in self.api_client.stream_chat(self.agent_id, payload):
                if self.session:
                    self.store.record_stream_event(
                        self.session.id,
                        event=event.event,
                        data=event.data,
                        raw=event.raw,
                    )
                if event.event == "run_created":
                    self._set_run_id(str(event.data.get("run_id") or ""))
                elif event.event == "delta":
                    content = str(event.data.get("content") or "")
                    assistant_chunks.append(content)
                    if not assistant_started:
                        assistant_started = True
                        self._safe_call(self._stream_assistant_begin)
                    self._safe_call(self._stream_assistant_append, content)
                    if interaction_mode == "plan":
                        self.plan_entries.append(content.rstrip("\n"))
                        self._safe_call(self._refresh_workbench)
                elif event.event == "tool_call_requested":
                    if interaction_mode == "plan":
                        self._safe_call(
                            self._tool_log,
                            f"[yellow]ignored[/yellow] {event.data.get('tool_call_id') or 'tool'} "
                            "in plan mode",
                        )
                    else:
                        approval_count_before = self._pending_approval_count()
                        self._last_tool_audit_failed = False
                        result_message = self._handle_tool_request(event, interaction_mode)
                        if result_message:
                            executed_results.append(result_message)
                        if self._last_tool_audit_failed:
                            break
                        if self._pending_approval_count() > approval_count_before:
                            break
                elif event.event == "error":
                    self._safe_call(
                        self._chat,
                        f"[red]stream error[/red] {event.data.get('message')}",
                    )
        except Exception as exc:
            self._safe_call(self._chat, self._format_stream_failure(exc))
            return
        assistant_content = "".join(assistant_chunks).strip()
        if assistant_content:
            if interaction_mode == "plan" and not self.plan_entries:
                self.plan_entries.append(assistant_content)
            self._record_message_thread(
                "assistant",
                assistant_content,
                metadata=self._workflow_metadata(interaction_mode),
            )
            self._safe_call(self._status)
        self._safe_call(self._chat_stream_end)
        if (
            executed_results
            and self._can_auto_continue(depth)
            and self._pending_approval_count() == 0
        ):
            self._run_turn_sync(
                "Continue using the local tool results.",
                depth + 1,
                interaction_mode,
            )

    def _format_stream_failure(self, exc: Exception) -> str:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        if status_code == 401:
            return (
                "[red]stream failed[/red] authentication failed (401). "
                "Run `hao login --api-url http://127.0.0.1:8000 --token <token>` "
                "or set HAO_API_TOKEN."
            )
        if status_code == 403:
            return (
                "[red]stream failed[/red] permission denied (403). "
                "Check the saved hao token and agent access."
            )
        return f"[red]stream failed[/red] {exc}"

    def _can_auto_continue(self, depth: int) -> bool:
        return depth < self.max_auto_turns

    def _set_run_id(self, run_id: str) -> None:
        if not run_id:
            return
        self.run_id = run_id
        if self.session:
            self.store.update_run_id(self.session.id, run_id)
        self._safe_call(self._status)

    def _handle_tool_request(self, event: SSEEvent, interaction_mode: str) -> str | None:
        if self.run_id is None:
            self._safe_call(self._tool_log, "[red]tool request arrived before run_id[/red]")
            return None
        tool_name = str(event.data.get("tool_name") or "")
        input_json = event.data.get("input_json") if isinstance(event.data, dict) else {}
        if not isinstance(input_json, dict):
            input_json = {}
        workflow_metadata = self._workflow_metadata(interaction_mode)
        execution_target = self.target
        permission_mode = self.permission_mode
        decision = PermissionEngine(permission_mode).decide(
            tool_name,
            input_json,
            target=execution_target,
        )
        pending_id = self._pending_tool_id(event.data.get("tool_call_id"), tool_name)
        if decision.denied:
            result = ToolExecutionResult(
                tool_name=tool_name,
                status="DENIED",
                input_json=input_json,
                output_json={"denied": True, "reason": decision.reason},
                duration_ms=0,
                error_message=decision.reason,
            )
            return self._record_tool_result(
                result,
                decision.risk_level,
                workflow_metadata=workflow_metadata,
                execution_target=execution_target,
                permission_mode=permission_mode,
            )
        if execution_target == "host" and tool_name in WRITE_COMMAND_TOOLS:
            return self._handle_pending_change_request(
                tool_name,
                input_json,
                decision.risk_level,
                decision.requires_confirmation,
                workflow_metadata=workflow_metadata,
                execution_target=execution_target,
                permission_mode=permission_mode,
            )
        if decision.requires_confirmation:
            self.pending_tools[pending_id] = PendingTool(
                pending_id=pending_id,
                run_id=self.run_id,
                tool_name=tool_name,
                input_json=input_json,
                decision=decision,
                workflow_metadata=workflow_metadata,
                execution_target=execution_target,
                permission_mode=permission_mode,
            )
            self._safe_call(
                self._approval_log,
                f"[yellow]pending[/yellow] {pending_id} {tool_name}: {decision.reason}",
            )
            self._safe_call(
                self._tool_log,
                f"[yellow]pending[/yellow] {pending_id} {tool_name}: {decision.reason}",
            )
            return None
        return self._execute_tool(
            tool_name,
            input_json,
            decision.risk_level,
            workflow_metadata=workflow_metadata,
            execution_target=execution_target,
            permission_mode=permission_mode,
        )

    @work(thread=True)
    def approve_tool_worker(self, pending_id: str) -> None:
        pending = self.pending_tools.pop(pending_id, None)
        if pending is None:
            self._safe_call(self._tool_log, f"[red]unknown pending tool[/red] {pending_id}")
            return
        result_message = self._execute_tool(
            pending.tool_name,
            pending.input_json,
            pending.decision.risk_level,
            workflow_metadata=pending.workflow_metadata,
            execution_target=pending.execution_target,
            permission_mode=pending.permission_mode,
        )
        if result_message and self.run_id:
            self._run_turn_sync(
                "Continue using the approved local tool result.",
                1,
                str(pending.workflow_metadata["interaction_mode"]),
            )

    @work(thread=True)
    def approve_change_worker(self, change_id: str) -> None:
        if self.session is None:
            self._safe_call(self._tool_log, "[red]session missing[/red]")
            return
        try:
            change = self.store.get_pending_change(change_id)
        except Exception as exc:
            self._safe_call(self._tool_log, f"[red]pending change lookup failed[/red] {exc}")
            return
        if change is None:
            self._safe_call(self._tool_log, f"[red]unknown pending change[/red] {change_id}")
            return
        if change["status"] != "pending":
            self._safe_call(
                self._tool_log,
                f"[yellow]pending change not pending[/yellow] {change_id} {change['status']}",
            )
            return
        approval_metadata = change.get("metadata") or {}
        workflow_metadata = approval_metadata.get("workflow_metadata")
        if not isinstance(workflow_metadata, dict):
            workflow_metadata = self._workflow_metadata(self.interaction_mode)
        execution_target = str(approval_metadata.get("execution_target") or "host")
        permission_mode = str(approval_metadata.get("permission_mode") or self.permission_mode)
        risk_level = str(approval_metadata.get("risk_level") or "high")
        commit_tool = self._commit_tool_name(change["tool_name"])
        if commit_tool is None:
            self._safe_call(
                self._tool_log,
                f"[red]unsupported pending change tool[/red] {change['tool_name']}",
            )
            return
        result_message = self._execute_tool(
            commit_tool,
            {"change_id": change_id},
            risk_level,
            workflow_metadata=workflow_metadata,
            execution_target=execution_target,
            permission_mode=permission_mode,
            audit_host=False,
        )
        if result_message and self.run_id:
            self._run_turn_sync(
                "Continue using the approved local tool result.",
                1,
                str(workflow_metadata["interaction_mode"]),
            )

    def reject_tool(self, pending_id: str) -> None:
        pending = self.pending_tools.pop(pending_id, None)
        if pending is None:
            self._reject_pending_change(pending_id)
            return
        result = ToolExecutionResult(
            tool_name=pending.tool_name,
            status="DENIED",
            input_json=pending.input_json,
            output_json={"denied": True, "reason": "user rejected local tool"},
            duration_ms=0,
            error_message="user rejected local tool",
        )
        self._record_tool_result(
            result,
            pending.decision.risk_level,
            workflow_metadata=pending.workflow_metadata,
            execution_target=pending.execution_target,
            permission_mode=pending.permission_mode,
        )

    @work(thread=True)
    def reject_change_worker(self, change_id: str) -> None:
        self._reject_pending_change(change_id)

    def _reject_pending_change(self, change_id: str) -> None:
        if self.session is None:
            self._safe_call(self._tool_log, "[red]session missing[/red]")
            return
        change = self.store.get_pending_change(change_id)
        if change is None:
            self._safe_call(self._tool_log, f"[red]unknown pending change[/red] {change_id}")
            return
        if change["status"] != "pending":
            self._safe_call(
                self._tool_log,
                f"[yellow]pending change not pending[/yellow] {change_id} {change['status']}",
            )
            return
        approval_metadata = change.get("metadata") or {}
        workflow_metadata = approval_metadata.get("workflow_metadata")
        if not isinstance(workflow_metadata, dict):
            workflow_metadata = self._workflow_metadata(self.interaction_mode)
        execution_target = str(approval_metadata.get("execution_target") or "host")
        permission_mode = str(approval_metadata.get("permission_mode") or self.permission_mode)
        risk_level = str(approval_metadata.get("risk_level") or "high")
        try:
            updated = self.store.update_pending_change_status(
                change_id,
                status="rejected",
                error_message="user rejected local change",
            )
        except Exception as exc:
            self._safe_call(self._tool_log, f"[red]reject failed[/red] {exc}")
            return
        result = ToolExecutionResult(
            tool_name=str(change["tool_name"]),
            status="DENIED",
            input_json=change["input_json"],
            output_json={
                "denied": True,
                "reason": "user rejected local change",
                "change_id": change_id,
                "change_status": updated["status"],
            },
            duration_ms=0,
            error_message="user rejected local change",
        )
        self._record_tool_result(
            result,
            risk_level,
            workflow_metadata=workflow_metadata,
            execution_target=execution_target,
            permission_mode=permission_mode,
        )

    def _execute_tool(
        self,
        tool_name: str,
        input_json: dict[str, Any],
        risk_level: str,
        *,
        workflow_metadata: dict[str, Any] | None = None,
        execution_target: str | None = None,
        permission_mode: str | None = None,
        audit_host: bool = True,
    ) -> str | None:
        if workflow_metadata is None:
            workflow_metadata = self._workflow_metadata(self.interaction_mode)
        execution_target = execution_target or self.target
        permission_mode = permission_mode or self.permission_mode
        if execution_target == "sandbox":
            if not self.run_id:
                self._safe_call(self._tool_log, "[red]sandbox tool missing run_id[/red]")
                return None
            try:
                sandbox_result = execute_sandbox_tool(
                    self.api_client,
                    run_id=self.run_id,
                    tool_name=tool_name,
                    input_json=input_json,
                )
            except Exception as exc:
                self._safe_call(self._tool_log, f"[red]sandbox failed[/red] {exc}")
                return None
            result = ToolExecutionResult(
                tool_name=tool_name,
                status=sandbox_result.status,
                input_json=input_json,
                output_json=sandbox_result.output_json,
                duration_ms=sandbox_result.duration_ms,
                error_message=sandbox_result.error_message,
            )
            return self._record_tool_result(
                result,
                risk_level,
                backend_tool_call_id=sandbox_result.tool_call_id,
                audit_host=False,
                workflow_metadata=workflow_metadata,
                execution_target=execution_target,
                permission_mode=permission_mode,
            )
        session_aware_tools = SHELL_COMMAND_TOOLS | WRITE_COMMAND_TOOLS
        session_aware_tools |= PREVIEW_COMMAND_TOOLS | COMMIT_COMMAND_TOOLS
        if self.session is not None and tool_name in session_aware_tools:
            result = execute_local_tool(
                tool_name,
                input_json,
                self.cwd,
                session_store=self.store,
                session_id=self.session.id,
            )
        else:
            result = execute_local_tool(tool_name, input_json, self.cwd)
        return self._record_tool_result(
            result,
            risk_level,
            audit_host=audit_host,
            workflow_metadata=workflow_metadata,
            execution_target=execution_target,
            permission_mode=permission_mode,
        )

    def _record_tool_result(
        self,
        result: ToolExecutionResult,
        risk_level: str,
        *,
        backend_tool_call_id: str | None = None,
        audit_host: bool = True,
        workflow_metadata: dict[str, Any] | None = None,
        execution_target: str | None = None,
        permission_mode: str | None = None,
    ) -> str | None:
        tool_call_id = backend_tool_call_id
        if workflow_metadata is None:
            workflow_metadata = self._workflow_metadata(self.interaction_mode)
        execution_target = execution_target or self.target
        permission_mode = permission_mode or self.permission_mode
        audit_error: str | None = None
        if audit_host and self.run_id:
            try:
                response = self.api_client.record_local_tool_event(
                    self.run_id,
                    {
                        "tool_name": result.tool_name,
                        "input_json": result.input_json,
                        "output_json": result.output_json,
                        "status": result.status,
                        "risk_level": risk_level,
                        "requires_sandbox": False,
                        "duration_ms": result.duration_ms,
                        "error_message": result.error_message,
                        "execution_target": execution_target,
                        "permission_mode": permission_mode,
                        "local_session_id": self.session.id if self.session else None,
                        "cwd": str(self.cwd),
                        "interaction_mode": workflow_metadata["interaction_mode"],
                        "act_intent": workflow_metadata["act_intent"],
                    },
                )
                tool_call = response.get("tool_call", {})
                if isinstance(tool_call, dict):
                    tool_call_id = str(tool_call.get("id") or "") or tool_call_id
            except Exception as exc:
                audit_error = str(exc)
                self._safe_call(
                    self._tool_log,
                    f"[red]audit failed[/red] {audit_error}; local tool result not continued",
                )
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
        tool_event_id: str | None = None
        if self.session:
            tool_event_id = self.store.record_tool_event(
                self.session.id,
                run_id=self.run_id,
                tool_call_id=tool_call_id,
                tool_name=stored_result.tool_name,
                status=stored_result.status,
                input_json=stored_result.input_json,
                output_json=stored_result.output_json,
                duration_ms=stored_result.duration_ms,
            )
            if (
                "diff" in stored_result.output_json
                and isinstance(stored_result.output_json["diff"], str)
            ):
                self.diff_entries.append(
                    f"[bold]{stored_result.tool_name}[/bold] "
                    f"{stored_result.status}\n{stored_result.output_json['diff']}"
                )
                if self.side_view == "diff":
                    self._safe_call(self._refresh_workbench)
            command_id = None
            if isinstance(stored_result.output_json, dict):
                command_id_value = stored_result.output_json.get("command_id")
                if command_id_value:
                    command_id = str(command_id_value)
            tool_entry = (
                f"[bold]{stored_result.tool_name}[/bold] "
                f"{stored_result.status} {stored_result.duration_ms}ms"
                + (f" command={command_id}" if command_id else "")
            )
            self.tool_entries.append(tool_entry)
            self._safe_call(self._inline_workbench_message, "tool", tool_entry)
            if command_id and tool_event_id is not None:
                try:
                    self.store.link_command_tool_event(command_id, tool_event_id)
                except Exception as exc:
                    self._safe_call(self._tool_log, f"[red]command link failed[/red] {exc}")
                self._maybe_record_verification(
                    stored_result,
                    command_id=command_id,
                    tool_event_id=tool_event_id,
                )
            change_id = None
            if isinstance(stored_result.output_json, dict):
                change_id_value = stored_result.output_json.get("change_id")
                if change_id_value:
                    change_id = str(change_id_value)
            if change_id and tool_event_id is not None:
                try:
                    self.store.link_pending_change_tool_event(change_id, tool_event_id)
                except Exception as exc:
                    self._safe_call(self._tool_log, f"[red]change link failed[/red] {exc}")
        if audit_error is not None:
            self._last_tool_audit_failed = True
            self._safe_call(self._refresh_workbench)
            return None
        self._last_tool_audit_failed = False
        compact = json.dumps(result.output_json, ensure_ascii=False)[:4000]
        message = f"Local tool result {result.tool_name} status={result.status}: {compact}"
        self._record_message_thread(
            "tool",
            message,
            tool_event_id=tool_event_id,
            metadata={
                "tool_name": result.tool_name,
                "status": result.status,
                "tool_call_id": tool_call_id,
                "execution_target": execution_target,
                "permission_mode": permission_mode,
                **workflow_metadata,
            },
        )
        self._safe_call(self._refresh_workbench)
        return message

    def _maybe_record_verification(
        self,
        result: ToolExecutionResult,
        *,
        command_id: str,
        tool_event_id: str,
    ) -> None:
        if self.session is None or result.tool_name != "run_tests":
            return
        active_leaf = self._active_leaf_message()
        branch_id = None if active_leaf is None else str(active_leaf["branch_id"])
        leaf_id = None if active_leaf is None else str(active_leaf["id"])
        output = result.output_json
        status = "passed" if result.status == "SUCCESS" else "failed"
        command = str(output.get("command") or result.input_json.get("command") or "run_tests")
        exit_code = output.get("exit_code")
        evidence_summary = f"{command} -> {status}"
        if exit_code is not None:
            evidence_summary += f" exit={exit_code}"
        stdout = str(output.get("stdout") or "").strip()
        stderr = str(output.get("stderr") or "").strip()
        if stdout:
            evidence_summary += f" stdout={stdout.splitlines()[0][:120]}"
        elif stderr:
            evidence_summary += f" stderr={stderr.splitlines()[0][:120]}"
        try:
            self.store.create_verification(
                self.session.id,
                label=command,
                status=status,
                branch_id=branch_id,
                leaf_id=leaf_id,
                command_id=command_id,
                tool_event_id=tool_event_id,
                evidence_summary=evidence_summary,
                metadata={"tool_name": result.tool_name, "tool_status": result.status},
            )
        except Exception as exc:
            self._safe_call(self._tool_log, f"[red]verification record failed[/red] {exc}")

    def _commit_tool_name(self, tool_name: str) -> str | None:
        if tool_name == "write_file":
            return "commit_write_file"
        if tool_name == "apply_patch":
            return "commit_apply_patch"
        return None

    def _pending_tool_id(self, raw_id: Any, tool_name: str) -> str:
        value = str(raw_id or tool_name).strip() or tool_name
        if value.startswith("tool-"):
            return value
        return f"tool-{value}"

    def _handle_pending_change_request(
        self,
        tool_name: str,
        input_json: dict[str, Any],
        risk_level: str,
        requires_confirmation: bool,
        *,
        workflow_metadata: dict[str, Any],
        execution_target: str,
        permission_mode: str,
    ) -> str | None:
        if self.session is None:
            self._safe_call(self._tool_log, "[red]session missing[/red]")
            return None
        pending_change_metadata = {
            "workflow_metadata": workflow_metadata,
            "execution_target": execution_target,
            "permission_mode": permission_mode,
            "risk_level": risk_level,
        }
        result = execute_local_tool(
            tool_name,
            input_json,
            self.cwd,
            session_store=self.store,
            session_id=self.session.id,
            pending_change_metadata=pending_change_metadata,
        )
        preview_message = self._record_tool_result(
            result,
            risk_level,
            workflow_metadata=workflow_metadata,
            execution_target=execution_target,
            permission_mode=permission_mode,
        )
        change_id = str(result.output_json.get("change_id") or "")
        if result.status == "SUCCESS" and preview_message is None and change_id:
            try:
                self.store.update_pending_change_status(
                    change_id,
                    status="failed",
                    error_message="audit failed before local change approval",
                )
            except Exception as exc:
                self._safe_call(self._tool_log, f"[red]change status update failed[/red] {exc}")
            return None
        if result.status != "SUCCESS":
            return preview_message
        if requires_confirmation:
            self._safe_call(
                self._approval_log,
                f"[yellow]pending change[/yellow] {change_id} {tool_name}",
            )
            self._safe_call(
                self._tool_log,
                f"[yellow]pending change[/yellow] {change_id} {tool_name}",
            )
            return None
        commit_tool = self._commit_tool_name(tool_name)
        if commit_tool is None:
            self._safe_call(self._tool_log, f"[red]unsupported write tool[/red] {tool_name}")
            return preview_message
        commit_result = execute_local_tool(
            commit_tool,
            {"change_id": change_id},
            self.cwd,
            session_store=self.store,
            session_id=self.session.id,
        )
        return self._record_tool_result(
            commit_result,
            risk_level,
            audit_host=False,
            workflow_metadata=workflow_metadata,
            execution_target=execution_target,
            permission_mode=permission_mode,
        )

    @work(thread=True)
    def retry_command_worker(self, command_id: str) -> None:
        if self.session is None:
            self._safe_call(self._tool_log, "[red]session missing[/red]")
            return
        try:
            result = retry_local_command_tool(
                command_id,
                self.cwd,
                session_store=self.store,
            )
        except Exception as exc:
            self._safe_call(self._tool_log, f"[red]retry failed[/red] {exc}")
            return
        self._record_tool_result(
            result,
            "high",
            workflow_metadata=self._workflow_metadata(self.interaction_mode),
            execution_target=self.target,
            permission_mode=self.permission_mode,
        )
