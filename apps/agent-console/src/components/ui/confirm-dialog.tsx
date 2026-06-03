import { useCallback, useEffect, useRef, useState } from "react";

import { useI18n } from "../../lib/i18n";
import { Button } from "./button";
import { ConfigDialog } from "./config-dialog";

type ConfirmOptions = {
  title: string;
  description: string;
  confirmText?: string;
  cancelText?: string;
  variant?: "primary" | "danger";
};

type PendingConfirm = ConfirmOptions & {
  resolve: (confirmed: boolean) => void;
};

export function useConfirmDialog() {
  const { text } = useI18n();
  const pendingRef = useRef<PendingConfirm | null>(null);
  const [pending, setPending] = useState<PendingConfirm | null>(null);

  const closeDialog = useCallback((confirmed: boolean) => {
    const active = pendingRef.current;
    pendingRef.current = null;
    setPending(null);
    active?.resolve(confirmed);
  }, []);

  useEffect(() => {
    return () => {
      pendingRef.current?.resolve(false);
      pendingRef.current = null;
    };
  }, []);

  const confirm = useCallback(
    (options: ConfirmOptions) =>
      new Promise<boolean>((resolve) => {
        const request = { ...options, resolve };
        pendingRef.current = request;
        setPending(request);
      }),
    [],
  );

  const confirmDialog = pending ? (
    <ConfigDialog
      open
      title={pending.title}
      description={pending.description}
      onClose={() => closeDialog(false)}
      className="max-w-md"
    >
      <div className="flex items-center justify-end gap-2">
        <Button type="button" variant="ghost" onClick={() => closeDialog(false)}>
          {pending.cancelText ?? text("取消", "Cancel")}
        </Button>
        <Button
          type="button"
          variant={pending.variant ?? "primary"}
          onClick={() => closeDialog(true)}
        >
          {pending.confirmText ?? text("确认", "Confirm")}
        </Button>
      </div>
    </ConfigDialog>
  ) : null;

  return { confirm, confirmDialog };
}
