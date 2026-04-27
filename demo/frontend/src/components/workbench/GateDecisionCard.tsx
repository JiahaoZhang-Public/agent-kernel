import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { ShieldCheck } from "lucide-react";
import type { TimelineEvent } from "@/lib/types";
import { CodeBlock } from "./CodeBlock";
import { EmptyState } from "./EmptyState";
import { StatusBadge } from "./StatusBadge";
import { formatMs } from "@/lib/format";

export function GateDecisionCard({
  event,
  caption,
}: {
  event: TimelineEvent | null;
  caption?: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="h-3.5 w-3.5 text-muted-foreground" /> Gate decision
        </CardTitle>
        <CardDescription>
          {caption ?? "The kernel's most recent verdict on an action request."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {!event ? (
          <EmptyState
            title="No decisions yet"
            hint="Run a scenario or submit a manual action."
          />
        ) : (
          <>
            <div className="flex items-center gap-2">
              <StatusBadge status={event.result?.status} />
              {event.record?.duration_ms !== undefined &&
              event.record?.duration_ms !== null ? (
                <span className="text-xs text-muted-foreground">
                  {formatMs(event.record.duration_ms)}
                </span>
              ) : null}
            </div>
            {event.request ? (
              <div className="space-y-1">
                <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                  Request
                </div>
                <CodeBlock value={event.request} />
              </div>
            ) : null}
            {event.result?.error ? (
              <div className="space-y-1">
                <div className="text-[11px] font-medium uppercase tracking-wide text-destructive">
                  Reason
                </div>
                <div className="rounded border border-destructive/30 bg-destructive/5 px-2 py-1.5 text-xs text-destructive">
                  {event.result.error}
                </div>
              </div>
            ) : null}
            {event.record ? (
              <div className="space-y-1">
                <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                  Audit record
                </div>
                <CodeBlock value={event.record} />
              </div>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}
