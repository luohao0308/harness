# Story 5.1 - API Examples

## Endpoint: GET /api/onboarding/templates

### Request

```http
GET /api/onboarding/templates HTTP/1.1
Host: localhost:8000
Accept: application/json
```

### Response (Success - 200 OK)

```json
[
  {
    "id": "code-assistant",
    "name": "Code Assistant",
    "description": "A specialized agent for software development, code review, debugging, and technical problem-solving. Ideal for engineers working on coding projects.",
    "icon": "💻",
    "tags": ["coding", "development", "debugging", "technical"],
    "config": {
      "system_prompt": "You are an expert software engineer and coding assistant. Help users write clean, efficient, and well-documented code. Provide debugging support, code reviews, and technical guidance. Follow best practices and industry standards.",
      "suggested_tools": ["code_execution", "web_search", "file_operations"],
      "default_model": "claude-sonnet-4",
      "parameters": {
        "temperature": 0.3
      }
    }
  },
  {
    "id": "data-analyst",
    "name": "Data Analyst",
    "description": "Specialized in data analysis, visualization, statistical analysis, and extracting insights from datasets. Perfect for data-driven decision making.",
    "icon": "📊",
    "tags": ["data", "analytics", "statistics", "visualization"],
    "config": {
      "system_prompt": "You are an expert data analyst. Help users analyze datasets, perform statistical analysis, create visualizations, and extract actionable insights. Explain your methodology clearly and provide data-driven recommendations.",
      "suggested_tools": ["code_execution", "file_operations", "data_processing"],
      "default_model": "claude-sonnet-4",
      "parameters": {
        "temperature": 0.4
      }
    }
  },
  {
    "id": "devops-helper",
    "name": "DevOps Helper",
    "description": "Assists with infrastructure management, deployment automation, CI/CD pipelines, monitoring, and operational tasks.",
    "icon": "🚀",
    "tags": ["devops", "infrastructure", "deployment", "automation"],
    "config": {
      "system_prompt": "You are a DevOps and infrastructure expert. Help users with deployment automation, CI/CD pipelines, infrastructure as code, monitoring, and operational best practices. Focus on reliability, security, and scalability.",
      "suggested_tools": ["code_execution", "web_search", "file_operations", "shell_commands"],
      "default_model": "claude-sonnet-4",
      "parameters": {
        "temperature": 0.3
      }
    }
  },
  {
    "id": "general-assistant",
    "name": "General Assistant",
    "description": "A versatile all-purpose agent that can handle a wide variety of tasks. Great starting point for users who need flexible assistance.",
    "icon": "🤖",
    "tags": ["general", "versatile", "all-purpose"],
    "config": {
      "system_prompt": "You are a helpful and versatile AI assistant. Help users with a wide range of tasks including writing, research, problem-solving, brainstorming, and general assistance. Adapt your approach based on the user's needs.",
      "suggested_tools": ["web_search", "code_execution", "file_operations"],
      "default_model": "claude-sonnet-4",
      "parameters": {
        "temperature": 0.7
      }
    }
  },
  {
    "id": "research-assistant",
    "name": "Research Assistant",
    "description": "An agent optimized for information gathering, research, fact-checking, and synthesizing knowledge from multiple sources.",
    "icon": "🔍",
    "tags": ["research", "information", "analysis", "investigation"],
    "config": {
      "system_prompt": "You are a thorough research assistant. Help users find accurate information, verify facts, synthesize knowledge from multiple sources, and provide well-cited summaries. Be objective and comprehensive in your research.",
      "suggested_tools": ["web_search", "web_fetch", "document_analysis"],
      "default_model": "claude-sonnet-4",
      "parameters": {
        "temperature": 0.5
      }
    }
  }
]
```

## Usage Examples

### JavaScript/TypeScript (Frontend)

```typescript
// Fetch all agent templates
async function fetchAgentTemplates() {
  const response = await fetch('http://localhost:8000/api/onboarding/templates');
  
  if (!response.ok) {
    throw new Error('Failed to fetch templates');
  }
  
  const templates = await response.json();
  return templates;
}

// Example: Display templates in UI
async function displayTemplates() {
  const templates = await fetchAgentTemplates();
  
  templates.forEach(template => {
    console.log(`${template.icon} ${template.name}`);
    console.log(`  ${template.description}`);
    console.log(`  Tags: ${template.tags.join(', ')}`);
    console.log('');
  });
}

// Example: Select a template
function applyTemplate(template, agentForm) {
  agentForm.systemPrompt = template.config.system_prompt;
  agentForm.selectedTools = template.config.suggested_tools;
  agentForm.defaultModel = template.config.default_model;
  agentForm.temperature = template.config.parameters.temperature;
}
```

### Python (Backend/Testing)

```python
import httpx

# Fetch all templates
async def get_templates():
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/api/onboarding/templates")
        response.raise_for_status()
        return response.json()

# Example: Filter templates by tag
def filter_by_tag(templates, tag):
    return [t for t in templates if tag in t['tags']]

# Example usage
templates = await get_templates()
coding_templates = filter_by_tag(templates, 'coding')
```

### cURL (Manual Testing)

```bash
# Get all templates
curl -X GET http://localhost:8000/api/onboarding/templates \
  -H "Accept: application/json" \
  | jq '.'

# Get templates and filter by tag
curl -s http://localhost:8000/api/onboarding/templates \
  | jq '.[] | select(.tags[] | contains("coding"))'

# Get only template IDs and names
curl -s http://localhost:8000/api/onboarding/templates \
  | jq '.[] | {id: .id, name: .name, icon: .icon}'

# Count templates
curl -s http://localhost:8000/api/onboarding/templates \
  | jq 'length'
```

## Frontend Integration Example

### React Component

```typescript
import React, { useEffect, useState } from 'react';

interface AgentTemplate {
  id: string;
  name: string;
  description: string;
  icon: string;
  tags: string[];
  config: {
    system_prompt: string;
    suggested_tools: string[];
    default_model: string;
    parameters: Record<string, any>;
  };
}

export function TemplateSelector({ onSelect }: { onSelect: (template: AgentTemplate) => void }) {
  const [templates, setTemplates] = useState<AgentTemplate[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/onboarding/templates')
      .then(res => res.json())
      .then(data => {
        setTemplates(data);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return <div>Loading templates...</div>;
  }

  return (
    <div className="template-grid">
      {templates.map(template => (
        <div 
          key={template.id} 
          className="template-card"
          onClick={() => onSelect(template)}
        >
          <div className="template-icon">{template.icon}</div>
          <h3>{template.name}</h3>
          <p>{template.description}</p>
          <div className="template-tags">
            {template.tags.map(tag => (
              <span key={tag} className="tag">{tag}</span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
```

### Vue Component

```vue
<template>
  <div class="template-selector">
    <div v-if="loading">Loading templates...</div>
    
    <div v-else class="template-grid">
      <div 
        v-for="template in templates" 
        :key="template.id"
        class="template-card"
        @click="selectTemplate(template)"
      >
        <div class="template-icon">{{ template.icon }}</div>
        <h3>{{ template.name }}</h3>
        <p>{{ template.description }}</p>
        <div class="template-tags">
          <span 
            v-for="tag in template.tags" 
            :key="tag" 
            class="tag"
          >
            {{ tag }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';

const templates = ref([]);
const loading = ref(true);

const emit = defineEmits(['select']);

onMounted(async () => {
  const response = await fetch('/api/onboarding/templates');
  templates.value = await response.json();
  loading.value = false;
});

function selectTemplate(template) {
  emit('select', template);
}
</script>
```

## Error Scenarios

### Empty Response (No Templates)

```json
[]
```

**When**: All templates are marked as `is_active = false`

### Server Error (500)

```json
{
  "detail": "Internal server error"
}
```

**When**: Database connection issues or server errors

## Response Schema

### TypeScript Definition

```typescript
interface AgentTemplateConfig {
  system_prompt: string;
  suggested_tools: string[];
  default_model: string;
  parameters: Record<string, any>;
}

interface AgentTemplate {
  id: string;
  name: string;
  description: string;
  icon: string;
  tags: string[];
  config: AgentTemplateConfig;
}

type AgentTemplatesResponse = AgentTemplate[];
```

### JSON Schema

```json
{
  "type": "array",
  "items": {
    "type": "object",
    "required": ["id", "name", "description", "icon", "tags", "config"],
    "properties": {
      "id": {
        "type": "string",
        "description": "Unique template identifier"
      },
      "name": {
        "type": "string",
        "description": "Display name"
      },
      "description": {
        "type": "string",
        "description": "Template description"
      },
      "icon": {
        "type": "string",
        "description": "Emoji or icon identifier"
      },
      "tags": {
        "type": "array",
        "items": {
          "type": "string"
        },
        "description": "Categorization tags"
      },
      "config": {
        "type": "object",
        "required": ["system_prompt", "suggested_tools", "default_model"],
        "properties": {
          "system_prompt": {
            "type": "string"
          },
          "suggested_tools": {
            "type": "array",
            "items": {
              "type": "string"
            }
          },
          "default_model": {
            "type": "string"
          },
          "parameters": {
            "type": "object"
          }
        }
      }
    }
  }
}
```

## Testing the Endpoint

### Using pytest

```python
def test_get_templates_endpoint(client):
    """Test the GET /api/onboarding/templates endpoint."""
    response = client.get("/api/onboarding/templates")
    
    assert response.status_code == 200
    data = response.json()
    
    assert isinstance(data, list)
    assert len(data) == 5
    
    # Check first template structure
    template = data[0]
    assert "id" in template
    assert "name" in template
    assert "description" in template
    assert "icon" in template
    assert "tags" in template
    assert "config" in template
    
    # Check config structure
    config = template["config"]
    assert "system_prompt" in config
    assert "suggested_tools" in config
    assert "default_model" in config
```

### Using httpx (async)

```python
import httpx
import pytest

@pytest.mark.asyncio
async def test_get_templates_async():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.get("/api/onboarding/templates")
        
        assert response.status_code == 200
        templates = response.json()
        
        assert len(templates) == 5
        assert all('config' in t for t in templates)
```

## OpenAPI Documentation

The endpoint is automatically documented at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
