import * as React from "react";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { TimelineEvent } from "@/lib/types";
import { formatMs } from "@/lib/format";
import { StatusBadge } from "./StatusBadge";
import { CodeBlock } from "./CodeBlock";

const laneAccent: Record<string, string> = {
  naive: "border-l-destructive",
  kernel: "border-l-success",
  system: "border-l-muted-foreground/50",
};

export function EventCard({
  event,
  selected,
  onSelect,
  compact = false,
  trailing,
}: {
  event: TimelineEvent;
  selected?: boolean;
  onSelect?: (ev: TimelineEvent) => void;
  compact?: boolean;
  trailing?: React.ReactNode;
}) {
  const { status } = event.result ?? {};
  const duration = event.record?.duration_ms ?? null;
  const accent = laneAccent[event.lane] ?? laneAccent.system;
  return (
    <Card
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : -1}
      onClick={() => onSelect?.(event)}
      onKeyDown={(e) => {
        if (!onSelect) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(event);
        }
      }}
      className={cn(
        "border-l-4 transition-shadow animate-fade-in",
        accent,
        onSelect && "cursor-pointer hover:shadow-sm",
        selected && "ring-2 ring-ring shadow-sm",
      )}
    >
      <CardHeader className={cn("pb-2", compact && "p-3 pb-1")}>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-muted-foreground">
              <span>seq {event.seq}</span>
              <span aria-hidden>·</span>
              <span>{event.type}</span>
              {duration !== null ? (
                <>
                  <span aria-hidden>·</span>
                  <span className="tabular-nums">{formatMs(duration)}</span>
                </>
              ) : null}
            </div>
            <div className="mt-0.5 text-sm font-medium text-foreground">
              {event.title}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {status ? <StatusBadge status={status} /> : null}
          </div>
        </div>
      </CardHeader>
      {!compact ? (
        <CardContent className="space-y-2 pt-0">
          {event.detail ? (
            <p className="text-xs text-muted-foreground">{event.detail}</p>
          ) : null}
          {event.payloads?.map((p) => (
            <div key={p.label} className="space-y-1">
              <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground/80">
                {p.label}
              </div>
              <CodeBlock value={p.value} />
            </div>
          ))}
          {trailing ? (
            <div className="flex items-center justify-end gap-2 pt-1">
              {trailing}
            </div>
          ) : null}
        </CardContent>
      ) : null}
    </Card>
  );
}
