import { Plus, Send } from "lucide-react-native";
import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

interface NewTaskSheetProps {
  onCreate: (input: { title: string; goal: string }) => Promise<void>;
}

export function NewTaskSheet({ onCreate }: NewTaskSheetProps) {
  const [expanded, setExpanded] = useState(false);
  const [title, setTitle] = useState("");
  const [goal, setGoal] = useState("");
  const [saving, setSaving] = useState(false);

  const canSubmit = title.trim().length > 0 && goal.trim().length > 0 && !saving;

  async function submit() {
    if (!canSubmit) return;
    setSaving(true);
    await onCreate({ title, goal });
    setTitle("");
    setGoal("");
    setExpanded(false);
    setSaving(false);
  }

  if (!expanded) {
    return (
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="新建离线任务"
        onPress={() => setExpanded(true)}
        style={({ pressed }) => [styles.fab, pressed && styles.fabPressed]}
      >
        <Plus size={20} color="#ffffff" />
        <Text style={styles.fabText}>新建任务</Text>
      </Pressable>
    );
  }

  return (
    <View style={styles.sheet}>
      <Text style={styles.sheetTitle}>新建任务</Text>
      <TextInput
        accessibilityLabel="任务标题"
        value={title}
        onChangeText={setTitle}
        placeholder="任务标题"
        placeholderTextColor="#94a3b8"
        style={styles.input}
      />
      <TextInput
        accessibilityLabel="任务目标"
        value={goal}
        onChangeText={setGoal}
        placeholder="写下目标，离线时也会先保存"
        placeholderTextColor="#94a3b8"
        multiline
        style={[styles.input, styles.textarea]}
      />
      <View style={styles.actions}>
        <Pressable
          accessibilityRole="button"
          onPress={() => setExpanded(false)}
          style={styles.cancel}
        >
          <Text style={styles.cancelText}>取消</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          disabled={!canSubmit}
          onPress={submit}
          style={({ pressed }) => [
            styles.submit,
            !canSubmit && styles.submitDisabled,
            pressed && canSubmit && styles.submitPressed,
          ]}
        >
          <Send size={16} color={canSubmit ? "#ffffff" : "#94a3b8"} />
          <Text style={[styles.submitText, !canSubmit && styles.submitTextDisabled]}>
            {saving ? "保存中" : "保存"}
          </Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  fab: {
    position: "absolute",
    right: 18,
    bottom: 22,
    minHeight: 52,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    borderRadius: 8,
    backgroundColor: "#0f766e",
    paddingHorizontal: 18,
    shadowColor: "#0f172a",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.18,
    shadowRadius: 16,
    elevation: 6,
  },
  fabPressed: {
    backgroundColor: "#115e59",
  },
  fabText: {
    color: "#ffffff",
    fontWeight: "800",
    fontSize: 15,
  },
  sheet: {
    position: "absolute",
    left: 12,
    right: 12,
    bottom: 12,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#cbd5e1",
    backgroundColor: "#ffffff",
    padding: 14,
    gap: 10,
    shadowColor: "#0f172a",
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.18,
    shadowRadius: 18,
    elevation: 8,
  },
  sheetTitle: {
    color: "#0f172a",
    fontSize: 16,
    fontWeight: "900",
  },
  input: {
    minHeight: 46,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#cbd5e1",
    paddingHorizontal: 12,
    color: "#0f172a",
    fontSize: 15,
    backgroundColor: "#f8fafc",
  },
  textarea: {
    minHeight: 92,
    paddingTop: 12,
    textAlignVertical: "top",
  },
  actions: {
    minHeight: 48,
    flexDirection: "row",
    justifyContent: "flex-end",
    alignItems: "center",
    gap: 10,
  },
  cancel: {
    minHeight: 44,
    justifyContent: "center",
    paddingHorizontal: 16,
  },
  cancelText: {
    color: "#475569",
    fontWeight: "700",
  },
  submit: {
    minHeight: 44,
    minWidth: 96,
    borderRadius: 8,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    backgroundColor: "#0f766e",
  },
  submitPressed: {
    backgroundColor: "#115e59",
  },
  submitDisabled: {
    backgroundColor: "#e2e8f0",
  },
  submitText: {
    color: "#ffffff",
    fontWeight: "900",
  },
  submitTextDisabled: {
    color: "#94a3b8",
  },
});
