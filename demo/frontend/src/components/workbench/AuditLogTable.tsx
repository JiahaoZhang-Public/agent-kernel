import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { ScrollText } from "lucide-react";
import type { LogRecord } from "@/lib/types";
import { formatMs, formatTimestamp } from "@/lib/format";
import { StatusBadge } from "./StatusBadge";

export function AuditLogTable({
  logs,
  limit,
  className,
}: {
  logs: LogRecord[];
  limit?: number;
  className?: string;
}) {
  const sliced = limit ? logs.slice(-limit).reverse() : [...logs].reverse();
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ScrollText className="h-3.5 w-3.5 text-muted-foreground" /> Audit log
        </CardTitle>
        <CardDescription>
          {logs.length} record{logs.length === 1 ? "" : "s"}
        </CardDescription>
      </CardHeader>
      <CardContent className="px-0 pb-2">
        {sliced.length === 0 ? (
          <div className="px-4 pb-2 text-xs text-muted-foreground">
            No kernel records yet.
          </div>
        ) : (
          <div className="max-h-72 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-card text-[10px] uppercase tracking-wide text-muted-foreground">
                <tr className="border-b border-border">
                  <th className="px-4 py-1.5 text-left font-medium">Time</th>
                  <th className="px-2 py-1.5 text-left font-medium">Action</th>
                  <th className="px-2 py-1.5 text-left font-medium">Target</th>
                  <th className="px-2 py-1.5 text-left font-medium">Status</th>
                  <th className="px-4 py-1.5 text-right font-medium">Dur</th>
                </tr>
              </thead>
              <tbody>
                {sliced.map((r, idx) => (
                  <tr
                    key={`${r.timestamp}-${idx}`}
                    className="border-b border-border/60 last:border-b-0 hover:bg-muted/40"
                  >
                    <td className="px-4 py-1.5 font-mono text-[11px] text-muted-foreground">
                      {formatTimestamp(r.timestamp)}
                    </td>
                    <td className="px-2 py-1.5 font-mono text-[11px]">{r.action}</td>
                    <td className="px-2 py-1.5 font-mono text-[11px] truncate max-w-[180px]">
                      {r.target}
                    </td>
                    <td className="px-2 py-1.5">
                      <StatusBadge status={r.status} showIcon={false} />
                    </td>
                    <td className="px-4 py-1.5 text-right font-mono tabular-nums text-[11px] text-muted-foreground">
                      {formatMs(r.duration_ms)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
