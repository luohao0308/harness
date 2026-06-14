"""
Agent Template Service - Story 5.1: Agent Template Repository

Handles fetching agent templates for the onboarding wizard Step 6.
Templates provide pre-configured agent setups with system prompts, tools, and settings.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from sqlalchemy import select

from app.db.models import AgentTemplate

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class AgentTemplateDict(TypedDict):
    """Agent template response structure."""

    id: str
    name: str
    description: str
    icon: str
    tags: list[str]
    config: dict


class AgentTemplateService:
    """
    Service for managing agent templates.

    This service handles:
    - Story 5.1: Fetching active agent templates
    - Story 5.1: Template retrieval by ID
    - Story 5.1: Template filtering (active only)

    Templates include:
    - Code Assistant: For development and coding tasks
    - Research Assistant: For information gathering and research
    - Data Analyst: For data analysis and insights
    - DevOps Helper: For infrastructure and deployment tasks
    - General Assistant: For general-purpose assistance
    """

    def __init__(self, session: Session) -> None:
        """Initialize agent template service with database session."""
        self.session = session

    def get_all_templates(self) -> list[AgentTemplateDict]:
        """
        Get all active agent templates.

        Returns only templates where is_active=True.

        Returns:
            List of template dictionaries with all fields including config
        """
        templates = self.session.execute(
            select(AgentTemplate).where(AgentTemplate.is_active == True).order_by(AgentTemplate.name)
        ).scalars().all()

        return [self._template_to_dict(template) for template in templates]

    def get_template_by_id(self, template_id: str) -> AgentTemplateDict | None:
        """
        Get a specific agent template by ID.

        Only returns the template if it is active.

        Args:
            template_id: Template identifier

        Returns:
            Template dictionary or None if not found or inactive
        """
        template = self.session.execute(
            select(AgentTemplate).where(
                AgentTemplate.id == template_id,
                AgentTemplate.is_active == True,
            )
        ).scalar_one_or_none()

        if template is None:
            return None

        return self._template_to_dict(template)

    def _template_to_dict(self, template: AgentTemplate) -> AgentTemplateDict:
        """Convert AgentTemplate model to dictionary."""
        return {
            "id": template.id,
            "name": template.name,
            "description": template.description,
            "icon": template.icon,
            "tags": template.tags,
            "config": template.config,
        }
