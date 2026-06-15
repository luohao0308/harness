# Story 5.1 - Agent Template Repository Architecture

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (Wizard Step 6)                 │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Template Selection UI                                     │  │
│  │  - Display 5 templates as cards                            │  │
│  │  - Show icon, name, description, tags                      │  │
│  │  - Allow user to select one                                │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                   │
│                              │ GET /api/onboarding/templates    │
└──────────────────────────────┼───────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                         API Layer                                │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  app/api/agent_templates.py                               │  │
│  │                                                            │  │
│  │  @router.get("/api/onboarding/templates")                 │  │
│  │  def get_agent_templates(session: DbSession)              │  │
│  │      └─> service.get_all_templates()                      │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Service Layer                               │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  app/services/agent_template_service.py                   │  │
│  │                                                            │  │
│  │  class AgentTemplateService:                              │  │
│  │    def get_all_templates() -> list[AgentTemplateDict]     │  │
│  │        - Query active templates                            │  │
│  │        - Sort by name                                      │  │
│  │        - Convert to dict                                   │  │
│  │                                                            │  │
│  │    def get_template_by_id(id) -> AgentTemplateDict | None │  │
│  │        - Query by ID + active filter                       │  │
│  │        - Return None if not found                          │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Data Layer                                 │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  app/db/models.py                                          │  │
│  │                                                            │  │
│  │  class AgentTemplate(Base):                               │  │
│  │    __tablename__ = "agent_templates"                      │  │
│  │                                                            │  │
│  │    id: str                                                 │  │
│  │    name: str                                               │  │
│  │    description: str                                        │  │
│  │    icon: str                                               │  │
│  │    tags: list (JSON)                                       │  │
│  │    config: dict (JSON)                                     │  │
│  │    is_active: bool                                         │  │
│  │    created_at: datetime                                    │  │
│  │    updated_at: datetime                                    │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Database                                  │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  agent_templates table                                     │  │
│  │                                                            │  │
│  │  ┌──────────────┬─────────────────────────────────────┐  │  │
│  │  │ id           │ "code-assistant"                     │  │  │
│  │  │ name         │ "Code Assistant"                     │  │  │
│  │  │ description  │ "A specialized agent for..."         │  │  │
│  │  │ icon         │ "💻"                                  │  │  │
│  │  │ tags         │ ["coding", "development"]            │  │  │
│  │  │ config       │ {"system_prompt": "...", ...}        │  │  │
│  │  │ is_active    │ true                                 │  │  │
│  │  └──────────────┴─────────────────────────────────────┘  │  │
│  │  ... 4 more templates ...                                 │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow

### Request Flow (GET /api/onboarding/templates)

```
1. Frontend sends GET request
   └─> GET /api/onboarding/templates

2. FastAPI router receives request
   └─> agent_templates.get_agent_templates(session)

3. Service layer processes request
   └─> service.get_all_templates()
   └─> SELECT * FROM agent_templates WHERE is_active = true ORDER BY name

4. Database returns rows
   └─> [AgentTemplate(id="code-assistant", ...), ...]

5. Service converts to dictionaries
   └─> [{"id": "code-assistant", "name": "...", ...}, ...]

6. API returns JSON response
   └─> HTTP 200 with JSON array

7. Frontend displays templates
   └─> Render template selection cards
```

## Template Config Schema

```json
{
  "system_prompt": "You are an expert software engineer...",
  "suggested_tools": [
    "code_execution",
    "web_search",
    "file_operations"
  ],
  "default_model": "claude-sonnet-4",
  "parameters": {
    "temperature": 0.3
  }
}
```

## Database Migration

```
Migration: 20260615_0040_create_agent_templates.py

┌─────────────────────────────────────────┐
│  upgrade()                              │
│                                         │
│  1. CREATE TABLE agent_templates        │
│     - All columns defined               │
│     - Index on is_active                │
│                                         │
│  2. INSERT seed data                    │
│     - 5 default templates               │
│     - Complete config for each          │
│                                         │
│  downgrade()                            │
│                                         │
│  1. DROP INDEX ix_agent_templates_...  │
│  2. DROP TABLE agent_templates          │
└─────────────────────────────────────────┘
```

## 5 Default Templates

```
┌────────────────────┬─────────┬──────────────────────────────────┐
│ Template           │ Icon    │ Use Case                         │
├────────────────────┼─────────┼──────────────────────────────────┤
│ Code Assistant     │ 💻      │ Software development, debugging  │
│ Research Assistant │ 🔍      │ Information gathering, research  │
│ Data Analyst       │ 📊      │ Data analysis, visualization     │
│ DevOps Helper      │ 🚀      │ Infrastructure, deployment       │
│ General Assistant  │ 🤖      │ All-purpose, versatile tasks     │
└────────────────────┴─────────┴──────────────────────────────────┘
```

## Testing Strategy

```
Test Suite: test_agent_template_service.py

┌──────────────────────────────────────────────────────────────┐
│  Unit Tests (6 tests)                                        │
│                                                              │
│  ✓ test_get_all_templates_returns_list                      │
│    - Verifies active filtering                              │
│    - Tests multiple templates                               │
│                                                              │
│  ✓ test_get_all_templates_includes_required_fields          │
│    - Schema validation                                      │
│    - Config structure check                                 │
│                                                              │
│  ✓ test_get_template_by_id_returns_template                 │
│    - Single template retrieval                              │
│                                                              │
│  ✓ test_get_template_by_id_returns_none_for_nonexistent     │
│    - 404 handling                                           │
│                                                              │
│  ✓ test_get_template_by_id_excludes_inactive                │
│    - Active-only filtering by ID                            │
│                                                              │
│  ✓ test_default_templates_exist_after_seed                  │
│    - Seed data verification                                 │
└──────────────────────────────────────────────────────────────┘
```

## Integration with Wizard

```
Wizard Step Flow:

Step 1: Welcome          [✓ Implemented - Story 1.1]
Step 2: Model Provider   [Pending]
Step 3: Create Agent     [Pending]
Step 4: Knowledge Base   [Pending]
Step 5: Tool Config      [Pending]
Step 6: Agent Template   [✓ Backend Ready - Story 5.1]
   │
   ├─> GET /api/onboarding/templates
   │   └─> Returns 5 templates
   │
   ├─> User selects template
   │
   └─> Frontend uses template.config to:
       - Set agent system_prompt
       - Pre-select suggested_tools
       - Set default_model
       - Apply parameters

Step 7: Review & Complete [Pending]
```
