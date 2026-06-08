import { useI18n } from "../../../lib/i18n";

export interface AgentReadinessRingProps {
  toolsCount: number;
  knowledgeCount: number;
  connectionsCount: number;
  label?: string;
  size?: "sm" | "md";
}

export function AgentReadinessRing({
  toolsCount,
  knowledgeCount,
  connectionsCount,
  label,
  size = "md",
}: AgentReadinessRingProps) {
  const { text } = useI18n();
  const total = 3;
  const ready = [
    toolsCount > 0,
    knowledgeCount > 0,
    connectionsCount > 0,
  ].filter(Boolean).length;
  const percentage = (ready / total) * 100;
  const readinessText = text(`就绪: ${ready}/${total}`, `Ready: ${ready}/${total}`);
  const accessibleLabel = label ? `${label} · ${readinessText}` : readinessText;
  const sizeClass = size === "sm" ? "h-10 w-10" : "h-12 w-12";

  return (
    <div
      className={`relative shrink-0 ${sizeClass}`}
      title={accessibleLabel}
      role="img"
      aria-label={accessibleLabel}
    >
      <svg viewBox="0 0 36 36" className={`${sizeClass} -rotate-90`} aria-hidden="true">
        <circle
          cx="18"
          cy="18"
          r="16"
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
          className="text-slate-200"
        />
        <circle
          cx="18"
          cy="18"
          r="16"
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
          strokeDasharray={`${percentage} 100`}
          strokeLinecap="round"
          className={ready === total ? "text-emerald-500" : ready > 0 ? "text-amber-500" : "text-slate-300"}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center text-[11px] font-semibold text-slate-700">
        {ready}/{total}
      </div>
    </div>
  );
}
