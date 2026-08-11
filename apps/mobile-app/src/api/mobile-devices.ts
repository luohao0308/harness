import * as Application from "expo-application";
import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import { MobileApiClient } from "../sync/api-client";

type PlatformName = "ios" | "android";

export interface RegisterDeviceResult {
  registered: boolean;
  reason?: string;
  token?: string;
}

export async function registerForPushNotifications(
  api = new MobileApiClient(),
): Promise<RegisterDeviceResult> {
  if (!Device.isDevice) {
    return { registered: false, reason: "Push notifications require a physical device." };
  }

  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("harness-runs", {
      name: "Harness Run Updates",
      importance: Notifications.AndroidImportance.DEFAULT,
      vibrationPattern: [0, 200, 120, 200],
      lightColor: "#0f766e",
    });
  }

  const permission = await Notifications.getPermissionsAsync();
  const finalPermission = permission.granted
    ? permission
    : await Notifications.requestPermissionsAsync();
  if (!finalPermission.granted) {
    return { registered: false, reason: "Notification permission was not granted." };
  }

  const projectId =
    Constants.expoConfig?.extra?.eas?.projectId ??
    Constants.easConfig?.projectId;
  if (!projectId) {
    return { registered: false, reason: "Missing EAS project id for Expo push token." };
  }

  const token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
  await api.request("/api/mobile/devices", {
    method: "POST",
    body: JSON.stringify({
      platform: Platform.OS as PlatformName,
      push_token: token,
      device_name: Device.deviceName ?? Device.modelName ?? Platform.OS,
      app_version: Application.nativeApplicationVersion ?? Constants.expoConfig?.version,
      notifications_enabled: true,
      preferences_json: {
        run_terminal: true,
        conflict: true,
        approval_required: true,
      },
    }),
  });

  return { registered: true, token };
}
