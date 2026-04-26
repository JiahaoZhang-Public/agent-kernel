import * as React from "react";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon,
  title,
  hint,
  className,
}: {
  icon?: React.ReactNode;
  title: string;
  hint?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-md border border-dashed border-border bg-muted/30 px-6 py-8 text-center",
        className,
      )}
    >
      {icon ? (
        <div className="text-muted-foreground/70">{icon}</div>
      ) : null}
      <div className="text-sm font-medium text-foreground">{title}</div>
      {hint ? (
        <div className="text-xs text-muted-foreground">{hint}</div>
      ) : null}
    </div>
  );
}
