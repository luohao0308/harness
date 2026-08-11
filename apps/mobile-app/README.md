# Harness Mobile

React Native + Expo mobile client for the Harness task surface.

## What This App Reuses

- `/api/desktop/sync`
- `/api/desktop/sync/operations`
- the desktop task sync shape from `apps/desktop-app/src/stores/types.ts`
- the same offline-first queue semantics: local task cache, pending operation queue, conflict evidence, and last-sync timestamp

The first screen is the actual task list. It supports pull-to-refresh, local task creation, completion, conflict/dirty badges, and an offline banner.

## Local Development

```bash
cd apps/mobile-app
npm install
npm test
npm run type-check
npm start
```

Set `EXPO_PUBLIC_API_BASE_URL` and an auth token in SecureStore before connecting to a non-dev API. In local dev, the backend can be started at `http://127.0.0.1:8000`.

## Push Notifications

The app uses `expo-notifications` to request permission, get an Expo push token, and register it with:

```text
POST /api/mobile/devices
```

EAS credentials still need the real APNs key/certificate and FCM configuration before TestFlight or Google Play Beta can receive production push notifications.

## Platform Features

- iOS WidgetKit source: `ios/Widgets/HarnessTaskWidget.swift`
- iOS App Shortcuts source: `ios/Shortcuts/HarnessShortcuts.swift`
- Android Quick Settings tile source: `android/app/src/main/java/com/harness/mobile/tiles/HarnessQuickSettingsTile.kt`
- Android widget provider metadata: `android/app/src/main/res/xml/harness_task_widget_info.xml`
- Android manifest merge snippet: `android/AndroidManifest.phase7-snippet.xml`

For fully managed Expo builds, move the native manifest/source wiring into a config plugin before production submission. The current files are the Phase 7 native source of truth and prebuild integration contract.

## Beta And Store Commands

```bash
npm run build:ios:beta
npm run submit:ios:beta
npm run build:android:beta
npm run submit:android:beta
npm run build:ios:production
npm run submit:ios:production
npm run build:android:production
npm run submit:android:production
```

Real submission requires the private EAS, Apple Developer, App Store Connect, Google Play Console, APNs, and FCM credentials listed in `.env.example`.
