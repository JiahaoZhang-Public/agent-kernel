import * as React from "react";
import { cn } from "@/lib/utils";
import { prettyJson } from "@/lib/format";

export function CodeBlock({
  value,
  className,
}: {
  value: unknown;
  className?: string;
}) {
  const text = typeof value === "string" ? value : prettyJson(value);
  return (
    <pre
      className={cn(
        "max-w-full overflow-x-auto rounded border border-border bg-muted/60 p-2.5 font-mono text-[11px] leading-snug text-foreground/90",
        className,
      )}
    >
      {text}
    </pre>
  );
}
