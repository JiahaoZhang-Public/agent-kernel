import type {
  ActionRequest,
  LLMTestResult,
  LogRecord,
  ManualResult,
  RollbackResponse,
  Scenario,
  WorldSnapshot,
} from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

async function jsonFetch<T>(
  path: string,
  init?: RequestInit & { signal?: AbortSignal },
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = body?.detail ?? body?.error ?? JSON.stringify(body);
    } catch {
      detail = await res.text();
    }
    throw new Error(`${res.status} ${res.statusText}${detail ? ` — ${detail}` : ""}`);
  }
  return (await res.json()) as T;
}

export async function getScenarios(): Promise<Scenario[]> {
  return jsonFetch<Scenario[]>("/api/scenarios");
}

export async function getDefaultPolicy(): Promise<{ policyYaml: string }> {
  return jsonFetch<{ policyYaml: string }>("/api/policy/default");
}

export async function getWorld(): Promise<WorldSnapshot> {
  return jsonFetch<WorldSnapshot>("/api/world");
}

export async function resetWorld(): Promise<{
  world: WorldSnapshot;
  logs: LogRecord[];
}> {
  return jsonFetch<{ world: WorldSnapshot; logs: LogRecord[] }>(
    "/api/world/reset",
    { method: "POST" },
  );
}

export async function getLogs(): Promise<LogRecord[]> {
  return jsonFetch<LogRecord[]>("/api/logs");
}

export async function submitManual(payload: {
  action: string;
  target: string;
  params: Record<string, unknown>;
  policyYaml: string;
}): Promise<ManualResult> {
  return jsonFetch<ManualResult>("/api/kernel/submit", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function testLlm(payload: {
  apiKey?: string;
  baseUrl?: string;
  model?: string;
}): Promise<LLMTestResult> {
  return jsonFetch<LLMTestResult>("/api/llm/test", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function createRun(payload: {
  scenario: string;
  prompt: string;
  mode: string;
  policyYaml: string;
  llm?: { apiKey?: string; baseUrl?: string; model?: string };
}): Promise<{ runId: string }> {
  return jsonFetch<{ runId: string }>("/api/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function eventStreamUrl(runId: string): string {
  return `${API_BASE}/api/runs/${encodeURIComponent(runId)}/events`;
}

export async function rollback(payload: {
  recordId: string;
  policyYaml: string;
}): Promise<RollbackResponse> {
  return jsonFetch<RollbackResponse>("/api/kernel/rollback", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type { ActionRequest };
