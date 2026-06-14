"""
Agent Instantiation API Endpoints - Story 5.2: Template Instantiation

Provides endpoints for creating agents from templates with parameter substitution.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.services.agent_template_service import AgentTemplateService

router = APIRouter(prefix="/onboarding/agents", tags=["onboarding"])
DbSession = Annotated[Session, Depends(get_db_session)]


class AgentInstantiationRequest(BaseModel):
    """Request schema for creating agent from template."""

    template_id: str = Field(description="Template identifier")
    name: str = Field(min_length=1, max_length=255, description="Agent name")
    parameters: dict[str, str] = Field(
        default_factory=dict,
        description="Parameters for template substitution (e.g., {'user_name': 'John', 'expertise_area': 'Python'})",
    )


class AgentInstantiationResponse(BaseModel):
    """Response schema for created agent."""

    id: str = Field(description="Agent identifier")
    organization_id: str = Field(description="Organization that owns the agent")
    name: str = Field(description="Agent name")
    description: str = Field(description="Agent description")
    role: str = Field(description="Agent role")
    status: str = Field(description="Agent status (e.g., ACTIVE)")
    model_provider: str = Field(description="Model provider")
    model_name: str = Field(description="Model name")
    system_prompt: str = Field(description="System prompt with substituted parameters")
    tools_json: list[str] = Field(description="Available tools")
    template_id: str = Field(description="Source template ID")


@router.post(
    "/from-template",
    response_model=AgentInstantiationResponse,
    summary="Create agent from template (Story 5.2)",
    status_code=201,
)
def create_agent_from_template(
    request: AgentInstantiationRequest,
    session: DbSession,
) -> dict:
    """
    Create an agent instance from a template with parameter substitution.

    Story 5.2: Wizard Step 6 - Template Instantiation

    This endpoint:
    1. Fetches the specified template (must be active)
    2. Validates that all required parameters are provided
    3. Substitutes parameters in the system_prompt (e.g., {{user_name}} → "John")
    4. Creates and stores the agent with the applied configuration
    5. Returns the complete agent configuration

    **Request Example:**
    ```json
    {
      "template_id": "code-assistant-template",
      "name": "My Code Assistant",
      "parameters": {
        "user_name": "John",
        "expertise_area": "Python"
      }
    }
    ```

    **Response Example:**
    ```json
    {
      "id": "agent-abc123",
      "organization_id": "org-456",
      "name": "My Code Assistant",
      "description": "Agent created from template: Code Assistant",
      "role": "assistant",
      "status": "ACTIVE",
      "model_provider": "default",
      "model_name": "claude-sonnet-4",
      "system_prompt": "You are a coding assistant for John. Your expertise is in Python.",
      "tools_json": ["code_execution", "web_search"],
      "template_id": "code-assistant-template"
    }
    ```

    **Error Cases:**
    - 404: Template not found or inactive
    - 400: Missing required parameters
    - 400: Invalid parameter values
    """
    service = AgentTemplateService(session)

    # For now, use a default organization ID
    # In production, this would come from authenticated user context
    organization_id = "default-org"

    try:
        agent = service.instantiate_from_template(
            template_id=request.template_id,
            name=request.name,
            parameters=request.parameters,
            organization_id=organization_id,
        )
        return agent
    except ValueError as e:
        error_message = str(e)
        if "Template not found" in error_message:
            raise HTTPException(status_code=404, detail=error_message)
        elif "Missing required parameter" in error_message:
            raise HTTPException(status_code=400, detail=error_message)
        else:
            raise HTTPException(status_code=400, detail=error_message)
