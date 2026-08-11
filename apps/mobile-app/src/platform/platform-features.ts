export const platformFeatureMatrix = {
  ios: {
    widgets: "WidgetKit source lives in ios/Widgets/HarnessTaskWidget.swift.",
    shortcuts: "AppIntents source lives in ios/Shortcuts/HarnessShortcuts.swift.",
    push: "APNs is configured through EAS credentials and expo-notifications.",
  },
  android: {
    widgets: "AppWidget provider metadata lives in android/app/src/main/res/xml/harness_task_widget_info.xml.",
    quickSettings: "TileService source lives in android/app/src/main/java/com/harness/mobile/tiles/HarnessQuickSettingsTile.kt.",
    push: "FCM is configured through google-services.json and expo-notifications.",
  },
} as const;
