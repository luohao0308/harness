/**
 * ModelPicker — provider/model dropdown for the current Workspace session
 * (Req 6.6 / 6.10). Front-end state only; never writes back to the agent
 * configuration.
 *
 * Behaviour:
 *   - The trigger chip shows the currently selected `providerLabel /
 *     modelLabel` or `modelLabelFallback` when nothing is selected.
 *   - When `providers.length === 0` the chip is `disabled` and labelled
 *     "模型设置不可用 / Model settings unavailable" followed by
 *     `modelLabelFallback` (Req 6.10).
 *   - Clicking the chip toggles a dropdown (`absolute bottom-full right-0`)
 *     that groups entries by `providerId`. Each row is a `<button>`; clicking
 *     invokes `onModelChange(providerId, modelId)` and closes the dropdown.
 *   - Outside clicks and Escape close the dropdown via `useOutsideClick`
 *     (Req 6.1).
 *
 * Pure presentational: no writes to `useWorkspaceStore`; the parent owns
 * selection state.
 */

import type { JSX } from "react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Brain, ChevronDown } from "lucide-react";

import { useI18n } from "../../../lib/i18n";
import { cn } from "../../../lib/utils";
import { useOutsideClick } from "../hooks/useOutsideClick";

/**
 * Minimal provider+model option shape consumed by the picker. Derived from
 * `ModelSettings.providers` in `features/tasks/api.ts` without widening the
 * API surface.
 */
export type ModelOption = {
  providerId: string;
  providerLabel: string;
  modelId: string;
  modelLabel: string;
};

export type ModelPickerProps = {
  providers: ModelOption[];
  selectedProviderId: string | null;
  selectedModelId: string | null;
  onModelChange: (providerId: string, modelId: string) => void;
  /** Req 6.10 fallback when `getModelSettings()` is empty or failing. */
  modelLabelFallback: string;
  /**
   * v3 additive: increments (monotonically) when an external caller
   * (e.g. `/model` slash command) wants to pop the dropdown open. The
   * picker re-opens on every increment; leaving the prop undefined
   * preserves v2 behaviour.
   */
  openRequestSeq?: number;
};

type ProviderGroup = {
  providerId: string;
  providerLabel: string;
  models: ModelOption[];
};

function groupByProvider(options: ModelOption[]): ProviderGroup[] {
  const order: string[] = [];
  const groups = new Map<string, ProviderGroup>();

  for (const option of options) {
    const existing = groups.get(option.providerId);
    if (existing === undefined) {
      order.push(option.providerId);
      groups.set(option.providerId, {
        providerId: option.providerId,
        providerLabel: option.providerLabel,
        models: [option],
      });
    } else {
      existing.models.push(option);
    }
  }

  return order.map((providerId) => {
    const group = groups.get(providerId);
    if (group === undefined) {
      // Unreachable — every entry in `order` was inserted alongside its group.
      return { providerId, providerLabel: providerId, models: [] };
    }
    return group;
  });
}

export function ModelPicker({
  providers,
  selectedProviderId,
  selectedModelId,
  onModelChange,
  modelLabelFallback,
  openRequestSeq,
}: ModelPickerProps): JSX.Element {
  const { text } = useI18n();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useOutsideClick(containerRef, () => setOpen(false), open);

  // v3: respond to external "please open me" requests from the slash
  // command dispatcher. We guard with `providers.length > 0` so the menu
  // doesn't try to open in the disabled state.
  useEffect(() => {
    if (openRequestSeq === undefined) return;
    if (openRequestSeq <= 0) return;
    if (providers.length === 0) return;
    setOpen(true);
  }, [openRequestSeq, providers.length]);

  const selected = useMemo(
    () =>
      providers.find(
        (option) =>
          option.providerId === selectedProviderId &&
          option.modelId === selectedModelId,
      ) ?? null,
    [providers, selectedProviderId, selectedModelId],
  );

  const groups = useMemo(() => groupByProvider(providers), [providers]);
  const disabled = providers.length === 0;

  const buttonLabel = disabled
    ? `${text("模型设置不可用", "Model settings unavailable")} · ${modelLabelFallback}`
    : selected !== null
      ? `${selected.providerLabel} / ${selected.modelLabel}`
      : modelLabelFallback;

  const ariaLabel = text("切换模型", "Switch model");

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => {
          if (disabled) return;
          setOpen((prev) => !prev);
        }}
        disabled={disabled}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={buttonLabel}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-700 transition-colors hover:bg-slate-50",
          "max-w-[220px] truncate",
          disabled && "cursor-not-allowed text-slate-400 hover:bg-white",
        )}
      >
        <Brain aria-hidden="true" className="h-3 w-3 shrink-0" />
        <span className="truncate">{buttonLabel}</span>
        <ChevronDown aria-hidden="true" className="h-3 w-3 shrink-0" />
      </button>

      {open && disabled === false && (
        <div
          role="listbox"
          aria-label={ariaLabel}
          className="absolute bottom-full right-0 z-30 mb-2 w-[280px] rounded-2xl border border-slate-200 bg-white p-1 shadow-lg"
        >
          {groups.map((group) => (
            <div key={group.providerId} className="px-1 py-1">
              <div className="px-2 py-1 text-[11px] font-medium uppercase tracking-wide text-slate-400">
                {group.providerLabel}
              </div>
              <div className="flex flex-col">
                {group.models.map((model) => {
                  const isSelected =
                    model.providerId === selectedProviderId &&
                    model.modelId === selectedModelId;
                  return (
                    <button
                      key={`${model.providerId}:${model.modelId}`}
                      type="button"
                      role="option"
                      aria-selected={isSelected}
                      onClick={() => {
                        onModelChange(model.providerId, model.modelId);
                        setOpen(false);
                      }}
                      className={cn(
                        "flex items-center justify-between rounded-xl px-2 py-1.5 text-left text-xs text-slate-700 transition-colors hover:bg-slate-50",
                        isSelected && "bg-slate-100 font-medium text-slate-900",
                      )}
                    >
                      <span className="truncate">{model.modelLabel}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
