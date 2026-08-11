# App Store Review Notes

## App Name

Harness

## Subtitle

Agent task control, online or offline

## Promotional Text

Track Harness Agent tasks from iPhone and iPad, keep working offline, and receive run updates when attention is needed.

## Description

Harness Mobile is the companion app for the AI Harness Platform. It lets operators review Agent tasks, create follow-up tasks, mark work complete, and keep local changes available when the network is unreliable.

The app syncs with the Harness backend using the same offline-first task synchronization mechanism as Harness Desktop. Local edits are queued on device and uploaded when connectivity returns. Push notifications can alert users about run completion, approval needs, and sync conflicts.

## Keywords

agent,task,ai,workflow,operations,offline,sync,automation

## Review Account

Provide an internal Harness test account with access to a seeded private deployment.

```text
API base URL: <private review deployment URL>
Username: <review account email>
Password: <review account password>
```

## Review Notes

- The app is a companion client for a private Harness deployment.
- First screen is the task list.
- Pull down on the task list to refresh.
- Create a task while offline to verify offline-first behavior; the task shows `待同步` until network returns.
- Push notifications require notification permission and a TestFlight build configured with APNs credentials.

## Privacy Answers

- Data linked to user: account identifier, task metadata, push token.
- Data not used for tracking.
- Push token is used only for Harness notifications.
- Offline task data is stored on device for sync/recovery.

## Screenshots Needed Before Submission

- iPhone 6.7": task list with synced tasks.
- iPhone 6.7": offline banner with pending operation.
- iPad 13": task list in larger layout.
- Notification permission prompt or delivered run update.
