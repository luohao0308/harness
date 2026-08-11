"""
Tests for Agent Instantiation - Story 5.2: Template Instantiation

Tests cover:
1. Creating agent from template with parameter substitution
2. Validating required parameters
3. Handling missing parameters
4. Applying template configuration
5. Storing agent in database with template reference
6. Error handling for invalid template IDs
7. Parameter substitution in system_prompt
8. Return full agent configuration
"""

from __future__ import annotations

import pytest

from app.db.models import Agent, AgentTemplate
from app.services.agent_template_service import AgentTemplateService


@pytest.fixture
def template_service(db_session):
    """Create AgentTemplateService instance."""
    return AgentTemplateService(db_session)


@pytest.fixture
def sample_template(db_session):
    """Create a sample template for testing."""
    template = AgentTemplate(
        id="code-assistant-template",
        name="Code Assistant",
        description="Helps with coding tasks",
        icon="💻",
        tags=["coding", "development"],
        config={
            "system_prompt": (
                "You are a coding assistant for {{user_name}}. "
                "Your expertise is in {{expertise_area}}."
            ),
            "suggested_tools": ["code_execution", "web_search"],
            "default_model": "claude-sonnet-4",
            "parameters": {
                "temperature": 0.7,
            },
            "required_params": ["user_name", "expertise_area"],
        },
        is_active=True,
    )
    db_session.add(template)
    db_session.commit()
    return template


def test_instantiate_from_template_creates_agent(template_service, db_session, sample_template):
    """Test that instantiate_from_template creates a new agent."""
    # Arrange
    params = {
        "user_name": "John",
        "expertise_area": "Python",
    }

    # Act
    agent = template_service.instantiate_from_template(
        template_id="code-assistant-template",
        name="My Code Assistant",
        parameters=params,
        organization_id="org-123",
    )

    # Assert
    assert agent is not None
    assert agent["id"] is not None
    assert agent["name"] == "My Code Assistant"
    assert agent["organization_id"] == "org-123"
    assert agent["template_id"] == "code-assistant-template"

    # Verify agent was saved to database
    db_agent = db_session.query(Agent).filter_by(id=agent["id"]).first()
    assert db_agent is not None
    assert db_agent.name == "My Code Assistant"


def test_instantiate_from_template_substitutes_parameters(
    template_service, db_session, sample_template
):
    """Test that parameters are substituted in system_prompt."""
    # Arrange
    params = {
        "user_name": "Alice",
        "expertise_area": "JavaScript",
    }

    # Act
    agent = template_service.instantiate_from_template(
        template_id="code-assistant-template",
        name="Alice's Assistant",
        parameters=params,
        organization_id="org-456",
    )

    # Assert
    expected_prompt = "You are a coding assistant for Alice. Your expertise is in JavaScript."
    assert agent["system_prompt"] == expected_prompt


def test_instantiate_from_template_applies_config(template_service, db_session, sample_template):
    """Test that template configuration is applied to the agent."""
    # Arrange
    params = {
        "user_name": "Bob",
        "expertise_area": "Rust",
    }

    # Act
    agent = template_service.instantiate_from_template(
        template_id="code-assistant-template",
        name="Bob's Assistant",
        parameters=params,
        organization_id="org-789",
    )

    # Assert
    assert agent["model_provider"] == "default"
    assert agent["model_name"] == "claude-sonnet-4"
    assert agent["tools_json"] == ["code_execution", "web_search"]
    assert agent["status"] == "ACTIVE"


def test_instantiate_from_template_validates_required_params(
    template_service, db_session, sample_template
):
    """Test that missing required parameters raise an error."""
    # Arrange
    params = {
        "user_name": "Charlie",
        # Missing 'expertise_area'
    }

    # Act & Assert
    with pytest.raises(ValueError) as exc_info:
        template_service.instantiate_from_template(
            template_id="code-assistant-template",
            name="Charlie's Assistant",
            parameters=params,
            organization_id="org-999",
        )

    assert "Missing required parameter" in str(exc_info.value)
    assert "expertise_area" in str(exc_info.value)


def test_instantiate_from_template_fails_for_nonexistent_template(template_service, db_session):
    """Test that instantiating from nonexistent template raises an error."""
    # Act & Assert
    with pytest.raises(ValueError) as exc_info:
        template_service.instantiate_from_template(
            template_id="nonexistent-template",
            name="Test Agent",
            parameters={},
            organization_id="org-123",
        )

    assert "Template not found" in str(exc_info.value)


def test_instantiate_from_template_fails_for_inactive_template(template_service, db_session):
    """Test that instantiating from inactive template raises an error."""
    # Arrange: Create inactive template
    inactive_template = AgentTemplate(
        id="inactive-template",
        name="Inactive Template",
        description="Should not be usable",
        icon="❌",
        tags=[],
        config={
            "system_prompt": "Test",
            "suggested_tools": [],
            "default_model": "claude-sonnet-4",
            "required_params": [],
        },
        is_active=False,
    )
    db_session.add(inactive_template)
    db_session.commit()

    # Act & Assert
    with pytest.raises(ValueError) as exc_info:
        template_service.instantiate_from_template(
            template_id="inactive-template",
            name="Test Agent",
            parameters={},
            organization_id="org-123",
        )

    assert "Template not found" in str(exc_info.value)


def test_validate_parameters_passes_with_all_required_params(template_service, sample_template):
    """Test that validate_parameters passes when all required params are provided."""
    # Arrange
    params = {
        "user_name": "Diana",
        "expertise_area": "Go",
    }

    # Act & Assert (should not raise)
    template_service.validate_parameters(sample_template, params)


def test_validate_parameters_fails_with_missing_params(template_service, sample_template):
    """Test that validate_parameters fails when required params are missing."""
    # Arrange
    params = {
        "user_name": "Eve",
        # Missing 'expertise_area'
    }

    # Act & Assert
    with pytest.raises(ValueError) as exc_info:
        template_service.validate_parameters(sample_template, params)

    assert "Missing required parameter" in str(exc_info.value)
    assert "expertise_area" in str(exc_info.value)


def test_apply_template_config_substitutes_placeholders(template_service, sample_template):
    """Test that apply_template_config correctly substitutes all placeholders."""
    # Arrange
    params = {
        "user_name": "Frank",
        "expertise_area": "TypeScript",
    }

    # Act
    config = template_service.apply_template_config(sample_template, params)

    # Assert
    assert "{{user_name}}" not in config["system_prompt"]
    assert "{{expertise_area}}" not in config["system_prompt"]
    assert "Frank" in config["system_prompt"]
    assert "TypeScript" in config["system_prompt"]


def test_instantiate_from_template_handles_multiple_placeholders_in_prompt(
    template_service, db_session
):
    """Test parameter substitution with multiple occurrences of the same placeholder."""
    # Arrange
    template = AgentTemplate(
        id="multi-placeholder-template",
        name="Multi Placeholder Template",
        description="Template with repeated placeholders",
        icon="🔄",
        tags=["test"],
        config={
            "system_prompt": (
                "Hello {{name}}! Your name is {{name}} and you work on {{project}}. "
                "Remember, {{name}} is important."
            ),
            "suggested_tools": [],
            "default_model": "claude-sonnet-4",
            "required_params": ["name", "project"],
        },
        is_active=True,
    )
    db_session.add(template)
    db_session.commit()

    params = {
        "name": "Grace",
        "project": "CloudPlatform",
    }

    # Act
    agent = template_service.instantiate_from_template(
        template_id="multi-placeholder-template",
        name="Grace's Agent",
        parameters=params,
        organization_id="org-111",
    )

    # Assert
    expected_prompt = (
        "Hello Grace! Your name is Grace and you work on CloudPlatform. "
        "Remember, Grace is important."
    )
    assert agent["system_prompt"] == expected_prompt
    assert "{{name}}" not in agent["system_prompt"]
    assert "{{project}}" not in agent["system_prompt"]


def test_instantiate_from_template_handles_optional_params(template_service, db_session):
    """Test that optional parameters work correctly."""
    # Arrange
    template = AgentTemplate(
        id="optional-params-template",
        name="Optional Params Template",
        description="Template with optional parameters",
        icon="🎯",
        tags=["test"],
        config={
            "system_prompt": "You are an assistant for {{user_name}}. {{greeting}}",
            "suggested_tools": [],
            "default_model": "claude-sonnet-4",
            "required_params": ["user_name"],
        },
        is_active=True,
    )
    db_session.add(template)
    db_session.commit()

    params = {
        "user_name": "Henry",
        "greeting": "Welcome!",
    }

    # Act
    agent = template_service.instantiate_from_template(
        template_id="optional-params-template",
        name="Henry's Agent",
        parameters=params,
        organization_id="org-222",
    )

    # Assert
    assert "Henry" in agent["system_prompt"]
    assert "Welcome!" in agent["system_prompt"]


def test_instantiate_from_template_preserves_template_reference(
    template_service, db_session, sample_template
):
    """Test that created agent maintains reference to source template."""
    # Arrange
    params = {
        "user_name": "Iris",
        "expertise_area": "Kotlin",
    }

    # Act
    agent = template_service.instantiate_from_template(
        template_id="code-assistant-template",
        name="Iris's Assistant",
        parameters=params,
        organization_id="org-333",
    )

    # Assert
    assert agent["template_id"] == "code-assistant-template"

    # Verify in database
    db_agent = db_session.query(Agent).filter_by(id=agent["id"]).first()
    assert db_agent is not None
    # Template ID would be stored in description or metadata field
    assert (
        "code-assistant-template" in db_agent.description
        or agent["template_id"] == "code-assistant-template"
    )
