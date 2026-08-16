# Phase 7 Mobile Release

## Scope

Phase 7 adds a React Native + Expo mobile client at `apps/mobile-app` for the Harness task workflow.

Delivered engineering surfaces:

- touch-optimized task list with pull-to-refresh;
- offline-first local task cache and operation queue;
- sync reuse of `/api/desktop/sync` and `/api/desktop/sync/operations`;
- backend mobile device push-token registration at `/api/mobile/devices`;
- server-side Expo Push dispatch for observability alert selectors such as `mobile:*`;
- Expo push notification registration through `expo-notifications`;
- iOS WidgetKit and App Shortcuts source contracts;
- Android app widget metadata and Quick Settings Tile source contract;
- EAS beta/production build and submit profiles;
- App Store and Google Play review material drafts.

## Official References

- Expo Push Notifications overview: https://docs.expo.dev/push-notifications/overview/
- Expo push setup: https://docs.expo.dev/push-notifications/push-notifications-setup/
- Expo Notifications SDK: https://docs.expo.dev/versions/latest/sdk/notifications/
- EAS Build: https://docs.expo.dev/build/introduction/
- EAS Submit: https://docs.expo.dev/submit/introduction/
- Expo config plugins: https://docs.expo.dev/config-plugins/introduction/
- Apple WidgetKit: https://developer.apple.com/documentation/widgetkit
- Apple App Intents: https://developer.apple.com/documentation/appintents
- Android App Widgets: https://developer.android.com/develop/ui/views/appwidgets/overview
- Android Quick Settings Tiles: https://developer.android.com/develop/ui/views/quicksettings-tiles

## Local Verification

```bash
cd apps/mobile-app
npm test
npm run type-check

cd ../..
services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_notification_dispatcher.py services/api-server/tests/test_mobile_devices.py services/api-server/tests/test_desktop_sync.py -q
python3 scripts/validate-docs.py
```

## Credential-Gated Release Steps

These require private accounts and cannot be completed from an unauthenticated local shell:

1. Create or select an Expo project and set `EXPO_PUBLIC_EAS_PROJECT_ID`.
2. Configure APNs credentials in EAS for the iOS bundle id.
3. Configure FCM v1 / `google-services.json` for the Android package.
4. Create App Store Connect app record and Google Play app record.
5. Upload final app icon, screenshots, privacy answers, support URL, and review account.
6. Build beta binaries:

   ```bash
   cd apps/mobile-app
   npm run build:ios:beta
   npm run build:android:beta
   ```

7. Submit beta builds:

   ```bash
   npm run submit:ios:beta
   npm run submit:android:beta
   ```

8. Run TestFlight and Google Play internal testing. Minimum acceptance:
   - login to private Harness deployment;
   - task list loads from backend;
   - pull-to-refresh updates `lastSyncAt`;
   - offline-created task displays `待同步`;
   - reconnect sync clears pending operation;
   - push token appears in `/api/mobile/devices`;
   - delivered notification opens the app;
   - Android Quick Settings tile opens the app;
   - iOS widget opens `agentharness://tasks`.

9. Promote to production:

   ```bash
   npm run build:ios:production
   npm run submit:ios:production
   npm run build:android:production
   npm run submit:android:production
   ```

## Known Boundaries

- Real TestFlight, Google Play Beta, and production release are blocked without Apple Developer, Google Play, Expo/EAS, APNs, and FCM credentials.
- Native platform features are represented as source contracts and manifest/prebuild integration files. Before production, move Android manifest merging and iOS target membership into a config plugin or committed prebuild native project.
- The mobile app currently focuses on task list operations. Full Workspace chat, approvals, Run Detail replay, and desktop file bridge are intentionally not mirrored in the first mobile screen.
