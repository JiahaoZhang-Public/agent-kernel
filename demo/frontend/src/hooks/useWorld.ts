import { useCallback, useEffect, useState } from "react";
import { emptyWorld, type LogRecord, type WorldSnapshot } from "@/lib/types";
import * as api from "@/lib/api";

export function useWorld() {
  const [world, setWorld] = useState<WorldSnapshot>(emptyWorld);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const snap = await api.getWorld();
      setWorld(snap);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const reset = useCallback(async (): Promise<{
    world: WorldSnapshot;
    logs: LogRecord[];
  } | null> => {
    try {
      const out = await api.resetWorld();
      setWorld(out.world);
      setError(null);
      return out;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { world, setWorld, reset, refresh, error };
}
