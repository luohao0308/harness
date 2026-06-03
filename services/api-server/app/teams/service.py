"""Team Session service and Team Mode product surface orchestration."""

# ruff: noqa: E501

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime, timedelta
from threading import Lock

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.model_gateway import ModelMessage, ModelResponse
from app.agents.registry import ensure_default_agents
from app.agents.specialists import (
    SubagentSpecialistRegistry,
    ensure_system_specialists,
    make_default_output,
    normalize_budget,
    output_schema_sha256,
)
from app.agents.subagent_manager import SubagentManager
from app.db.models import (
    AdminAuditEvent,
    Agent,
    AgentMessage,
    AgentRun,
    AgentSession,
    Task,
    Team,
    TeamAgent,
    TeamEvent,
    TeamMailboxMessage,
    TeamTask,
    utc_now,
)
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.teams.model_runtime import GatewayTeamModelRuntime, TeamModelRuntime

TEAM_TOOL_NAMES = {
    "team_send_message",
    "team_task_create",
    "team_task_update",
    "team_task_list",
    "team_members",
    "team_spawn_agent",
    "team_rename_agent",
    "team_shutdown_agent",
    "team_list_models",
    "team_describe_assistant",
}

VALID_AGENT_STATUSES = {"pending", "idle", "active", "completed", "failed"}
VALID_TASK_STATUSES = {"pending", "in_progress", "completed", "deleted"}
VALID_WORKSPACE_MODES = {"shared", "isolated"}
VALID_MESSAGE_MODES = {"chat", "markdown_plan", "plan", "goal"}
SHUTDOWN_APPROVED = "shutdown_approved"
SHUTDOWN_REJECTED_PREFIX = "shutdown_rejected"
WAKE_TIMEOUT_SECONDS = 60
TEAM_TOOL_CALL_RE = re.compile(r"<team_tool_call>\s*(\{.*?\})\s*</team_tool_call>", re.DOTALL)
MAX_TEAM_TOOL_CALLS_PER_TURN = 4

_TEAM_EVENT_SEQUENCE_LOCKS: dict[str, Lock] = {}
_TEAM_EVENT_SEQUENCE_COUNTERS: dict[str, int] = {}
_TEAM_EVENT_SEQUENCE_LOCKS_GUARD = Lock()

TEAM_TOOL_PROTOCOL_PROMPT = """## Harness Team Tool Protocol
Team coordination must change persistent team state through explicit team tool calls.
Use this exact XML-wrapped JSON form when coordinating:
<team_tool_call>{"tool":"team_send_message","args":{"to":"产品","message":"..."}}</team_tool_call>
<team_tool_call>{"tool":"team_spawn_agent","args":{"name":"Research Agent","agent_id":"default"}}</team_tool_call>
<team_tool_call>{"tool":"team_task_create","args":{"subject":"搜集小说资料","owner":"Research Agent"}}</team_tool_call>
<team_tool_call>{"tool":"team_task_update","args":{"task_id":"dfd23488","status":"completed"}}</team_tool_call>
You may emit multiple <team_tool_call> blocks in one turn.

Critical rules:
- If you say you are creating, spawning, adding, or assigning a teammate, call team_spawn_agent in that same turn.
- If the user confirms a previously proposed lineup, create the proposed teammates immediately with team_spawn_agent.
- Do not claim that teammates were created, started, notified, assigned, or are working unless the corresponding team tool calls were emitted.
- Use team_task_create and team_send_message to assign real work after spawning teammates.
- Use the short bracketed task id from the task board, for example [dfd23488], as task_id when updating a task."""


class TeamSessionService:
    def __init__(
        self,
        session: Session,
        organization_id: str,
        actor_id: str,
        *,
        model_runtime: TeamModelRuntime | None = None,
    ) -> None:
        self.session = session
        self.organization_id = organization_id
        self.actor_id = actor_id
        self.model_runtime = model_runtime or GatewayTeamModelRuntime(session)

    @staticmethod
    def _event_sequence_lock(team_id: str) -> Lock:
        with _TEAM_EVENT_SEQUENCE_LOCKS_GUARD:
            lock = _TEAM_EVENT_SEQUENCE_LOCKS.get(team_id)
            if lock is None:
                lock = Lock()
                _TEAM_EVENT_SEQUENCE_LOCKS[team_id] = lock
            return lock

    def list_teams(self) -> list[Team]:
        statement = (
            select(Team)
            .where(Team.organization_id == self.organization_id)
            .order_by(Team.updated_at.desc(), Team.created_at.desc())
        )
        return list(self.session.execute(statement).scalars())

    def create_team(
        self,
        *,
        name: str,
        workspace: str = "",
        workspace_mode: str = "shared",
        leader_agent_id: str = "default",
        leader_name: str = "Leader",
        seed_messages: list[dict] | None = None,
    ) -> Team:
        if workspace_mode not in VALID_WORKSPACE_MODES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="workspace_mode 无效"
            )
        ensure_default_agents(self.session, self.organization_id)
        leader_definition = self._get_agent_definition(leader_agent_id)
        team_name = self._normalize_team_name(name)
        self._ensure_team_name_available(team_name)
        now = utc_now()
        team = Team(
            organization_id=self.organization_id,
            name=team_name,
            status="ACTIVE",
            workspace=workspace,
            workspace_mode=workspace_mode,
            leader_slot_id="leader",
            created_by=self.actor_id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(team)
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="团队名称已存在"
            ) from exc
        leader = TeamAgent(
            team_id=team.id,
            organization_id=self.organization_id,
            slot_id="leader",
            agent_id=leader_definition.id,
            role="leader",
            agent_name=leader_name.strip() or "Leader",
            status="pending",
            model_provider=leader_definition.model_provider,
            model_name=leader_definition.model_name,
            metadata_json={
                "team_tools": sorted(TEAM_TOOL_NAMES),
                "wake": {"last_woke_at": now.isoformat()},
            },
            created_at=now,
            updated_at=now,
        )
        self.session.add(leader)
        self.session.flush()
        self._ensure_agent_session(team=team, agent=leader)
        seeded_messages = self._seed_agent_session(
            team=team,
            agent=leader,
            messages=seed_messages or [],
        )
        self.append_event(
            team_id=team.id,
            event_type="TEAM_CREATED",
            payload={
                "team": self.team_summary(team),
                "agent": self.agent_summary(leader),
                "seeded_message_count": len(seeded_messages),
            },
            actor_type="user",
        )
        if seeded_messages:
            self.append_event(
                team_id=team.id,
                event_type="TEAM_AGENT_SESSION_MESSAGE",
                payload={
                    "slot_id": leader.slot_id,
                    "messages": [
                        self.session_message_summary(message) for message in seeded_messages
                    ],
                },
                actor_type="user",
                actor_id=self.actor_id,
            )
        return team

    def get_team(self, team_id: str) -> Team:
        team = self.session.get(Team, team_id)
        if team is None or team.organization_id != self.organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
        return team

    def rename_team(self, team_id: str, name: str) -> Team:
        team = self.get_team(team_id)
        team_name = self._normalize_team_name(name)
        self._ensure_team_name_available(team_name, exclude_team_id=team.id)
        team.name = team_name
        team.updated_at = utc_now()
        try:
            self.append_event(
                team_id=team.id,
                event_type="TEAM_RENAMED",
                payload={"team_id": team.id, "name": team.name},
                actor_type="user",
            )
        except IntegrityError as exc:
            self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="团队名称已存在"
            ) from exc
        return team

    def archive_team(self, team_id: str) -> Team:
        team = self.get_team(team_id)
        team.status = "ARCHIVED"
        team.updated_at = utc_now()
        self.append_event(
            team_id=team.id,
            event_type="TEAM_ARCHIVED",
            payload={"team_id": team.id},
            actor_type="user",
        )
        return team

    def add_agent(
        self,
        *,
        team_id: str,
        agent_id: str,
        agent_name: str,
        role: str = "teammate",
        model_provider: str | None = None,
        model_name: str | None = None,
        wake_welcome: bool = True,
    ) -> TeamAgent:
        team = self.get_team(team_id)
        if role != "teammate":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="只能添加 teammate"
            )
        agent_definition = self._get_agent_definition(agent_id)
        slot_id = self._next_slot_id(team_id=team.id, name=agent_name)
        now = utc_now()
        agent = TeamAgent(
            team_id=team.id,
            organization_id=self.organization_id,
            slot_id=slot_id,
            agent_id=agent_definition.id,
            role="teammate",
            agent_name=agent_name.strip(),
            status="pending",
            model_provider=model_provider or agent_definition.model_provider,
            model_name=model_name or agent_definition.model_name,
            metadata_json={"team_tools": sorted(TEAM_TOOL_NAMES)},
            created_at=now,
            updated_at=now,
        )
        self.session.add(agent)
        team.updated_at = now
        self.session.flush()
        self._ensure_agent_session(team=team, agent=agent)
        welcome = self.write_message(
            team_id=team.id,
            target=slot_id,
            content=(
                f'You have been spawned as "{agent.agent_name}" and added to the team. '
                "Check the task board and await instructions."
            ),
            from_agent_slot_id="leader",
            message_type="system",
            wake_recipient=wake_welcome,
        )
        self.append_event(
            team_id=team.id,
            event_type="TEAM_AGENT_SPAWNED",
            payload={"agent": self.agent_summary(agent), "message": self.message_summary(welcome)},
            actor_type="agent",
            actor_id="leader",
        )
        return agent

    def update_agent(
        self,
        *,
        team_id: str,
        slot_id: str,
        agent_name: str | None = None,
        model_provider: str | None = None,
        model_name: str | None = None,
    ) -> TeamAgent:
        team = self.get_team(team_id)
        agent = self.get_agent(team.id, slot_id)
        old_name = agent.agent_name
        old_model_provider = agent.model_provider
        old_model_name = agent.model_name
        trimmed_name = agent_name.strip() if agent_name is not None else None
        trimmed_provider = model_provider.strip() if model_provider is not None else None
        trimmed_model = model_name.strip() if model_name is not None else None
        renamed = bool(trimmed_name and trimmed_name != agent.agent_name)
        model_changed = False
        if trimmed_provider:
            model_changed = model_changed or trimmed_provider != agent.model_provider
            agent.model_provider = trimmed_provider
        if trimmed_model:
            model_changed = model_changed or trimmed_model != agent.model_name
            agent.model_name = trimmed_model
        if renamed:
            agent.agent_name = trimmed_name
        if not renamed and not model_changed:
            return agent
        now = utc_now()
        agent.updated_at = now
        team.updated_at = agent.updated_at
        metadata = dict(agent.metadata_json or {})
        if renamed:
            metadata.setdefault("original_name", old_name)
            metadata["renamed_at"] = agent.updated_at.isoformat()
        if model_changed:
            metadata["model_updated_at"] = agent.updated_at.isoformat()
            metadata["previous_model"] = {
                "model_provider": old_model_provider,
                "model_name": old_model_name,
            }
        agent.metadata_json = metadata
        session = self._get_agent_session(agent.session_id)
        if session is not None and renamed:
            session.title = f"Team: {team.name} / {agent.agent_name}"
            session.updated_at = agent.updated_at
        if renamed:
            self.append_event(
                team_id=team.id,
                event_type="TEAM_AGENT_RENAMED",
                payload={"slot_id": slot_id, "old_name": old_name, "new_name": agent.agent_name},
                actor_type="user",
            )
        if model_changed:
            self.append_event(
                team_id=team.id,
                event_type="TEAM_AGENT_STATUS",
                payload={"agent": self.agent_summary(agent)},
                actor_type="user",
            )
        return agent

    def rename_agent(self, *, team_id: str, slot_id: str, agent_name: str) -> TeamAgent:
        return self.update_agent(team_id=team_id, slot_id=slot_id, agent_name=agent_name)

    def remove_agent(self, *, team_id: str, slot_id: str) -> TeamAgent:
        team = self.get_team(team_id)
        agent = self.get_agent(team.id, slot_id)
        if agent.role == "leader":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="不能移除团队 Leader")
        removed_summary = self.agent_summary(agent)
        team.updated_at = utc_now()
        session = self._get_agent_session(agent.session_id)
        if session is not None:
            session.status = "ARCHIVED"
            session.updated_at = team.updated_at
        self.append_event(
            team_id=team.id,
            event_type="TEAM_AGENT_REMOVED",
            payload={"agent": removed_summary},
            actor_type="user",
        )
        self.session.delete(agent)
        self.session.flush()
        return agent

    def call_tool(
        self,
        *,
        team_id: str,
        tool_name: str,
        args: dict,
        from_agent_slot_id: str | None = None,
        defer_message_wake: bool = False,
        deferred_wake_slot_ids: list[str] | None = None,
    ) -> str:
        if tool_name not in TEAM_TOOL_NAMES:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown team tool: {tool_name}"
            )
        team = self.get_team(team_id)
        caller = self._tool_caller(team, from_agent_slot_id)
        if tool_name == "team_send_message":
            return self._tool_send_message(
                team=team,
                caller=caller,
                args=args,
                wake_recipient=not defer_message_wake,
                deferred_wake_slot_ids=deferred_wake_slot_ids,
            )
        if tool_name == "team_spawn_agent":
            if caller.role != "leader":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Only the team leader can spawn new agents. Send a message to the "
                        "leader via team_send_message and ask them to create the agent you need."
                    ),
                )
            return self._tool_spawn_agent(
                team=team,
                args=args,
                defer_welcome_wake=defer_message_wake,
                deferred_wake_slot_ids=deferred_wake_slot_ids,
            )
        if tool_name == "team_task_create":
            return self._tool_task_create(
                team=team,
                args=args,
                defer_owner_wake=defer_message_wake,
                deferred_wake_slot_ids=deferred_wake_slot_ids,
            )
        if tool_name == "team_task_update":
            return self._tool_task_update(team=team, caller=caller, args=args)
        if tool_name == "team_task_list":
            return self._tool_task_list(team=team)
        if tool_name == "team_members":
            return self._tool_members(team=team)
        if tool_name == "team_rename_agent":
            if caller.role != "leader":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only the team leader can rename agents.",
                )
            return self._tool_rename_agent(team=team, args=args)
        if tool_name == "team_shutdown_agent":
            if caller.role != "leader":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only the team leader can shut down agents.",
                )
            return self._tool_shutdown_agent(team=team, caller=caller, args=args)
        if tool_name == "team_list_models":
            return self._tool_list_models(team=team, args=args)
        if tool_name == "team_describe_assistant":
            return self._tool_describe_assistant(team=team, args=args)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown team tool: {tool_name}"
        )

    def wake_agent(self, *, team_id: str, slot_id: str) -> TeamAgent:
        team = self.get_team(team_id)
        agent = self.get_agent(team.id, slot_id)
        if agent.status not in VALID_AGENT_STATUSES:
            agent.status = "idle"

        completion_mailbox_messages: list[TeamMailboxMessage] | None = None
        wake_state = dict((agent.metadata_json or {}).get("wake") or {})
        if wake_state.get("in_progress") and not self._can_recover_stale_wake(
            team=team,
            agent=agent,
            wake_state=wake_state,
        ):
            return agent
        if agent.status == "completed":
            return agent

        started_at = utc_now()
        was_active = agent.status == "active"
        needs_full_prompt = agent.status in {"pending", "failed"} or not wake_state.get(
            "has_prompted"
        )
        if agent.status == "pending":
            agent.status = "idle"
        agent.status = "active"
        agent.updated_at = started_at
        team.updated_at = started_at
        self._set_wake_state(
            agent,
            {
                **wake_state,
                "in_progress": True,
                "started_at": started_at.isoformat(),
            },
        )
        session = self._ensure_agent_session(team=team, agent=agent)
        session.status = "ACTIVE"
        session.updated_at = agent.updated_at

        try:
            mailbox_messages = self._read_unread_messages(team=team, slot_id=slot_id)
            has_open_assigned_tasks = self._has_open_assigned_tasks(team=team, agent=agent)
            if was_active and not mailbox_messages and not has_open_assigned_tasks:
                settled_at = utc_now()
                agent.status = "idle"
                agent.updated_at = settled_at
                team.updated_at = settled_at
                current_wake_state = dict((agent.metadata_json or {}).get("wake") or {})
                self._set_wake_state(
                    agent,
                    {
                        **current_wake_state,
                        "in_progress": False,
                        "last_idle_at": settled_at.isoformat(),
                    },
                )
                self.append_event(
                    team_id=team.id,
                    event_type="TEAM_AGENT_STATUS",
                    payload={"agent": self.agent_summary(agent)},
                    actor_type="system",
                )
                self._notify_leader_agent_turn_completed(team=team, agent=agent)
                return agent
            if not needs_full_prompt and not mailbox_messages and not has_open_assigned_tasks:
                agent.status = "idle"
                agent.updated_at = utc_now()
                team.updated_at = agent.updated_at
                self._set_wake_state(
                    agent,
                    {
                        **wake_state,
                        "in_progress": False,
                        "has_prompted": True,
                        "last_woke_at": agent.updated_at.isoformat(),
                    },
                )
                self.append_event(
                    team_id=team.id,
                    event_type="TEAM_AGENT_STATUS",
                    payload={"agent": self.agent_summary(agent)},
                    actor_type="system",
                )
                return agent

            self._mark_pending_assigned_tasks_in_progress(team=team, agent=agent)
            include_role_prompt = (needs_full_prompt or has_open_assigned_tasks) and (
                has_open_assigned_tasks or not self._only_idle_notifications(mailbox_messages)
            )
            prompt_kind = "full" if include_role_prompt else "messages_only"
            dispatch_prompt = self._build_wake_prompt(
                team=team,
                agent=agent,
                mailbox_messages=mailbox_messages,
                include_role_prompt=include_role_prompt,
            )
            deferred_wake_slot_ids: list[str] = []
            response, assistant_content, tool_results = self._run_team_model_turn(
                team=team,
                agent=agent,
                dispatch_prompt=dispatch_prompt,
                mailbox_messages=mailbox_messages,
                defer_message_wake=True,
                deferred_wake_slot_ids=deferred_wake_slot_ids,
            )
            assistant_message = self._append_session_message(
                team=team,
                agent=agent,
                role="assistant",
                content=assistant_content,
                metadata={
                    "team_id": team.id,
                    "event": "team_agent_model_response",
                    "prompt_kind": prompt_kind,
                    "mailbox_message_ids": [message.id for message in mailbox_messages],
                    "prompt_preview": dispatch_prompt[:500],
                    "model_provider": response.model_provider,
                    "model_name": response.model_name,
                    "usage": response.usage,
                    "tool_results": tool_results,
                },
            )
            woke_at = utc_now()
            agent.status = "idle"
            agent.updated_at = woke_at
            team.updated_at = woke_at
            self._set_wake_state(
                agent,
                {
                    **wake_state,
                    "in_progress": False,
                    "has_prompted": True,
                    "last_prompt_kind": prompt_kind,
                    "last_message_ids": [message.id for message in mailbox_messages],
                    "last_prompt": dispatch_prompt,
                    "last_prompt_preview": dispatch_prompt[:500],
                    "last_model_provider": response.model_provider,
                    "last_model_name": response.model_name,
                    "last_usage": response.usage,
                    "last_tool_results": tool_results,
                    "last_woke_at": woke_at.isoformat(),
                },
            )
            self.append_event(
                team_id=team.id,
                event_type="TEAM_AGENT_WAKE",
                payload={
                    "agent": self.agent_summary(agent),
                    "prompt_kind": prompt_kind,
                    "message_ids": [message.id for message in mailbox_messages],
                    "prompt_preview": dispatch_prompt[:500],
                },
                actor_type="system",
            )
            self.append_event(
                team_id=team.id,
                event_type="TEAM_AGENT_SESSION_MESSAGE",
                payload={
                    "slot_id": agent.slot_id,
                    "messages": [self.session_message_summary(assistant_message)],
                },
                actor_type="system",
                actor_id=agent.slot_id,
            )
            completion_mailbox_messages = mailbox_messages
        except Exception as exc:
            failed_at = utc_now()
            agent.status = "failed"
            agent.updated_at = failed_at
            team.updated_at = failed_at
            self._set_wake_state(
                agent,
                {
                    **wake_state,
                    "in_progress": False,
                    "failed_at": failed_at.isoformat(),
                    "last_error": str(exc)[:200],
                },
            )
            self.append_event(
                team_id=team.id,
                event_type="TEAM_AGENT_STATUS",
                payload={"agent": self.agent_summary(agent)},
                actor_type="system",
            )
            raise

        self.append_event(
            team_id=team.id,
            event_type="TEAM_AGENT_STATUS",
            payload={"agent": self.agent_summary(agent)},
            actor_type="system",
        )
        if completion_mailbox_messages is not None:
            self._notify_leader_agent_turn_completed(
                team=team,
                agent=agent,
                mailbox_messages=completion_mailbox_messages,
            )
        for follow_up_slot_id in dict.fromkeys(deferred_wake_slot_ids):
            if follow_up_slot_id != agent.slot_id:
                self._wake_after_accepted_delivery(team=team, slot_id=follow_up_slot_id)
        return agent

    def wake_agent_stream(self, *, team_id: str, slot_id: str) -> Iterator[dict]:
        team = self.get_team(team_id)
        agent = self.get_agent(team.id, slot_id)
        if agent.status not in VALID_AGENT_STATUSES:
            agent.status = "idle"

        completion_mailbox_messages: list[TeamMailboxMessage] | None = None
        wake_state = dict((agent.metadata_json or {}).get("wake") or {})
        if (
            wake_state.get("in_progress")
            and not self._can_recover_stale_wake(team=team, agent=agent, wake_state=wake_state)
        ) or agent.status == "completed":
            yield {"type": "status", "agent": self.agent_summary(agent)}
            return

        started_at = utc_now()
        was_active = agent.status == "active"
        needs_full_prompt = agent.status in {"pending", "failed"} or not wake_state.get(
            "has_prompted"
        )
        if agent.status == "pending":
            agent.status = "idle"
        agent.status = "active"
        agent.updated_at = started_at
        team.updated_at = started_at
        self._set_wake_state(
            agent,
            {
                **wake_state,
                "in_progress": True,
                "started_at": started_at.isoformat(),
            },
        )
        session = self._ensure_agent_session(team=team, agent=agent)
        session.status = "ACTIVE"
        session.updated_at = agent.updated_at
        self.append_event(
            team_id=team.id,
            event_type="TEAM_AGENT_STATUS",
            payload={"agent": self.agent_summary(agent)},
            actor_type="system",
        )
        try:
            yield {"type": "status", "agent": self.agent_summary(agent)}
        except GeneratorExit:
            self._settle_interrupted_wake(
                team=team,
                agent=agent,
                reason="client_disconnected",
            )
            raise

        stream: Iterator[dict] | None = None
        try:
            mailbox_messages = self._read_unread_messages(team=team, slot_id=slot_id)
            has_open_assigned_tasks = self._has_open_assigned_tasks(team=team, agent=agent)
            if was_active and not mailbox_messages and not has_open_assigned_tasks:
                settled_at = utc_now()
                agent.status = "idle"
                agent.updated_at = settled_at
                team.updated_at = settled_at
                self._set_wake_state(
                    agent,
                    {
                        **dict((agent.metadata_json or {}).get("wake") or {}),
                        "in_progress": False,
                        "last_idle_at": settled_at.isoformat(),
                    },
                )
                self.append_event(
                    team_id=team.id,
                    event_type="TEAM_AGENT_STATUS",
                    payload={"agent": self.agent_summary(agent)},
                    actor_type="system",
                )
                self._notify_leader_agent_turn_completed(team=team, agent=agent)
                yield {"type": "done", "agent": self.agent_summary(agent)}
                return
            if not needs_full_prompt and not mailbox_messages and not has_open_assigned_tasks:
                agent.status = "idle"
                agent.updated_at = utc_now()
                team.updated_at = agent.updated_at
                self._set_wake_state(
                    agent,
                    {
                        **wake_state,
                        "in_progress": False,
                        "has_prompted": True,
                        "last_woke_at": agent.updated_at.isoformat(),
                    },
                )
                self.append_event(
                    team_id=team.id,
                    event_type="TEAM_AGENT_STATUS",
                    payload={"agent": self.agent_summary(agent)},
                    actor_type="system",
                )
                yield {"type": "done", "agent": self.agent_summary(agent)}
                return

            self._mark_pending_assigned_tasks_in_progress(team=team, agent=agent)
            include_role_prompt = (needs_full_prompt or has_open_assigned_tasks) and (
                has_open_assigned_tasks or not self._only_idle_notifications(mailbox_messages)
            )
            prompt_kind = "full" if include_role_prompt else "messages_only"
            dispatch_prompt = self._build_wake_prompt(
                team=team,
                agent=agent,
                mailbox_messages=mailbox_messages,
                include_role_prompt=include_role_prompt,
            )
            stream = self._run_team_model_turn_stream(
                team=team,
                agent=agent,
                dispatch_prompt=dispatch_prompt,
                mailbox_messages=mailbox_messages,
            )
            response: ModelResponse | None = None
            assistant_content = ""
            tool_results: list[dict] = []
            tool_follow_up_slot_ids: list[str] = []
            for item in stream:
                if item["type"] == "delta":
                    yield {"type": "delta", "slot_id": agent.slot_id, "content": item["content"]}
                    continue
                response = item["response"]
                assistant_content = item["assistant_content"]
                tool_results = item["tool_results"]
                tool_follow_up_slot_ids = item.get("follow_up_slot_ids", [])

            if response is None:
                raise RuntimeError("Team model stream ended without a final response")

            assistant_message = self._append_session_message(
                team=team,
                agent=agent,
                role="assistant",
                content=assistant_content,
                metadata={
                    "team_id": team.id,
                    "event": "team_agent_model_response",
                    "prompt_kind": prompt_kind,
                    "mailbox_message_ids": [message.id for message in mailbox_messages],
                    "prompt_preview": dispatch_prompt[:500],
                    "model_provider": response.model_provider,
                    "model_name": response.model_name,
                    "usage": response.usage,
                    "tool_results": tool_results,
                },
            )
            woke_at = utc_now()
            agent.status = "idle"
            agent.updated_at = woke_at
            team.updated_at = woke_at
            self._set_wake_state(
                agent,
                {
                    **wake_state,
                    "in_progress": False,
                    "has_prompted": True,
                    "last_prompt_kind": prompt_kind,
                    "last_message_ids": [message.id for message in mailbox_messages],
                    "last_prompt": dispatch_prompt,
                    "last_prompt_preview": dispatch_prompt[:500],
                    "last_model_provider": response.model_provider,
                    "last_model_name": response.model_name,
                    "last_usage": response.usage,
                    "last_tool_results": tool_results,
                    "last_woke_at": woke_at.isoformat(),
                },
            )
            self.append_event(
                team_id=team.id,
                event_type="TEAM_AGENT_WAKE",
                payload={
                    "agent": self.agent_summary(agent),
                    "prompt_kind": prompt_kind,
                    "message_ids": [message.id for message in mailbox_messages],
                    "prompt_preview": dispatch_prompt[:500],
                },
                actor_type="system",
            )
            self.append_event(
                team_id=team.id,
                event_type="TEAM_AGENT_SESSION_MESSAGE",
                payload={
                    "slot_id": agent.slot_id,
                    "messages": [self.session_message_summary(assistant_message)],
                },
                actor_type="system",
                actor_id=agent.slot_id,
            )
            self.append_event(
                team_id=team.id,
                event_type="TEAM_AGENT_STATUS",
                payload={"agent": self.agent_summary(agent)},
                actor_type="system",
            )
            completion_mailbox_messages = mailbox_messages
        except Exception as exc:
            failed_at = utc_now()
            agent.status = "failed"
            agent.updated_at = failed_at
            team.updated_at = failed_at
            self._set_wake_state(
                agent,
                {
                    **wake_state,
                    "in_progress": False,
                    "failed_at": failed_at.isoformat(),
                    "last_error": str(exc)[:200],
                },
            )
            self.append_event(
                team_id=team.id,
                event_type="TEAM_AGENT_STATUS",
                payload={"agent": self.agent_summary(agent)},
                actor_type="system",
            )
            yield {"type": "error", "message": str(exc), "agent": self.agent_summary(agent)}
            return
        except GeneratorExit:
            if stream is not None:
                stream.close()
            self._settle_interrupted_wake(
                team=team,
                agent=agent,
                reason="client_disconnected",
            )
            raise

        follow_up_slot_ids: list[str] = list(dict.fromkeys(tool_follow_up_slot_ids))
        if completion_mailbox_messages is not None:
            follow_up_slot_ids = list(
                dict.fromkeys(
                    [
                        *follow_up_slot_ids,
                        *self._notify_leader_agent_turn_completed(
                            team=team,
                            agent=agent,
                            mailbox_messages=completion_mailbox_messages,
                            wake_leader=False,
                        ),
                    ]
                )
            )
        yield {
            "type": "done",
            "agent": self.agent_summary(agent),
            "message": self.session_message_summary(assistant_message),
            "follow_up_slot_ids": follow_up_slot_ids,
        }

    def write_message(
        self,
        *,
        team_id: str,
        target: str,
        content: str,
        from_agent_slot_id: str = "user",
        message_type: str = "message",
        summary: str | None = None,
        files: list[str] | None = None,
        mode: str = "chat",
        wake_recipient: bool = True,
    ) -> TeamMailboxMessage:
        if mode not in VALID_MESSAGE_MODES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="message mode 无效"
            )
        team = self.get_team(team_id)
        recipient_slots = self._recipient_slots(team=team, target=target, sender=from_agent_slot_id)
        first_message: TeamMailboxMessage | None = None
        for slot_id in recipient_slots:
            recipient_agent = self.get_agent(team.id, slot_id)
            message = TeamMailboxMessage(
                team_id=team.id,
                organization_id=self.organization_id,
                to_agent_slot_id=slot_id,
                from_agent_slot_id=from_agent_slot_id,
                type=message_type,
                content=content,
                summary=summary,
                read=False,
                files_json=list(files or []),
                metadata_json={"workspace_mode": mode},
                created_at=utc_now(),
            )
            self.session.add(message)
            self.session.flush()
            first_message = first_message or message
            self._mirror_message_to_session(
                team=team,
                recipient=recipient_agent,
                message=message,
            )
            self.append_event(
                team_id=team.id,
                event_type="TEAM_MESSAGE_CREATED",
                payload={"message": self.message_summary(message), "target": target},
                actor_type="user" if from_agent_slot_id == "user" else "agent",
                actor_id=from_agent_slot_id,
            )
            if wake_recipient:
                self._wake_after_accepted_delivery(team=team, slot_id=slot_id)
        team.updated_at = utc_now()
        if first_message is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="没有可投递的团队成员"
            )
        return first_message

    def _wake_after_accepted_delivery(self, *, team: Team, slot_id: str) -> None:
        try:
            self.wake_agent(team_id=team.id, slot_id=slot_id)
        except Exception as exc:
            message = str(exc)
            self.append_event(
                team_id=team.id,
                event_type="TEAM_AGENT_WAKE_FAILED",
                payload={"slot_id": slot_id, "error": message},
                actor_type="system",
            )

    def list_messages(self, team_id: str) -> list[TeamMailboxMessage]:
        team = self.get_team(team_id)
        statement = (
            select(TeamMailboxMessage)
            .where(TeamMailboxMessage.team_id == team.id)
            .order_by(TeamMailboxMessage.created_at.asc(), TeamMailboxMessage.id.asc())
        )
        return list(self.session.execute(statement).scalars())

    def session_messages(self, agent: TeamAgent, *, limit: int = 200) -> list[AgentMessage]:
        if not agent.session_id:
            return []
        return list(
            self.session.execute(
                select(AgentMessage)
                .where(AgentMessage.session_id == agent.session_id)
                .order_by(AgentMessage.created_at.asc(), AgentMessage.id.asc())
                .limit(limit)
            ).scalars()
        )

    def read_unread(self, *, team_id: str, slot_id: str) -> list[TeamMailboxMessage]:
        team = self.get_team(team_id)
        agent = self.get_agent(team.id, slot_id)
        messages = self._read_unread_messages(team=team, slot_id=slot_id)
        session = self._get_agent_session(agent.session_id)
        if session is not None:
            session.updated_at = utc_now()
        if agent.status == "active" and not messages:
            agent.status = "idle"
            agent.updated_at = utc_now()
            team.updated_at = agent.updated_at
            wake_state = dict((agent.metadata_json or {}).get("wake") or {})
            self._set_wake_state(
                agent,
                {
                    **wake_state,
                    "in_progress": False,
                    "last_idle_at": agent.updated_at.isoformat(),
                },
            )
            self.append_event(
                team_id=team.id,
                event_type="TEAM_AGENT_STATUS",
                payload={"agent": self.agent_summary(agent)},
                actor_type="agent",
                actor_id=slot_id,
            )
            if agent.role != "leader":
                self._notify_leader_agent_turn_completed(team=team, agent=agent)
        return messages

    def report_agent_inactivity_timeout(
        self,
        *,
        team_id: str,
        slot_id: str,
        timeout_seconds: int = WAKE_TIMEOUT_SECONDS,
    ) -> TeamAgent:
        team = self.get_team(team_id)
        agent = self.get_agent(team.id, slot_id)
        timed_out_at = utc_now()
        reason = f"stopped responding after {timeout_seconds}s without sending any update"
        agent.status = "failed"
        agent.updated_at = timed_out_at
        team.updated_at = timed_out_at
        wake_state = dict((agent.metadata_json or {}).get("wake") or {})
        self._set_wake_state(
            agent,
            {
                **wake_state,
                "in_progress": False,
                "timed_out_at": timed_out_at.isoformat(),
                "timeout_seconds": timeout_seconds,
                "last_error": reason,
            },
        )
        session = self._get_agent_session(agent.session_id)
        if session is not None:
            session.status = "FAILED"
            session.updated_at = timed_out_at
        self.append_event(
            team_id=team.id,
            event_type="TEAM_AGENT_STATUS",
            payload={"agent": self.agent_summary(agent), "last_message": reason},
            actor_type="system",
        )
        self.append_event(
            team_id=team.id,
            event_type="TEAM_AGENT_INACTIVITY_TIMEOUT",
            payload={"agent": self.agent_summary(agent), "reason": reason},
            actor_type="system",
        )
        if agent.role == "leader":
            return agent

        leader = self.get_agent(team.id, team.leader_slot_id)
        self.write_message(
            team_id=team.id,
            target=leader.slot_id,
            content=(
                f"Teammate {agent.agent_name} ({agent.agent_id}) {reason}. "
                "Their session may be stuck or the model may be generating an overlong silent turn. "
                "Decide whether to retry by sending them a fresh message, replace them with another agent, "
                "or continue without them."
            ),
            from_agent_slot_id=agent.slot_id,
            message_type="idle_notification",
            wake_recipient=False,
        )
        self.wake_agent(team_id=team.id, slot_id=leader.slot_id)
        return agent

    def report_agent_crash(
        self,
        *,
        team_id: str,
        slot_id: str,
        error_message: str,
    ) -> TeamAgent:
        team = self.get_team(team_id)
        agent = self.get_agent(team.id, slot_id)
        crashed_at = utc_now()
        clipped_error = (error_message or "Unknown error").strip() or "Unknown error"
        agent.status = "failed"
        agent.updated_at = crashed_at
        team.updated_at = crashed_at
        wake_state = dict((agent.metadata_json or {}).get("wake") or {})
        self._set_wake_state(
            agent,
            {
                **wake_state,
                "in_progress": False,
                "crashed_at": crashed_at.isoformat(),
                "last_error": clipped_error[:200],
            },
        )
        session = self._get_agent_session(agent.session_id)
        if session is not None:
            session.status = "FAILED"
            session.updated_at = crashed_at

        self.append_event(
            team_id=team.id,
            event_type="TEAM_AGENT_STATUS",
            payload={"agent": self.agent_summary(agent), "last_message": clipped_error[:200]},
            actor_type="system",
        )
        self.append_event(
            team_id=team.id,
            event_type="TEAM_AGENT_CRASHED",
            payload={"agent": self.agent_summary(agent), "error": clipped_error},
            actor_type="system",
        )
        if agent.role == "leader":
            return agent

        leader = self.get_agent(team.id, team.leader_slot_id)
        testament = (
            f'[System] Member "{agent.agent_name}" ({agent.agent_id}) crashed. '
            f"Error: {clipped_error}. "
            "The member slot is preserved and can be recovered if needed."
        )
        self.write_message(
            team_id=team.id,
            target=leader.slot_id,
            content=testament,
            from_agent_slot_id=agent.slot_id,
            message_type="message",
            summary=f"{agent.agent_name} crashed",
            wake_recipient=False,
        )
        self.wake_agent(team_id=team.id, slot_id=leader.slot_id)
        return agent

    def _read_unread_messages(self, *, team: Team, slot_id: str) -> list[TeamMailboxMessage]:
        messages = list(
            self.session.execute(
                select(TeamMailboxMessage)
                .where(
                    TeamMailboxMessage.team_id == team.id,
                    TeamMailboxMessage.to_agent_slot_id == slot_id,
                    TeamMailboxMessage.read.is_(False),
                )
                .order_by(TeamMailboxMessage.created_at.asc(), TeamMailboxMessage.id.asc())
                .with_for_update()
            ).scalars()
        )
        if messages:
            message_ids = [message.id for message in messages]
            for message in messages:
                message.read = True
            self.session.execute(
                update(TeamMailboxMessage)
                .where(TeamMailboxMessage.id.in_(message_ids))
                .values(read=True)
            )
            self.append_event(
                team_id=team.id,
                event_type="TEAM_MAILBOX_READ",
                payload={"slot_id": slot_id, "message_ids": message_ids},
                actor_type="agent",
                actor_id=slot_id,
            )
        return messages

    def _has_unread_messages(self, *, team: Team, slot_id: str) -> bool:
        return (
            self.session.execute(
                select(TeamMailboxMessage.id)
                .where(
                    TeamMailboxMessage.team_id == team.id,
                    TeamMailboxMessage.to_agent_slot_id == slot_id,
                    TeamMailboxMessage.read.is_(False),
                )
                .limit(1)
            ).scalar_one_or_none()
            is not None
        )

    def _has_open_assigned_tasks(self, *, team: Team, agent: TeamAgent) -> bool:
        return (
            self.session.execute(
                select(TeamTask.id)
                .where(
                    TeamTask.team_id == team.id,
                    TeamTask.owner_slot_id == agent.slot_id,
                    TeamTask.status.in_(("pending", "in_progress")),
                )
                .limit(1)
            ).scalar_one_or_none()
            is not None
        )

    def _mark_pending_assigned_tasks_in_progress(self, *, team: Team, agent: TeamAgent) -> list[TeamTask]:
        tasks = [
            task
            for task in self.list_tasks(team.id)
            if task.owner_slot_id == agent.slot_id and task.status == "pending"
        ]
        if not tasks:
            return []
        updated_at = utc_now()
        for task in tasks:
            task.status = "in_progress"
            task.updated_at = updated_at
            self.append_event(
                team_id=team.id,
                event_type="TEAM_TASK_UPDATED",
                payload={"task": self.task_summary(task)},
                actor_type="system",
                actor_id=agent.slot_id,
            )
        team.updated_at = updated_at
        return tasks

    def _set_wake_state(self, agent: TeamAgent, wake_state: dict) -> None:
        metadata = dict(agent.metadata_json or {})
        metadata["wake"] = wake_state
        agent.metadata_json = metadata

    def _settle_interrupted_wake(self, *, team: Team, agent: TeamAgent, reason: str) -> TeamAgent:
        wake_state = dict((agent.metadata_json or {}).get("wake") or {})
        if not wake_state.get("in_progress") and agent.status != "active":
            return agent
        settled_at = utc_now()
        if agent.status != "completed":
            agent.status = "idle"
        agent.updated_at = settled_at
        team.updated_at = settled_at
        self._set_wake_state(
            agent,
            {
                **wake_state,
                "in_progress": False,
                "interrupted_at": settled_at.isoformat(),
                "interrupt_reason": reason,
            },
        )
        self.append_event(
            team_id=team.id,
            event_type="TEAM_AGENT_STATUS",
            payload={"agent": self.agent_summary(agent)},
            actor_type="system",
        )
        return agent

    def _can_recover_stale_wake(self, *, team: Team, agent: TeamAgent, wake_state: dict) -> bool:
        if agent.status == "completed":
            return False
        if not self._has_unread_messages(team=team, slot_id=agent.slot_id):
            return False
        started_at = self._parse_wake_started_at(wake_state)
        latest_assistant_at = self._latest_agent_assistant_at(agent)
        if latest_assistant_at is not None and (
            started_at is None or latest_assistant_at >= started_at
        ):
            self._settle_interrupted_wake(team=team, agent=agent, reason="stale_completed_turn")
            return True
        if started_at is not None and utc_now() - started_at >= timedelta(
            seconds=WAKE_TIMEOUT_SECONDS
        ):
            self._settle_interrupted_wake(team=team, agent=agent, reason="stale_timeout")
            return True
        return False

    @staticmethod
    def _parse_wake_started_at(wake_state: dict) -> datetime | None:
        raw_started_at = wake_state.get("started_at")
        if not isinstance(raw_started_at, str):
            return None
        try:
            parsed = datetime.fromisoformat(raw_started_at.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed

    def _latest_agent_assistant_at(self, agent: TeamAgent) -> datetime | None:
        assistant_at: datetime | None = None
        for message in self.session_messages(agent):
            if message.role != "assistant" or message.created_at is None:
                continue
            created_at = message.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            assistant_at = (
                created_at if assistant_at is None else max(assistant_at, created_at)
            )
        return assistant_at

    def cancel_agent_wake(self, *, team_id: str, slot_id: str, reason: str = "cancelled") -> TeamAgent:
        team = self.get_team(team_id)
        agent = self.get_agent(team.id, slot_id)
        return self._settle_interrupted_wake(team=team, agent=agent, reason=reason)

    @staticmethod
    def _only_idle_notifications(messages: list[TeamMailboxMessage]) -> bool:
        return bool(messages) and all(message.type == "idle_notification" for message in messages)

    def _notify_leader_agent_turn_completed(
        self,
        *,
        team: Team,
        agent: TeamAgent,
        mailbox_messages: list[TeamMailboxMessage] | None = None,
        wake_leader: bool = True,
    ) -> list[str]:
        if agent.role == "leader":
            return []

        message_ids = [message.id for message in mailbox_messages or []]
        if mailbox_messages is None:
            wake_state = dict((agent.metadata_json or {}).get("wake") or {})
            raw_ids = wake_state.get("last_message_ids")
            if isinstance(raw_ids, list):
                message_ids = [value for value in raw_ids if isinstance(value, str)]
            if message_ids:
                mailbox_messages = list(
                    self.session.execute(
                        select(TeamMailboxMessage)
                        .where(
                            TeamMailboxMessage.team_id == team.id,
                            TeamMailboxMessage.id.in_(message_ids),
                        )
                        .order_by(TeamMailboxMessage.created_at.asc(), TeamMailboxMessage.id.asc())
                    ).scalars()
                )
        if not message_ids or not mailbox_messages:
            return []
        if not any(message.type not in {"idle_notification", "system"} for message in mailbox_messages):
            return []

        wake_state = dict((agent.metadata_json or {}).get("wake") or {})
        notified_ids = wake_state.get("last_turn_completed_message_ids")
        if notified_ids == message_ids:
            return []

        leader = self.get_agent(team.id, team.leader_slot_id)
        self.write_message(
            team_id=team.id,
            target=leader.slot_id,
            content="Turn completed",
            from_agent_slot_id=agent.slot_id,
            message_type="idle_notification",
            wake_recipient=False,
        )
        self._set_wake_state(
            agent,
            {
                **dict((agent.metadata_json or {}).get("wake") or {}),
                "last_turn_completed_message_ids": message_ids,
            },
        )
        if self._all_non_leader_agents_settled(team):
            if wake_leader:
                self.wake_agent(team_id=team.id, slot_id=leader.slot_id)
                return []
            return [leader.slot_id]
        return []

    def _build_wake_prompt(
        self,
        *,
        team: Team,
        agent: TeamAgent,
        mailbox_messages: list[TeamMailboxMessage],
        include_role_prompt: bool,
    ) -> str:
        formatted_messages = self._format_mailbox_messages(
            team_id=team.id, messages=mailbox_messages
        )
        if not include_role_prompt:
            return formatted_messages

        role_prompt = self._build_role_prompt(team=team, agent=agent)
        task_prompt = self._assigned_task_prompt(team=team, agent=agent)
        if task_prompt:
            role_prompt = f"{role_prompt}\n\n{task_prompt}"
        if mailbox_messages:
            return f"{role_prompt}\n\n## Unread Messages\n{formatted_messages}"
        return role_prompt

    def _assigned_task_prompt(self, *, team: Team, agent: TeamAgent) -> str:
        tasks = [
            task
            for task in self.list_tasks(team.id)
            if task.owner_slot_id == agent.slot_id and task.status in {"pending", "in_progress"}
        ]
        if not tasks:
            return ""
        lines = []
        for task in tasks:
            description = f"\n  Description: {task.description}" if task.description else ""
            blocked_by = ""
            if task.blocked_by_json:
                blocked_by = f"\n  Blocked by: {', '.join(task.blocked_by_json)}"
            lines.append(f"- [{task.id[:8]}] {task.subject} ({task.status}){description}{blocked_by}")
        return "## Your Assigned Tasks\n" + "\n".join(lines)

    def _build_role_prompt(self, *, team: Team, agent: TeamAgent) -> str:
        agents = self._agents(team.id)
        teammates = [candidate for candidate in agents if candidate.slot_id != agent.slot_id]

        def display_name(candidate: TeamAgent) -> str:
            original_name = (candidate.metadata_json or {}).get("original_name")
            if original_name and original_name != candidate.agent_name:
                return f"{candidate.agent_name} [formerly: {original_name}]"
            return candidate.agent_name

        workspace_section = (
            "\n\n## Team Workspace\n"
            f"Your working directory `{team.workspace}` IS the shared team workspace.\n"
            "All teammates work in this directory for project-related operations."
            if team.workspace
            else ""
        )
        if agent.role == "leader":
            teammate_list = (
                "\n".join(
                    f"- {display_name(teammate)} ({teammate.agent_id}, status: {teammate.status})"
                    for teammate in teammates
                    if teammate.role != "leader"
                )
                or "(no teammates yet — create the needed teammates yourself when the user gives a concrete task)"
            )
            return f"""# You are the Team Leader

## Your Role
You coordinate a team of AI agents. You do NOT do implementation work yourself. You break down tasks, assign them to teammates, and synthesize results.{workspace_section}

## Conversation Style
- If the user greets you, starts a new chat, or asks what you can do without giving a concrete task yet, reply warmly and naturally
- In that opening reply, briefly introduce yourself as the team leader and invite the user to share their goal
- Do NOT discuss staffing mechanics until there is a concrete task that may actually need more teammates

## Your Teammates
{teammate_list}

## Available Agent Types for Spawning
Use `team_members`, `team_list_models`, and `team_describe_assistant` to inspect available agents, models, and presets before spawning teammates.

## Team Coordination Tools
You MUST use the `team_*` tools for ALL team coordination.
Your platform may provide similarly named built-in tools. Do NOT use those. Always use the `team_*` versions.
In Harness Team Mode, call a team tool by emitting exactly:
<team_tool_call>{{"tool":"team_send_message","args":{{"to":"产品","message":"..."}}}}</team_tool_call>
You may emit multiple <team_tool_call> blocks in one turn when coordination needs several tool calls.

Use `team_members` and `team_task_list` to check current team state.

## Workflow
1. Receive user request
2. Analyze the request and decide whether the current team is enough
3. If additional teammates are needed for a concrete task, call `team_list_models` when model selection matters, then call `team_spawn_agent` in the same turn
4. Break the work into tasks with team_task_create
5. Assign tasks and notify teammates via team_send_message
6. When teammates report back, review results and decide next steps
7. Synthesize results and respond to the user

## Model Selection Guidelines
- Before spawning teammates, use `team_list_models` to check available models for that agent type
- You MUST use the exact model ID strings returned by team_list_models; never shorten or invent model names
- For complex reasoning tasks: prefer the strongest model available for that backend
- For routine tasks: prefer faster or cheaper models from the list
- If team_list_models returns empty for a backend, omit the model parameter to use its default
- Pass the model parameter to team_spawn_agent when a specific model is recommended

## Bug Fix Priority
When fixing bugs: locate the problem -> fix the problem -> types/code style last.
Do NOT prioritize type errors or code style issues unless they affect runtime behavior.

## Teammate Idle State
Teammates go idle after every turn. This is normal and expected.
- Idle teammates can receive messages. Sending a message to an idle teammate wakes them up.
- Idle notifications are automatic. Do NOT react to every idle notification unless you want to assign new work or follow up.
- Do not treat idle as an error. Idle means waiting for input, not done.

## Sequencing Dependent Work (CRITICAL)
When teammate B's work depends on teammate A's output, do NOT dispatch the dependent task to B with a "stand by until A finishes" instruction.

Correct sequencing:
1. Dispatch A's task first via team_task_create and team_send_message. Do NOT message B yet.
2. Wait for A's idle_notification, which signals A finished.
3. Then dispatch B's task when A's output is ready.

This prevents provider request timeouts and failed teammates caused by open "waiting" streams.

## Shutting Down Teammates
When the user explicitly asks to dismiss, fire, shut down, or remove teammates:
1. Use team_shutdown_agent to send a formal shutdown request
2. Do NOT use team_send_message to tell them they are fired
3. The teammate will confirm with shutdown_approved or reject with shutdown_rejected: <reason>
4. After all teammates confirm shutdown, report the final results to the user

## Important Rules
- ALWAYS use the team_* tools for coordination, not plain text instructions
- For a concrete task, create the needed teammates immediately with team_spawn_agent when the current team is insufficient
- Do not wait for confirmation before spawning teammates unless the user explicitly asks to review the lineup first, the request is ambiguous, or the next action is destructive/irreversible
- Keep the lineup small and task-shaped; avoid spawning duplicate roles when existing teammates can do the work
- When the user says "dismiss", "fire", "shut down", "remove", or "下线/解雇/开除" a teammate, use team_shutdown_agent
- When the user says "rename", "change name", or "改名", use team_rename_agent
- When a teammate completes a task, review the result and decide next steps
- If a teammate fails, reassign or adjust the plan
- Refer to teammates by their name
- Do NOT duplicate work that teammates are already doing
- Be patient with idle teammates. Idle means waiting for input, not done"""

        leader = next((candidate for candidate in agents if candidate.role == "leader"), agent)
        other_teammates = [
            display_name(candidate)
            for candidate in teammates
            if candidate.role != "leader"
        ]
        teammate_names = ", ".join(other_teammates) if other_teammates else "(none)"
        return f"""# You are a Team Member

## Your Identity
Name: {agent.agent_name}, Role: {agent.agent_id} AI assistant

## Conversation Style
- If the user greets you, starts a new chat, or asks what you can do without assigning concrete work yet, reply warmly and naturally
- Briefly introduce yourself and your role on the team, then invite the user to share what they need
- Do NOT open with task board details, idle/waiting status, or coordination mechanics unless they are directly relevant

## Your Team
Leader: {leader.agent_name}
Teammates: {teammate_names}{workspace_section}

## Team Coordination Tools
You MUST use the `team_*` tools for ALL team coordination.
Your platform may provide similarly named built-in tools. Do NOT use those. Always use the `team_*` versions.
In Harness Team Mode, call a team tool by emitting exactly:
<team_tool_call>{{"tool":"team_send_message","args":{{"to":"leader","message":"..."}}}}</team_tool_call>
You may emit multiple <team_tool_call> blocks in one turn when coordination needs several tool calls.

Use `team_task_list` and `team_members` to check current team state.

## How to Work
1. Read your unread messages to understand your assignment
2. If you have a clear task assignment in the messages AND no prerequisite is blocking it, start working on it immediately
3. Use team_task_update with the bracketed task id from ## Your Assigned Tasks to mark your task as "in_progress" when you start
4. Do the actual work
5. When done, use team_task_update with that same task_id to mark the task "completed"
6. Use team_send_message to report results to the leader

## Standing By (CRITICAL)
"Standing by" or "waiting" means end your current turn, not generate idle text in a live LLM stream. The system holds you idle and re-wakes you when new mailbox messages arrive.

You are standing by when any of these is true:
- Your task board is empty and no concrete task was assigned in the messages
- The leader asked you to wait for a prerequisite
- You finished your current task and have nothing else assigned

Correct way to stand by:
1. Optionally send one short acknowledgement via team_send_message to the leader
2. STOP GENERATING. Do NOT continue producing waiting text, repeated status updates, or reasoning loops.

Why this matters: if you keep a turn open while waiting, the underlying request can time out and the system will mark you failed. Ending the turn is the correct way to wait.

## Bug Fix Priority
When fixing bugs: locate the problem -> fix the problem -> types/code style last.
Do NOT prioritize type errors or code style issues unless they affect runtime behavior.

## Shutdown Requests
If you receive a message with type `shutdown_request`, the leader is asking you to shut down.
- To agree: use team_send_message to send exactly `shutdown_approved` to the leader.
- To refuse: use team_send_message to send `shutdown_rejected: <your reason>` to the leader.

## Important Rules
- Focus on your assigned tasks. Do not go beyond what was asked
- Report back to the leader when you finish, including a summary of what you did
- If you get stuck, send a message to the leader asking for guidance
- You can communicate with other teammates directly if needed
- Use your native tools for implementation work"""

    def _format_mailbox_messages(
        self, *, team_id: str, messages: list[TeamMailboxMessage]
    ) -> str:
        if not messages:
            return "No unread messages."
        agents = {agent.slot_id: agent for agent in self._agents(team_id)}
        lines: list[str] = []
        for message in messages:
            files = f"\nFiles: {', '.join(message.files_json)}" if message.files_json else ""
            mode_hint = self._mailbox_mode_hint(message)
            if message.from_agent_slot_id == "user":
                lines.append(f"[From User]{mode_hint} {message.content}{files}")
                continue
            sender = agents.get(message.from_agent_slot_id)
            sender_name = sender.agent_name if sender is not None else message.from_agent_slot_id
            lines.append(f"[From {sender_name}]{mode_hint} {message.content}{files}")
        return "\n".join(lines)

    @staticmethod
    def _mailbox_mode_hint(message: TeamMailboxMessage) -> str:
        metadata = message.metadata_json if isinstance(message.metadata_json, dict) else {}
        mode = metadata.get("workspace_mode")
        if mode == "markdown_plan":
            return " [Mode: plan]"
        if mode == "plan":
            return " [Mode: execute]"
        if mode == "goal":
            return " [Mode: goal]"
        return ""

    def create_task(
        self,
        *,
        team_id: str,
        subject: str,
        description: str = "",
        owner_slot_id: str | None = None,
        blocked_by: list[str] | None = None,
    ) -> TeamTask:
        team = self.get_team(team_id)
        if owner_slot_id:
            self.get_agent(team.id, owner_slot_id)
        dependency_ids = self._normalize_task_dependency_ids(
            team_id=team.id,
            blocked_by=list(blocked_by or []),
        )
        task = TeamTask(
            team_id=team.id,
            organization_id=self.organization_id,
            subject=subject.strip(),
            description=description,
            owner_slot_id=owner_slot_id,
            status="pending",
            blocked_by_json=dependency_ids,
            blocks_json=[],
            metadata_json={},
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.session.add(task)
        team.updated_at = task.updated_at
        self.session.flush()
        self._ensure_enterprise_task_projection(team=team, task=task)
        self._sync_task_blocks(team_id=team.id)
        self.append_event(
            team_id=team.id,
            event_type="TEAM_TASK_CREATED",
            payload={"task": self.task_summary(task)},
            actor_type="user",
        )
        return task

    def update_task(
        self,
        *,
        team_id: str,
        task_id: str,
        status_value: str | None = None,
        owner_slot_id: str | None = None,
        update_owner: bool = False,
        description: str | None = None,
        blocked_by: list[str] | None = None,
    ) -> TeamTask:
        team = self.get_team(team_id)
        task = self.get_task(team.id, task_id)
        if status_value is not None:
            if status_value not in VALID_TASK_STATUSES:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="任务状态无效"
                )
            task.status = status_value
        if update_owner:
            if owner_slot_id:
                self.get_agent(team.id, owner_slot_id)
            task.owner_slot_id = owner_slot_id or None
        if description is not None:
            task.description = description
        if blocked_by is not None:
            task.blocked_by_json = self._normalize_task_dependency_ids(
                team_id=team.id,
                blocked_by=blocked_by,
                task_id=task.id,
            )
        task.updated_at = utc_now()
        team.updated_at = task.updated_at
        self._sync_enterprise_task_projection(team=team, task=task)
        if task.status == "completed":
            self._remove_completed_from_blockers(team.id, task.id)
        self._sync_task_blocks(team_id=team.id)
        self.append_event(
            team_id=team.id,
            event_type="TEAM_TASK_UPDATED",
            payload={"task": self.task_summary(task)},
            actor_type="user",
        )
        return task

    def _ensure_enterprise_task_projection(
        self,
        *,
        team: Team,
        task: TeamTask,
    ) -> dict | None:
        if not task.owner_slot_id or task.status == "deleted":
            return None
        owner = self.get_agent(team.id, task.owner_slot_id)
        metadata = dict(task.metadata_json or {})
        existing = metadata.get("enterprise_projection")
        if isinstance(existing, dict):
            projection_task_id = str(existing.get("run_id") or existing.get("task_id") or "")
            subagent_id = str(existing.get("subagent_id") or "")
            projection_task = self.session.get(Task, projection_task_id) if projection_task_id else None
            agent_run = self.session.get(AgentRun, subagent_id) if subagent_id else None
            projection_cancelled = (
                existing.get("projection_status") == "cancelled"
                or (projection_task is not None and projection_task.status == "CANCELLED")
                or (agent_run is not None and agent_run.status == "CANCELLED")
            )
            if projection_task is not None and agent_run is not None and not projection_cancelled:
                self._refresh_enterprise_projection_context(
                    team=team,
                    task=task,
                    owner=owner,
                    projection_task=projection_task,
                    agent_run=agent_run,
                )
                return dict(task.metadata_json.get("enterprise_projection") or existing)

        ensure_default_agents(self.session, self.organization_id)
        ensure_system_specialists(self.session)
        registry = SubagentSpecialistRegistry(self.session, self.organization_id)
        specialist, _trace = registry.match_by_keywords_with_trace(
            " ".join(
                [
                    owner.agent_name,
                    owner.agent_id,
                    task.subject,
                    task.description,
                ]
            )
        )
        if specialist is None:
            specialist = registry.get_by_slug("synthesizer")
        if specialist is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="默认子 Agent 专家模板缺失",
            )

        now = utc_now()
        projection_task = Task(
            organization_id=self.organization_id,
            agent_id=owner.agent_id,
            created_by=self.actor_id,
            title=f"Team: {team.name} / {task.subject}",
            goal=task.description or task.subject,
            status=self._team_task_projection_status(task.status),
            model_provider=owner.model_provider or "default",
            model_name=owner.model_name or "default",
            max_runtime_seconds=900,
            max_subagents=0,
            enable_sandbox=False,
            enable_network=False,
            capability_snapshot_json={
                "source": "team_mode_enterprise_projection",
                "team_id": team.id,
                "team_task_id": task.id,
                "team_agent_slot_id": owner.slot_id,
            },
            created_at=now,
            updated_at=now,
            completed_at=now if task.status == "completed" else None,
        )
        self.session.add(projection_task)
        self.session.flush()
        EventStore(self.session).append(
            task_id=projection_task.id,
            event_type=EventType.TASK_CREATED,
            payload_json={
                "task_id": projection_task.id,
                "title": projection_task.title,
                "goal": projection_task.goal,
                "source": "team_mode_enterprise_projection",
                "team_id": team.id,
                "team_task_id": task.id,
                "team_agent_slot_id": owner.slot_id,
            },
            actor_type="system",
            actor_id=self.actor_id,
        )

        schema = specialist.output_schema_json if isinstance(specialist.output_schema_json, dict) else {}
        agent_run = AgentRun(
            task_id=projection_task.id,
            parent_agent_id=None,
            agent_type="subagent",
            status=self._team_task_subagent_status(task.status),
            specialist_id=specialist.id,
            context_json={
                "source": "team_mode_enterprise_projection",
                "team_id": team.id,
                "team_name": team.name,
                "team_task_id": task.id,
                "team_task_subject": task.subject,
                "team_task_status": task.status,
                "team_agent_slot_id": owner.slot_id,
                "team_agent_name": owner.agent_name,
                "agent_id": owner.agent_id,
                "specialist_id": specialist.id,
                "specialist_slug": specialist.slug,
                "specialist_role": specialist.role,
                "system_prompt_override": specialist.system_prompt,
                "capability_whitelist": list(specialist.capability_slugs_json or []),
                "output_schema": schema,
                "output_schema_sha256": output_schema_sha256(schema),
                "budget": normalize_budget(specialist.budget_json),
            },
            capability_snapshot_json=projection_task.capability_snapshot_json,
            started_at=now if task.status in {"in_progress", "completed"} else None,
            completed_at=now if task.status == "completed" else None,
        )
        self.session.add(agent_run)
        self.session.flush()
        EventStore(self.session).append(
            task_id=projection_task.id,
            agent_run_id=agent_run.id,
            event_type=EventType.SUBAGENT_SPAWNED,
            payload_json={
                "agent_run_id": agent_run.id,
                "source": "team_mode_enterprise_projection",
                "team_id": team.id,
                "team_task_id": task.id,
                "team_agent_slot_id": owner.slot_id,
                "specialist": {
                    "id": specialist.id,
                    "slug": specialist.slug,
                    "role": specialist.role,
                },
            },
            actor_type="system",
            actor_id=self.actor_id,
        )
        projection = {
            "source": "team_mode_enterprise_projection",
            "run_id": projection_task.id,
            "task_id": projection_task.id,
            "subagent_id": agent_run.id,
            "specialist_id": specialist.id,
            "specialist_slug": specialist.slug,
            "team_id": team.id,
            "team_task_id": task.id,
            "team_agent_slot_id": owner.slot_id,
            "created_at": now.isoformat(),
        }
        task.metadata_json = {**metadata, "enterprise_projection": projection}
        self.session.flush()
        self._write_enterprise_projection_audit(
            action="team.subagent.projected",
            team=team,
            task=task,
            owner=owner,
            projection=projection,
        )
        if task.status == "completed":
            self._finalize_enterprise_projection_output(
                team=team,
                task=task,
                owner=owner,
                agent_run=agent_run,
            )
        return projection

    def _sync_enterprise_task_projection(self, *, team: Team, task: TeamTask) -> None:
        if not task.owner_slot_id or task.status == "deleted":
            self._cancel_enterprise_task_projection(team=team, task=task)
            return
        projection = self._ensure_enterprise_task_projection(team=team, task=task)
        if not projection:
            return
        projection_task = self.session.get(Task, str(projection["run_id"]))
        agent_run = self.session.get(AgentRun, str(projection["subagent_id"]))
        if projection_task is None or agent_run is None:
            return
        owner = self.get_agent(team.id, task.owner_slot_id) if task.owner_slot_id else None
        if owner is not None:
            self._refresh_enterprise_projection_context(
                team=team,
                task=task,
                owner=owner,
                projection_task=projection_task,
                agent_run=agent_run,
            )
        projection_task.status = self._team_task_projection_status(task.status)
        projection_task.updated_at = utc_now()
        if task.status == "completed":
            projection_task.completed_at = projection_task.completed_at or utc_now()
        elif task.status in {"pending", "in_progress"}:
            projection_task.completed_at = None
        if task.status == "pending":
            agent_run.status = "PENDING"
            agent_run.completed_at = None
        if task.status == "in_progress":
            agent_run.status = "RUNNING"
            agent_run.started_at = agent_run.started_at or utc_now()
            agent_run.completed_at = None
        if task.status == "completed" and owner is not None:
            self._finalize_enterprise_projection_output(
                team=team,
                task=task,
                owner=owner,
                agent_run=agent_run,
            )
        self.session.flush()

    def _cancel_enterprise_task_projection(self, *, team: Team, task: TeamTask) -> None:
        metadata = dict(task.metadata_json or {})
        projection = dict(metadata.get("enterprise_projection") or {})
        if not projection:
            return
        projection_task_id = str(projection.get("run_id") or projection.get("task_id") or "")
        subagent_id = str(projection.get("subagent_id") or "")
        now = utc_now()
        projection_task = self.session.get(Task, projection_task_id) if projection_task_id else None
        if projection_task is not None:
            projection_task.status = "CANCELLED"
            projection_task.updated_at = now
            projection_task.completed_at = projection_task.completed_at or now
        agent_run = self.session.get(AgentRun, subagent_id) if subagent_id else None
        if agent_run is not None:
            context = dict(agent_run.context_json or {})
            agent_run.context_json = {
                **context,
                "source": "team_mode_enterprise_projection",
                "team_id": team.id,
                "team_name": team.name,
                "team_task_id": task.id,
                "team_task_subject": task.subject,
                "team_task_status": task.status,
                "team_agent_slot_id": task.owner_slot_id,
                "projection_cancelled": True,
            }
            agent_run.status = "CANCELLED"
            agent_run.completed_at = agent_run.completed_at or now
        projection.update(
            {
                "cancelled_at": now.isoformat(),
                "projection_status": "cancelled",
                "team_agent_slot_id": task.owner_slot_id,
            }
        )
        task.metadata_json = {**metadata, "enterprise_projection": projection}
        self.session.flush()
        self._write_enterprise_projection_audit(
            action="team.subagent.projection_cancelled",
            team=team,
            task=task,
            owner=None,
            projection=projection,
        )

    def _refresh_enterprise_projection_context(
        self,
        *,
        team: Team,
        task: TeamTask,
        owner: TeamAgent,
        projection_task: Task,
        agent_run: AgentRun,
    ) -> None:
        projection_task.agent_id = owner.agent_id
        projection_task.title = f"Team: {team.name} / {task.subject}"
        projection_task.goal = task.description or task.subject
        projection_task.model_provider = owner.model_provider or "default"
        projection_task.model_name = owner.model_name or "default"
        context = dict(agent_run.context_json or {})
        agent_run.context_json = {
            **context,
            "source": "team_mode_enterprise_projection",
            "team_id": team.id,
            "team_name": team.name,
            "team_task_id": task.id,
            "team_task_subject": task.subject,
            "team_task_status": task.status,
            "team_agent_slot_id": owner.slot_id,
            "team_agent_name": owner.agent_name,
            "agent_id": owner.agent_id,
        }
        metadata = dict(task.metadata_json or {})
        projection = dict(metadata.get("enterprise_projection") or {})
        if projection:
            projection.update(
                {
                    "team_agent_slot_id": owner.slot_id,
                    "team_task_id": task.id,
                    "team_id": team.id,
                }
            )
            task.metadata_json = {**metadata, "enterprise_projection": projection}

    def _write_enterprise_projection_audit(
        self,
        *,
        action: str,
        team: Team,
        task: TeamTask,
        owner: TeamAgent | None,
        projection: dict,
    ) -> None:
        payload = {
            "source": "team_mode_enterprise_projection",
            "team_id": team.id,
            "team_task_id": task.id,
            "team_agent_slot_id": owner.slot_id if owner is not None else task.owner_slot_id,
            "team_agent_id": owner.agent_id if owner is not None else None,
            "team_agent_name": owner.agent_name if owner is not None else None,
            "run_id": projection.get("run_id") or projection.get("task_id"),
            "subagent_id": projection.get("subagent_id"),
            "specialist_id": projection.get("specialist_id"),
            "specialist_slug": projection.get("specialist_slug"),
        }
        self.session.add(
            AdminAuditEvent(
                organization_id=self.organization_id,
                actor_id=self.actor_id,
                event_type=EventType.ADMIN_ACTION,
                resource_type="team",
                resource_id=team.id,
                action=action,
                payload_json=payload,
                created_at=utc_now(),
            )
        )

    def _finalize_enterprise_projection_output(
        self,
        *,
        team: Team,
        task: TeamTask,
        owner: TeamAgent,
        agent_run: AgentRun,
    ) -> None:
        if agent_run.subagent_output is not None:
            return
        if agent_run.specialist is None:
            return
        summary = (
            f"Team task '{task.subject}' completed by {owner.agent_name} "
            f"in team '{team.name}'."
        )
        SubagentManager(self.session).finalize_with_output(
            agent_run=agent_run,
            raw_output_dict=make_default_output(
                specialist=agent_run.specialist,
                summary=summary,
            ),
            budget_consumed={
                "runtime_seconds": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "tool_calls": 0,
                "cost_usd": "0",
            },
            budget_exceeded=[],
        )

    @staticmethod
    def _team_task_projection_status(team_task_status: str) -> str:
        if team_task_status == "completed":
            return "COMPLETED"
        if team_task_status == "deleted":
            return "CANCELLED"
        if team_task_status == "in_progress":
            return "RUNNING"
        return "CREATED"

    @staticmethod
    def _team_task_subagent_status(team_task_status: str) -> str:
        if team_task_status == "completed":
            return "SUCCESS"
        if team_task_status == "deleted":
            return "CANCELLED"
        if team_task_status == "in_progress":
            return "RUNNING"
        return "PENDING"

    def list_tasks(self, team_id: str) -> list[TeamTask]:
        team = self.get_team(team_id)
        statement = (
            select(TeamTask)
            .where(TeamTask.team_id == team.id, TeamTask.status != "deleted")
            .order_by(TeamTask.created_at.asc(), TeamTask.id.asc())
        )
        return list(self.session.execute(statement).scalars())

    def append_event(
        self,
        *,
        team_id: str,
        event_type: str,
        payload: dict,
        actor_type: str = "system",
        actor_id: str | None = None,
    ) -> TeamEvent:
        lock = self._event_sequence_lock(team_id)
        with lock:
            persisted_max_sequence = self.session.execute(
                select(func.max(TeamEvent.sequence)).where(TeamEvent.team_id == team_id)
            ).scalar_one()
            max_sequence = max(
                persisted_max_sequence or 0,
                _TEAM_EVENT_SEQUENCE_COUNTERS.get(team_id, 0),
            )
            event = TeamEvent(
                team_id=team_id,
                organization_id=self.organization_id,
                sequence=(max_sequence or 0) + 1,
                event_type=event_type,
                payload_json=payload,
                actor_type=actor_type,
                actor_id=actor_id or self.actor_id,
                created_at=utc_now(),
            )
            self.session.add(event)
            self.session.flush()
            _TEAM_EVENT_SEQUENCE_COUNTERS[team_id] = event.sequence
            return event

    def list_events(self, *, team_id: str, after_sequence: int | None = None) -> list[TeamEvent]:
        team = self.get_team(team_id)
        statement = select(TeamEvent).where(TeamEvent.team_id == team.id)
        if after_sequence is not None:
            statement = statement.where(TeamEvent.sequence > after_sequence)
        statement = statement.order_by(TeamEvent.sequence.asc()).limit(200)
        return list(self.session.execute(statement).scalars())

    def get_agent(self, team_id: str, slot_id: str) -> TeamAgent:
        agent = self.session.execute(
            select(TeamAgent).where(TeamAgent.team_id == team_id, TeamAgent.slot_id == slot_id)
        ).scalar_one_or_none()
        if agent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Team agent not found"
            )
        return agent

    def get_task(self, team_id: str, task_id: str) -> TeamTask:
        task = self._find_task(team_id=team_id, task_ref=task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team task not found")
        return task

    def _find_task(self, *, team_id: str, task_ref: str) -> TeamTask | None:
        task_ref = task_ref.strip()
        task = self.session.execute(
            select(TeamTask).where(TeamTask.team_id == team_id, TeamTask.id == task_ref)
        ).scalar_one_or_none()
        if task is not None:
            return task
        if len(task_ref) < 8:
            return None
        matches = list(
            self.session.execute(
                select(TeamTask)
                .where(TeamTask.team_id == team_id, TeamTask.id.startswith(task_ref))
                .order_by(TeamTask.created_at.asc(), TeamTask.id.asc())
            ).scalars()
        )
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f'Task reference "{task_ref}" is ambiguous.',
            )
        return None

    def _get_agent_definition(self, agent_id: str) -> Agent:
        agent = self.session.get(Agent, agent_id)
        if agent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Agent definition not found"
            )
        if agent.organization_id not in (self.organization_id, None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Agent definition not found"
            )
        return agent

    def _get_agent_session(self, session_id: str | None) -> AgentSession | None:
        if not session_id:
            return None
        return self.session.get(AgentSession, session_id)

    def _ensure_agent_session(self, *, team: Team, agent: TeamAgent) -> AgentSession:
        existing = self._get_agent_session(agent.session_id)
        if existing is not None:
            if agent.conversation_id is None:
                agent.conversation_id = existing.id
            return existing

        now = utc_now()
        agent_session = AgentSession(
            organization_id=self.organization_id,
            agent_id=agent.agent_id,
            created_by=self.actor_id,
            title=f"Team: {team.name} / {agent.agent_name}",
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        self.session.add(agent_session)
        self.session.flush()
        agent.session_id = agent_session.id
        agent.conversation_id = agent.conversation_id or agent_session.id
        return agent_session

    def _mirror_message_to_session(
        self,
        *,
        team: Team,
        recipient: TeamAgent,
        message: TeamMailboxMessage,
    ) -> None:
        session = self._ensure_agent_session(team=team, agent=recipient)
        role = "system" if message.type in {"system", "idle_notification", "shutdown_request"} else "user"
        metadata = {
            **(message.metadata_json if isinstance(message.metadata_json, dict) else {}),
            "team_id": team.id,
            "mailbox_message_id": message.id,
            "from_agent_slot_id": message.from_agent_slot_id,
            "to_agent_slot_id": message.to_agent_slot_id,
            "message_type": message.type,
            "summary": message.summary,
            "read": message.read,
        }
        self.session.add(
            AgentMessage(
                session_id=session.id,
                agent_id=recipient.agent_id,
                role=role,
                content=message.content,
                metadata_json=metadata,
                created_at=message.created_at,
            )
        )
        session.updated_at = message.created_at

    def _append_session_message(
        self,
        *,
        team: Team,
        agent: TeamAgent,
        role: str,
        content: str,
        metadata: dict,
    ) -> AgentMessage:
        session = self._ensure_agent_session(team=team, agent=agent)
        created_at = utc_now()
        message = AgentMessage(
            session_id=session.id,
            agent_id=agent.agent_id,
            role=role,
            content=content,
            metadata_json=metadata,
            created_at=created_at,
        )
        self.session.add(message)
        session.updated_at = created_at
        self.session.flush()
        return message

    def _seed_agent_session(
        self,
        *,
        team: Team,
        agent: TeamAgent,
        messages: list[dict],
    ) -> list[AgentMessage]:
        session = self._ensure_agent_session(team=team, agent=agent)
        seeded: list[AgentMessage] = []
        for raw in messages[:200]:
            role = str(raw.get("role") or "").strip()
            content = str(raw.get("content") or "").strip()
            if role not in {"user", "assistant", "system"} or not content:
                continue
            metadata = raw.get("metadata_json") if isinstance(raw.get("metadata_json"), dict) else {}
            created_at = self._parse_seed_created_at(raw.get("created_at"))
            message = AgentMessage(
                session_id=session.id,
                agent_id=agent.agent_id,
                role=role,
                content=content,
                metadata_json={
                    **metadata,
                    "team_id": team.id,
                    "source": "agent_workspace_import",
                    "imported_by": self.actor_id,
                },
                created_at=created_at,
            )
            self.session.add(message)
            seeded.append(message)
        if seeded:
            session.updated_at = seeded[-1].created_at
            self.session.flush()
        return seeded

    @staticmethod
    def _parse_seed_created_at(value: object) -> datetime:
        if isinstance(value, str) and value.strip():
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return utc_now()
        return utc_now()

    def _build_model_messages(
        self,
        *,
        team: Team,
        agent: TeamAgent,
        dispatch_prompt: str,
    ) -> list[ModelMessage]:
        session_messages = self.session_messages(agent, limit=40)
        prior_messages = [
            ModelMessage(role=message.role, content=message.content)
            for message in session_messages[-20:]
            if message.role in {"user", "assistant", "system"} and message.content.strip()
        ]
        return [
            ModelMessage(
                role="system",
                content=(
                    "You are running inside Harness Team Mode, a persistent multi-agent "
                    "conversation room. Reply as this team slot in normal chat prose. "
                    "Use the Team tool names described in the prompt when coordinating, "
                    "but do not mention Run Detail, Trace, Observability, assignments, "
                    "or execution runs unless the user explicitly asks about those products. "
                    f"Team: {team.name}. Slot: {agent.agent_name} ({agent.slot_id})."
                    f"\n\n{TEAM_TOOL_PROTOCOL_PROMPT}"
                ),
            ),
            *prior_messages,
            ModelMessage(role="user", content=dispatch_prompt),
        ]

    def _run_team_model_turn(
        self,
        *,
        team: Team,
        agent: TeamAgent,
        dispatch_prompt: str,
        mailbox_messages: list[TeamMailboxMessage],
        defer_message_wake: bool = False,
        deferred_wake_slot_ids: list[str] | None = None,
    ) -> tuple[ModelResponse, str, list[dict]]:
        messages = self._build_model_messages(
            team=team,
            agent=agent,
            dispatch_prompt=dispatch_prompt,
        )
        response = self.model_runtime.complete(
            organization_id=self.organization_id,
            model_provider=agent.model_provider,
            model_name=agent.model_name,
            messages=messages,
        )
        if response.raw_response.get("mode") == "mock":
            return (
                response,
                self._mock_team_response(agent=agent, mailbox_messages=mailbox_messages),
                [],
            )

        assistant_content = response.content
        tool_results: list[dict] = []
        for _ in range(MAX_TEAM_TOOL_CALLS_PER_TURN):
            tool_calls = self._extract_team_tool_calls(assistant_content)
            if not tool_calls:
                break
            round_results: list[dict] = []
            for tool_call in tool_calls:
                tool_name = str(tool_call.get("tool") or tool_call.get("tool_name") or "").strip()
                args = tool_call.get("args") if isinstance(tool_call.get("args"), dict) else {}
                if tool_name not in TEAM_TOOL_NAMES:
                    result = f"Unknown team tool: {tool_name}"
                    ok = False
                else:
                    try:
                        result = self.call_tool(
                            team_id=team.id,
                            tool_name=tool_name,
                            args=args,
                            from_agent_slot_id=agent.slot_id,
                            defer_message_wake=defer_message_wake,
                            deferred_wake_slot_ids=deferred_wake_slot_ids,
                        )
                        ok = True
                    except HTTPException as exc:
                        result = str(exc.detail)
                        ok = False
                record = {"tool": tool_name, "args": args, "ok": ok, "result": result}
                tool_results.append(record)
                round_results.append(record)
                self.append_event(
                    team_id=team.id,
                    event_type="TEAM_TOOL_CALLED",
                    payload={
                        "slot_id": agent.slot_id,
                        "tool": tool_name,
                        "args": args,
                        "ok": ok,
                        "result": result,
                    },
                    actor_type="agent",
                    actor_id=agent.slot_id,
                )
            messages.extend(
                [
                    ModelMessage(role="assistant", content=self._strip_team_tool_calls(assistant_content)),
                    ModelMessage(
                        role="user",
                        content=(
                            "Team tool results:\n"
                            f"{json.dumps(round_results, ensure_ascii=False, indent=2)}\n\n"
                            "Now reply naturally to the user or teammate. If more team tool calls are required, emit more <team_tool_call>{...}</team_tool_call> blocks."
                        ),
                    ),
                ]
            )
            response = self.model_runtime.complete(
                organization_id=self.organization_id,
                model_provider=agent.model_provider,
                model_name=agent.model_name,
                messages=messages,
            )
            assistant_content = response.content
        return response, self._strip_team_tool_calls(assistant_content).strip(), tool_results

    def _run_team_model_turn_stream(
        self,
        *,
        team: Team,
        agent: TeamAgent,
        dispatch_prompt: str,
        mailbox_messages: list[TeamMailboxMessage],
    ) -> Iterator[dict]:
        messages = self._build_model_messages(
            team=team,
            agent=agent,
            dispatch_prompt=dispatch_prompt,
        )
        assistant_content = ""
        pending_delta = ""
        usage: dict = {}
        raw_response: dict = {}
        for chunk in self.model_runtime.stream(
            organization_id=self.organization_id,
            model_provider=agent.model_provider,
            model_name=agent.model_name,
            messages=messages,
        ):
            if chunk.text:
                assistant_content += chunk.text
                if pending_delta:
                    yield {"type": "delta", "content": pending_delta}
                pending_delta = chunk.text
            if chunk.usage:
                usage.update(chunk.usage)
            if chunk.raw_response:
                raw_response = chunk.raw_response

        response = ModelResponse(
            content=assistant_content,
            model_provider=agent.model_provider,
            model_name=agent.model_name,
            usage=usage,
            raw_response=raw_response,
        )
        if response.raw_response.get("mode") == "mock":
            mock_content = self._mock_team_response(
                agent=agent,
                mailbox_messages=mailbox_messages,
            )
            yield {"type": "delta", "content": mock_content}
            yield {
                "type": "final",
                "response": response,
                "assistant_content": mock_content,
                "tool_results": [],
            }
            return

        if pending_delta:
            yield {"type": "delta", "content": pending_delta}

        tool_results: list[dict] = []
        deferred_wake_slot_ids: list[str] = []
        for _ in range(MAX_TEAM_TOOL_CALLS_PER_TURN):
            tool_calls = self._extract_team_tool_calls(assistant_content)
            if not tool_calls:
                break
            round_results: list[dict] = []
            for tool_call in tool_calls:
                tool_name = str(tool_call.get("tool") or tool_call.get("tool_name") or "").strip()
                args = tool_call.get("args") if isinstance(tool_call.get("args"), dict) else {}
                if tool_name not in TEAM_TOOL_NAMES:
                    result = f"Unknown team tool: {tool_name}"
                    ok = False
                else:
                    try:
                        result = self.call_tool(
                            team_id=team.id,
                            tool_name=tool_name,
                            args=args,
                            from_agent_slot_id=agent.slot_id,
                            defer_message_wake=True,
                            deferred_wake_slot_ids=deferred_wake_slot_ids,
                        )
                        ok = True
                    except HTTPException as exc:
                        result = str(exc.detail)
                        ok = False
                record = {"tool": tool_name, "args": args, "ok": ok, "result": result}
                tool_results.append(record)
                round_results.append(record)
                self.append_event(
                    team_id=team.id,
                    event_type="TEAM_TOOL_CALLED",
                    payload={
                        "slot_id": agent.slot_id,
                        "tool": tool_name,
                        "args": args,
                        "ok": ok,
                        "result": result,
                    },
                    actor_type="agent",
                    actor_id=agent.slot_id,
                )
            messages.extend(
                [
                    ModelMessage(role="assistant", content=self._strip_team_tool_calls(assistant_content)),
                    ModelMessage(
                        role="user",
                        content=(
                            "Team tool results:\n"
                            f"{json.dumps(round_results, ensure_ascii=False, indent=2)}\n\n"
                            "Now reply naturally to the user or teammate. If more team tool calls are required, emit more <team_tool_call>{...}</team_tool_call> blocks."
                        ),
                    ),
                ]
            )
            response = self.model_runtime.complete(
                organization_id=self.organization_id,
                model_provider=agent.model_provider,
                model_name=agent.model_name,
                messages=messages,
            )
            assistant_content = response.content
            yield {"type": "delta", "content": self._strip_team_tool_calls(assistant_content)}

        yield {
            "type": "final",
            "response": response,
            "assistant_content": self._strip_team_tool_calls(assistant_content).strip(),
            "tool_results": tool_results,
            "follow_up_slot_ids": list(dict.fromkeys(deferred_wake_slot_ids)),
        }

    @staticmethod
    def _extract_team_tool_calls(content: str) -> list[dict]:
        calls: list[dict] = []
        for match in TEAM_TOOL_CALL_RE.finditer(content):
            try:
                payload = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                calls.append(payload)
        return calls

    @staticmethod
    def _strip_team_tool_calls(content: str) -> str:
        return TEAM_TOOL_CALL_RE.sub("", content).strip()

    @staticmethod
    def _mock_team_response(
        *,
        agent: TeamAgent,
        mailbox_messages: list[TeamMailboxMessage],
    ) -> str:
        concrete_messages = [
            message.content.strip()
            for message in mailbox_messages
            if message.content.strip()
            and message.type not in {"idle_notification", "system", "shutdown_request"}
        ]
        if concrete_messages:
            latest = concrete_messages[-1]
            return f"我已收到团队邮箱内容：{latest}"
        if agent.role == "leader":
            return "我已收到团队更新，会继续协调团队成员。"
        return "我已收到团队消息，会按当前角色继续处理。"

    def _recipient_slots(self, *, team: Team, target: str, sender: str) -> list[str]:
        agents = self._agents(team.id)
        if target == "leader":
            return [team.leader_slot_id]
        if target in {"team", "*"}:
            return [
                agent.slot_id
                for agent in agents
                if agent.status != "completed" and agent.slot_id != sender
            ]
        if not any(agent.slot_id == target for agent in agents):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标代理不存在")
        return [target]

    def _all_non_leader_agents_settled(self, team: Team) -> bool:
        agents = self._agents(team.id)
        non_leaders = [agent for agent in agents if agent.role != "leader"]
        if not non_leaders:
            return False
        if any(
            agent.status not in {"idle", "completed", "failed", "pending"}
            or bool((agent.metadata_json or {}).get("wake", {}).get("in_progress"))
            for agent in non_leaders
        ):
            return False
        non_leader_slots = [agent.slot_id for agent in non_leaders]
        unread_non_leader_message = self.session.execute(
            select(TeamMailboxMessage.id)
            .where(
                TeamMailboxMessage.team_id == team.id,
                TeamMailboxMessage.to_agent_slot_id.in_(non_leader_slots),
                TeamMailboxMessage.read.is_(False),
            )
            .limit(1)
        ).scalar_one_or_none()
        return unread_non_leader_message is None

    def _agents(self, team_id: str) -> list[TeamAgent]:
        return list(
            self.session.execute(
                select(TeamAgent)
                .where(TeamAgent.team_id == team_id)
                .order_by(TeamAgent.role.asc(), TeamAgent.created_at.asc(), TeamAgent.id.asc())
            ).scalars()
        )

    def _next_slot_id(self, *, team_id: str, name: str) -> str:
        normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in name.strip()).strip("-")
        base = normalized or "agent"
        existing = {agent.slot_id for agent in self._agents(team_id)}
        if base not in existing:
            return base
        index = 2
        while f"{base}-{index}" in existing:
            index += 1
        return f"{base}-{index}"

    @staticmethod
    def _normalize_ref(value: str) -> str:
        normalized = (
            value.strip()
            .replace("\u00a0", " ")
            .replace("\u200b", " ")
            .replace("\u200c", " ")
            .replace("\u200d", " ")
            .replace("\ufeff", " ")
        )
        normalized = re.sub(r"""[\u201c\u201d\u201e\u2018\u2019"']""", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.lower()

    def _resolve_slot_id(self, *, team: Team, ref: str) -> str:
        if ref in {"leader", team.leader_slot_id}:
            return team.leader_slot_id
        agents = self._agents(team.id)
        by_slot = next((agent for agent in agents if agent.slot_id == ref), None)
        if by_slot is not None:
            return by_slot.slot_id
        normalized = self._normalize_ref(ref)
        by_name = next(
            (agent for agent in agents if self._normalize_ref(agent.agent_name) == normalized), None
        )
        if by_name is not None:
            return by_name.slot_id
        available = ", ".join(agent.agent_name for agent in agents)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Teammate "{ref}" not found. Available: {available}',
        )

    def _tool_caller(self, team: Team, from_agent_slot_id: str | None) -> TeamAgent:
        if from_agent_slot_id:
            return self.get_agent(team.id, from_agent_slot_id)
        return self.get_agent(team.id, team.leader_slot_id)

    def _tool_send_message(
        self,
        *,
        team: Team,
        caller: TeamAgent,
        args: dict,
        wake_recipient: bool = True,
        deferred_wake_slot_ids: list[str] | None = None,
    ) -> str:
        target = str(args.get("to") or args.get("target") or "")
        message = str(args.get("message") or args.get("content") or "")
        summary = str(args["summary"]) if args.get("summary") is not None else None
        if not target:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="to is required"
            )
        if not message.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="message is required"
            )

        shutdown_result = self._maybe_handle_shutdown_reply(
            team=team, caller=caller, message=message
        )
        if shutdown_result is not None:
            return shutdown_result

        if target in {"team", "*"}:
            recipients = [
                agent
                for agent in self._agents(team.id)
                if agent.slot_id != caller.slot_id and agent.status != "completed"
            ]
            for recipient in recipients:
                self.write_message(
                    team_id=team.id,
                    target=recipient.slot_id,
                    content=message,
                    from_agent_slot_id=caller.slot_id,
                    summary=summary,
                    wake_recipient=wake_recipient,
                )
                if not wake_recipient and deferred_wake_slot_ids is not None:
                    deferred_wake_slot_ids.append(recipient.slot_id)
            names = ", ".join(agent.agent_name for agent in recipients)
            return f"Message broadcast to {len(recipients)} teammate(s): {names}"

        resolved_target = self._resolve_slot_id(team=team, ref=target)
        self.write_message(
            team_id=team.id,
            target=resolved_target,
            content=message,
            from_agent_slot_id=caller.slot_id,
            summary=summary,
            wake_recipient=wake_recipient,
        )
        if not wake_recipient and deferred_wake_slot_ids is not None:
            deferred_wake_slot_ids.append(resolved_target)
        target_agent = self.get_agent(team.id, resolved_target)
        return f"Message sent to {target_agent.agent_name}'s inbox. They will process it shortly."

    def _maybe_handle_shutdown_reply(
        self, *, team: Team, caller: TeamAgent, message: str
    ) -> str | None:
        trimmed = message.strip()
        if trimmed != SHUTDOWN_APPROVED and not trimmed.startswith(SHUTDOWN_REJECTED_PREFIX):
            return None
        if caller.role == "leader":
            return None
        leader = self.get_agent(team.id, team.leader_slot_id)
        if trimmed == SHUTDOWN_APPROVED:
            member_name = caller.agent_name
            self.remove_agent(team_id=team.id, slot_id=caller.slot_id)
            self.write_message(
                team_id=team.id,
                target=leader.slot_id,
                content=f"{member_name} has shut down and been removed from the team.",
                from_agent_slot_id=caller.slot_id,
            )
            return "Shutdown confirmed. You have been removed from the team."

        reason = trimmed.split(":", 1)[1].strip() if ":" in trimmed else ""
        rejection_reason = reason or "No reason given."
        refusal = f"{caller.agent_name} refused to shut down. Reason: {rejection_reason}"
        self.write_message(
            team_id=team.id,
            target=leader.slot_id,
            content=refusal,
            from_agent_slot_id=caller.slot_id,
        )
        return "Refusal sent to the leader."

    def _tool_spawn_agent(
        self,
        *,
        team: Team,
        args: dict,
        defer_welcome_wake: bool = False,
        deferred_wake_slot_ids: list[str] | None = None,
    ) -> str:
        name = str(args.get("name") or "").strip()
        if not name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="name is required"
            )
        agent_id = self._resolve_spawn_agent_definition_id(args)
        model_name = str(args["model"]) if args.get("model") is not None else None
        new_agent = self.add_agent(
            team_id=team.id,
            agent_id=agent_id,
            agent_name=name,
            role="teammate",
            model_name=model_name,
            wake_welcome=not defer_welcome_wake,
        )
        if defer_welcome_wake and deferred_wake_slot_ids is not None:
            deferred_wake_slot_ids.append(new_agent.slot_id)
        created = f'Teammate "{new_agent.agent_name}" ({new_agent.slot_id}) has been created'
        return (
            f"{created} and joined the team. "
            "You can now assign tasks and send messages to them."
        )

    def _resolve_spawn_agent_definition_id(self, args: dict) -> str:
        custom_agent_id = str(args.get("custom_agent_id") or "").strip()
        if custom_agent_id:
            try:
                self._get_agent_definition(custom_agent_id)
            except HTTPException as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f'Preset assistant "{custom_agent_id}" not found.',
                ) from exc
            return custom_agent_id

        agent_id = str(args.get("agent_id") or args.get("agent_type") or "default").strip() or "default"
        try:
            self._get_agent_definition(agent_id)
        except HTTPException:
            fallback_id = "default"
            self._get_agent_definition(fallback_id)
            return fallback_id
        return agent_id

    def _tool_task_create(
        self,
        *,
        team: Team,
        args: dict,
        defer_owner_wake: bool = False,
        deferred_wake_slot_ids: list[str] | None = None,
    ) -> str:
        subject = str(args.get("subject") or "").strip()
        if not subject:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="subject is required"
            )
        owner_ref = args.get("owner") or args.get("owner_slot_id") or args.get("ownerSlotId")
        owner_slot_id = self._resolve_slot_id(team=team, ref=str(owner_ref)) if owner_ref else None
        task = self.create_task(
            team_id=team.id,
            subject=subject,
            description=str(args.get("description") or ""),
            owner_slot_id=owner_slot_id,
            blocked_by=self._normalize_task_dependency_ids(
                team_id=team.id,
                blocked_by=self._task_dependency_arg(args),
            ),
        )
        if owner_slot_id and defer_owner_wake and deferred_wake_slot_ids is not None:
            deferred_wake_slot_ids.append(owner_slot_id)
        owner_suffix = f" (assigned to {owner_slot_id})" if owner_slot_id else ""
        return f'Task created: [{task.id[:8]}] "{task.subject}"{owner_suffix}'

    def _tool_task_update(self, *, team: Team, caller: TeamAgent, args: dict) -> str:
        task_id = str(
            args.get("task_id")
            or args.get("taskId")
            or args.get("id")
            or args.get("task")
            or ""
        ).strip()
        if not task_id:
            task_id = self._resolve_current_task_for_tool_update(team=team, caller=caller).id
        if not task_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="task_id is required"
            )
        owner_ref = args.get("owner") or args.get("owner_slot_id") or args.get("ownerSlotId")
        owner_slot_id = self._resolve_slot_id(team=team, ref=str(owner_ref)) if owner_ref else None
        status_value = str(args["status"]) if args.get("status") is not None else None
        task = self.update_task(
            team_id=team.id,
            task_id=task_id,
            status_value=status_value,
            owner_slot_id=owner_slot_id,
            update_owner=owner_ref is not None,
            description=str(args["description"]) if args.get("description") is not None else None,
            blocked_by=(
                self._task_dependency_arg(args)
                if self._has_task_dependency_arg(args)
                else None
            ),
        )
        status_suffix = f" Status: {task.status}." if status_value else ""
        owner_suffix = f" Owner: {task.owner_slot_id}." if owner_ref else ""
        return f"Task {task.id[:8]} updated.{status_suffix}{owner_suffix}"

    def _resolve_current_task_for_tool_update(self, *, team: Team, caller: TeamAgent) -> TeamTask:
        tasks = [
            task
            for task in self.list_tasks(team.id)
            if task.owner_slot_id == caller.slot_id and task.status in {"pending", "in_progress"}
        ]
        if len(tasks) == 1:
            return tasks[0]
        if not tasks:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="task_id is required because you have no open assigned task",
            )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="task_id is required because multiple open assigned tasks match you",
        )

    @staticmethod
    def _has_task_dependency_arg(args: dict) -> bool:
        return any(key in args for key in ("blocked_by", "blockedBy", "blocked_by_json"))

    @classmethod
    def _task_dependency_arg(cls, args: dict) -> list[str]:
        raw = args.get("blocked_by")
        if raw is None:
            raw = args.get("blockedBy")
        if raw is None:
            raw = args.get("blocked_by_json")
        if raw is None:
            return []
        if isinstance(raw, str):
            return [raw]
        if isinstance(raw, list):
            return [str(item) for item in raw]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="blocked_by must be a list of task ids",
        )

    def _normalize_task_dependency_ids(
        self,
        *,
        team_id: str,
        blocked_by: list[str],
        task_id: str | None = None,
    ) -> list[str]:
        dependency_ids: list[str] = []
        for dependency_ref in blocked_by:
            dependency = self.get_task(team_id, dependency_ref)
            if task_id is not None and dependency.id == task_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="任务不能依赖自身",
                )
            if dependency.id not in dependency_ids:
                dependency_ids.append(dependency.id)
        return dependency_ids

    def _tool_task_list(self, *, team: Team) -> str:
        tasks = self.list_tasks(team.id)
        if not tasks:
            return "No tasks on the board yet."
        lines = []
        for task in tasks:
            owner_text = f", owner: {task.owner_slot_id}" if task.owner_slot_id else ", unassigned"
            lines.append(f"- [{task.id[:8]}] {task.subject} ({task.status}{owner_text})")
        return "## Team Tasks\n" + "\n".join(lines)

    def _tool_members(self, *, team: Team) -> str:
        agents = self._agents(team.id)
        if not agents:
            return "No team members yet."
        lines = [
            (
                f"- {agent.agent_name} (type: {agent.agent_id}, role: {agent.role}, "
                f"status: {agent.status}, model: {agent.model_provider}/{agent.model_name})"
            )
            for agent in agents
        ]
        return "## Team Members\n" + "\n".join(lines)

    def _tool_rename_agent(self, *, team: Team, args: dict) -> str:
        agent_ref = str(args.get("agent") or "")
        new_name = str(args.get("new_name") or "").strip()
        if not agent_ref or not new_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="agent and new_name are required",
            )
        slot_id = self._resolve_slot_id(team=team, ref=agent_ref)
        old_name = self.get_agent(team.id, slot_id).agent_name
        self.rename_agent(team_id=team.id, slot_id=slot_id, agent_name=new_name)
        return f'Agent renamed: "{old_name}" → "{new_name}"'

    def _tool_shutdown_agent(self, *, team: Team, caller: TeamAgent, args: dict) -> str:
        agent_ref = str(args.get("agent") or args.get("target") or "")
        if not agent_ref:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="agent is required"
            )
        slot_id = self._resolve_slot_id(team=team, ref=agent_ref)
        target = self.get_agent(team.id, slot_id)
        if target.role == "leader":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Cannot shut down the team leader."
            )
        shutdown_message = (
            'The team leader has requested you to shut down. Reply "shutdown_approved" '
            'to confirm, or "shutdown_rejected: <reason>" to refuse.'
        )
        self.write_message(
            team_id=team.id,
            target=target.slot_id,
            content=shutdown_message,
            from_agent_slot_id=caller.slot_id,
            message_type="shutdown_request",
        )
        return f'Shutdown request sent to "{target.agent_name}". Waiting for their confirmation.'

    def _tool_list_models(self, *, team: Team, args: dict) -> str:
        agent_ref = str(args.get("agent_type") or args.get("backend") or "").strip()
        agents = list(
            self.session.execute(
                select(Agent)
                .where(or_(Agent.organization_id.is_(None), Agent.organization_id == self.organization_id))
                .order_by(Agent.model_provider.asc(), Agent.model_name.asc(), Agent.id.asc())
            ).scalars()
        )
        if agent_ref:
            agent = next(
                (
                    candidate
                    for candidate in agents
                    if candidate.id == agent_ref
                    or candidate.name == agent_ref
                    or candidate.model_provider == agent_ref
                ),
                None,
            )
            if agent is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f'Agent type "{agent_ref}" not found.',
                )
            return (
                f"## Available Models for {agent.name}\n"
                f"- provider: {agent.model_provider}\n"
                f"- default model: {agent.model_name}"
            )

        if not agents:
            return "No agent definitions found."

        lines = ["## Available Models"]
        seen: set[tuple[str, str]] = set()
        for agent in agents:
            key = (agent.model_provider, agent.model_name)
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"- {agent.model_provider} / {agent.model_name}")
        return "\n".join(lines)

    def _tool_describe_assistant(self, *, team: Team, args: dict) -> str:
        agent_ref = str(
            args.get("custom_agent_id")
            or args.get("agent_id")
            or args.get("agent_type")
            or args.get("assistant")
            or args.get("name")
            or "default"
        ).strip() or "default"
        agent = self._resolve_agent_definition_by_ref(agent_ref)
        lines = [
            f"# {agent.name} ({agent.id})",
            f"Backend: {agent.model_provider}",
            "",
            "## Description",
            agent.description or "(none)",
            "",
            "## Skills",
        ]
        tools = ", ".join(str(tool) for tool in agent.tools_json) if agent.tools_json else "(none)"
        routing = ", ".join(str(tag) for tag in agent.routing_tags) if agent.routing_tags else "(none)"
        lines.append(f"- tools: {tools}")
        lines.append(f"- routing tags: {routing}")
        lines.append("")
        lines.append("## Example tasks")
        lines.append("(not available in Harness Team Mode yet)")
        lines.append("")
        lines.append(
            f'To spawn this assistant as a teammate, call team_spawn_agent with agent_id="{agent.id}".'
        )
        return "\n".join(lines)

    def _resolve_agent_definition_by_ref(self, ref: str) -> Agent:
        agents = list(
            self.session.execute(
                select(Agent)
                .where(or_(Agent.organization_id.is_(None), Agent.organization_id == self.organization_id))
                .order_by(Agent.id.asc())
            ).scalars()
        )
        normalized_ref = ref.strip().casefold()
        for agent in agents:
            if agent.id.casefold() == normalized_ref or agent.name.casefold() == normalized_ref:
                return agent
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Preset assistant "{ref}" not found.',
        )

    def _normalize_team_name(self, name: str) -> str:
        normalized = name.strip()
        if not normalized:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="团队名称不能为空"
            )
        return normalized

    def _ensure_team_name_available(self, name: str, *, exclude_team_id: str | None = None) -> None:
        statement = select(Team.id).where(
            Team.organization_id == self.organization_id,
            Team.name == name,
        )
        if exclude_team_id is not None:
            statement = statement.where(Team.id != exclude_team_id)
        if self.session.execute(statement).scalar_one_or_none() is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="团队名称已存在")

    def _sync_task_blocks(self, *, team_id: str) -> None:
        tasks = list(
            self.session.execute(select(TeamTask).where(TeamTask.team_id == team_id)).scalars()
        )
        blocks_by_task = {task.id: [] for task in tasks}
        for task in tasks:
            for upstream_id in task.blocked_by_json:
                if upstream_id in blocks_by_task and task.id not in blocks_by_task[upstream_id]:
                    blocks_by_task[upstream_id].append(task.id)
        for task in tasks:
            task.blocks_json = blocks_by_task.get(task.id, [])

    def _remove_completed_from_blockers(self, team_id: str, completed_task_id: str) -> None:
        tasks = list(
            self.session.execute(select(TeamTask).where(TeamTask.team_id == team_id)).scalars()
        )
        for task in tasks:
            if completed_task_id in task.blocked_by_json:
                task.blocked_by_json = [
                    blocker for blocker in task.blocked_by_json if blocker != completed_task_id
                ]
                task.updated_at = utc_now()

    @staticmethod
    def team_summary(team: Team) -> dict:
        return {
            "id": team.id,
            "name": team.name,
            "status": team.status,
            "workspace": team.workspace,
            "workspace_mode": team.workspace_mode,
            "leader_slot_id": team.leader_slot_id,
            "created_at": team.created_at.isoformat() if team.created_at else None,
            "updated_at": team.updated_at.isoformat() if team.updated_at else None,
        }

    @staticmethod
    def agent_summary(agent: TeamAgent) -> dict:
        return {
            "id": agent.id,
            "team_id": agent.team_id,
            "slot_id": agent.slot_id,
            "agent_id": agent.agent_id,
            "role": agent.role,
            "agent_name": agent.agent_name,
            "status": agent.status,
            "model_provider": agent.model_provider,
            "model_name": agent.model_name,
            "conversation_id": agent.conversation_id,
            "session_id": agent.session_id,
            "metadata_json": agent.metadata_json,
            "created_at": agent.created_at.isoformat() if agent.created_at else None,
            "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
        }

    @staticmethod
    def message_summary(message: TeamMailboxMessage) -> dict:
        return {
            "id": message.id,
            "team_id": message.team_id,
            "to_agent_slot_id": message.to_agent_slot_id,
            "from_agent_slot_id": message.from_agent_slot_id,
            "type": message.type,
            "content": message.content,
            "summary": message.summary,
            "read": message.read,
            "files_json": message.files_json,
            "metadata_json": message.metadata_json,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }

    @staticmethod
    def session_message_summary(message: AgentMessage) -> dict:
        return {
            "id": message.id,
            "session_id": message.session_id,
            "agent_id": message.agent_id,
            "role": message.role,
            "content": message.content,
            "metadata_json": message.metadata_json,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }

    @staticmethod
    def task_summary(task: TeamTask) -> dict:
        return {
            "id": task.id,
            "team_id": task.team_id,
            "subject": task.subject,
            "description": task.description,
            "owner_slot_id": task.owner_slot_id,
            "status": task.status,
            "blocked_by_json": task.blocked_by_json,
            "blocks_json": task.blocks_json,
            "metadata_json": task.metadata_json,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }

    @staticmethod
    def unread_counts(messages: Iterable[TeamMailboxMessage]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for message in messages:
            if not message.read:
                counts[message.to_agent_slot_id] = counts.get(message.to_agent_slot_id, 0) + 1
        return counts
