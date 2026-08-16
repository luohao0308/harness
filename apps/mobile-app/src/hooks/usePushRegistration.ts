import { useEffect, useState } from "react";

import { registerForPushNotifications } from "../api/mobile-devices";

export function usePushRegistration() {
  const [status, setStatus] = useState<"idle" | "registered" | "skipped" | "failed">("idle");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    registerForPushNotifications()
      .then((result) => {
        if (!mounted) return;
        setStatus(result.registered ? "registered" : "skipped");
        setMessage(result.reason ?? null);
      })
      .catch((error: unknown) => {
        if (!mounted) return;
        setStatus("failed");
        setMessage(error instanceof Error ? error.message : String(error));
      });
    return () => {
      mounted = false;
    };
  }, []);

  return { status, message };
}
