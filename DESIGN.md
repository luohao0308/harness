# Design

## Source of truth

- Status: Active
- Last refreshed: 2026-05-26
- Primary product surfaces: Agent Console, Agent Workspace, Knowledge workbench, Team Mode, Tool Registry, Observability.
- Evidence reviewed: `docs/design/design-tokens.json`, `docs/design/page-inventory.md`, `docs/ai/reference/frontend-spec.md`, `omx_wiki/workspace-demo-ready-constraints.md`, `omx_wiki/session-2026-05-13-workspace-browser-smoke.md`, `omx_wiki/session-2026-05-18-agent-knowledge-p7-release-demo-hardening.md`, existing Console components under `apps/agent-console/src`.

## Brand

- Personality: precise, operational, enterprise-ready, quiet.
- Trust signals: real backend state, audit evidence, explicit status, clear policy boundaries.
- Avoid: marketing-style hero sections, decorative dashboards, one-off visual gimmicks, inline forms that crowd operational pages.

## Product goals

- Goals: make Harness capabilities configurable, auditable, and easy to operate from the Console.
- Non-goals: public marketing polish, generic chatbot UI, fake static console data.
- Success signals: users can scan state first, then open focused configuration flows only when needed.

## Personas and jobs

- Primary personas: internal platform engineer, agent operator, evaluator, demo reviewer.
- User jobs: configure agents, attach capabilities, manage knowledge, inspect evidence, run validation.
- Key contexts of use: local private deployment, demo review, iterative internal testing.

## Information architecture

- Primary navigation: Console sidebar owns stable product areas.
- Core routes/screens: Agents, Teams, Knowledge, Tools, Runs, Observability, Token Savings, Eval, Policy, Models.
- Content hierarchy: overview and status first; details second; create/edit/configure actions in dialogs or compact popovers.

## Design principles

- Principle 1: keep operational work surfaces scannable before they are editable.
- Principle 2: configuration should be a focused modal or popover when it is not the primary page content.
- Tradeoffs: favor compact, explicit controls over large always-visible forms; expose advanced details only when selected.

## Visual language

- Color: restrained neutral base with status colors for state and evidence.
- Typography: compact console typography; no viewport-scaled font sizes.
- Spacing/layout rhythm: dense but breathable 8px-oriented spacing; avoid nested cards.
- Shape/radius/elevation: small radius, light borders, limited elevation for dialogs/popovers.
- Motion: minimal, functional feedback only.
- Imagery/iconography: use lucide icons for tools/actions; no decorative imagery in console screens.

## Components

- Existing components to reuse: `ConsoleShell`, `Card`, `Button`, `Badge`, `Input`, `Textarea`, `MenuSelect`.
- New/changed components: feature-local modal shells are acceptable when no shared dialog component exists.
- Variants and states: all controls need loading, disabled, empty, error, and success states where applicable.
- Token/component ownership: keep styling in Tailwind classes and existing UI primitives unless a repeated pattern justifies extraction.

## Accessibility

- Target standard: keyboard-operable, semantic controls, readable contrast.
- Keyboard/focus behavior: dialogs use `role="dialog"` and `aria-modal="true"`; popovers/dialogs must have clear close paths.
- Contrast/readability: status badges must remain legible on light backgrounds.
- Screen-reader semantics: buttons and inputs require accessible names.
- Reduced motion and sensory considerations: avoid nonessential animation.

## Responsive behavior

- Supported breakpoints/devices: desktop console first, narrow mobile checks for overflow regressions.
- Layout adaptations: sidebars and panels may stack; action rows wrap instead of overflowing.
- Touch/hover differences: do not require hover-only access to critical actions.

## Interaction states

- Loading: show compact text or disabled controls.
- Empty: describe the empty state and provide the next primary action.
- Error: render request failures inline near the action.
- Success: refresh server state and close modal dialogs after successful mutation.
- Disabled: explain or visually imply unavailable actions where practical.
- Offline/slow network, if applicable: avoid blocking page scanability while queries refresh.

## Content voice

- Tone: Chinese-first console copy, concise and operational.
- Terminology: preserve required technical terms such as API, MCP, RAG, JSON, Markdown, Trace, WarmPool.
- Microcopy rules: say what the action changes; avoid feature explanations inside the main work surface.

## Implementation constraints

- Framework/styling system: React, TypeScript, TanStack Query, Tailwind classes, existing UI primitives.
- Design-token constraints: use existing colors, radius, borders, and component sizes.
- Performance constraints: avoid heavy client-only visual layers and unnecessary dependencies.
- Compatibility constraints: frontend state must remain API-backed; no placeholder routes or static console data.
- Test/screenshot expectations: pair UI changes with targeted Vitest, lint/build, and Playwright overflow/smoke evidence when layout risk is visible.

## Open questions

- [ ] Whether a shared Dialog primitive should replace feature-local modal shells once a second or third modal pattern repeats across product areas.
