import Constants from "expo-constants";
import * as SecureStore from "expo-secure-store";

import type {
  DesktopSyncOperation,
  DesktopSyncOperationsResponse,
  DesktopSyncResponse,
} from "./types";

export const AUTH_TOKEN_KEY = "harness.mobile.auth_token";
export const API_BASE_URL_KEY = "harness.mobile.api_base_url";

type ExtraConfig = {
  apiBaseUrl?: string;
};

function configuredApiBaseUrl() {
  const extra = (Constants.expoConfig?.extra ?? {}) as ExtraConfig;
  return extra.apiBaseUrl ?? "http://127.0.0.1:8000";
}

function stripTrailingSlash(value: string) {
  return value.replace(/\/$/, "");
}

export async function getMobileApiBaseUrl() {
  const stored = await SecureStore.getItemAsync(API_BASE_URL_KEY);
  return stripTrailingSlash(stored?.trim() || configuredApiBaseUrl());
}

export async function setMobileApiBaseUrl(value: string) {
  await SecureStore.setItemAsync(API_BASE_URL_KEY, stripTrailingSlash(value.trim()));
}

export async function getMobileAuthToken() {
  return (await SecureStore.getItemAsync(AUTH_TOKEN_KEY)) ?? "";
}

export async function setMobileAuthToken(value: string) {
  await SecureStore.setItemAsync(AUTH_TOKEN_KEY, value.trim());
}

export async function getMobileConnectionSettings() {
  const [apiBaseUrl, authToken] = await Promise.all([
    getMobileApiBaseUrl(),
    getMobileAuthToken(),
  ]);
  return { apiBaseUrl, authToken };
}

export class MobileApiClient {
  constructor(
    private readonly getBaseUrl = getMobileApiBaseUrl,
    private readonly getAuthToken = getMobileAuthToken,
  ) {}

  async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const baseUrl = await this.getBaseUrl();
    const token = await this.getAuthToken();
    const response = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init.headers,
      },
    });
    if (!response.ok) {
      throw new Error(`API request failed: ${response.status} ${response.statusText}`);
    }
    return (await response.json()) as T;
  }

  async fetchDesktopSync(lastSyncTimestamp: string | null): Promise<DesktopSyncResponse> {
    const params = new URLSearchParams();
    if (lastSyncTimestamp) params.set("since", lastSyncTimestamp);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return this.request<DesktopSyncResponse>(`/api/desktop/sync${suffix}`);
  }

  async pushDesktopOperations(operations: DesktopSyncOperation[]) {
    return this.request<DesktopSyncOperationsResponse>("/api/desktop/sync/operations", {
      method: "POST",
      body: JSON.stringify({ operations }),
    });
  }
}
