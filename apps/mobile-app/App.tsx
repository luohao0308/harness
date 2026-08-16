import { RefreshControl, SafeAreaView, StyleSheet, Text, View } from "react-native";
import { FlashList } from "@shopify/flash-list";
import { StatusBar } from "expo-status-bar";

import { ConnectionSheet } from "./src/components/ConnectionSheet";
import { NewTaskSheet } from "./src/components/NewTaskSheet";
import { SyncBanner } from "./src/components/SyncBanner";
import { TaskCard } from "./src/components/TaskCard";
import { useMobileTasks } from "./src/hooks/useMobileTasks";
import { usePushRegistration } from "./src/hooks/usePushRegistration";

export default function App() {
  const {
    tasks,
    loading,
    refreshing,
    refresh,
    createTask,
    markCompleted,
    error,
    syncState,
  } = useMobileTasks();
  const pushRegistration = usePushRegistration();

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar style="dark" />
      <View style={styles.container}>
        <View style={styles.header}>
          <View style={styles.headerCopy}>
            <Text style={styles.eyebrow}>Model + Harness = Agent</Text>
            <Text style={styles.title}>任务</Text>
          </View>
          <ConnectionSheet onSaved={refresh} />
        </View>
        <SyncBanner
          offline={syncState.offline}
          pendingOperations={syncState.pendingOperations}
          conflicts={syncState.conflicts}
          lastSyncAt={syncState.lastSyncAt}
        />
        {error ? (
          <View style={styles.errorBox}>
            <Text style={styles.errorTitle}>同步失败</Text>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        ) : null}
        {pushRegistration.status === "failed" || pushRegistration.status === "skipped" ? (
          <View style={styles.noticeBox}>
            <Text style={styles.noticeTitle}>推送未启用</Text>
            <Text style={styles.noticeText}>
              {pushRegistration.message ?? "稍后可在系统设置中开启通知。"}
            </Text>
          </View>
        ) : null}
        <FlashList
          data={tasks}
          keyExtractor={(task) => task.id}
          contentContainerStyle={styles.listContent}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
          ListEmptyComponent={
            <View style={styles.empty}>
              <Text style={styles.emptyTitle}>{loading ? "加载任务中" : "暂无任务"}</Text>
              <Text style={styles.emptyText}>
                {loading ? "正在读取本机缓存并同步服务器。" : "新建一个任务，离线时也会进入待同步队列。"}
              </Text>
            </View>
          }
          renderItem={({ item }) => <TaskCard task={item} onComplete={markCompleted} />}
          ItemSeparatorComponent={() => <View style={styles.separator} />}
        />
        <NewTaskSheet onCreate={createTask} />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: "#f8fafc",
  },
  container: {
    flex: 1,
    backgroundColor: "#f8fafc",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingHorizontal: 16,
    paddingTop: 14,
    paddingBottom: 4,
  },
  headerCopy: {
    flex: 1,
  },
  eyebrow: {
    color: "#0f766e",
    fontSize: 12,
    fontWeight: "800",
  },
  title: {
    color: "#0f172a",
    fontSize: 32,
    lineHeight: 38,
    fontWeight: "900",
  },
  errorBox: {
    marginHorizontal: 16,
    marginTop: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#fecaca",
    backgroundColor: "#fef2f2",
    padding: 12,
    gap: 4,
  },
  errorTitle: {
    color: "#b91c1c",
    fontWeight: "900",
  },
  errorText: {
    color: "#7f1d1d",
    fontSize: 12,
    lineHeight: 18,
  },
  noticeBox: {
    marginHorizontal: 16,
    marginTop: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#bae6fd",
    backgroundColor: "#f0f9ff",
    padding: 12,
    gap: 4,
  },
  noticeTitle: {
    color: "#0369a1",
    fontWeight: "900",
  },
  noticeText: {
    color: "#075985",
    fontSize: 12,
    lineHeight: 18,
  },
  listContent: {
    paddingHorizontal: 16,
    paddingTop: 14,
    paddingBottom: 110,
  },
  separator: {
    height: 10,
  },
  empty: {
    marginTop: 70,
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 28,
  },
  emptyTitle: {
    color: "#0f172a",
    fontSize: 18,
    fontWeight: "900",
  },
  emptyText: {
    color: "#64748b",
    textAlign: "center",
    fontSize: 14,
    lineHeight: 20,
  },
});
