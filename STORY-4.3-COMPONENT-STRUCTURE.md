# Story 4.3 - Component Structure

## File Structure

```
apps/agent-console/src/components/onboarding/
├── steps/
│   ├── WelcomeStep.tsx                    (Step 1 - Existing ✅)
│   ├── ModelProviderStep.tsx              (Step 2 - NEW ✅)
│   ├── FirstAgentStep.tsx                 (Step 3 - NEW ✅)
│   ├── KnowledgeBaseStep.tsx              (Step 4 - NEW ✅)
│   ├── ToolConfigStep.tsx                 (Step 5 - NEW ✅)
│   └── __tests__/
│       ├── WelcomeStep.test.tsx           (Existing)
│       └── ConfigurationSteps.test.tsx    (NEW - 8 tests ✅)
├── WizardLayout.tsx                        (Existing)
├── NavigationButtons.tsx                   (Existing)
├── StepIndicator.tsx                       (Existing)
└── index.ts                                (Updated with new exports ✅)
```

## Component Props Interface

### ModelProviderStep
```typescript
interface ModelProviderStepProps {
  onSubmit: (data: ModelProviderFormData) => void | Promise<void>;
  initialData?: Partial<ModelProviderFormData>;
}

type ModelProviderFormData = {
  apiKey: string;
  baseUrl: string;
  model: string;
}
```

### FirstAgentStep
```typescript
interface FirstAgentStepProps {
  onSubmit: (data: FirstAgentFormData) => void | Promise<void>;
  initialData?: Partial<FirstAgentFormData>;
}

type FirstAgentFormData = {
  name: string;         // 3-50 chars
  description: string;  // 10-200 chars
  systemPrompt: string; // 20-2000 chars
}
```

### KnowledgeBaseStep
```typescript
interface KnowledgeBaseStepProps {
  onSubmit: (data: KnowledgeBaseFormData) => void | Promise<void>;
  initialData?: Partial<KnowledgeBaseFormData>;
}

type KnowledgeBaseFormData = {
  url?: string;        // Valid URL format
  files?: File[];      // PDF, TXT, MD files
}
// Note: Requires at least URL or one file
```

### ToolConfigStep
```typescript
interface ToolConfigStepProps {
  onSubmit: (data: ToolConfigFormData) => void | Promise<void>;
  initialData?: Partial<ToolConfigFormData>;
}

type ToolConfigFormData = {
  tools: string[];  // Minimum 1 tool required
}

// Available tools:
// - "web-search"
// - "code-execution"
// - "file-operations"
// - "api-calls"
// - "database-query"
```

## Usage Example

```typescript
import { 
  ModelProviderStep, 
  FirstAgentStep, 
  KnowledgeBaseStep, 
  ToolConfigStep 
} from '@/components/onboarding';

// Step 2: Model Provider
<ModelProviderStep 
  onSubmit={async (data) => {
    await saveModelConfig(data);
  }}
/>

// Step 3: First Agent
<FirstAgentStep 
  onSubmit={async (data) => {
    await createAgent(data);
  }}
/>

// Step 4: Knowledge Base
<KnowledgeBaseStep 
  onSubmit={async (data) => {
    await uploadKnowledgeBase(data);
  }}
/>

// Step 5: Tool Configuration
<ToolConfigStep 
  onSubmit={async (data) => {
    await saveToolConfig(data);
  }}
/>
```

## Validation Rules Summary

| Component | Field | Validation |
|-----------|-------|------------|
| ModelProviderStep | apiKey | Required |
| | baseUrl | Required, valid URL |
| | model | Required |
| FirstAgentStep | name | Required, 3-50 chars |
| | description | Required, 10-200 chars |
| | systemPrompt | Required, 20-2000 chars |
| KnowledgeBaseStep | url | Optional, valid URL if provided |
| | files | Optional, .pdf/.txt/.md |
| | *Combined* | At least URL or 1 file required |
| ToolConfigStep | tools | Minimum 1 tool selected |

## State Management

Each component uses React Hook Form with:
- `register()` for input binding
- `handleSubmit()` for form submission
- `formState.errors` for validation errors
- `setValue()` for programmatic updates (KnowledgeBaseStep, ToolConfigStep)
- `watch()` for reactive values (FirstAgentStep character counter)

## Styling Pattern

All components follow consistent Tailwind styling:
- Input/textarea: `rounded-md border border-slate-300 px-3 py-2`
- Labels: `text-sm font-medium text-slate-700`
- Error text: `text-sm text-red-600`
- Submit buttons: `bg-blue-600 hover:bg-blue-700`
- Loading spinner: Lucide `Loader2` icon with `animate-spin`
