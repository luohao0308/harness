"""
Agent Template API Endpoints - Story 5.1: Agent Template Repository

Provides endpoints for fetching agent templates used in onboarding wizard Step 6.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.services.agent_template_service import AgentTemplateService

router = APIRouter(prefix="/onboarding/templates", tags=["onboarding"])
DbSession = Annotated[Session, Depends(get_db_session)]


class AgentTemplateConfigResponse(BaseModel):
    """Template configuration schema."""

    system_prompt: str = Field(description="System prompt for the agent")
    suggested_tools: list[str] = Field(default_factory=list, description="Recommended tools")
    default_model: str = Field(description="Default model to use")
    parameters: dict = Field(default_factory=dict, description="Additional parameters")


class AgentTemplateResponse(BaseModel):
    """Agent template response schema."""

    id: str = Field(description="Template identifier")
    name: str = Field(description="Template name")
    description: str = Field(description="Template description")
    icon: str = Field(description="Template icon (emoji or icon name)")
    tags: list[str] = Field(description="Template tags for categorization")
    config: dict = Field(description="Template configuration (system_prompt, tools, model, etc.)")


@router.get(
    "",
    response_model=list[AgentTemplateResponse],
    summary="Get all agent templates (Story 5.1)",
)
def get_agent_templates(session: DbSession) -> list[dict]:
    """
    Get all active agent templates for wizard Step 6.

    Story 5.1: Returns pre-configured templates including:
    - Code Assistant
    - Research Assistant
    - Data Analyst
    - DevOps Helper
    - General Assistant

    Each template includes:
    - id: Unique template identifier
    - name: Display name
    - description: What the template does
    - icon: Emoji or icon identifier
    - tags: Categories for filtering
    - config: JSON with system_prompt, suggested_tools, default_model, parameters
    """
    service = AgentTemplateService(session)
    return service.get_all_templates()
