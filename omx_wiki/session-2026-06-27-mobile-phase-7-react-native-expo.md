# Mobile Phase 7 React Native Expo

Category: session-log
Tags: `mobile`, `react-native`, `expo`, `offline-sync`, `push-notifications`, `app-store`, `google-play`

## Summary

Phase 7 mobile is implemented as a React Native + Expo companion app under `apps/mobile-app`.

The first screen is the task list, not a landing page. It supports touch-sized task cards, pull-to-refresh, local task creation, local completion, offline pending state, conflict state, and sync status copy. The mobile sync core reuses the desktop `/api/desktop/sync` and `/api/desktop/sync/operations` protocol instead of inventing a separate mobile task contract.

## Delivered

- Added `apps/mobile-app` with Expo SDK 56 / React Native 0.86 configuration, EAS beta/production build profiles, local README, and `.env.example`.
- Added mobile offline-first sync core in `src/sync/` with Expo SQLite persistence, memory tests, operation queue, metadata, conflict storage, and desktop sync operation mapping.
- Added task-list UI and private-deployment connection settings in `App.tsx`, `src/hooks/useMobileTasks.ts`, and `src/components/`.
- Added Expo push registration with Android notification channel setup, Expo push token retrieval, backend registration, server-side `mobile:*` alert dispatch, and fail-soft UI notices.
- Added backend mobile device registration through `services/api-server/app/api/mobile.py`, `MobileDevice`, migration `20260627_0048_create_mobile_devices.py`, and tests.
- Added platform feature source contracts for iOS WidgetKit, iOS App Shortcuts, Android widget metadata, and Android Quick Settings Tile.
- Added `docs/operations/mobile/phase7-mobile-release.md`, `apps/mobile-app/store-assets/app-store-review.md`, and `apps/mobile-app/store-assets/google-play-review.md`.

## Validation

```text
cd apps/mobile-app && npm test
1 file / 5 tests passed

cd apps/mobile-app && npm run type-check
passed

services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_notification_dispatcher.py services/api-server/tests/test_mobile_devices.py services/api-server/tests/test_desktop_sync.py -q
15 passed

services/api-server/.venv/bin/python -m ruff check services/api-server/app/api/mobile.py services/api-server/app/observability/notification_dispatcher.py services/api-server/tests/test_mobile_devices.py services/api-server/tests/test_notification_dispatcher.py
passed

python3 scripts/validate-docs.py
passed
```

## Official References

- Expo Push Notifications: https://docs.expo.dev/push-notifications/overview/
- Expo Notifications SDK: https://docs.expo.dev/versions/latest/sdk/notifications/
- EAS Build: https://docs.expo.dev/build/introduction/
- EAS Submit: https://docs.expo.dev/submit/introduction/
- Expo config plugins: https://docs.expo.dev/config-plugins/introduction/
- Apple WidgetKit: https://developer.apple.com/documentation/widgetkit
- Apple App Intents: https://developer.apple.com/documentation/appintents
- Android App Widgets: https://developer.android.com/develop/ui/views/appwidgets/overview
- Android Quick Settings Tiles: https://developer.android.com/develop/ui/views/quicksettings-tiles

## Boundaries

- Real TestFlight, Google Play Beta, and production release are credential-gated by Apple Developer, App Store Connect, Google Play Console, Expo/EAS, APNs, and FCM credentials.
- The repo now contains the beta/production build and submit commands plus review materials, but it does not claim external publication from this local unauthenticated shell.
- Native iOS/Android feature files are source contracts for the Phase 7 platform surfaces. Before production, wire them into a config plugin or committed prebuild native project so EAS includes the target membership and Android manifest declarations.
- The mobile app intentionally starts with the task workflow. Full Workspace chat, Run Detail replay, approvals, and desktop file bridge are future mobile surfaces.
