# Google Play Review Notes

## App Name

Harness

## Short Description

Offline-first Agent task control.

## Full Description

Harness Mobile helps teams operate AI Harness Agent tasks from Android devices. Users can refresh task status, create tasks, mark tasks complete, receive run notifications, and keep working when connectivity is poor.

The app reuses the Harness Desktop synchronization contract. Changes are stored locally first, queued for upload, and reconciled with the backend when the device reconnects. Conflict and pending-sync states are visible in the task list.

## Internal Testing Instructions

1. Install the Android beta from the internal testing track.
2. Sign in to the provided private Harness deployment.
3. Pull down on the task list to refresh.
4. Disable network and create a task.
5. Re-enable network and pull to refresh; the pending task should sync.
6. Add the Quick Settings tile named `Harness` and tap it to open the app.

## Data Safety

- Account info: used for authentication.
- App activity: task status and task metadata used to provide sync.
- Device identifiers: Expo push token used for notifications only.
- No third-party advertising or cross-app tracking.
- Users can disable notifications in Android settings.

## Review Account

```text
API base URL: <private review deployment URL>
Username: <review account email>
Password: <review account password>
```

## Graphics Needed Before Submission

- App icon: replace initial desktop-derived icon with final mobile icon.
- Feature graphic: 1024 x 500.
- Phone screenshots: task list, offline pending state, notification update.
- Tablet screenshots if tablet distribution is enabled.
