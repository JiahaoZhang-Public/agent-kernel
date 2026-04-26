import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Lane, TimelineEvent } from "@/lib/types";
import { laneLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import { EventCard } from "./EventCard";
import { EmptyState } from "./EmptyState";

const LANE_TINT: Record<Exclude<Lane, "system">, string> = {
  naive: "before:bg-destructive",
  kernel: "before:bg-success",
};

export function TimelineColumn({
  lane,
  events,
  selectedSeq,
  onSelect,
  trailingFor,
}: {
  lane: Exclude<Lane, "system">;
  events: TimelineEvent[];
  selectedSeq?: number | null;
  onSelect?: (ev: TimelineEvent) => void;
  trailingFor?: (ev: TimelineEvent) => React.ReactNode;
}) {
  const filtered = events.filter((e) => e.lane === lane);
  return (
    <Card
      className={cn(
        "relative overflow-hidden",
        "before:absolute before:left-0 before:top-0 before:h-1 before:w-full",
        LANE_TINT[lane],
      )}
    >
      <CardHeader className="pt-5">
        <CardTitle>{laneLabel(lane)}</CardTitle>
        <CardDescription>
          {lane === "naive"
            ? "Direct provider.execute — no policy mediation, no audit."
            : "Every action passes through Gate (policy → execute → audit)."}
        </CardDescription>
      </CardHeader>
      <CardContent className="pt-0">
        {filtered.length === 0 ? (
          <EmptyState
            title="Idle"
            hint="Run a scenario to populate this lane."
          />
        ) : (
          <div className="max-h-[480px] min-w-0 space-y-2 overflow-y-auto overflow-x-hidden pr-1">
            {filtered.map((ev) => (
              <EventCard
                key={ev.seq}
                event={ev}
                selected={selectedSeq === ev.seq}
                onSelect={onSelect}
                trailing={trailingFor?.(ev)}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function TimelineList({
  events,
  selectedSeq,
  onSelect,
  trailingFor,
}: {
  events: TimelineEvent[];
  selectedSeq?: number | null;
  onSelect?: (ev: TimelineEvent) => void;
  trailingFor?: (ev: TimelineEvent) => React.ReactNode;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <TimelineColumn
        lane="naive"
        events={events}
        selectedSeq={selectedSeq}
        onSelect={onSelect}
        trailingFor={trailingFor}
      />
      <TimelineColumn
        lane="kernel"
        events={events}
        selectedSeq={selectedSeq}
        onSelect={onSelect}
        trailingFor={trailingFor}
      />
    </div>
  );
}
