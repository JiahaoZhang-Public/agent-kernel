import { ShieldCheck } from "lucide-react";
import type { TimelineEvent, WorldSnapshot } from "@/lib/types";
import { EventCard } from "./EventCard";
import { GateDecisionCard } from "./GateDecisionCard";
import { PolicyRuleTrace } from "./PolicyRuleTrace";
import { WorldStateCard } from "./WorldStateCard";
import { EmptyState } from "./EmptyState";

export function InspectorPanel({
  events,
  selectedSeq,
  policyYaml,
  worldKernel,
  trailingFor,
}: {
  events: TimelineEvent[];
  selectedSeq: number | null;
  policyYaml: string;
  worldKernel: WorldSnapshot;
  trailingFor?: (ev: TimelineEvent) => React.ReactNode;
}) {
  const selected =
    selectedSeq !== null
      ? events.find((e) => e.seq === selectedSeq) ?? null
      : null;
  const latestKernelDecision =
    [...events]
      .reverse()
      .find((e) => e.lane === "kernel" && e.type === "kernel-decision") ??
    null;

  if (!selected) {
    if (events.length === 0) {
      return (
        <div className="h-full min-w-0 overflow-y-auto overflow-x-hidden">
          <div className="space-y-3 p-4">
            <EmptyState
              icon={<ShieldCheck className="h-5 w-5" />}
              title="Inspector"
              hint="Run a scenario or click a timeline event to see its details, the matching policy rule, and any reversible record."
            />
            <WorldStateCard
              title="World state · Kernel"
              world={worldKernel}
              compact
            />
          </div>
        </div>
      );
    }
    return (
      <div className="h-full min-w-0 overflow-y-auto overflow-x-hidden">
        <div className="space-y-3 p-4">
          <GateDecisionCard event={latestKernelDecision} />
          <WorldStateCard
            title="World state · Kernel"
            world={worldKernel}
            compact
          />
        </div>
      </div>
    );
  }

  const showRuleTrace =
    selected.lane === "kernel" &&
    (selected.type === "kernel-decision" ||
      selected.type === "manual" ||
      Boolean(selected.request));

  return (
    <div className="h-full min-w-0 overflow-y-auto overflow-x-hidden">
      <div className="space-y-3 p-4">
        <EventCard event={selected} trailing={trailingFor?.(selected)} />
        {showRuleTrace ? (
          <PolicyRuleTrace
            policyYaml={policyYaml}
            request={selected.request}
            verdict={selected.result?.status}
          />
        ) : null}
        {selected.lane === "kernel" && selected.world ? (
          <WorldStateCard title="World state at this step" world={selected.world} compact />
        ) : null}
      </div>
    </div>
  );
}
