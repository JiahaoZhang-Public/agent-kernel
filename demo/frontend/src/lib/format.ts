export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1) return "<1 ms";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  } catch {
    return iso;
  }
}

export function prettyJson(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function statusTone(
  status: string | undefined | null,
): "success" | "destructive" | "warning" | "muted" {
  if (!status) return "muted";
  const upper = status.toUpperCase();
  if (upper === "OK" || upper === "OK ") return "success";
  if (upper === "DENIED") return "destructive";
  if (upper === "FAILED" || upper === "ERROR" || upper === "INVALID")
    return "warning";
  return "muted";
}

export function laneLabel(lane: string): string {
  if (lane === "naive") return "Naive agent";
  if (lane === "kernel") return "Kernel agent";
  return "System";
}
