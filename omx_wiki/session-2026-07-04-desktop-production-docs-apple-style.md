# Desktop Production Docs Apple Style

Category: `session`

Tags: `desktop`, `electron`, `documentation`, `apple-style`, `release`, `production`

## Summary

Desktop documentation is now production-ready enough to serve as the canonical
operator, release, design, and support entry point for Harness Desktop. The work
uses the 2026-07-04 full desktop startup smoke as runtime evidence and turns it
into durable docs that explain what is proven locally, what is credential-gated,
and what Apple-style means for this product.

## Delivered

- Added `docs/development/desktop/README.md` as the production desktop guide:
  - product contract and first-screen expectations;
  - capability ownership map for `/desktop`, `/terminal`, Profile, Run windows,
    offline tasks, local model, file bridge, system integration, updates,
    feedback/metrics, and packaging;
  - local startup commands, including `ELECTRON_RUN_AS_NODE=` and `NO_PROXY`;
  - PR desktop gate, release-candidate gate, and external promotion gate;
  - release operations, update-channel env vars, privacy/security rules, support
    playbook, and official Apple references.
- Added `docs/design/desktop/apple-style-guidelines.md` as the Apple-style experience
  contract for Harness Desktop:
  - native-feeling restraint rather than Apple-brand imitation;
  - rules for windows, workbench layout, sidebar/toolbar/menus, settings,
    notifications, terminal, offline/local-model behavior, file bridge, updates,
    motion, visual language, and accessibility;
  - production review blockers for bridge-state ambiguity, credential leakage,
    false notarization claims, notification noise, overflow, and keyboard gaps.
- Added `apps/desktop-app/README.md` with package-local scripts, launch commands,
  verification, source map, and local Electron pitfalls.
- Refreshed `DESIGN.md` so future desktop work has an explicit Apple-style and
  production-docs contract.
- Linked the desktop production guide from local-development, release, CI/CD,
  troubleshooting, and spec-index docs.

## Evidence

Runtime evidence reused from [[session-2026-07-04-desktop-full-function-startup-smoke]]:

```text
backend desktop API pytest -> 30 passed
Agent Console desktop/terminal/file-bridge/VirtualList Vitest -> 57 passed
Agent Console production build -> passed with existing chunk-size warning
desktop-app npm test -> 28 files / 259 tests passed
desktop build:main/build:renderer -> passed
electron-builder --dir --publish never -> passed with expected unsigned/notarization warnings
browser /desktop and /terminal smokes -> passed
real Electron preload/native bridge smoke -> profile/window/offline/local-model/file/system APIs passed
real Electron terminal smoke -> command output returned
release YAML parse, release script syntax, docs validation, git diff --check -> passed
```

Fresh docs validation for this slice:

```text
python3 scripts/validate-docs.py -> docs validation passed
git diff --check -> passed
```

## Apple References Used

- Apple Human Interface Guidelines:
  https://developer.apple.com/design/human-interface-guidelines
- HIG Navigation and Search:
  https://developer.apple.com/design/human-interface-guidelines/navigation-and-search
- HIG Settings:
  https://developer.apple.com/design/human-interface-guidelines/settings
- HIG Notifications:
  https://developer.apple.com/design/human-interface-guidelines/notifications
- HIG Menu Bar:
  https://developer.apple.com/design/human-interface-guidelines/the-menu-bar
- HIG Accessibility:
  https://developer.apple.com/design/human-interface-guidelines/accessibility
- Apple notarization:
  https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution
- Hardened Runtime:
  https://developer.apple.com/documentation/security/hardened_runtime

## Boundaries

- This was a documentation and design-contract slice. It did not modify desktop
  runtime code.
- Real Apple notarization, Developer ID signing, Windows Authenticode signing,
  and Sentry sourcemap upload remain private-credential external steps.
- The production guide deliberately separates local package proof from external
  trust proof, so future releases do not overclaim from an unsigned local build.

## Next Work

- Keep `docs/development/desktop/README.md` and `docs/design/desktop/apple-style-guidelines.md`
  current whenever desktop bridge namespaces, release workflow, update policy,
  or native UX behavior changes.
- If the Desktop UI itself is redesigned later, use the Apple-style contract as
  the review checklist before running visual implementation work.
