import { AlertTriangle, CheckCircle2, RefreshCw, WifiOff } from "lucide-react-native";
import { StyleSheet, Text, View } from "react-native";

interface SyncBannerProps {
  offline: boolean;
  pendingOperations: number;
  conflicts: number;
  lastSyncAt: string | null;
}

export function SyncBanner({
  offline,
  pendingOperations,
  conflicts,
  lastSyncAt,
}: SyncBannerProps) {
  const hasWork = pendingOperations > 0 || conflicts > 0;
  const color = conflicts > 0 ? "#c2410c" : offline ? "#92400e" : hasWork ? "#0e7490" : "#047857";
  const Icon = conflicts > 0 ? AlertTriangle : offline ? WifiOff : hasWork ? RefreshCw : CheckCircle2;

  return (
    <View style={[styles.banner, { borderColor: color }]}>
      <Icon size={18} color={color} />
      <View style={styles.copy}>
        <Text style={[styles.title, { color }]}>
          {conflicts > 0
            ? `${conflicts} 个同步冲突`
            : offline
              ? "离线模式"
              : hasWork
                ? `${pendingOperations} 个操作待同步`
                : "已同步"}
        </Text>
        <Text style={styles.detail}>
          {offline
            ? "任务会先保存在本机，网络恢复后复用桌面同步机制上传。"
            : lastSyncAt
              ? `上次同步 ${formatTime(lastSyncAt)}`
              : "下拉刷新即可拉取服务器任务。"}
        </Text>
      </View>
    </View>
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
  banner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    borderWidth: 1,
    borderRadius: 8,
    backgroundColor: "#ffffff",
    padding: 12,
    marginHorizontal: 16,
    marginTop: 12,
  },
  copy: {
    flex: 1,
    gap: 2,
  },
  title: {
    fontSize: 14,
    fontWeight: "800",
  },
  detail: {
    color: "#475569",
    fontSize: 12,
    lineHeight: 18,
  },
});
