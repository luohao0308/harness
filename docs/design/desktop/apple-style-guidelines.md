# Apple-Style Desktop Experience Contract

## Intent

"Apple style" for Forge Harness Desktop means native-feeling restraint, not imitation
of Apple branding. The desktop app should feel calm, direct, spatially clear,
keyboard-friendly, privacy-aware, and consistent with macOS expectations while
still using the existing Harness visual system.

Use this contract with `DESIGN.md` and `docs/development/desktop/README.md` when changing
`/desktop`, `/terminal`, Electron windows, native menus, notifications, settings,
update flows, or desktop release UX.

## Official Sources

Primary references:

- Apple Human Interface Guidelines: https://developer.apple.com/design/human-interface-guidelines
- Navigation and search: https://developer.apple.com/design/human-interface-guidelines/navigation-and-search
- Settings: https://developer.apple.com/design/human-interface-guidelines/settings
- Notifications: https://developer.apple.com/design/human-interface-guidelines/notifications
- The menu bar: https://developer.apple.com/design/human-interface-guidelines/the-menu-bar
- Accessibility: https://developer.apple.com/design/human-interface-guidelines/accessibility

Apple's current HIG emphasizes hierarchy, harmony, consistency, platform
conventions, accessibility, and user control. Harness converts those principles
into the concrete rules below.

## Experience Principles

1. Hierarchy before decoration.
   - Start every desktop surface with status and intent.
   - Put primary actions near the evidence they act on.
   - Keep configuration behind disclosure until it is needed.

2. Native predictability.
   - Preserve macOS window behavior, app menu expectations, keyboard shortcuts,
     close-to-tray semantics, and deep-link routing.
   - Use icon buttons for familiar commands and text only when the command needs
     disambiguation.

3. Quiet confidence.
   - Prefer neutral surfaces, concise Chinese copy, steady spacing, and clear
     state badges.
   - Avoid marketing hero layouts, oversized gradients, decorative orbs, and
     dense card piles.

4. Privacy by posture.
   - Make local file roots, auth-bearing profiles, crash reporting, feedback
     payloads, and local model endpoints explicit.
   - Never hide credential-gated release work behind a green local build.

5. Accessibility is part of production.
   - Keyboard access, readable contrast, non-color state indicators, and reduced
     motion behavior are release requirements.

## Interface Rules

### Windows

- The main window opens to the Console route and can route to `/desktop`.
- Independent Run windows open one Run per profile/run key and restore bounds.
- Reopening an existing Run focuses it instead of duplicating it.
- Window titles should identify either `Forge Harness Desktop` or the Run being shown.
- Empty or invalid deep-link routes normalize to `/`.

### Workbench Layout

- `/desktop` remains the first-class desktop entry.
- The first viewport shows bridge state, profile state, immediate actions, and
  recent results.
- Sections are short operating chapters, not dashboard tiles.
- Long forms stay folded until the user chooses to configure that area.
- Status labels must distinguish `desktop bridge connected`, `web fallback`, and
  `bridge read failed`.

### Sidebar, Toolbar, And Menus

- Keep the global Console sidebar stable; desktop is a top-level destination.
- Native menu entries should mirror ordinary macOS expectations: show, hide,
  quit, check for updates, and route to common Harness surfaces.
- Toolbar-like controls should favor icons for known actions and include
  accessible labels or tooltips.
- Avoid using a visible text button where a standard command icon is clearer.

### Settings

- Settings are scoped by user intent: Profile, Local Model, Updates, Feedback,
  File Root, and System Startup.
- Dangerous or credential-bearing settings need confirmation and plain-language
  consequences.
- API base URLs, auth tokens, local file roots, and local model endpoints must
  be editable only in deliberate configuration areas.

### Notifications

- Native notifications are reserved for completed, failed, error, or conflict
  Agent events.
- Notifications must click through to the relevant Run or route.
- Do not use notifications for routine progress noise.
- Notification copy stays short, Chinese-first, and action-oriented.

### Terminal

- `/terminal` is a tool surface, not a decorative console preview.
- Four terminal panes must have stable titles and keyboard switching.
- Layout persistence must not resize or shift when output changes.
- Terminal output must not overlap with controls at desktop or narrow widths.

### Offline And Local Model

- Offline deterministic output is always available for simple tasks.
- Optional local model calls can improve output, but failure must fail soft.
- Copy must explain whether the result came from deterministic local logic or a
  local model endpoint.

### File Bridge

- The file bridge starts from an explicit root.
- Watch/list/read/write states show the active root and truncation status.
- File errors must name what failed without exposing secrets or unrelated paths.

### Updates And Release

- Stable and beta channels must be visibly distinct.
- The backend update policy is checked before updater download.
- Update prompts should say what version is available and whether restart is
  required.
- Local unsigned packaging must never be described as notarized production.

### Motion And Visual Design

- Use restrained transitions and busy states; avoid bouncing, blinking, or
  peripheral animation.
- Preserve the existing semantic colors: slate, cyan, emerald, amber, red.
- Use spacing and typography to communicate importance before color.
- Cards are for individual repeated items or framed tools, not nested page
  sections.

### Accessibility Checklist

- Keyboard-only operation reaches every command.
- Focus states are visible.
- State uses text or icon plus color, not color alone.
- Text remains readable at desktop and narrow widths.
- Control targets stay comfortable for pointer use.
- High-contrast mode remains available and does not erase information hierarchy.
- Reduced motion does not remove status feedback.

## Review Gate

A desktop UI change is not production-ready if any of these are true:

- The first screen cannot explain bridge status and next action.
- A credential, token, file path, crash log, or screenshot can leak by default.
- A web fallback claim is presented as native bridge success.
- A local package is described as signed/notarized without external credentials.
- Terminal, workbench, or modal content overflows horizontally.
- Notifications fire for low-value progress.
- Keyboard users cannot complete the same core workflow.

## Implementation Evidence

Current owner files:

- `apps/agent-console/src/features/settings/pages/AdvancedFeaturesPage.tsx`
- `apps/agent-console/src/features/terminal/`
- `apps/agent-console/src/lib/desktop-bridge.ts`
- `apps/desktop-app/src/main.ts`
- `apps/desktop-app/src/preload.ts`
- `apps/desktop-app/src/preload-api.ts`
- `apps/desktop-app/src/services/system-integration.ts`
- `apps/desktop-app/src/services/window-manager.ts`
- `apps/desktop-app/src/services/phase6-service.ts`
- `apps/desktop-app/src/services/desktop-updates.ts`
- `apps/desktop-app/src/services/file-service.ts`

Current evidence page:

- `omx_wiki/session-2026-07-04-desktop-full-function-startup-smoke.md`
