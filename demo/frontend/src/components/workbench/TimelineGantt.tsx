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
import { useResizeObserver } from "@/hooks/useResizeObserver";
import type { TimelineEvent } from "@/lib/types";
import { formatMs, statusTone } from "@/lib/format";
import { cn } from "@/lib/utils";

const LANE_HEIGHT = 28;
const LANE_GAP = 8;
const AXIS_HEIGHT = 22;
const PADDING_X = 8;
const MIN_BAR_WIDTH_PX = 8;
const SYNTHETIC_DURATION_MS = 12;

const TONE_FILL: Record<string, string> = {
  success: "hsl(var(--success))",
  destructive: "hsl(var(--destructive))",
  warning: "hsl(var(--warning))",
  muted: "hsl(var(--muted-foreground) / 0.5)",
};

type Lane = "naive" | "kernel";

type Bar = {
  ev: TimelineEvent;
  startMs: number;
  durationMs: number;
};

function buildLanes(events: TimelineEvent[]): {
  naive: Bar[];
  kernel: Bar[];
  totalMs: number;
} {
  const lanes: Record<Lane, Bar[]> = { naive: [], kernel: [] };
  const cursor: Record<Lane, number> = { naive: 0, kernel: 0 };
  for (const ev of events) {
    if (ev.lane !== "naive" && ev.lane !== "kernel") continue;
    const lane = ev.lane as Lane;
    const dur = ev.record?.duration_ms ?? SYNTHETIC_DURATION_MS;
    lanes[lane].push({ ev, startMs: cursor[lane], durationMs: dur });
    cursor[lane] += dur;
  }
  const totalMs = Math.max(cursor.naive, cursor.kernel, SYNTHETIC_DURATION_MS);
  return { naive: lanes.naive, kernel: lanes.kernel, totalMs };
}

function GanttLane({
  bars,
  width,
  totalMs,
  selectedSeq,
  onSelect,
  laneAccent,
  laneLabel,
}: {
  bars: Bar[];
  width: number;
  totalMs: number;
  selectedSeq: number | null;
  onSelect?: (ev: TimelineEvent) => void;
  laneAccent: string;
  laneLabel: string;
}) {
  const innerWidth = Math.max(0, width - PADDING_X * 2);
  return (
    <g>
      <rect
        x={0}
        y={0}
        width={width}
        height={LANE_HEIGHT}
        rx={6}
        ry={6}
        className="fill-muted/40"
      />
      <text
        x={PADDING_X}
        y={LANE_HEIGHT / 2 + 4}
        className="fill-muted-foreground"
        fontSize={10}
        fontWeight={600}
        style={{ textTransform: "uppercase", letterSpacing: 0.6 }}
      >
        {laneLabel}
      </text>
      <line
        x1={0}
        y1={0}
        x2={0}
        y2={LANE_HEIGHT}
        strokeWidth={3}
        stroke={laneAccent}
      />
      {bars.map((bar) => {
        const tone = statusTone(bar.ev.result?.status);
        const fill = TONE_FILL[tone] ?? TONE_FILL.muted;
        const x =
          totalMs > 0
            ? PADDING_X + (bar.startMs / totalMs) * innerWidth
            : PADDING_X;
        const w = Math.max(
          MIN_BAR_WIDTH_PX,
          totalMs > 0 ? (bar.durationMs / totalMs) * innerWidth : MIN_BAR_WIDTH_PX,
        );
        const selected = selectedSeq === bar.ev.seq;
        return (
          <TooltipProvider key={bar.ev.seq} delayDuration={120}>
            <Tooltip>
              <TooltipTrigger asChild>
                <rect
                  x={x}
                  y={4}
                  width={w}
                  height={LANE_HEIGHT - 8}
                  rx={3}
                  ry={3}
                  fill={fill}
                  fillOpacity={selected ? 1 : 0.85}
                  stroke={selected ? "hsl(var(--ring))" : "none"}
                  strokeWidth={selected ? 1.5 : 0}
                  style={{ cursor: onSelect ? "pointer" : "default" }}
                  onClick={() => onSelect?.(bar.ev)}
                />
              </TooltipTrigger>
              <TooltipContent>
                <div className="font-medium">{bar.ev.title}</div>
                <div className="text-muted-foreground">
                  {bar.ev.request?.action ?? bar.ev.type}
                  {bar.ev.request?.target ? ` · ${bar.ev.request.target}` : ""}
                  {bar.ev.result?.status ? ` · ${bar.ev.result.status}` : ""}
                  {" · "}
                  {formatMs(bar.durationMs)}
                </div>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        );
      })}
    </g>
  );
}

export function TimelineGantt({
  events,
  selectedSeq,
  onSelect,
  className,
}: {
  events: TimelineEvent[];
  selectedSeq?: number | null;
  onSelect?: (ev: TimelineEvent) => void;
  className?: string;
}) {
  const { ref, size } = useResizeObserver<HTMLDivElement>();
  const { naive, kernel, totalMs } = useMemo(() => buildLanes(events), [events]);
  const w = Math.max(280, size.width || 0);
  const totalHeight = AXIS_HEIGHT + LANE_HEIGHT * 2 + LANE_GAP;
  const ticks = [0, 0.25, 0.5, 0.75, 1];

  const innerWidth = Math.max(0, w - PADDING_X * 2);

  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardHeader>
        <CardTitle>Performance gantt</CardTitle>
        <CardDescription>
          Time-aligned bars for each lane. Hover for details · click to inspect.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div ref={ref} className="w-full">
          {events.length === 0 ? (
            <div className="rounded-md border border-dashed border-border bg-muted/30 px-4 py-8 text-center text-xs text-muted-foreground">
              Run a scenario to populate the timeline.
            </div>
          ) : (
            <svg width={w} height={totalHeight} role="img">
              <g transform={`translate(0, 0)`}>
                {ticks.map((t) => {
                  const x = PADDING_X + t * innerWidth;
                  return (
                    <g key={t}>
                      <line
                        x1={x}
                        y1={AXIS_HEIGHT - 6}
                        x2={x}
                        y2={AXIS_HEIGHT}
                        stroke="hsl(var(--border))"
                        strokeWidth={1}
                      />
                      <text
                        x={x}
                        y={AXIS_HEIGHT - 8}
                        textAnchor={t === 0 ? "start" : t === 1 ? "end" : "middle"}
                        className="fill-muted-foreground"
                        fontSize={10}
                      >
                        {formatMs(t * totalMs)}
                      </text>
                    </g>
                  );
                })}
              </g>
              <g transform={`translate(0, ${AXIS_HEIGHT})`}>
                <GanttLane
                  bars={naive}
                  width={w}
                  totalMs={totalMs}
                  selectedSeq={selectedSeq ?? null}
                  onSelect={onSelect}
                  laneAccent="hsl(var(--lane-naive))"
                  laneLabel="Naive"
                />
              </g>
              <g transform={`translate(0, ${AXIS_HEIGHT + LANE_HEIGHT + LANE_GAP})`}>
                <GanttLane
                  bars={kernel}
                  width={w}
                  totalMs={totalMs}
                  selectedSeq={selectedSeq ?? null}
                  onSelect={onSelect}
                  laneAccent="hsl(var(--lane-kernel))"
                  laneLabel="Kernel"
                />
              </g>
            </svg>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
