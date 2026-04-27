import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { ShieldCheck, Settings2, RotateCcw, Loader2 } from "lucide-react";
import { formatMs } from "@/lib/format";

export type LlmStatus = "untested" | "ok" | "error";

export function Topbar({
  running,
  lastSeq,
  durationMs,
  llmStatus,
  llmModel,
  onOpenSettings,
  onResetWorld,
  resetting,
}: {
  running: boolean;
  lastSeq: number | null;
  durationMs: number | null;
  llmStatus: LlmStatus;
  llmModel?: string;
  onOpenSettings: () => void;
  onResetWorld: () => void;
  resetting?: boolean;
}) {
  let pillLabel = "Idle";
  let pillTone:
    | "default"
    | "success"
    | "warning"
    | "destructive"
    | "secondary" = "secondary";
  if (running) {
    pillLabel = lastSeq ? `Streaming · seq ${lastSeq}` : "Starting...";
    pillTone = "default";
  } else if (durationMs !== null) {
    pillLabel = `Run done · ${formatMs(durationMs)}`;
    pillTone = "success";
  }

  const llmDot =
    llmStatus === "ok"
      ? "bg-success"
      : llmStatus === "error"
        ? "bg-destructive"
        : "bg-muted-foreground/40";

  return (
    <header
      data-testid="topbar"
      className="sticky top-0 z-40 flex h-14 items-center gap-3 border-b border-border bg-card/95 px-4 backdrop-blur"
    >
      <div className="flex items-center gap-2">
        <span className="grid h-7 w-7 place-items-center rounded-md bg-primary/10 text-primary">
          <ShieldCheck className="h-4 w-4" />
        </span>
        <div className="flex flex-col leading-tight">
          <span className="text-sm font-semibold tracking-tight">
            Agent Kernel Workbench
          </span>
          <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
            Naive vs Kernel · gate · audit · rollback
          </span>
        </div>
      </div>
      <div className="ml-2 hidden md:flex">
        <Badge variant={pillTone}>
          {running ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : null}
          <span>{pillLabel}</span>
        </Badge>
      </div>
      <div className="ml-auto flex items-center gap-2">
        <TooltipProvider delayDuration={150}>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={onOpenSettings}
                className="flex items-center gap-1.5 rounded-md border border-border bg-muted/40 px-2 py-1 text-xs hover:bg-muted"
              >
                <span
                  className={cn(
                    "inline-block h-2 w-2 rounded-full",
                    llmDot,
                    llmStatus === "untested" && "animate-pulse-soft",
                  )}
                  aria-hidden
                />
                <span className="font-medium">LLM</span>
                {llmModel ? (
                  <span className="text-muted-foreground">{llmModel}</span>
                ) : null}
              </button>
            </TooltipTrigger>
            <TooltipContent>
              {llmStatus === "ok"
                ? "LLM connection OK"
                : llmStatus === "error"
                  ? "LLM test failed — open settings"
                  : "LLM not yet tested"}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <Button variant="outline" size="sm" onClick={onOpenSettings}>
          <Settings2 /> Settings
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onResetWorld}
          disabled={resetting}
          aria-label="Reset demo world"
        >
          <RotateCcw />
          Reset world
        </Button>
      </div>
    </header>
  );
}
