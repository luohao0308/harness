from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.model_gateway import ModelMessage, ModelResponse, ModelStreamChunk
from app.db.models import AgentMessage, AgentSession, TeamMailboxMessage
from app.main import app
from app.teams.service import TeamSessionService
from tests.conftest import AUTH_HEADERS


def _create_team(client: TestClient, name: str = "Aion Style Team") -> dict:
    response = client.post(
        "/api/teams",
        headers=AUTH_HEADERS,
        json={
            "name": name,
            "workspace": "/tmp/harness-team",
            "workspace_mode": "shared",
            "leader_agent_id": "default",
            "leader_name": "Leader",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_team_crud_scopes_to_organization_and_creates_leader(db_session: Session) -> None:
    client = TestClient(app)

    team = _create_team(client)

    assert team["name"] == "Aion Style Team"
    assert team["leader_slot_id"] == "leader"
    assert team["workspace_mode"] == "shared"
    assert team["team_tools"] == sorted(team["team_tools"])
    assert "team_send_message" in team["team_tools"]
    assert len(team["agents"]) == 1
    assert team["agents"][0]["role"] == "leader"
    assert team["agents"][0]["slot_id"] == "leader"
    assert team["agents"][0]["session_id"] is not None
    assert team["agents"][0]["conversation_id"] == team["agents"][0]["session_id"]

    leader_session = db_session.get(AgentSession, team["agents"][0]["session_id"])
    assert leader_session is not None
    assert leader_session.agent_id == "default"
    assert leader_session.title == f"Team: {team['name']} / Leader"
    assert leader_session.status == "ACTIVE"

    listed = client.get("/api/teams", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [team["id"]]

    other_org = client.get(
        f"/api/teams/{team['id']}",
        headers={"Authorization": "Bearer dev-other-org-token"},
    )
    assert other_org.status_code == 404

    renamed = client.patch(
        f"/api/teams/{team['id']}",
        headers=AUTH_HEADERS,
        json={"name": "Renamed Team"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed Team"

    archived = client.delete(f"/api/teams/{team['id']}", headers=AUTH_HEADERS)
    assert archived.status_code == 200
    assert archived.json()["status"] == "ARCHIVED"


def test_team_agent_response_normalizes_stale_active_without_wake_in_progress(
    db_session: Session,
) -> None:
    client = TestClient(app)
    team = _create_team(client)
    teammate = client.post(
        f"/api/teams/{team['id']}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "产品", "role": "teammate"},
    ).json()

    service = TeamSessionService(
        db_session,
        organization_id=team["organization_id"],
        actor_id="test",
    )
    stale_agent = service.get_agent(team["id"], teammate["slot_id"])
    stale_agent.status = "active"
    stale_agent.metadata_json = {}
    db_session.commit()

    response = client.get(f"/api/teams/{team['id']}", headers=AUTH_HEADERS)

    assert response.status_code == 200
    product = next(
        agent for agent in response.json()["agents"] if agent["slot_id"] == teammate["slot_id"]
    )
    assert product["status"] == "idle"
    assert product["metadata_json"] == {}


def test_team_agent_response_normalizes_completed_turn_with_stale_wake_flag(
    db_session: Session,
) -> None:
    client = TestClient(app)
    team = _create_team(client)
    teammate = client.post(
        f"/api/teams/{team['id']}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "产品", "role": "teammate"},
    ).json()

    service = TeamSessionService(
        db_session,
        organization_id=team["organization_id"],
        actor_id="test",
    )
    team_model = service.get_team(team["id"])
    stale_agent = service.get_agent(team["id"], teammate["slot_id"])
    service._append_session_message(
        team=team_model,
        agent=stale_agent,
        role="assistant",
        content="回复已经完成但旧 wake 标记仍在",
        metadata={"event": "team_agent_model_response"},
    )
    stale_agent.status = "active"
    stale_agent.metadata_json = {"wake": {"in_progress": True}}
    db_session.commit()

    response = client.get(f"/api/teams/{team['id']}", headers=AUTH_HEADERS)

    assert response.status_code == 200
    product = next(
        agent for agent in response.json()["agents"] if agent["slot_id"] == teammate["slot_id"]
    )
    assert product["status"] == "idle"
    assert product["metadata_json"]["wake"]["in_progress"] is False
    assert product["session_messages"][-1]["content"] == "回复已经完成但旧 wake 标记仍在"


def test_team_name_conflicts_return_409_instead_of_500() -> None:
    client = TestClient(app)

    created = _create_team(client, name="Aion 协作团队")

    duplicate = client.post(
        "/api/teams",
        headers={**AUTH_HEADERS, "Origin": "http://127.0.0.1:5173"},
        json={
            "name": "Aion 协作团队",
            "workspace": "/tmp/harness-team",
            "workspace_mode": "shared",
            "leader_agent_id": "default",
            "leader_name": "Leader",
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert duplicate.json()["detail"] == "团队名称已存在"

    same_name_other_org = client.post(
        "/api/teams",
        headers={"Authorization": "Bearer dev-other-org-token"},
        json={
            "name": "Aion 协作团队",
            "workspace": "/tmp/harness-team",
            "workspace_mode": "shared",
            "leader_agent_id": "default",
            "leader_name": "Leader",
        },
    )
    assert same_name_other_org.status_code == 201

    second = _create_team(client, name="Renamable Team")
    rename_conflict = client.patch(
        f"/api/teams/{second['id']}",
        headers=AUTH_HEADERS,
        json={"name": created["name"]},
    )
    assert rename_conflict.status_code == 409
    assert rename_conflict.json()["detail"] == "团队名称已存在"


def test_team_leader_prompt_auto_spawns_for_concrete_tasks(db_session: Session) -> None:
    client = TestClient(app)
    team = _create_team(client)
    service = TeamSessionService(
        db_session,
        organization_id=team["organization_id"],
        actor_id="test",
    )
    team_model = service.get_team(team["id"])
    leader = service.get_agent(team["id"], "leader")

    prompt = service._build_role_prompt(team=team_model, agent=leader)

    assert "create the needed teammates yourself when the user gives a concrete task" in prompt
    assert "call `team_spawn_agent` in the same turn" in prompt
    assert "Do NOT call team_spawn_agent immediately" not in prompt
    assert "Wait for explicit confirmation before using team_spawn_agent" not in prompt
    assert "End your turn after the proposal" not in prompt


def test_team_tool_protocol_is_preserved_on_messages_only_wakes(
    db_session: Session,
) -> None:
    client = TestClient(app)
    team = _create_team(client)

    runtime = SequencedTeamRuntime(
        [
            (
                '<team_tool_call>{"tool":"team_spawn_agent","args":'
                '{"name":"Research Agent","agent_id":"default"}}</team_tool_call>'
            ),
            "我已加入团队，等待任务。",
            "Research Agent 已创建。",
        ]
    )
    service = TeamSessionService(
        db_session,
        organization_id=team["organization_id"],
        actor_id="test",
        model_runtime=runtime,
    )
    leader = service.get_agent(team["id"], "leader")
    leader.status = "idle"
    leader.metadata_json = {
        "team_tools": [],
        "wake": {"has_prompted": True},
    }
    service.write_message(
        team_id=team["id"],
        target="leader",
        content="确认，你创建 Research Agent",
        wake_recipient=False,
    )

    service.wake_agent(team_id=team["id"], slot_id="leader")
    db_session.commit()

    first_call = runtime.calls[0]
    assert first_call[0].role == "system"
    assert "If the user confirms a previously proposed lineup" in first_call[0].content
    assert "team_spawn_agent" in first_call[0].content
    assert any("确认，你创建 Research Agent" in message.content for message in first_call)

    after_wake = client.get(f"/api/teams/{team['id']}", headers=AUTH_HEADERS).json()
    assert any(agent["agent_name"] == "Research Agent" for agent in after_wake["agents"])
    leader_after = next(agent for agent in after_wake["agents"] if agent["slot_id"] == "leader")
    assert leader_after["metadata_json"]["wake"]["last_prompt_kind"] == "messages_only"
    assert (
        leader_after["session_messages"][-1]["metadata_json"]["tool_results"][0]["tool"]
        == "team_spawn_agent"
    )


def test_team_create_seeds_leader_session_without_mailbox_unread(
    db_session: Session,
) -> None:
    client = TestClient(app)

    response = client.post(
        "/api/teams",
        headers=AUTH_HEADERS,
        json={
            "name": "Seeded Workspace Team",
            "workspace": "/tmp/harness-team",
            "workspace_mode": "shared",
            "leader_agent_id": "default",
            "leader_name": "Leader",
            "seed_messages": [
                {
                    "role": "user",
                    "content": "当前智能体页面的问题",
                    "created_at": "2026-05-23T08:00:00Z",
                    "metadata_json": {"workspace_node_id": "node-1"},
                },
                {
                    "role": "assistant",
                    "content": "当前智能体页面的回答",
                    "created_at": "2026-05-23T08:01:00Z",
                    "metadata_json": {"source_run_id": "run-seeded-1"},
                },
            ],
        },
    )

    assert response.status_code == 201, response.text
    team = response.json()
    leader = team["agents"][0]
    assert team["messages"] == []
    assert team["unread_counts"] == {}
    assert [message["content"] for message in leader["session_messages"]] == [
        "当前智能体页面的问题",
        "当前智能体页面的回答",
    ]
    assert leader["session_messages"][0]["metadata_json"] == {
        "workspace_node_id": "node-1",
        "team_id": team["id"],
        "source": "agent_workspace_import",
        "imported_by": "dev-engineer",
    }
    assert leader["session_messages"][1]["metadata_json"]["source_run_id"] == "run-seeded-1"

    persisted = db_session.execute(
        select(AgentMessage)
        .where(AgentMessage.session_id == leader["session_id"])
        .order_by(AgentMessage.created_at.asc(), AgentMessage.id.asc())
    ).scalars().all()
    assert [message.content for message in persisted] == [
        "当前智能体页面的问题",
        "当前智能体页面的回答",
    ]

    events = client.get(f"/api/teams/{team['id']}/events", headers=AUTH_HEADERS).json()
    created_event = next(event for event in events if event["event_type"] == "TEAM_CREATED")
    assert created_event["payload_json"]["seeded_message_count"] == 2
    session_events = [
        event for event in events if event["event_type"] == "TEAM_AGENT_SESSION_MESSAGE"
    ]
    assert len(session_events) == 1
    assert session_events[0]["payload_json"]["slot_id"] == "leader"


def test_team_agents_mailbox_leader_entrypoint_and_read_flow(db_session: Session) -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]

    added = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "产品", "role": "teammate"},
    )
    assert added.status_code == 201, added.text
    product = added.json()
    assert product["slot_id"]
    assert product["role"] == "teammate"
    assert product["session_id"] is not None
    assert product["conversation_id"] == product["session_id"]

    renamed = client.patch(
        f"/api/teams/{team_id}/agents/{product['slot_id']}",
        headers=AUTH_HEADERS,
        json={"agent_name": "产品经理"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["agent_name"] == "产品经理"
    assert renamed.json()["metadata_json"]["original_name"] == "产品"
    renamed_session = db_session.get(AgentSession, product["session_id"])
    assert renamed_session is not None
    assert renamed_session.title == f"Team: {team['name']} / 产品经理"

    after_spawn = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    product_after_spawn = next(
        agent for agent in after_spawn["agents"] if agent["slot_id"] == product["slot_id"]
    )
    spawn_wake = product_after_spawn["metadata_json"]["wake"]
    assert spawn_wake["last_prompt_kind"] == "full"
    assert "# You are a Team Member" in spawn_wake["last_prompt"]
    assert "If you have a clear task assignment" in spawn_wake["last_prompt"]
    assert "Standing by" in spawn_wake["last_prompt"]

    direct = client.post(
        f"/api/teams/{team_id}/messages",
        headers=AUTH_HEADERS,
        json={"target": product["slot_id"], "content": "请拆解需求"},
    )
    assert direct.status_code == 201
    assert direct.json()["to_agent_slot_id"] == product["slot_id"]
    product_after_delivery = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    product_before_manual_wake = next(
        agent
        for agent in product_after_delivery["agents"]
        if agent["slot_id"] == product["slot_id"]
    )
    assert product_before_manual_wake["metadata_json"]["wake"]["last_prompt_kind"] == "full"

    ui = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "UI", "role": "teammate"},
    )
    assert ui.status_code == 201, ui.text
    ui_agent = ui.json()

    team_entry = client.post(
        f"/api/teams/{team_id}/messages",
        headers=AUTH_HEADERS,
        json={"target": "team", "content": "同步当前任务板"},
    )
    assert team_entry.status_code == 201
    assert team_entry.json()["to_agent_slot_id"] == "leader"

    before_idle = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    leader_before_idle = next(
        agent for agent in before_idle["agents"] if agent["slot_id"] == "leader"
    )
    leader_before_idle_wake = leader_before_idle["metadata_json"]["wake"]
    assert leader_before_idle_wake.get("last_prompt_kind") is None
    assert leader_before_idle_wake.get("last_prompt") is None

    manual_wake_product = client.post(
        f"/api/teams/{team_id}/agents/{product['slot_id']}/wake",
        headers=AUTH_HEADERS,
    )
    assert manual_wake_product.status_code == 200

    manual_wake_leader = client.post(
        f"/api/teams/{team_id}/agents/leader/wake",
        headers=AUTH_HEADERS,
    )
    assert manual_wake_leader.status_code == 200

    mailbox = client.post(
        f"/api/teams/{team_id}/agents/{product['slot_id']}/mailbox/read",
        headers=AUTH_HEADERS,
    )
    assert mailbox.status_code == 200
    assert mailbox.json() == []

    delivered = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    product_messages = [
        message
        for message in delivered["messages"]
        if message["to_agent_slot_id"] == product["slot_id"]
    ]
    product_contents = [message["content"] for message in product_messages]
    assert all(message["read"] for message in product_messages)
    assert 'You have been spawned as "产品"' in product_contents[0]
    assert "请拆解需求" in product_contents
    assert "同步当前任务板" in product_contents
    ui_messages = [
        message
        for message in delivered["messages"]
        if message["to_agent_slot_id"] == ui_agent["slot_id"]
    ]
    assert any(message["content"] == "同步当前任务板" for message in ui_messages)

    product_after_wake = next(
        agent for agent in delivered["agents"] if agent["slot_id"] == product["slot_id"]
    )
    assert product_after_wake["status"] == "idle"
    wake_state = product_after_wake["metadata_json"]["wake"]
    assert wake_state["has_prompted"] is True
    assert wake_state["last_prompt_kind"] == "messages_only"
    assert "[From User] 请拆解需求" in wake_state["last_prompt"]

    after_idle = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    leader_after_idle = next(
        agent for agent in after_idle["agents"] if agent["slot_id"] == "leader"
    )
    assert leader_after_idle["status"] == "idle"
    leader_after_idle_wake = leader_after_idle["metadata_json"]["wake"]
    assert leader_after_idle_wake["last_prompt_kind"] == "full"
    assert "同步当前任务板" in leader_after_idle_wake["last_prompt"]
    assert "Turn completed" in leader_after_idle_wake["last_prompt"]

    teammate_session_messages = db_session.execute(
        select(AgentMessage)
        .where(AgentMessage.session_id == product["session_id"])
        .order_by(AgentMessage.created_at.asc(), AgentMessage.id.asc())
    ).scalars().all()
    assert teammate_session_messages[0].role == "system"
    assert any(message.role == "user" for message in teammate_session_messages)
    assert any(message.content == "请拆解需求" for message in teammate_session_messages)
    assert any(
        message.content.startswith('You have been spawned as "产品"')
        for message in teammate_session_messages
    )
    assert any(
        message.role == "assistant"
        and message.metadata_json.get("event") == "team_agent_model_response"
        and message.metadata_json.get("prompt_kind") == "messages_only"
        and message.metadata_json.get("model_provider") == "deepseek-flash"
        and "同步当前任务板" in message.content
        for message in teammate_session_messages
    )
    assert product_after_wake["session_messages"][0]["role"] == "system"
    assert any(message["role"] == "user" for message in product_after_wake["session_messages"])
    assert any(
        message["content"] == "请拆解需求"
        for message in product_after_wake["session_messages"]
    )
    assert any(
        message["content"] == "同步当前任务板"
        for message in product_after_wake["session_messages"]
    )
    assert any(
        message["role"] == "assistant"
        and message["metadata_json"].get("event") == "team_agent_model_response"
        for message in product_after_wake["session_messages"]
    )

    session_message_events = [
        event
        for event in client.get(f"/api/teams/{team_id}/events", headers=AUTH_HEADERS).json()
        if event["event_type"] == "TEAM_AGENT_SESSION_MESSAGE"
    ]
    product_session_event = next(
        event
        for event in session_message_events
        if event["payload_json"]["slot_id"] == product["slot_id"]
    )
    assert product_session_event["payload_json"]["messages"][0]["role"] == "assistant"

    leader_mailbox = client.post(
        f"/api/teams/{team_id}/agents/leader/mailbox/read",
        headers=AUTH_HEADERS,
    )
    assert leader_mailbox.status_code == 200
    assert leader_mailbox.json() == []
    delivered_after_leader = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    leader_after_wake = next(
        agent for agent in delivered_after_leader["agents"] if agent["slot_id"] == "leader"
    )
    assert leader_after_wake["status"] == "idle"
    leader_wake = leader_after_wake["metadata_json"]["wake"]
    assert leader_wake["last_prompt_kind"] == "full"
    assert "同步当前任务板" in leader_wake["last_prompt"]
    assert "Turn completed" in leader_wake["last_prompt"]

    after_read = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    assert after_read["unread_counts"].get(product["slot_id"], 0) == 0
    product_after_read = next(
        agent for agent in after_read["agents"] if agent["slot_id"] == product["slot_id"]
    )
    assert product_after_read["status"] == "idle"

    removed = client.delete(
        f"/api/teams/{team_id}/agents/{product['slot_id']}",
        headers=AUTH_HEADERS,
    )
    assert removed.status_code == 200
    db_session.expire_all()
    archived_session = db_session.get(AgentSession, product["session_id"])
    assert archived_session is not None
    assert archived_session.status == "ARCHIVED"

    remove_leader = client.delete(f"/api/teams/{team_id}/agents/leader", headers=AUTH_HEADERS)
    assert remove_leader.status_code == 409


def test_team_mailbox_star_target_routes_to_active_teammates_except_sender() -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]

    product = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "产品", "role": "teammate"},
    ).json()
    ui = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "UI", "role": "teammate"},
    ).json()

    broadcast = client.post(
        f"/api/teams/{team_id}/messages",
        headers=AUTH_HEADERS,
        json={
            "target": "*",
            "from_agent_slot_id": "leader",
            "content": "全员同步",
            "summary": "broadcast",
            "files": ["docs/spec.md"],
        },
    )
    assert broadcast.status_code == 201

    delivered = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    routed_messages = [
        message for message in delivered["messages"] if message["content"] == "全员同步"
    ]
    assert {message["to_agent_slot_id"] for message in routed_messages} == {
        product["slot_id"],
        ui["slot_id"],
    }
    assert all(message["from_agent_slot_id"] == "leader" for message in routed_messages)
    assert all(message["summary"] == "broadcast" for message in routed_messages)
    assert all(message["files_json"] == ["docs/spec.md"] for message in routed_messages)


def test_team_mailbox_read_returns_and_marks_only_target_unread_messages(
    db_session: Session,
) -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]
    product = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "产品", "role": "teammate"},
    ).json()

    manual_message = TeamMailboxMessage(
        team_id=team_id,
        organization_id=team["organization_id"],
        to_agent_slot_id=product["slot_id"],
        from_agent_slot_id="leader",
        type="message",
        content="只读一次",
        summary=None,
        read=False,
        files_json=[],
        metadata_json={},
    )
    leader_message = TeamMailboxMessage(
        team_id=team_id,
        organization_id=team["organization_id"],
        to_agent_slot_id="leader",
        from_agent_slot_id=product["slot_id"],
        type="message",
        content="不要被产品读取",
        summary=None,
        read=False,
        files_json=[],
        metadata_json={},
    )
    db_session.add_all([manual_message, leader_message])
    db_session.commit()

    mailbox = client.post(
        f"/api/teams/{team_id}/agents/{product['slot_id']}/mailbox/read",
        headers=AUTH_HEADERS,
    )
    assert mailbox.status_code == 200
    assert [message["id"] for message in mailbox.json()] == [manual_message.id]
    assert mailbox.json()[0]["read"] is True

    db_session.expire_all()
    assert db_session.get(TeamMailboxMessage, manual_message.id).read is True
    assert db_session.get(TeamMailboxMessage, leader_message.id).read is False
    after_read = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    assert after_read["unread_counts"].get(product["slot_id"], 0) == 0
    assert after_read["unread_counts"]["leader"] == 1


def test_team_message_delivery_is_decoupled_from_wake_failure(monkeypatch) -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]
    product = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "产品", "role": "teammate"},
    ).json()

    def fail_wake(self, *, team_id: str, slot_id: str):  # noqa: ARG001
        raise RuntimeError("wake worker unavailable")

    monkeypatch.setattr(TeamSessionService, "wake_agent", fail_wake)

    delivered = client.post(
        f"/api/teams/{team_id}/messages",
        headers=AUTH_HEADERS,
        json={"target": product["slot_id"], "content": "wake 失败也要入箱"},
    )
    assert delivered.status_code == 201, delivered.text
    assert delivered.json()["content"] == "wake 失败也要入箱"

    after_delivery = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    persisted = [
        message
        for message in after_delivery["messages"]
        if message["content"] == "wake 失败也要入箱"
    ]
    assert len(persisted) == 1
    assert persisted[0]["read"] is False
    assert after_delivery["unread_counts"][product["slot_id"]] >= 1

    events = client.get(f"/api/teams/{team_id}/events", headers=AUTH_HEADERS)
    assert events.status_code == 200
    wake_failures = [
        event for event in events.json() if event["event_type"] == "TEAM_AGENT_WAKE_FAILED"
    ]
    assert wake_failures == []


def test_team_idle_notification_wakes_leader_only_after_all_teammates_settle() -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]
    product = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "产品", "role": "teammate"},
    ).json()
    ui = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "UI", "role": "teammate"},
    ).json()

    client.post(
        f"/api/teams/{team_id}/messages",
        headers=AUTH_HEADERS,
        json={"target": product["slot_id"], "content": "产品先整理需求"},
    )
    client.post(
        f"/api/teams/{team_id}/messages",
        headers=AUTH_HEADERS,
        json={"target": ui["slot_id"], "content": "UI 同步界面状态"},
    )
    before_idle = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    leader_before_idle = next(
        agent for agent in before_idle["agents"] if agent["slot_id"] == "leader"
    )
    previous_leader_woke_at = leader_before_idle["metadata_json"]["wake"]["last_woke_at"]

    product_wake = client.post(
        f"/api/teams/{team_id}/agents/{product['slot_id']}/wake",
        headers=AUTH_HEADERS,
    )
    assert product_wake.status_code == 200
    after_product_idle = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    leader_after_product_idle = next(
        agent for agent in after_product_idle["agents"] if agent["slot_id"] == "leader"
    )
    assert (
        leader_after_product_idle["metadata_json"]["wake"]["last_woke_at"]
        == previous_leader_woke_at
    )
    assert after_product_idle["unread_counts"]["leader"] == 1

    ui_wake = client.post(
        f"/api/teams/{team_id}/agents/{ui['slot_id']}/wake",
        headers=AUTH_HEADERS,
    )
    assert ui_wake.status_code == 200
    after_all_idle = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    leader_after_all_idle = next(
        agent for agent in after_all_idle["agents"] if agent["slot_id"] == "leader"
    )
    assert leader_after_all_idle["metadata_json"]["wake"]["last_prompt_kind"] == "messages_only"
    assert "Turn completed" in leader_after_all_idle["metadata_json"]["wake"]["last_prompt"]
    assert after_all_idle["unread_counts"].get("leader", 0) == 0


def test_team_agent_inactivity_timeout_marks_failed_and_notifies_leader(
    db_session: Session,
) -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]
    product = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "产品", "role": "teammate"},
    ).json()

    product_agent = TeamSessionService(
        db_session,
        organization_id=team["organization_id"],
        actor_id="test",
    ).get_agent(team_id, product["slot_id"])
    product_agent.status = "active"
    db_session.commit()

    service = TeamSessionService(
        db_session,
        organization_id=team["organization_id"],
        actor_id="test",
    )
    timed_out = service.report_agent_inactivity_timeout(
        team_id=team_id,
        slot_id=product["slot_id"],
        timeout_seconds=60,
    )
    db_session.commit()

    assert timed_out.status == "failed"
    assert timed_out.metadata_json["wake"]["in_progress"] is False
    assert timed_out.metadata_json["wake"]["last_error"] == (
        "stopped responding after 60s without sending any update"
    )

    after_timeout = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    product_after_timeout = next(
        agent for agent in after_timeout["agents"] if agent["slot_id"] == product["slot_id"]
    )
    leader_after_timeout = next(
        agent for agent in after_timeout["agents"] if agent["slot_id"] == "leader"
    )
    assert product_after_timeout["status"] == "failed"
    assert leader_after_timeout["metadata_json"]["wake"]["last_prompt_kind"] == "messages_only"
    leader_prompt = leader_after_timeout["metadata_json"]["wake"]["last_prompt"]
    assert "stopped responding after 60s" in leader_prompt
    assert any(
        message["to_agent_slot_id"] == "leader"
        and message["from_agent_slot_id"] == product["slot_id"]
        and message["type"] == "idle_notification"
        and "replace them with another agent" in message["content"]
        for message in after_timeout["messages"]
    )

    events = client.get(f"/api/teams/{team_id}/events", headers=AUTH_HEADERS).json()
    assert any(event["event_type"] == "TEAM_AGENT_INACTIVITY_TIMEOUT" for event in events)
    assert any(agent["slot_id"] == product["slot_id"] for agent in after_timeout["agents"])


def test_team_teammate_crash_preserves_slot_and_writes_testament_to_leader(
    db_session: Session,
) -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]
    product = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "产品", "role": "teammate"},
    ).json()

    product_agent = TeamSessionService(
        db_session,
        organization_id=team["organization_id"],
        actor_id="test",
    ).get_agent(team_id, product["slot_id"])
    product_agent.status = "active"
    product_agent.metadata_json = {
        **product_agent.metadata_json,
        "wake": {"in_progress": True, "started_at": "2026-05-23T00:00:00+00:00"},
    }
    db_session.commit()

    service = TeamSessionService(
        db_session,
        organization_id=team["organization_id"],
        actor_id="test",
    )
    crashed = service.report_agent_crash(
        team_id=team_id,
        slot_id=product["slot_id"],
        error_message="process exited with code 137",
    )
    db_session.commit()

    assert crashed.status == "failed"
    assert crashed.metadata_json["wake"]["in_progress"] is False
    assert crashed.metadata_json["wake"]["last_error"] == "process exited with code 137"

    after_crash = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    product_after_crash = next(
        agent for agent in after_crash["agents"] if agent["slot_id"] == product["slot_id"]
    )
    leader_after_crash = next(
        agent for agent in after_crash["agents"] if agent["slot_id"] == "leader"
    )
    assert product_after_crash["status"] == "failed"
    assert product_after_crash["session_id"] == product["session_id"]
    leader_prompt = leader_after_crash["metadata_json"]["wake"]["last_prompt"]
    assert '[System] Member "产品" (default) crashed.' in leader_prompt
    assert "The member slot is preserved and can be recovered if needed." in leader_prompt

    testament = next(
        message
        for message in after_crash["messages"]
        if message["from_agent_slot_id"] == product["slot_id"]
        and message["to_agent_slot_id"] == "leader"
        and message["summary"] == "产品 crashed"
    )
    assert testament["type"] == "message"
    assert testament["read"] is True
    assert testament["content"] == (
        '[System] Member "产品" (default) crashed. '
        "Error: process exited with code 137. "
        "The member slot is preserved and can be recovered if needed."
    )

    db_session.expire_all()
    crashed_session = db_session.get(AgentSession, product["session_id"])
    assert crashed_session is not None
    assert crashed_session.status == "FAILED"

    events = client.get(f"/api/teams/{team_id}/events", headers=AUTH_HEADERS).json()
    assert any(event["event_type"] == "TEAM_AGENT_CRASHED" for event in events)
    assert any(agent["slot_id"] == product["slot_id"] for agent in after_crash["agents"])


def test_team_leader_crash_marks_failed_without_self_mailbox_notification(
    db_session: Session,
) -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]

    leader_agent = TeamSessionService(
        db_session,
        organization_id=team["organization_id"],
        actor_id="test",
    ).get_agent(team_id, "leader")
    leader_agent.status = "active"
    leader_agent.metadata_json = {
        **leader_agent.metadata_json,
        "wake": {"in_progress": True, "started_at": "2026-05-23T00:00:00+00:00"},
    }
    db_session.commit()

    service = TeamSessionService(
        db_session,
        organization_id=team["organization_id"],
        actor_id="test",
    )
    crashed = service.report_agent_crash(
        team_id=team_id,
        slot_id="leader",
        error_message="leader process crashed",
    )
    db_session.commit()

    assert crashed.status == "failed"
    assert crashed.metadata_json["wake"]["in_progress"] is False
    assert crashed.metadata_json["wake"]["last_error"] == "leader process crashed"

    after_crash = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    leader_after_crash = next(
        agent for agent in after_crash["agents"] if agent["slot_id"] == "leader"
    )
    assert leader_after_crash["status"] == "failed"
    assert after_crash["messages"] == []

    db_session.expire_all()
    crashed_session = db_session.get(AgentSession, team["agents"][0]["session_id"])
    assert crashed_session is not None
    assert crashed_session.status == "FAILED"

    events = client.get(f"/api/teams/{team_id}/events", headers=AUTH_HEADERS).json()
    assert any(event["event_type"] == "TEAM_AGENT_CRASHED" for event in events)


def test_team_tools_match_aionui_mail_and_shutdown_protocol() -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]

    list_models = client.post(
        f"/api/teams/{team_id}/tools/team_list_models",
        headers=AUTH_HEADERS,
        json={"from_agent_slot_id": "leader", "args": {}},
    )
    assert list_models.status_code == 200
    assert "## Available Models" in list_models.json()["result"]

    describe = client.post(
        f"/api/teams/{team_id}/tools/team_describe_assistant",
        headers=AUTH_HEADERS,
        json={"from_agent_slot_id": "leader", "args": {"custom_agent_id": "default"}},
    )
    assert describe.status_code == 200
    assert "default" in describe.json()["result"]

    describe_default = client.post(
        f"/api/teams/{team_id}/tools/team_describe_assistant",
        headers=AUTH_HEADERS,
        json={"from_agent_slot_id": "leader", "args": {}},
    )
    assert describe_default.status_code == 200
    assert "default" in describe_default.json()["result"]

    describe_alias = client.post(
        f"/api/teams/{team_id}/tools/team_describe_assistant",
        headers=AUTH_HEADERS,
        json={"from_agent_slot_id": "leader", "args": {"agent_id": "default"}},
    )
    assert describe_alias.status_code == 200
    assert "default" in describe_alias.json()["result"]

    for alias_args in (
        {"agent_type": "default"},
        {"assistant": "default"},
        {"name": "Default Agent"},
    ):
        describe_alias = client.post(
            f"/api/teams/{team_id}/tools/team_describe_assistant",
            headers=AUTH_HEADERS,
            json={"from_agent_slot_id": "leader", "args": alias_args},
        )
        assert describe_alias.status_code == 200
        assert "default" in describe_alias.json()["result"]

    spawned = client.post(
        f"/api/teams/{team_id}/tools/team_spawn_agent",
        headers=AUTH_HEADERS,
        json={"from_agent_slot_id": "leader", "args": {"name": "研究"}},
    )
    assert spawned.status_code == 200, spawned.text
    assert 'Teammate "研究"' in spawned.json()["result"]

    team_after_spawn = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    researcher = next(
        agent for agent in team_after_spawn["agents"] if agent["agent_name"] == "研究"
    )
    assert researcher["status"] == "idle"

    non_leader_spawn = client.post(
        f"/api/teams/{team_id}/tools/team_spawn_agent",
        headers=AUTH_HEADERS,
        json={"from_agent_slot_id": researcher["slot_id"], "args": {"name": "越权"}},
    )
    assert non_leader_spawn.status_code == 403

    direct = client.post(
        f"/api/teams/{team_id}/tools/team_send_message",
        headers=AUTH_HEADERS,
        json={
            "from_agent_slot_id": "leader",
            "args": {"to": "研究", "message": "请先收集资料"},
        },
    )
    assert direct.status_code == 200
    assert "Message sent to" in direct.json()["result"]

    shutdown_leader = client.post(
        f"/api/teams/{team_id}/tools/team_shutdown_agent",
        headers=AUTH_HEADERS,
        json={"from_agent_slot_id": "leader", "args": {"agent": "leader"}},
    )
    assert shutdown_leader.status_code == 409

    shutdown = client.post(
        f"/api/teams/{team_id}/tools/team_shutdown_agent",
        headers=AUTH_HEADERS,
        json={"from_agent_slot_id": "leader", "args": {"agent": "研究"}},
    )
    assert shutdown.status_code == 200
    assert "Shutdown request sent" in shutdown.json()["result"]

    researcher_mail = client.post(
        f"/api/teams/{team_id}/agents/{researcher['slot_id']}/mailbox/read",
        headers=AUTH_HEADERS,
    )
    assert researcher_mail.status_code == 200
    assert researcher_mail.json() == []
    after_shutdown_request = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    researcher_after_shutdown_request = next(
        agent
        for agent in after_shutdown_request["agents"]
        if agent["slot_id"] == researcher["slot_id"]
    )
    assert (
        researcher_after_shutdown_request["metadata_json"]["wake"]["last_prompt_kind"]
        == "messages_only"
    )
    assert any(
        message["type"] == "shutdown_request" and message["read"]
        for message in after_shutdown_request["messages"]
    )

    rejected = client.post(
        f"/api/teams/{team_id}/tools/team_send_message",
        headers=AUTH_HEADERS,
        json={
            "from_agent_slot_id": researcher["slot_id"],
            "args": {"to": "leader", "message": "shutdown_rejected: still working"},
        },
    )
    assert rejected.status_code == 200
    assert rejected.json()["result"] == "Refusal sent to the leader."
    still_present = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    assert any(agent["slot_id"] == researcher["slot_id"] for agent in still_present["agents"])

    approved = client.post(
        f"/api/teams/{team_id}/tools/team_send_message",
        headers=AUTH_HEADERS,
        json={
            "from_agent_slot_id": researcher["slot_id"],
            "args": {"to": "leader", "message": "shutdown_approved"},
        },
    )
    assert approved.status_code == 200
    assert approved.json()["result"] == "Shutdown confirmed. You have been removed from the team."
    after_shutdown = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    assert all(agent["slot_id"] != researcher["slot_id"] for agent in after_shutdown["agents"])
    assert any(
        "has shut down and been removed" in message["content"]
        for message in after_shutdown["messages"]
    )


def test_team_spawn_agent_honors_custom_agent_id_and_falls_back_for_unknown_types() -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]

    spawned_custom = client.post(
        f"/api/teams/{team_id}/tools/team_spawn_agent",
        headers=AUTH_HEADERS,
        json={
            "from_agent_slot_id": "leader",
            "args": {"name": "资料研究", "custom_agent_id": "researcher"},
        },
    )
    assert spawned_custom.status_code == 200, spawned_custom.text
    assert 'Teammate "资料研究"' in spawned_custom.json()["result"]

    after_custom_spawn = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    custom_agent = next(
        agent for agent in after_custom_spawn["agents"] if agent["agent_name"] == "资料研究"
    )
    assert custom_agent["agent_id"] == "researcher"

    unknown_custom = client.post(
        f"/api/teams/{team_id}/tools/team_spawn_agent",
        headers=AUTH_HEADERS,
        json={
            "from_agent_slot_id": "leader",
            "args": {"name": "不存在预设", "custom_agent_id": "missing-preset"},
        },
    )
    assert unknown_custom.status_code == 404
    assert unknown_custom.json()["detail"] == 'Preset assistant "missing-preset" not found.'

    unknown_type = client.post(
        f"/api/teams/{team_id}/tools/team_spawn_agent",
        headers=AUTH_HEADERS,
        json={
            "from_agent_slot_id": "leader",
            "args": {"name": "不存在类型", "agent_type": "missing-agent-type"},
        },
    )
    assert unknown_type.status_code == 200, unknown_type.text
    assert 'Teammate "不存在类型"' in unknown_type.json()["result"]

    after_unknown_spawn = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    fallback_agent = next(
        agent for agent in after_unknown_spawn["agents"] if agent["agent_name"] == "不存在类型"
    )
    assert fallback_agent["agent_id"] == "default"


def test_team_tool_member_lookup_normalizes_quotes_spaces_and_zero_width_chars() -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]

    teammate = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "资料  研究", "role": "teammate"},
    ).json()

    delivered = client.post(
        f"/api/teams/{team_id}/tools/team_send_message",
        headers=AUTH_HEADERS,
        json={
            "from_agent_slot_id": "leader",
            "args": {"to": "\u201c资料\u200b 研究\u201d", "message": "按规范化名称投递"},
        },
    )
    assert delivered.status_code == 200, delivered.text

    team_after_delivery = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    assert any(
        message["to_agent_slot_id"] == teammate["slot_id"]
        and message["content"] == "按规范化名称投递"
        for message in team_after_delivery["messages"]
    )


def test_team_leader_only_tools_reject_teammate_callers() -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]

    teammate = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "研究", "role": "teammate"},
    ).json()

    rename_leader = client.post(
        f"/api/teams/{team_id}/tools/team_rename_agent",
        headers=AUTH_HEADERS,
        json={
            "from_agent_slot_id": teammate["slot_id"],
            "args": {"agent": "leader", "new_name": "越权改名"},
        },
    )
    assert rename_leader.status_code == 403

    shutdown_leader = client.post(
        f"/api/teams/{team_id}/tools/team_shutdown_agent",
        headers=AUTH_HEADERS,
        json={"from_agent_slot_id": teammate["slot_id"], "args": {"agent": "leader"}},
    )
    assert shutdown_leader.status_code == 403


def test_team_task_tools_return_aionui_style_text_board() -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]

    created = client.post(
        f"/api/teams/{team_id}/tools/team_task_create",
        headers=AUTH_HEADERS,
        json={
            "from_agent_slot_id": "leader",
            "args": {
                "subject": "定义邮箱协议",
                "description": "复刻 AionUi mailbox",
                "owner": "leader",
            },
        },
    )
    assert created.status_code == 200, created.text
    assert "Task created:" in created.json()["result"]

    listed = client.post(
        f"/api/teams/{team_id}/tools/team_task_list",
        headers=AUTH_HEADERS,
        json={"from_agent_slot_id": "leader", "args": {}},
    )
    assert listed.status_code == 200
    assert "## Team Tasks" in listed.json()["result"]
    assert "定义邮箱协议" in listed.json()["result"]

    members = client.post(
        f"/api/teams/{team_id}/tools/team_members",
        headers=AUTH_HEADERS,
        json={"from_agent_slot_id": "leader", "args": {}},
    )
    assert members.status_code == 200
    assert "## Team Members" in members.json()["result"]
    assert "Leader" in members.json()["result"]


def test_team_tasks_dependencies_and_sse_projection() -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]

    ui_agent = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "UI", "role": "teammate"},
    ).json()

    upstream = client.post(
        f"/api/teams/{team_id}/tasks",
        headers=AUTH_HEADERS,
        json={
            "subject": "规划协作协议",
            "description": "定义 Leader 和 Teammate 的消息边界",
            "owner_slot_id": "leader",
        },
    )
    assert upstream.status_code == 201
    upstream_task = upstream.json()

    dependent = client.post(
        f"/api/teams/{team_id}/tasks",
        headers=AUTH_HEADERS,
        json={
            "subject": "实现横向多列 UI",
            "description": "按 AionUi 布局复刻",
            "owner_slot_id": ui_agent["slot_id"],
            "blocked_by": [upstream_task["id"]],
        },
    )
    assert dependent.status_code == 201
    assert dependent.json()["blocked_by_json"] == [upstream_task["id"]]

    tasks = client.get(f"/api/teams/{team_id}/tasks", headers=AUTH_HEADERS).json()
    upstream_with_blocks = next(task for task in tasks if task["id"] == upstream_task["id"])
    assert dependent.json()["id"] in upstream_with_blocks["blocks_json"]

    completed = client.patch(
        f"/api/teams/{team_id}/tasks/{upstream_task['id']}",
        headers=AUTH_HEADERS,
        json={"status": "completed"},
    )
    assert completed.status_code == 200
    tasks_after = client.get(f"/api/teams/{team_id}/tasks", headers=AUTH_HEADERS).json()
    dependent_after = next(task for task in tasks_after if task["id"] == dependent.json()["id"])
    assert dependent_after["blocked_by_json"] == []

    stream = client.get(f"/api/teams/{team_id}/stream?once=true", headers=AUTH_HEADERS)
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "TEAM_CREATED" in stream.text
    assert "TEAM_TASK_UPDATED" in stream.text

    events = client.get(f"/api/teams/{team_id}/events?after_sequence=1", headers=AUTH_HEADERS)
    assert events.status_code == 200
    assert all(event["sequence"] > 1 for event in events.json())


def test_team_task_dependencies_accept_aionui_style_aliases_and_short_task_ids() -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]

    upstream = client.post(
        f"/api/teams/{team_id}/tasks",
        headers=AUTH_HEADERS,
        json={"subject": "先完成协议", "owner": "leader"},
    )
    assert upstream.status_code == 201, upstream.text
    upstream_task = upstream.json()

    dependent = client.post(
        f"/api/teams/{team_id}/tasks",
        headers=AUTH_HEADERS,
        json={
            "subject": "再实现 UI",
            "ownerSlotId": "leader",
            "blockedBy": [upstream_task["id"][:8]],
        },
    )
    assert dependent.status_code == 201, dependent.text
    dependent_task = dependent.json()
    assert dependent_task["owner_slot_id"] == "leader"
    assert dependent_task["blocked_by_json"] == [upstream_task["id"]]

    second_upstream = client.post(
        f"/api/teams/{team_id}/tools/team_task_create",
        headers=AUTH_HEADERS,
        json={
            "from_agent_slot_id": "leader",
            "args": {"subject": "补齐事件", "ownerSlotId": "leader"},
        },
    )
    assert second_upstream.status_code == 200, second_upstream.text
    tasks_after_second = client.get(f"/api/teams/{team_id}/tasks", headers=AUTH_HEADERS).json()
    second_upstream_task = next(
        task for task in tasks_after_second if task["subject"] == "补齐事件"
    )

    updated_dependency = client.post(
        f"/api/teams/{team_id}/tools/team_task_update",
        headers=AUTH_HEADERS,
        json={
            "from_agent_slot_id": "leader",
            "args": {
                "task_id": dependent_task["id"][:8],
                "blockedBy": [upstream_task["id"][:8], second_upstream_task["id"][:8]],
            },
        },
    )
    assert updated_dependency.status_code == 200, updated_dependency.text

    tasks_after_update = client.get(f"/api/teams/{team_id}/tasks", headers=AUTH_HEADERS).json()
    dependent_after_update = next(
        task for task in tasks_after_update if task["id"] == dependent_task["id"]
    )
    first_after_update = next(
        task for task in tasks_after_update if task["id"] == upstream_task["id"]
    )
    second_after_update = next(
        task for task in tasks_after_update if task["id"] == second_upstream_task["id"]
    )
    assert dependent_after_update["blocked_by_json"] == [
        upstream_task["id"],
        second_upstream_task["id"],
    ]
    assert dependent_task["id"] in first_after_update["blocks_json"]
    assert dependent_task["id"] in second_after_update["blocks_json"]

    completed_first = client.post(
        f"/api/teams/{team_id}/tools/team_task_update",
        headers=AUTH_HEADERS,
        json={
            "from_agent_slot_id": "leader",
            "args": {"task_id": upstream_task["id"][:8], "status": "completed"},
        },
    )
    assert completed_first.status_code == 200, completed_first.text
    still_blocked = client.get(f"/api/teams/{team_id}/tasks", headers=AUTH_HEADERS).json()
    dependent_still_blocked = next(
        task for task in still_blocked if task["id"] == dependent_task["id"]
    )
    assert dependent_still_blocked["blocked_by_json"] == [second_upstream_task["id"]]

    completed_second = client.patch(
        f"/api/teams/{team_id}/tasks/{second_upstream_task['id'][:8]}",
        headers=AUTH_HEADERS,
        json={"status": "completed"},
    )
    assert completed_second.status_code == 200, completed_second.text
    unblocked = client.get(f"/api/teams/{team_id}/tasks", headers=AUTH_HEADERS).json()
    dependent_unblocked = next(task for task in unblocked if task["id"] == dependent_task["id"])
    assert dependent_unblocked["blocked_by_json"] == []

    missing_dependency = client.post(
        f"/api/teams/{team_id}/tasks",
        headers=AUTH_HEADERS,
        json={"subject": "坏依赖", "blockedBy": ["missing-task"]},
    )
    assert missing_dependency.status_code == 404


def test_team_task_update_tool_accepts_id_alias_and_current_assigned_task() -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]
    writer = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "写作助手", "role": "teammate"},
    )
    assert writer.status_code == 201, writer.text
    writer_slot_id = writer.json()["slot_id"]
    reviewer = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "审阅助手", "role": "teammate"},
    )
    assert reviewer.status_code == 201, reviewer.text
    reviewer_slot_id = reviewer.json()["slot_id"]

    first = client.post(
        f"/api/teams/{team_id}/tools/team_task_create",
        headers=AUTH_HEADERS,
        json={
            "from_agent_slot_id": "leader",
            "args": {"subject": "创作短篇小说", "owner": writer_slot_id},
        },
    )
    assert first.status_code == 200, first.text
    tasks = client.get(f"/api/teams/{team_id}/tasks", headers=AUTH_HEADERS).json()
    first_task = next(task for task in tasks if task["subject"] == "创作短篇小说")

    completed_by_id_alias = client.post(
        f"/api/teams/{team_id}/tools/team_task_update",
        headers=AUTH_HEADERS,
        json={
            "from_agent_slot_id": writer_slot_id,
            "args": {"id": first_task["id"][:8], "status": "completed"},
        },
    )
    assert completed_by_id_alias.status_code == 200, completed_by_id_alias.text
    tasks_after_alias = client.get(f"/api/teams/{team_id}/tasks", headers=AUTH_HEADERS).json()
    first_after_alias = next(
        task for task in tasks_after_alias if task["id"] == first_task["id"]
    )
    assert first_after_alias["status"] == "completed"

    second = client.post(
        f"/api/teams/{team_id}/tools/team_task_create",
        headers=AUTH_HEADERS,
        json={
            "from_agent_slot_id": "leader",
            "args": {"subject": "润色短篇小说", "owner": writer_slot_id},
        },
    )
    assert second.status_code == 200, second.text
    completed_current = client.post(
        f"/api/teams/{team_id}/tools/team_task_update",
        headers=AUTH_HEADERS,
        json={
            "from_agent_slot_id": writer_slot_id,
            "args": {"status": "completed"},
        },
    )
    assert completed_current.status_code == 200, completed_current.text
    tasks_after_current = client.get(f"/api/teams/{team_id}/tasks", headers=AUTH_HEADERS).json()
    second_after_current = next(
        task for task in tasks_after_current if task["subject"] == "润色短篇小说"
    )
    assert second_after_current["status"] == "completed"

    owner_task_response = client.post(
        f"/api/teams/{team_id}/tools/team_task_create",
        headers=AUTH_HEADERS,
        json={
            "from_agent_slot_id": "leader",
            "args": {"subject": "审阅短篇小说", "owner": writer_slot_id},
        },
    )
    assert owner_task_response.status_code == 200, owner_task_response.text
    owner_task = next(
        task
        for task in client.get(f"/api/teams/{team_id}/tasks", headers=AUTH_HEADERS).json()
        if task["subject"] == "审阅短篇小说"
    )
    reassigned = client.post(
        f"/api/teams/{team_id}/tools/team_task_update",
        headers=AUTH_HEADERS,
        json={
            "from_agent_slot_id": "leader",
            "args": {"task_id": owner_task["id"][:8], "owner_slot_id": reviewer_slot_id},
        },
    )
    assert reassigned.status_code == 200, reassigned.text
    assert f"Owner: {reviewer_slot_id}" in reassigned.json()["result"]
    owner_task_after = next(
        task
        for task in client.get(f"/api/teams/{team_id}/tasks", headers=AUTH_HEADERS).json()
        if task["id"] == owner_task["id"]
    )
    assert owner_task_after["owner_slot_id"] == reviewer_slot_id

    for subject in ("任务 A", "任务 B"):
        created = client.post(
            f"/api/teams/{team_id}/tools/team_task_create",
            headers=AUTH_HEADERS,
            json={
                "from_agent_slot_id": "leader",
                "args": {"subject": subject, "owner": writer_slot_id},
            },
        )
        assert created.status_code == 200, created.text
    ambiguous = client.post(
        f"/api/teams/{team_id}/tools/team_task_update",
        headers=AUTH_HEADERS,
        json={
            "from_agent_slot_id": writer_slot_id,
            "args": {"status": "completed"},
        },
    )
    assert ambiguous.status_code == 422
    assert "multiple open assigned tasks" in ambiguous.text


class SequencedTeamRuntime:
    def __init__(self, contents: list[str]) -> None:
        self.contents = contents
        self.calls: list[list[ModelMessage]] = []

    def complete(
        self,
        *,
        organization_id: str,
        model_provider: str,
        model_name: str,
        messages: list[ModelMessage],
    ) -> ModelResponse:
        self.calls.append(messages)
        content = self.contents.pop(0)
        return ModelResponse(
            content=content,
            model_provider=model_provider,
            model_name=model_name,
            usage={"prompt_tokens": 10, "completion_tokens": max(1, len(content) // 4)},
            raw_response={"mode": "fake"},
        )

    def stream(
        self,
        *,
        organization_id: str,
        model_provider: str,
        model_name: str,
        messages: list[ModelMessage],
    ):
        response = self.complete(
            organization_id=organization_id,
            model_provider=model_provider,
            model_name=model_name,
            messages=messages,
        )
        midpoint = max(1, len(response.content) // 2)
        yield ModelStreamChunk(text=response.content[:midpoint])
        yield ModelStreamChunk(text=response.content[midpoint:])
        yield ModelStreamChunk(
            usage=response.usage,
            raw_response=response.raw_response,
            done=True,
        )


def test_team_wake_executes_model_declared_team_tools(db_session: Session) -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]
    teammate = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "产品", "role": "teammate"},
    ).json()

    runtime = SequencedTeamRuntime(
        [
            (
                "需要拆任务。\n"
                '<team_tool_call>{"tool":"team_task_create","args":{"subject":"整理需求","owner":"产品"}}</team_tool_call>\n'
                '<team_tool_call>{"tool":"team_send_message","args":{"to":"产品","message":"请整理需求并回报。"}}</team_tool_call>'
            ),
            "已创建任务并通知产品同学。",
            "我已收到整理需求任务。",
            "已收到成员完成通知。",
        ]
    )
    service = TeamSessionService(
        db_session,
        organization_id=team["organization_id"],
        actor_id="test",
        model_runtime=runtime,
    )
    service.write_message(team_id=team_id, target="leader", content="请安排产品整理需求")
    db_session.commit()

    after_wake = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    leader = next(agent for agent in after_wake["agents"] if agent["slot_id"] == "leader")
    product_after_wake = next(
        agent for agent in after_wake["agents"] if agent["slot_id"] == teammate["slot_id"]
    )
    assert any(
        message["content"] == "已创建任务并通知产品同学。"
        for message in leader["session_messages"]
    )
    assert leader["session_messages"][-1]["content"] == "已收到成员完成通知。"
    assert product_after_wake["session_messages"][-1]["content"] == "我已收到整理需求任务。"
    assert (
        next(
            message
            for message in leader["session_messages"]
            if message["content"] == "已创建任务并通知产品同学。"
        )["metadata_json"]["tool_results"][0]["tool"]
        == "team_task_create"
    )
    assert len(runtime.calls) == 4
    assert any("Team tool results" in call[-1].content for call in runtime.calls)

    tasks = client.get(f"/api/teams/{team_id}/tasks", headers=AUTH_HEADERS).json()
    assert any(
        task["subject"] == "整理需求" and task["owner_slot_id"] == teammate["slot_id"]
        for task in tasks
    )
    messages = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()["messages"]
    assert any(
        message["to_agent_slot_id"] == teammate["slot_id"]
        and message["from_agent_slot_id"] == "leader"
        and message["content"] == "请整理需求并回报。"
        for message in messages
    )
    events = client.get(f"/api/teams/{team_id}/events", headers=AUTH_HEADERS).json()
    assert any(event["event_type"] == "TEAM_TOOL_CALLED" for event in events)


def test_team_wake_auto_runs_task_owner_after_tool_task_create_without_message(
    db_session: Session,
) -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]
    product = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "产品", "role": "teammate"},
    ).json()

    runtime = SequencedTeamRuntime(
        [
            '<team_tool_call>{"tool":"team_task_create","args":{"subject":"整理需求","owner":"产品","description":"输出三条需求"}}</team_tool_call>',
            "已创建任务。",
            "我已看到整理需求任务并开始执行。",
        ]
    )
    service = TeamSessionService(
        db_session,
        organization_id=team["organization_id"],
        actor_id="test",
        model_runtime=runtime,
    )
    service.write_message(team_id=team_id, target="leader", content="请安排产品整理需求")
    db_session.commit()

    db_session.expire_all()
    after_wake = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    assigned_task = next(task for task in after_wake["tasks"] if task["subject"] == "整理需求")
    product_after_wake = next(
        agent for agent in after_wake["agents"] if agent["slot_id"] == product["slot_id"]
    )

    assert assigned_task["owner_slot_id"] == product["slot_id"]
    assert assigned_task["status"] == "in_progress"
    assert product_after_wake["metadata_json"]["wake"]["in_progress"] is False
    assert "## Your Assigned Tasks" in product_after_wake["metadata_json"]["wake"]["last_prompt"]
    assert (
        product_after_wake["session_messages"][-1]["content"]
        == "我已看到整理需求任务并开始执行。"
    )
    assert len(runtime.calls) == 3


def test_team_leader_can_spawn_and_assign_teammates_in_one_turn(db_session: Session) -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]

    runtime = SequencedTeamRuntime(
        [
            (
                "我会直接创建需要的执行成员。\n"
                '<team_tool_call>{"tool":"team_spawn_agent","args":{"name":"前端工程师","agent_id":"default"}}</team_tool_call>\n'
                '<team_tool_call>{"tool":"team_task_create","args":{"subject":"优化团队聊天布局","owner":"前端工程师"}}</team_tool_call>\n'
                '<team_tool_call>{"tool":"team_send_message","args":{"to":"前端工程师","message":"请优化团队模式聊天布局并回报。"}}'
                "</team_tool_call>"
            ),
            "已创建前端工程师并派发任务。",
            "我已收到布局优化任务。",
            "团队成员已就位。",
        ]
    )
    service = TeamSessionService(
        db_session,
        organization_id=team["organization_id"],
        actor_id="test",
        model_runtime=runtime,
    )
    service.write_message(team_id=team_id, target="leader", content="优化团队模式聊天体验")
    db_session.commit()

    after_wake = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    spawned = next(
        agent for agent in after_wake["agents"] if agent["agent_name"] == "前端工程师"
    )
    assert spawned["status"] == "idle"
    assert any(
        task["subject"] == "优化团队聊天布局" and task["owner_slot_id"] == spawned["slot_id"]
        for task in after_wake["tasks"]
    )
    assert any(
        message["to_agent_slot_id"] == spawned["slot_id"]
        and message["content"] == "请优化团队模式聊天布局并回报。"
        for message in after_wake["messages"]
    )
    assert len(runtime.calls) == 4


def test_team_wake_stream_finishes_idle_and_returns_final_message(db_session: Session) -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]
    product = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "产品", "role": "teammate"},
    ).json()

    runtime = SequencedTeamRuntime(["我已完成本轮处理。"])
    service = TeamSessionService(
        db_session,
        organization_id=team["organization_id"],
        actor_id="test",
        model_runtime=runtime,
    )
    service.write_message(
        team_id=team_id,
        target=product["slot_id"],
        content="请处理这个任务",
        wake_recipient=False,
    )
    events = list(service.wake_agent_stream(team_id=team_id, slot_id=product["slot_id"]))
    db_session.commit()

    assert [event["type"] for event in events] == ["status", "delta", "delta", "done"]
    streamed_content = "".join(
        event["content"] for event in events if event["type"] == "delta"
    )
    assert streamed_content == "我已完成本轮处理。"
    done = events[-1]
    assert done["agent"]["status"] == "idle"
    assert done["message"]["content"] == "我已完成本轮处理。"
    assert done["follow_up_slot_ids"] == ["leader"]

    db_session.expire_all()
    after_wake = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    product_after_wake = next(
        agent for agent in after_wake["agents"] if agent["slot_id"] == product["slot_id"]
    )
    leader_after_wake = next(
        agent for agent in after_wake["agents"] if agent["slot_id"] == "leader"
    )
    assert product_after_wake["status"] == "idle"
    assert product_after_wake["metadata_json"]["wake"]["in_progress"] is False
    assert product_after_wake["session_messages"][-1]["content"] == "我已完成本轮处理。"
    assert leader_after_wake["metadata_json"]["wake"].get("last_prompt_kind") is None


def test_team_wake_stream_generator_close_settles_idle(db_session: Session) -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]
    product = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "产品", "role": "teammate"},
    ).json()

    service = TeamSessionService(
        db_session,
        organization_id=team["organization_id"],
        actor_id="test",
        model_runtime=SequencedTeamRuntime(["一段较长的流式回复。"]),
    )
    service.write_message(
        team_id=team_id,
        target=product["slot_id"],
        content="请处理这个任务",
        wake_recipient=False,
    )
    events = service.wake_agent_stream(team_id=team_id, slot_id=product["slot_id"])
    first = next(events)
    assert first["type"] == "status"
    events.close()
    db_session.commit()

    db_session.expire_all()
    after_wake = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    product_after_wake = next(
        agent for agent in after_wake["agents"] if agent["slot_id"] == product["slot_id"]
    )
    assert product_after_wake["status"] == "idle"
    assert product_after_wake["metadata_json"]["wake"]["in_progress"] is False
    assert product_after_wake["metadata_json"]["wake"]["interrupt_reason"] == "client_disconnected"


def test_team_wake_cancel_settles_idle(db_session: Session) -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]
    product = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "产品", "role": "teammate"},
    ).json()

    service = TeamSessionService(
        db_session,
        organization_id=team["organization_id"],
        actor_id="test",
        model_runtime=SequencedTeamRuntime(["一段较长的流式回复。"]),
    )
    service.write_message(
        team_id=team_id,
        target=product["slot_id"],
        content="请处理这个任务",
        wake_recipient=False,
    )
    events = service.wake_agent_stream(team_id=team_id, slot_id=product["slot_id"])
    assert next(events)["type"] == "status"

    cancelled = client.post(
        f"/api/teams/{team_id}/agents/{product['slot_id']}/wake/cancel",
        headers=AUTH_HEADERS,
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "idle"
    assert cancelled.json()["metadata_json"]["wake"]["in_progress"] is False
    assert cancelled.json()["metadata_json"]["wake"]["interrupt_reason"] == "user_cancelled"
    events.close()


def test_team_wake_stream_defers_tool_message_wakes(db_session: Session) -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]
    product = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "产品", "role": "teammate"},
    ).json()

    runtime = SequencedTeamRuntime(
        [
            '<team_tool_call>{"tool":"team_send_message","args":{"to":"产品","message":"请整理需求并回报。"}}</team_tool_call>',
            "已通知产品同学。",
        ]
    )
    service = TeamSessionService(
        db_session,
        organization_id=team["organization_id"],
        actor_id="test",
        model_runtime=runtime,
    )
    service.write_message(
        team_id=team_id,
        target="leader",
        content="请安排产品整理需求",
        wake_recipient=False,
    )
    events = list(service.wake_agent_stream(team_id=team_id, slot_id="leader"))
    db_session.commit()

    done = events[-1]
    assert done["type"] == "done"
    assert done["agent"]["status"] == "idle"
    assert done["message"]["content"] == "已通知产品同学。"
    assert done["follow_up_slot_ids"] == [product["slot_id"]]
    assert len(runtime.calls) == 2

    db_session.expire_all()
    after_wake = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    product_after_wake = next(
        agent for agent in after_wake["agents"] if agent["slot_id"] == product["slot_id"]
    )
    leader_after_wake = next(
        agent for agent in after_wake["agents"] if agent["slot_id"] == "leader"
    )
    assert leader_after_wake["status"] == "idle"
    assert product_after_wake["status"] == "idle"
    assert any(
        message["to_agent_slot_id"] == product["slot_id"]
        and message["read"] is False
        and message["content"] == "请整理需求并回报。"
        for message in after_wake["messages"]
    )


def test_team_wake_stream_defers_task_owner_wake(db_session: Session) -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]
    product = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "产品", "role": "teammate"},
    ).json()

    runtime = SequencedTeamRuntime(
        [
            '<team_tool_call>{"tool":"team_task_create","args":{"subject":"整理需求","owner":"产品","description":"输出三条需求"}}</team_tool_call>',
            "任务已创建。",
            "我已看到整理需求任务。",
        ]
    )
    service = TeamSessionService(
        db_session,
        organization_id=team["organization_id"],
        actor_id="test",
        model_runtime=runtime,
    )
    service.write_message(
        team_id=team_id,
        target="leader",
        content="请安排产品整理需求",
        wake_recipient=False,
    )
    events = list(service.wake_agent_stream(team_id=team_id, slot_id="leader"))
    db_session.commit()

    done = events[-1]
    assert done["type"] == "done"
    assert done["follow_up_slot_ids"] == [product["slot_id"]]
    product_events = list(service.wake_agent_stream(team_id=team_id, slot_id=product["slot_id"]))
    db_session.commit()
    product_done = product_events[-1]
    assert product_done["type"] == "done"

    db_session.expire_all()
    after_wake = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    product_after_wake = next(
        agent for agent in after_wake["agents"] if agent["slot_id"] == product["slot_id"]
    )
    assigned_task = next(task for task in after_wake["tasks"] if task["subject"] == "整理需求")
    assert assigned_task["owner_slot_id"] == product["slot_id"]
    assert assigned_task["status"] == "in_progress"
    assert product_after_wake["metadata_json"]["wake"]["in_progress"] is False
    assert "## Your Assigned Tasks" in product_after_wake["metadata_json"]["wake"]["last_prompt"]
    assert "整理需求" in product_after_wake["metadata_json"]["wake"]["last_prompt"]


def test_team_wake_runs_assigned_task_without_new_message(db_session: Session) -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]
    product = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "产品", "role": "teammate"},
    ).json()

    runtime = SequencedTeamRuntime(["我已看到任务并开始执行。"])
    service = TeamSessionService(
        db_session,
        organization_id=team["organization_id"],
        actor_id="test",
        model_runtime=runtime,
    )
    product_agent = service.get_agent(team_id, product["slot_id"])
    product_agent.status = "idle"
    product_agent.metadata_json = {
        **product_agent.metadata_json,
        "wake": {"has_prompted": True, "in_progress": False},
    }
    service.create_task(
        team_id=team_id,
        subject="整理需求",
        description="输出三条需求",
        owner_slot_id=product["slot_id"],
    )
    db_session.commit()

    recovered = service.wake_agent(team_id=team_id, slot_id=product["slot_id"])
    db_session.commit()

    assert recovered.status == "idle"
    assert recovered.metadata_json["wake"]["last_prompt_kind"] == "full"
    assert "## Your Assigned Tasks" in recovered.metadata_json["wake"]["last_prompt"]
    assert "整理需求" in recovered.metadata_json["wake"]["last_prompt"]

    db_session.expire_all()
    after_wake = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    assigned_task = next(task for task in after_wake["tasks"] if task["subject"] == "整理需求")
    product_after_wake = next(
        agent for agent in after_wake["agents"] if agent["slot_id"] == product["slot_id"]
    )
    assert assigned_task["status"] == "in_progress"
    assert product_after_wake["session_messages"][-1]["content"] == "我已看到任务并开始执行。"


def test_team_wake_recovers_stale_in_progress_when_unread_arrives(
    db_session: Session,
) -> None:
    client = TestClient(app)
    team = _create_team(client)
    team_id = team["id"]
    product = client.post(
        f"/api/teams/{team_id}/agents",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "agent_name": "产品", "role": "teammate"},
    ).json()

    service = TeamSessionService(
        db_session,
        organization_id=team["organization_id"],
        actor_id="test",
        model_runtime=SequencedTeamRuntime(["收到新任务，开始处理。", "已收到成员完成通知。"]),
    )
    product_agent = service.get_agent(team_id, product["slot_id"])
    product_agent.status = "active"
    product_agent.metadata_json = {
        **product_agent.metadata_json,
        "wake": {
            "in_progress": True,
            "started_at": "2026-05-23T00:00:00+00:00",
            "has_prompted": True,
        },
    }
    service.write_message(
        team_id=team_id,
        target=product["slot_id"],
        content="请继续执行未处理任务",
        wake_recipient=False,
    )
    db_session.commit()

    recovered = service.wake_agent(team_id=team_id, slot_id=product["slot_id"])
    db_session.commit()

    assert recovered.status == "idle"
    assert recovered.metadata_json["wake"]["in_progress"] is False
    assert recovered.metadata_json["wake"]["last_prompt_kind"] == "messages_only"

    db_session.expire_all()
    after_wake = client.get(f"/api/teams/{team_id}", headers=AUTH_HEADERS).json()
    product_after_wake = next(
        agent for agent in after_wake["agents"] if agent["slot_id"] == product["slot_id"]
    )
    assert product_after_wake["session_messages"][-1]["content"] == "收到新任务，开始处理。"
    assert after_wake["unread_counts"].get(product["slot_id"], 0) == 0
