import {
  Card,
  CardContent,
  CardDescription,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { ShieldCheck, ScrollText, GitCompare } from "lucide-react";
import type { LogRecord, TimelineEvent, WorldSnapshot } from "@/lib/types";

type KpiTone = "default" | "success" | "destructive" | "warning";

const TONE_BORDER: Record<KpiTone, string> = {
  default: "border-l-primary",
  success: "border-l-success",
  destructive: "border-l-destructive",
  warning: "border-l-warning",
};

function Kpi({
  icon,
  label,
  value,
  hint,
  tone = "default",
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  hint?: string;
  tone?: KpiTone;
}) {
  return (
    <Card
      className={cn(
        "border-l-4 shadow-none",
        TONE_BORDER[tone],
      )}
    >
      <CardContent className="space-y-1 p-4">
        <CardDescription className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide">
          {icon}
          <span>{label}</span>
        </CardDescription>
        <CardTitle className="text-2xl font-semibold tabular-nums tracking-tight">
          {value}
        </CardTitle>
        {hint ? (
          <CardDescription className="text-xs">{hint}</CardDescription>
        ) : null}
      </CardContent>
    </Card>
  );
}

function totalRows(world?: WorldSnapshot): number {
  if (!world) return 0;
  return Object.values(world.tables ?? {}).reduce(
    (sum, t) => sum + (t?.rows?.length ?? 0),
    0,
  );
}

export function SummaryHeader({
  events,
  logs,
  comparison,
}: {
  events: TimelineEvent[];
  logs: LogRecord[];
  comparison: { naive?: WorldSnapshot; kernel?: WorldSnapshot };
}) {
  const blocked = events.filter(
    (e) => e.lane === "kernel" && e.result?.status === "DENIED",
  ).length;
  const audited = logs.length;
  const naiveRows = totalRows(comparison.naive);
  const kernelRows = totalRows(comparison.kernel);
  const delta = kernelRows - naiveRows;

  return (
    <div className="grid gap-3 sm:grid-cols-3">
      <Kpi
        icon={<ShieldCheck className="h-3.5 w-3.5" />}
        label="Actions blocked"
        value={blocked}
        hint="Kernel-lane denials in this run."
        tone={blocked > 0 ? "destructive" : "default"}
      />
      <Kpi
        icon={<ScrollText className="h-3.5 w-3.5" />}
        label="Actions audited"
        value={audited}
        hint="Records in the kernel audit log."
        tone="default"
      />
      <Kpi
        icon={<GitCompare className="h-3.5 w-3.5" />}
        label="Rows preserved by kernel"
        value={delta >= 0 ? `+${delta}` : delta}
        hint={
          comparison.naive || comparison.kernel
            ? `Naive: ${naiveRows} rows · Kernel: ${kernelRows} rows`
            : "Run a comparison scenario to populate."
        }
        tone={delta > 0 ? "success" : "default"}
      />
    </div>
  );
}
