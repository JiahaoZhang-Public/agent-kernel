import { useCallback, useRef, useState } from "react";
import { emptyWorld, type LogRecord, type TimelineEvent, type WorldSnapshot } from "@/lib/types";
import * as api from "@/lib/api";
import { useEventStream } from "./useEventStream";

export type RunRequestPayload = {
  scenario: string;
  prompt: string;
  mode: string;
  policyYaml: string;
  llm?: { apiKey?: string; baseUrl?: string; model?: string };
};

export type ScenarioRunState = {
  events: TimelineEvent[];
  comparisonWorlds: { naive?: WorldSnapshot; kernel?: WorldSnapshot };
  running: boolean;
  error: string | null;
  durationMs: number | null;
  lastSeq: number | null;
};

const initial: ScenarioRunState = {
  events: [],
  comparisonWorlds: {},
  running: false,
  error: null,
  durationMs: null,
  lastSeq: null,
};

export function useScenarioRun(opts: {
  onWorld?: (w: WorldSnapshot) => void;
  onLog?: (r: LogRecord | null | undefined) => void;
}) {
  const [state, setState] = useState<ScenarioRunState>(initial);
  const startedAtRef = useRef<number | null>(null);
  const { open, close } = useEventStream();

  const runScenario = useCallback(
    async (payload: RunRequestPayload) => {
      setState({ ...initial, running: true });
      startedAtRef.current = performance.now();
      try {
        const { runId } = await api.createRun(payload);
        open(runId, {
          onEvent: (ev) => {
            setState((prev) => {
              const next: ScenarioRunState = {
                ...prev,
                events: [...prev.events, ev],
                lastSeq: ev.seq,
              };
              if (ev.worlds) {
                next.comparisonWorlds = ev.worlds;
              }
              return next;
            });
            // Side effects are deliberately outside the state updater so
            // React 18+ StrictMode (and any future double-render) cannot
            // duplicate world / log mutations.
            if (ev.world) opts.onWorld?.(ev.world);
            if (ev.record) opts.onLog?.(ev.record);
          },
          onDone: () => {
            const elapsed =
              startedAtRef.current !== null
                ? performance.now() - startedAtRef.current
                : null;
            setState((prev) => ({ ...prev, running: false, durationMs: elapsed }));
          },
          onError: (err) => {
            setState((prev) => ({
              ...prev,
              running: false,
              error: err instanceof Error ? err.message : String(err),
            }));
          },
        });
      } catch (e) {
        setState((prev) => ({
          ...prev,
          running: false,
          error: e instanceof Error ? e.message : String(e),
        }));
      }
    },
    [open, opts],
  );

  const reset = useCallback(() => {
    close();
    setState(initial);
    startedAtRef.current = null;
  }, [close]);

  const pushEvent = useCallback((ev: TimelineEvent) => {
    setState((prev) => ({
      ...prev,
      events: [...prev.events, ev],
      lastSeq: ev.seq,
    }));
  }, []);

  return { ...state, runScenario, reset, pushEvent };
}
