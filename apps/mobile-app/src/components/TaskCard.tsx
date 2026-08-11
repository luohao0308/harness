import { CheckCircle2, ChevronRight } from "lucide-react-native";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { TaskWithSyncMetadata } from "../sync/types";
import { isTerminalStatus } from "../sync/types";
import { StatusPill } from "./StatusPill";

interface TaskCardProps {
  task: TaskWithSyncMetadata;
  onComplete: (task: TaskWithSyncMetadata) => void;
}

export function TaskCard({ task, onComplete }: TaskCardProps) {
  const completeDisabled = isTerminalStatus(task.status);
  return (
    <Pressable style={({ pressed }) => [styles.card, pressed && styles.cardPressed]}>
      <View style={styles.header}>
        <View style={styles.heading}>
          <Text style={styles.title} numberOfLines={2}>
            {task.title || "未命名任务"}
          </Text>
          <Text style={styles.model} numberOfLines={1}>
            {task.model_provider} · {task.model_name}
          </Text>
        </View>
        <StatusPill
          status={task.status}
          dirty={task.has_local_changes}
          conflict={task.conflict_detected}
        />
      </View>
      <Text style={styles.goal} numberOfLines={3}>
        {task.goal}
      </Text>
      <View style={styles.footer}>
        <Text style={styles.updated}>{formatTime(task.updated_at)}</Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`完成任务 ${task.title}`}
          disabled={completeDisabled}
          onPress={() => onComplete(task)}
          style={({ pressed }) => [
            styles.action,
            completeDisabled && styles.actionDisabled,
            pressed && !completeDisabled && styles.actionPressed,
          ]}
        >
          <CheckCircle2 size={16} color={completeDisabled ? "#94a3b8" : "#047857"} />
          <Text style={[styles.actionText, completeDisabled && styles.actionTextDisabled]}>
            完成
          </Text>
        </Pressable>
        <ChevronRight size={18} color="#94a3b8" />
      </View>
    </Pressable>
  );
}

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#ffffff",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#e2e8f0",
    padding: 14,
    gap: 10,
  },
  cardPressed: {
    backgroundColor: "#f8fafc",
  },
  header: {
    flexDirection: "row",
    gap: 12,
    alignItems: "flex-start",
  },
  heading: {
    flex: 1,
    gap: 4,
  },
  title: {
    color: "#0f172a",
    fontSize: 17,
    lineHeight: 23,
    fontWeight: "800",
  },
  model: {
    color: "#64748b",
    fontSize: 12,
  },
  goal: {
    color: "#334155",
    fontSize: 14,
    lineHeight: 20,
  },
  footer: {
    minHeight: 44,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  updated: {
    flex: 1,
    color: "#64748b",
    fontSize: 12,
  },
  action: {
    minHeight: 40,
    minWidth: 86,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#a7f3d0",
    backgroundColor: "#ecfdf5",
  },
  actionPressed: {
    backgroundColor: "#d1fae5",
  },
  actionDisabled: {
    borderColor: "#e2e8f0",
    backgroundColor: "#f8fafc",
  },
  actionText: {
    color: "#047857",
    fontWeight: "800",
    fontSize: 13,
  },
  actionTextDisabled: {
    color: "#94a3b8",
  },
});
