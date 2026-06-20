import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { Button } from "./button";

type EmptyStateAction = {
  label: string;
  href?: string;
  onClick?: () => void;
  primary?: boolean;
};

export function EmptyState({
  icon,
  title,
  description,
  action,
  actions = [],
}: {
  icon: ReactNode;
  title: string;
  description: string;
  action?: ReactNode;
  actions?: EmptyStateAction[];
}) {
  return (
    <div className="flex min-h-[180px] items-center justify-center rounded-lg border border-dashed border-slate-200 bg-white p-6 text-center">
      <div className="max-w-md">
        <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-md bg-slate-100 text-slate-500">
          {icon}
        </div>
        <div className="mt-3 text-sm font-semibold text-slate-900">{title}</div>
        <p className="mt-1 text-xs leading-5 text-slate-500">{description}</p>
        {action ? (
          <div className="mt-4 flex justify-center">{action}</div>
        ) : actions.length ? (
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            {actions.map((action) =>
              action.href ? (
                <Link key={action.label} to={action.href}>
                  <Button variant={action.primary ? "primary" : "secondary"}>{action.label}</Button>
                </Link>
              ) : (
                <Button
                  key={action.label}
                  variant={action.primary ? "primary" : "secondary"}
                  onClick={action.onClick}
                >
                  {action.label}
                </Button>
              ),
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}
