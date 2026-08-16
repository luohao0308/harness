import { StyleSheet, Text, View } from "react-native";

import { taskStatusLabel } from "../sync/types";

interface StatusPillProps {
  status: string;
  conflict?: boolean;
  dirty?: boolean;
}

export function StatusPill({ status, conflict = false, dirty = false }: StatusPillProps) {
  const tone = conflict ? "conflict" : dirty ? "dirty" : statusTone(status);
  return (
    <View style={[styles.pill, styles[tone]]}>
      <Text style={[styles.label, styles[`${tone}Label`]]}>
        {conflict ? "冲突" : dirty ? "待同步" : taskStatusLabel(status)}
      </Text>
    </View>
  );
}

function statusTone(status: string): "active" | "done" | "failed" | "neutral" {
  if (["RUNNING", "PLANNING", "PLANNED", "WAITING_SUBAGENTS", "WAITING_APPROVAL", "in_progress"].includes(status)) {
    return "active";
  }
  if (["COMPLETED", "completed"].includes(status)) return "done";
  if (["FAILED", "CANCELLED"].includes(status)) return "failed";
  return "neutral";
}

const styles = StyleSheet.create({
  pill: {
    minHeight: 28,
    borderRadius: 6,
    paddingHorizontal: 10,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
  },
  label: {
    fontSize: 12,
    fontWeight: "700",
  },
  active: {
    backgroundColor: "#ecfeff",
    borderColor: "#67e8f9",
  },
  activeLabel: {
    color: "#0e7490",
  },
  done: {
    backgroundColor: "#ecfdf5",
    borderColor: "#6ee7b7",
  },
  doneLabel: {
    color: "#047857",
  },
  failed: {
    backgroundColor: "#fef2f2",
    borderColor: "#fecaca",
  },
  failedLabel: {
    color: "#b91c1c",
  },
  dirty: {
    backgroundColor: "#fffbeb",
    borderColor: "#fcd34d",
  },
  dirtyLabel: {
    color: "#92400e",
  },
  conflict: {
    backgroundColor: "#fff7ed",
    borderColor: "#fdba74",
  },
  conflictLabel: {
    color: "#c2410c",
  },
  neutral: {
    backgroundColor: "#f8fafc",
    borderColor: "#cbd5e1",
  },
  neutralLabel: {
    color: "#475569",
  },
});
