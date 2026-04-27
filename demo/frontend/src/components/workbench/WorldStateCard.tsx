import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { WorldSnapshot } from "@/lib/types";
import { Database, Globe, Network } from "lucide-react";
import { CodeBlock } from "./CodeBlock";

export function WorldStateCard({
  title = "World state",
  world,
  compact = false,
}: {
  title?: string;
  world: WorldSnapshot;
  compact?: boolean;
}) {
  const tableEntries = Object.entries(world.tables ?? {});
  const totalRows = tableEntries.reduce(
    (sum, [, t]) => sum + (t.rows?.length ?? 0),
    0,
  );
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Database className="h-3.5 w-3.5 text-muted-foreground" /> {title}
        </CardTitle>
        <CardDescription>
          {tableEntries.length} tables · {totalRows} rows ·{" "}
          {world.httpCalls?.length ?? 0} http · {world.mcpCalls?.length ?? 0} mcp
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {tableEntries.length === 0 ? (
          <div className="text-xs text-muted-foreground">
            No database tables touched yet.
          </div>
        ) : (
          <ul className="space-y-1.5">
            {tableEntries.map(([name, t]) => (
              <li
                key={name}
                className="flex items-center justify-between gap-2 rounded border border-border bg-muted/30 px-2.5 py-1.5"
              >
                <div className="flex min-w-0 items-center gap-2">
                  <span className="font-mono text-xs text-foreground truncate">
                    {name}
                  </span>
                  {t.dropped ? (
                    <Badge variant="destructive">dropped</Badge>
                  ) : null}
                </div>
                <span className="text-xs text-muted-foreground tabular-nums">
                  {t.rows?.length ?? 0} rows
                </span>
              </li>
            ))}
          </ul>
        )}
        {!compact && (world.httpCalls?.length ?? 0) > 0 ? (
          <div className="space-y-1">
            <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              <Globe className="h-3 w-3" /> HTTP calls
            </div>
            <CodeBlock value={world.httpCalls} />
          </div>
        ) : null}
        {!compact && (world.mcpCalls?.length ?? 0) > 0 ? (
          <div className="space-y-1">
            <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              <Network className="h-3 w-3" /> MCP calls
            </div>
            <CodeBlock value={world.mcpCalls} />
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
