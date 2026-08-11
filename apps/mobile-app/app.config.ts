import type { ExpoConfig } from "expo/config";

const bundleIdentifier = process.env.EXPO_PUBLIC_IOS_BUNDLE_ID ?? "com.harness.mobile";
const androidPackage = process.env.EXPO_PUBLIC_ANDROID_PACKAGE ?? "com.harness.mobile";

const config: ExpoConfig = {
  name: "Harness",
  slug: "harness-mobile",
  owner: process.env.EXPO_PUBLIC_EAS_OWNER,
  version: "0.1.0",
  orientation: "portrait",
  userInterfaceStyle: "automatic",
  scheme: "agentharness",
  platforms: ["ios", "android"],
  ios: {
    bundleIdentifier,
    supportsTablet: true,
    associatedDomains: ["applinks:harness.local"],
    infoPlist: {
      NSFaceIDUsageDescription: "Harness uses device security to protect offline task data.",
      UIBackgroundModes: ["fetch", "remote-notification"],
    },
    entitlements: {
      "aps-environment": process.env.EXPO_PUBLIC_APNS_ENVIRONMENT ?? "development",
    },
  },
  android: {
    package: androidPackage,
    adaptiveIcon: {
      foregroundImage: "./assets/adaptive-icon.png",
      backgroundColor: "#0f766e",
    },
    permissions: [
      "android.permission.POST_NOTIFICATIONS",
      "android.permission.RECEIVE_BOOT_COMPLETED",
      "android.permission.FOREGROUND_SERVICE",
    ],
  },
  plugins: [
    "expo-secure-store",
    "expo-sqlite",
    [
      "expo-notifications",
      {
        icon: "./assets/notification-icon.png",
        color: "#0f766e",
        defaultChannel: "harness-runs",
      },
    ],
    [
      "expo-widgets",
      {
        ios: {
          widgetsFolder: "ios/Widgets",
        },
      },
    ],
  ],
  extra: {
    apiBaseUrl: process.env.EXPO_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000",
    eas: {
      projectId: process.env.EXPO_PUBLIC_EAS_PROJECT_ID,
    },
  },
};

export default config;
