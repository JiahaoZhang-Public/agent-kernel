export type Scenario = {
  id: string;
  title: string;
  prompt: string;
};

export type ActionRequest = {
  action: string;
  target: string;
  params?: Record<string, unknown>;
};

export type ActionResult = {
  status: "OK" | "DENIED" | "FAILED" | "INVALID" | string;
  data?: unknown;
  error?: string | null;
  record_id?: string | null;
};

export type LogRecord = {
  timestamp: string;
  action: string;
  target: string;
  status: string;
  error: string | null;
  duration_ms: number | null;
  record_id?: string | null;
};

export type WorldSnapshot = {
  tables: Record<string, { dropped: boolean; rows: unknown[] }>;
  httpCalls: Array<{ url: string; method: string }>;
  mcpCalls: Array<{ target: string; query: string }>;
};

export const emptyWorld: WorldSnapshot = {
  tables: {},
  httpCalls: [],
  mcpCalls: [],
};

export type Lane = "system" | "naive" | "kernel";

export type Payload = { label: string; value: unknown };

export type TimelineEvent = {
  seq: number;
  lane: Lane;
  type: string;
  title: string;
  detail?: string;
  request?: ActionRequest;
  result?: ActionResult;
  record?: LogRecord | null;
  world?: WorldSnapshot;
  worlds?: { naive: WorldSnapshot; kernel: WorldSnapshot };
  payloads?: Payload[];
  record_id?: string | null;
};

export type ManualResult = {
  request: ActionRequest;
  result: ActionResult;
  record: LogRecord | null;
  world: WorldSnapshot;
};

export type LLMTestResult = {
  ok: boolean;
  baseUrl: string;
  model: string;
  message?: string;
  error?: string;
};

export type RunMode = "comparison" | "kernel" | "naive" | "llm";

export const MODEL_OPTIONS = [
  "deepseek-v4-flash",
  "gpt-5.5",
  "kimi-k2.6",
  "qwen3.6-flash",
  "glm-5.1",
] as const;

export type RollbackResponse = {
  result: ActionResult;
  record: LogRecord | null;
  world: WorldSnapshot;
};
