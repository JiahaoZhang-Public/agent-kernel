import { useCallback, useEffect, useRef } from "react";
import type { TimelineEvent } from "@/lib/types";
import { eventStreamUrl } from "@/lib/api";

export type EventStreamHandlers = {
  onEvent: (ev: TimelineEvent) => void;
  onDone?: () => void;
  onError?: (err: unknown) => void;
};

export function useEventStream() {
  const sourceRef = useRef<EventSource | null>(null);
  const retriedRef = useRef(false);

  const close = useCallback(() => {
    sourceRef.current?.close();
    sourceRef.current = null;
    retriedRef.current = false;
  }, []);

  useEffect(() => () => close(), [close]);

  const open = useCallback(
    (runId: string, handlers: EventStreamHandlers) => {
      close();
      retriedRef.current = false;
      const url = eventStreamUrl(runId);

      const start = () => {
        const src = new EventSource(url);
        sourceRef.current = src;
        src.onmessage = (msg) => {
          try {
            const data = JSON.parse(msg.data) as TimelineEvent;
            handlers.onEvent(data);
            if (data.type === "done") {
              handlers.onDone?.();
              close();
            }
          } catch (e) {
            handlers.onError?.(e);
          }
        };
        src.onerror = (err) => {
          if (!retriedRef.current) {
            retriedRef.current = true;
            src.close();
            setTimeout(() => start(), 500);
            return;
          }
          handlers.onError?.(err);
          close();
        };
      };

      start();
    },
    [close],
  );

  return { open, close };
}
