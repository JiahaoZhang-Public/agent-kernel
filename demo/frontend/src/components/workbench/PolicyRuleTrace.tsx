import { useMemo } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { traceRequest, type RuleTrace } from "@/lib/policyMatch";
import type { ActionRequest } from "@/lib/types";
import { CodeBlock } from "./CodeBlock";
import { ShieldCheck, AlertTriangle, Ban, ScanEye } from "lucide-react";

const STATUS_META: Record<
  RuleTrace["status"],
  { label: string; tooltip: string; tone: "ok" | "warn" | "fail" | "muted" }
> = {
  matched: {
    label: "matched",
    tooltip: "All of action, resource, and constraint matched.",
    tone: "ok",
  },
  "constraint-fail": {
    label: "constraint failed",
    tooltip:
      "Action and resource matched, but a rule constraint (e.g. method) didn't.",
    tone: "warn",
  },
  "action-only": {
    label: "resource missed",
    tooltip: "Action matched, but the target glob did not.",
    tone: "warn",
  },
  "resource-only": {
    label: "action missed",
    tooltip: "Resource matched, but the requested action is different.",
    tone: "muted",
  },
  "no-match": {
    label: "—",
    tooltip: "Neither action nor resource matched this rule.",
    tone: "muted",
  },
};

const TONE_BORDER: Record<string, string> = {
  ok: "border-l-success",
  warn: "border-l-warning",
  fail: "border-l-destructive",
  muted: "border-l-border",
};

const TONE_PILL: Record<string, string> = {
  ok: "bg-success/10 text-success",
  warn: "bg-warning/10 text-warning",
  fail: "bg-destructive/10 text-destructive",
  muted: "bg-muted text-muted-foreground",
};

function PolicyLine({ rule }: { rule: RuleTrace }) {
  const meta = STATUS_META[rule.status];
  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <div
            data-testid="rule-line"
            data-status={rule.status}
            className={cn(
              "flex items-center justify-between gap-3 rounded-r border-l-4 bg-muted/30 px-3 py-1.5 transition-colors hover:bg-muted/60",
              TONE_BORDER[meta.tone],
            )}
          >
            <div className="flex min-w-0 items-center gap-2 font-mono text-xs">
              <span className="text-muted-foreground tabular-nums">
                L{rule.line}
              </span>
              <span className="text-foreground/90 truncate">
                {rule.action}
              </span>
              <span className="text-muted-foreground/70">·</span>
              <span className="text-foreground/80 truncate">{rule.resource}</span>
              {rule.constraint ? (
                <span className="text-muted-foreground truncate">
                  {" "}
                  {Object.entries(rule.constraint)
                    .map(([k, v]) => `${k}=${String(v)}`)
                    .join(", ")}
                </span>
              ) : null}
            </div>
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-[10px] font-medium",
                TONE_PILL[meta.tone],
              )}
            >
              {meta.label}
            </span>
          </div>
        </TooltipTrigger>
        <TooltipContent>
          <div className="font-medium">Rule #{rule.index + 1}</div>
          <div>{meta.tooltip}</div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export function PolicyRuleTrace({
  policyYaml,
  request,
  verdict,
  className,
}: {
  policyYaml: string;
  request: ActionRequest | null | undefined;
  verdict: "OK" | "DENIED" | string | null | undefined;
  className?: string;
}) {
  const trace = useMemo(
    () =>
      request
        ? traceRequest(policyYaml, request)
        : { rules: [], matchedIndex: null, parseError: null },
    [policyYaml, request],
  );

  const Header = () => {
    if (trace.parseError) {
      return (
        <div className="flex items-center gap-2 text-warning">
          <AlertTriangle className="h-4 w-4" />
          Policy YAML failed to parse: {trace.parseError}
        </div>
      );
    }
    if (!request) {
      return (
        <div className="flex items-center gap-2 text-muted-foreground">
          <ScanEye className="h-4 w-4" />
          Select an event to see how the policy evaluated this request.
        </div>
      );
    }
    if (trace.matchedIndex !== null) {
      const matched = trace.rules[trace.matchedIndex];
      return (
        <div className="flex items-center gap-2 text-success">
          <ShieldCheck className="h-4 w-4" />
          Allowed by rule #{matched.index + 1} (line {matched.line}).
        </div>
      );
    }
    return (
      <div className="flex items-center gap-2 text-destructive">
        <Ban className="h-4 w-4" />
        No capability rule matched — default-deny applied.
      </div>
    );
  };

  return (
    <Card className={className} data-testid="rule-trace">
      <CardHeader>
        <CardTitle>Policy rule trace</CardTitle>
        <CardDescription>
          {verdict ? (
            <>
              Verdict <span className="font-mono">{verdict}</span> against the
              capabilities below.
            </>
          ) : (
            "Pick an event to see which rule (if any) authorized it."
          )}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Header />
        {request ? (
          <div className="space-y-1">
            <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Request
            </div>
            <CodeBlock value={request} />
          </div>
        ) : null}
        <div className="space-y-1.5">
          <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            Capability rules
          </div>
          <div className="space-y-1">
            {trace.rules.length === 0 ? (
              <div className="rounded border border-dashed border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                {trace.parseError ?? "No capability rules defined."}
              </div>
            ) : (
              trace.rules.map((r) => <PolicyLine key={r.index} rule={r} />)
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
