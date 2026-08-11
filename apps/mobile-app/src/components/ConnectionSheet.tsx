import { Settings, Wifi } from "lucide-react-native";
import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import {
  getMobileConnectionSettings,
  setMobileApiBaseUrl,
  setMobileAuthToken,
} from "../sync/api-client";

interface ConnectionSheetProps {
  onSaved: () => Promise<void>;
}

export function ConnectionSheet({ onSaved }: ConnectionSheetProps) {
  const [open, setOpen] = useState(false);
  const [apiBaseUrl, setApiBaseUrl] = useState("");
  const [authToken, setAuthToken] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    getMobileConnectionSettings().then((settings) => {
      setApiBaseUrl(settings.apiBaseUrl);
      setAuthToken(settings.authToken);
    });
  }, [open]);

  async function save() {
    setSaving(true);
    await Promise.all([
      setMobileApiBaseUrl(apiBaseUrl),
      setMobileAuthToken(authToken),
    ]);
    await onSaved();
    setSaving(false);
    setOpen(false);
  }

  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="配置连接"
        onPress={() => setOpen(true)}
        style={({ pressed }) => [styles.iconButton, pressed && styles.iconButtonPressed]}
      >
        <Settings size={20} color="#0f172a" />
      </Pressable>
      {open ? (
        <View style={styles.sheet}>
          <View style={styles.titleRow}>
            <Wifi size={18} color="#0f766e" />
            <Text style={styles.title}>连接</Text>
          </View>
          <TextInput
            accessibilityLabel="API 地址"
            value={apiBaseUrl}
            onChangeText={setApiBaseUrl}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            placeholder="https://harness.example.com"
            placeholderTextColor="#94a3b8"
            style={styles.input}
          />
          <TextInput
            accessibilityLabel="Bearer token"
            value={authToken}
            onChangeText={setAuthToken}
            autoCapitalize="none"
            autoCorrect={false}
            secureTextEntry
            placeholder="Bearer token"
            placeholderTextColor="#94a3b8"
            style={styles.input}
          />
          <View style={styles.actions}>
            <Pressable
              accessibilityRole="button"
              onPress={() => setOpen(false)}
              style={styles.secondary}
            >
              <Text style={styles.secondaryText}>取消</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              disabled={saving || apiBaseUrl.trim().length === 0}
              onPress={save}
              style={({ pressed }) => [
                styles.primary,
                pressed && styles.primaryPressed,
                (saving || apiBaseUrl.trim().length === 0) && styles.primaryDisabled,
              ]}
            >
              <Text style={styles.primaryText}>{saving ? "保存中" : "保存并刷新"}</Text>
            </Pressable>
          </View>
        </View>
      ) : null}
    </>
  );
}

const styles = StyleSheet.create({
  iconButton: {
    width: 44,
    height: 44,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#cbd5e1",
    backgroundColor: "#ffffff",
    alignItems: "center",
    justifyContent: "center",
  },
  iconButtonPressed: {
    backgroundColor: "#f1f5f9",
  },
  sheet: {
    position: "absolute",
    top: 76,
    left: 12,
    right: 12,
    zIndex: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#cbd5e1",
    backgroundColor: "#ffffff",
    padding: 14,
    gap: 10,
    shadowColor: "#0f172a",
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.16,
    shadowRadius: 18,
    elevation: 8,
  },
  titleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  title: {
    color: "#0f172a",
    fontSize: 16,
    fontWeight: "900",
  },
  input: {
    minHeight: 46,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#cbd5e1",
    backgroundColor: "#f8fafc",
    paddingHorizontal: 12,
    color: "#0f172a",
    fontSize: 14,
  },
  actions: {
    minHeight: 48,
    flexDirection: "row",
    justifyContent: "flex-end",
    gap: 10,
  },
  secondary: {
    minHeight: 44,
    justifyContent: "center",
    paddingHorizontal: 14,
  },
  secondaryText: {
    color: "#475569",
    fontWeight: "700",
  },
  primary: {
    minHeight: 44,
    minWidth: 118,
    borderRadius: 8,
    backgroundColor: "#0f766e",
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 14,
  },
  primaryPressed: {
    backgroundColor: "#115e59",
  },
  primaryDisabled: {
    backgroundColor: "#cbd5e1",
  },
  primaryText: {
    color: "#ffffff",
    fontWeight: "900",
  },
});
