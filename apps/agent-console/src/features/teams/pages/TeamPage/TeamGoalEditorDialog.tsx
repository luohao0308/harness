import { Button } from "../../../../components/ui/button";
import { ConfigDialog } from "../../../../components/ui/config-dialog";
import { Input } from "../../../../components/ui/input";

import type { TextFn } from "./types";

export function TeamGoalEditorDialog({
  open,
  objective,
  text,
  onClose,
  onObjectiveChange,
  onSave,
}: {
  open: boolean;
  objective: string;
  text: TextFn;
  onClose: () => void;
  onObjectiveChange: (value: string) => void;
  onSave: () => void;
}) {
  const canSave = objective.trim().length > 0;
  return (
    <ConfigDialog
      open={open}
      title={text("编辑团队目标", "Edit team goal")}
      description={text("更新当前团队目标的目标描述。", "Update the current team goal objective.")}
      onClose={onClose}
      className="max-w-lg"
    >
      <div className="space-y-4">
        <label className="flex flex-col gap-1.5 text-xs font-medium text-slate-600">
          {text("目标", "Objective")}
          <Input value={objective} onChange={(event) => onObjectiveChange(event.target.value)} />
        </label>
      </div>
      <div className="mt-5 flex justify-end gap-2 border-t border-slate-200 pt-5">
        <Button variant="secondary" onClick={onClose}>
          {text("取消", "Cancel")}
        </Button>
        <Button onClick={onSave} disabled={!canSave}>{text("保存", "Save")}</Button>
      </div>
    </ConfigDialog>
  );
}
