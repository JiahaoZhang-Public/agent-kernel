import { useCallback, useEffect, useState } from "react";
import type { LogRecord } from "@/lib/types";
import * as api from "@/lib/api";

export function useLogs() {
  const [logs, setLogs] = useState<LogRecord[]>([]);

  const refresh = useCallback(async () => {
    try {
      const out = await api.getLogs();
      setLogs(out);
    } catch {
      // tolerate failure on initial hydrate
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const append = useCallback((record: LogRecord | null | undefined) => {
    if (!record) return;
    setLogs((prev) => [...prev, record]);
  }, []);

  const replace = useCallback((next: LogRecord[]) => setLogs(next), []);

  return { logs, refresh, append, replace };
}
