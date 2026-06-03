import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bell } from "lucide-react";

import { Button } from "../../../components/ui/button";
import { notifyFeedback } from "../../../components/ui/feedback-toast";
import { listAlertEvents } from "../../tasks/api";

export function AlertBell() {
  const alerts = useQuery({
    queryKey: ["observability", "alert-events", "bell"],
    queryFn: () => listAlertEvents({ limit: 20 }),
    refetchInterval: 30_000,
    retry: false,
  });
  const active = alerts.data?.items.filter((item) => item.status === "active") ?? [];
  const critical = active.some((item) => item.severity === "critical");

  useEffect(() => {
    if (!active.length) return;
    const latest = active[0];
    const key = `alert-toast:${latest.id}`;
    if (sessionStorage.getItem(key)) return;
    sessionStorage.setItem(key, "shown");
    notifyFeedback({
      tone: latest.severity === "critical" ? "error" : "warning",
      title: "告警已触发",
      description: latest.message,
    });
  }, [active]);

  return (
    <Button
      variant="ghost"
      className="relative w-8 px-0"
      aria-label={active.length ? `${active.length} 条活跃告警` : "告警"}
      title={active.length ? `${active.length} 条活跃告警` : "告警"}
      onClick={() => {
        window.location.href = "/observability/alerts";
      }}
    >
      <Bell className="h-4 w-4" />
      {active.length ? (
        <span
          className={`absolute right-1 top-1 h-2 w-2 rounded-full ${
            critical ? "bg-red-500" : "bg-amber-500"
          }`}
        />
      ) : null}
    </Button>
  );
}
