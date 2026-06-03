/**
 * ModelPicker — provider/model dropdown for the current Workspace session
 * (Req 6.6 / 6.10). Front-end state only; never writes back to the agent
 * configuration.
 *
 * Behaviour:
 *   - Renders through the shared `MenuSelect` component so the trigger and
 *     list match other workspace selectors.
 *   - The selected value shows the current model label with the provider as
 *     small supporting text, or `modelLabelFallback` when nothing is selected.
 *   - When `providers.length === 0` the control is disabled and shows
 *     "模型设置不可用 / Model settings unavailable" with the fallback label
 *     as supporting text (Req 6.10).
 *   - External open requests from the slash-command flow are still honored
 *     through `openRequestSeq` (Req 6.1).
 *
 * Pure presentational: no writes to `useWorkspaceStore`; the parent owns
 * selection state.
 */

import type { JSX } from "react";
import { useMemo } from "react";

import { Brain } from "lucide-react";

import { MenuSelect } from "../../../components/ui/menu-select";
import { useI18n } from "../../../lib/i18n";

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

function modelKey(option: ModelOption): string {
  return JSON.stringify([option.providerId, option.modelId]);
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

  const selected = useMemo(
    () =>
      providers.find(
        (option) =>
          option.providerId === selectedProviderId &&
          option.modelId === selectedModelId,
      ) ?? null,
    [providers, selectedProviderId, selectedModelId],
  );
  const disabled = providers.length === 0;

  const ariaLabel = text("切换模型", "Switch model");
  const selectedValue = disabled
    ? "__disabled__"
    : selected === null
      ? ""
      : modelKey(selected);
  const options = disabled
    ? [
        {
          value: "__disabled__",
          label: text("模型设置不可用", "Model settings unavailable"),
          description: modelLabelFallback,
          leading: <Brain aria-hidden="true" className="h-4 w-4" />,
          disabled: true,
        },
      ]
    : providers.map((option) => ({
        value: modelKey(option),
        label: option.modelLabel,
        description: option.providerLabel,
        group: option.providerLabel,
        meta:
          option.providerId === selectedProviderId && option.modelId === selectedModelId
            ? text("当前", "Current")
            : option.providerId,
      }));

  return (
    <MenuSelect
      ariaLabel={ariaLabel}
      value={selectedValue}
      options={options}
      onChange={(value) => {
        const next = providers.find((option) => modelKey(option) === value);
        if (next === undefined) return;
        onModelChange(next.providerId, next.modelId);
      }}
      placeholder={modelLabelFallback}
      leading={<Brain aria-hidden="true" className="h-4 w-4" />}
      disabled={disabled}
      openRequestSeq={openRequestSeq}
      placement="top"
      className="w-full"
      buttonClassName="h-auto rounded-2xl border-slate-200 px-4 py-3"
      menuClassName="w-full"
    />
  );
}
