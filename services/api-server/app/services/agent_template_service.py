"""
Agent Template Service - Story 5.1 & 5.2: Agent Template Repository & Instantiation

Handles fetching agent templates for the onboarding wizard Step 6.
Templates provide pre-configured agent setups with system prompts, tools, and settings.

Story 5.2: Adds template instantiation with parameter substitution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict
from uuid import uuid4

from sqlalchemy import select

from app.db.models import Agent, AgentTemplate

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


class AgentDict(TypedDict):
    """Agent instance response structure."""

    id: str
    organization_id: str
    name: str
    description: str
    role: str
    status: str
    model_provider: str
    model_name: str
    system_prompt: str
    tools_json: list[str]
    template_id: str


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
        templates = (
            self.session.execute(
                select(AgentTemplate).where(AgentTemplate.is_active).order_by(AgentTemplate.name)
            )
            .scalars()
            .all()
        )

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
                AgentTemplate.is_active,
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

    def instantiate_from_template(
        self,
        template_id: str,
        name: str,
        parameters: dict,
        organization_id: str,
    ) -> AgentDict:
        """
        Create an agent instance from a template with parameter substitution.

        Story 5.2: Instantiates an agent from a template by:
        1. Fetching the template (must be active)
        2. Validating required parameters
        3. Applying template configuration
        4. Substituting parameters in system_prompt
        5. Creating and storing the agent

        Args:
            template_id: Template identifier
            name: Name for the new agent
            parameters: Parameters for substitution (e.g., {"user_name": "John"})
            organization_id: Organization that owns the agent

        Returns:
            Created agent dictionary with all fields

        Raises:
            ValueError: If template not found, inactive, or parameters invalid
        """
        # Fetch template (only active templates)
        template = self.get_template_by_id(template_id)
        if template is None:
            raise ValueError(f"Template not found: {template_id}")

        # Convert dict back to model for validation
        template_model = self.session.execute(
            select(AgentTemplate).where(
                AgentTemplate.id == template_id,
                AgentTemplate.is_active,
            )
        ).scalar_one_or_none()

        if template_model is None:
            raise ValueError(f"Template not found: {template_id}")

        # Validate parameters
        self.validate_parameters(template_model, parameters)

        # Apply template configuration with parameter substitution
        config = self.apply_template_config(template_model, parameters)

        # Create agent instance
        agent_id = f"agent-{uuid4().hex[:16]}"
        agent = Agent(
            id=agent_id,
            organization_id=organization_id,
            name=name,
            description=f"Agent created from template: {template['name']}",
            role="assistant",
            status="ACTIVE",
            model_provider="default",
            model_name=config.get("default_model", "claude-sonnet-4"),
            system_prompt=config["system_prompt"],
            tools_json=config.get("suggested_tools", []),
            routing_tags=[],
            max_parallel_assignments=1,
        )

        # Save to database
        self.session.add(agent)
        self.session.commit()
        self.session.refresh(agent)

        # Return agent as dictionary
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
            "template_id": template_id,
        }

    def validate_parameters(self, template: AgentTemplate, parameters: dict) -> None:
        """
        Validate that all required parameters are provided.

        Args:
            template: AgentTemplate model
            parameters: Parameters provided for instantiation

        Raises:
            ValueError: If required parameters are missing
        """
        config = template.config
        required_params = config.get("required_params", [])

        missing_params = [param for param in required_params if param not in parameters]

        if missing_params:
            raise ValueError(f"Missing required parameter(s): {', '.join(missing_params)}")

    def apply_template_config(
        self,
        template: AgentTemplate,
        parameters: dict,
    ) -> dict:
        """
        Apply template configuration with parameter substitution.

        Substitutes {{parameter_name}} placeholders in system_prompt with actual values.

        Args:
            template: AgentTemplate model
            parameters: Parameters for substitution

        Returns:
            Configuration dict with substituted values
        """
        config = template.config.copy()

        # Substitute parameters in system_prompt
        system_prompt = config.get("system_prompt", "")

        # Replace all {{parameter_name}} with actual values
        for param_name, param_value in parameters.items():
            placeholder = f"{{{{{param_name}}}}}"
            system_prompt = system_prompt.replace(placeholder, str(param_value))

        config["system_prompt"] = system_prompt

        return config
