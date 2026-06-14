"""
Agent Service - Story 5.2: Agent CRUD Operations

Handles agent creation, retrieval, update, and deletion operations.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.db.models import Agent

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class AgentService:
    """
    Service for managing agents.

    This service handles:
    - Agent retrieval by ID
    - Agent listing by organization
    - Agent updates
    - Agent deletion
    """

    def __init__(self, session: Session) -> None:
        """Initialize agent service with database session."""
        self.session = session

    def get_agent_by_id(self, agent_id: str, organization_id: str | None = None) -> dict | None:
        """
        Get a specific agent by ID.

        Args:
            agent_id: Agent identifier
            organization_id: Optional organization filter

        Returns:
            Agent dictionary or None if not found
        """
        query = select(Agent).where(Agent.id == agent_id)

        if organization_id is not None:
            query = query.where(Agent.organization_id == organization_id)

        agent = self.session.execute(query).scalar_one_or_none()

        if agent is None:
            return None

        return self._agent_to_dict(agent)

    def get_agents_by_organization(self, organization_id: str) -> list[dict]:
        """
        Get all agents for an organization.

        Args:
            organization_id: Organization identifier

        Returns:
            List of agent dictionaries
        """
        agents = self.session.execute(
            select(Agent)
            .where(Agent.organization_id == organization_id)
            .order_by(Agent.created_at.desc())
        ).scalars().all()

        return [self._agent_to_dict(agent) for agent in agents]

    def _agent_to_dict(self, agent: Agent) -> dict:
        """Convert Agent model to dictionary."""
        return {
            "id": agent.id,
            "organization_id": agent.organization_id,
            "name": agent.name,
            "description": agent.description,
            "role": agent.role,
            "status": agent.status,
            "model_provider": agent.model_provider,
            "model_name": agent.model_name,
            "system_prompt": agent.system_prompt,
            "tools_json": agent.tools_json,
            "routing_tags": agent.routing_tags,
            "max_parallel_assignments": agent.max_parallel_assignments,
            "created_at": agent.created_at.isoformat(),
            "updated_at": agent.updated_at.isoformat(),
        }
