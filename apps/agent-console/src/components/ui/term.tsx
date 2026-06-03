import type { ReactNode } from "react";

import { cn } from "../../lib/utils";

export function TermHint({
  children,
  description,
  className,
  descriptionClassName,
}: {
  children: ReactNode;
  description: string;
  className?: string;
  descriptionClassName?: string;
}) {
  return (
    <span className={cn("inline-flex min-w-0 flex-col leading-tight", className)} title={description}>
      <span className="min-w-0 truncate">{children}</span>
      <span className={cn("mt-0.5 text-[10px] font-normal leading-3 text-slate-400", descriptionClassName)}>
        {description}
      </span>
    </span>
  );
}

export function InlineTermHint({
  term,
  description,
  className,
}: {
  term: string;
  description: string;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex items-baseline gap-1", className)} title={description}>
      <span>{term}</span>
      <span className="text-[10px] font-normal text-slate-400">{description}</span>
    </span>
  );
}
