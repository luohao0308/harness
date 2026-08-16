import { AlertTriangle, Check, X } from "lucide-react";
import { useState } from "react";

import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { ConfigDialog } from "../../components/ui/config-dialog";

interface ConflictInfo {
  entity_id: string;
  entity_type: string;
  server_version: Record<string, unknown>;
  client_version: Record<string, unknown>;
}

interface ConflictResolutionDialogProps {
  open: boolean;
  conflicts: ConflictInfo[];
  onClose: () => void;
  onResolve: (resolutions: ConflictResolution[]) => void;
}

export interface ConflictResolution {
  entity_id: string;
  entity_type: string;
  resolution: "server" | "client";
  merged_data?: Record<string, unknown>;
}

export function ConflictResolutionDialog({
  open,
  conflicts,
  onClose,
  onResolve,
}: ConflictResolutionDialogProps) {
  const [resolutions, setResolutions] = useState<Map<string, "server" | "client">>(
    new Map()
  );

  const handleResolutionChange = (entityId: string, resolution: "server" | "client") => {
    setResolutions((prev) => {
      const next = new Map(prev);
      next.set(entityId, resolution);
      return next;
    });
  };

  const handleResolveAll = () => {
    const resolutionList: ConflictResolution[] = conflicts.map((conflict) => ({
      entity_id: conflict.entity_id,
      entity_type: conflict.entity_type,
      resolution: resolutions.get(conflict.entity_id) ?? "server",
    }));

    onResolve(resolutionList);
    setResolutions(new Map());
  };

  const allResolved = conflicts.every((conflict) =>
    resolutions.has(conflict.entity_id)
  );

  return (
    <ConfigDialog
      open={open}
      title="Resolve Sync Conflicts"
      description="Choose which version to keep for each conflicting entity. Server version is the current state on the server, client version is your local changes."
      onClose={onClose}
      className="max-w-4xl"
    >
      <div className="grid gap-4 text-xs">
        <div className="flex items-center gap-2 rounded-md border border-amber-100 bg-amber-50 px-3 py-2 text-amber-800">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>
            {conflicts.length} conflict{conflicts.length !== 1 ? "s" : ""} detected.
            Review each conflict and choose which version to keep.
          </span>
        </div>

        <div className="max-h-[60vh] space-y-3 overflow-auto">
          {conflicts.map((conflict) => (
            <ConflictCard
              key={conflict.entity_id}
              conflict={conflict}
              resolution={resolutions.get(conflict.entity_id)}
              onResolutionChange={(resolution) =>
                handleResolutionChange(conflict.entity_id, resolution)
              }
            />
          ))}
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-200 pt-3">
          <Button onClick={onClose} variant="ghost">
            <X className="h-3.5 w-3.5" /> Cancel
          </Button>
          <Button onClick={handleResolveAll} disabled={!allResolved}>
            <Check className="h-3.5 w-3.5" /> Resolve All ({resolutions.size}/
            {conflicts.length})
          </Button>
        </div>
      </div>
    </ConfigDialog>
  );
}

interface ConflictCardProps {
  conflict: ConflictInfo;
  resolution?: "server" | "client";
  onResolutionChange: (resolution: "server" | "client") => void;
}

function ConflictCard({
  conflict,
  resolution,
  onResolutionChange,
}: ConflictCardProps) {
  const diffFields = findDiffFields(
    conflict.server_version,
    conflict.client_version
  );

  return (
    <div className="rounded-md border border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2">
        <div>
          <div className="font-semibold text-slate-900">
            {conflict.entity_type} · {conflict.entity_id.slice(0, 8)}
          </div>
          <div className="mt-0.5 text-[11px] text-slate-500">
            {diffFields.length} field{diffFields.length !== 1 ? "s" : ""} differ
          </div>
        </div>
        <Badge tone={resolution ? "success" : "warning"}>
          {resolution ? `Resolved: ${resolution}` : "Needs resolution"}
        </Badge>
      </div>

      <div className="grid gap-3 p-3 lg:grid-cols-2">
        <VersionPanel
          title="Server Version"
          version={conflict.server_version}
          diffFields={diffFields}
          selected={resolution === "server"}
          onSelect={() => onResolutionChange("server")}
        />
        <VersionPanel
          title="Client Version"
          version={conflict.client_version}
          diffFields={diffFields}
          selected={resolution === "client"}
          onSelect={() => onResolutionChange("client")}
        />
      </div>
    </div>
  );
}

interface VersionPanelProps {
  title: string;
  version: Record<string, unknown>;
  diffFields: string[];
  selected: boolean;
  onSelect: () => void;
}

function VersionPanel({
  title,
  version,
  diffFields,
  selected,
  onSelect,
}: VersionPanelProps) {
  return (
    <div
      className={[
        "rounded-md border p-3 transition cursor-pointer",
        selected
          ? "border-emerald-300 bg-emerald-50"
          : "border-slate-200 bg-slate-50 hover:border-slate-300",
      ].join(" ")}
      onClick={onSelect}
    >
      <div className="mb-2 flex items-center justify-between">
        <span className="font-medium text-slate-700">{title}</span>
        {selected ? (
          <Check className="h-4 w-4 text-emerald-600" />
        ) : (
          <div className="h-4 w-4 rounded border-2 border-slate-300" />
        )}
      </div>
      <div className="space-y-1 text-[11px]">
        {Object.entries(version).map(([key, value]) => (
          <div
            key={key}
            className={
              diffFields.includes(key)
                ? "rounded bg-amber-100 px-1 py-0.5 font-medium text-amber-900"
                : "text-slate-600"
            }
          >
            <span className="font-mono">{key}:</span>{" "}
            <span>{formatValue(value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function findDiffFields(
  server: Record<string, unknown>,
  client: Record<string, unknown>
): string[] {
  const allKeys = new Set([...Object.keys(server), ...Object.keys(client)]);
  const diffFields: string[] = [];

  for (const key of allKeys) {
    if (JSON.stringify(server[key]) !== JSON.stringify(client[key])) {
      diffFields.push(key);
    }
  }

  return diffFields;
}

function formatValue(value: unknown): string {
  if (value === null) return "null";
  if (value === undefined) return "undefined";
  if (typeof value === "string") return `"${value}"`;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
