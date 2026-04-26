import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  Database,
  KeyRound,
  Network,
  Play,
  RotateCcw,
  ScrollText,
  Search,
  Send,
  Settings2,
  ShieldCheck
} from "lucide-react";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

const FALLBACK_POLICY = `capabilities:
  - action: db.read
    resource: prod/**

  - action: db.write
    resource: prod/test_*

  - action: mcp.call
    resource: scholar/*

  - action: net.http
    resource: https://api.example.com/**
    constraint:
      method: GET
`;

type Scenario = {
  id: string;
  title: string;
  prompt: string;
};

type TimelineEvent = {
  seq: number;
  lane: "system" | "naive" | "kernel";
  type: string;
  title: string;
  detail?: string;
  request?: unknown;
  result?: { status?: string; data?: unknown; error?: string | null };
  payloads?: Array<{ label: string; value: unknown }>;
  record?: LogRecord;
  world?: WorldSnapshot;
  worlds?: { naive: WorldSnapshot; kernel: WorldSnapshot };
};

type LogRecord = {
  timestamp: string;
  action: string;
  target: string;
  status: string;
  error: string | null;
  duration_ms: number | null;
};

type WorldSnapshot = {
  tables: Record<string, { dropped: boolean; rows: unknown[] }>;
  httpCalls: unknown[];
  mcpCalls: unknown[];
};

type ManualResult = {
  result: { status: string; data?: unknown; error?: string | null };
  record: LogRecord | null;
  world: WorldSnapshot;
};

type LLMTestResult = {
  ok: boolean;
  baseUrl: string;
  model: string;
  message?: string;
  error?: string;
};

const emptyWorld: WorldSnapshot = {
  tables: {},
  httpCalls: [],
  mcpCalls: []
};

const MODEL_OPTIONS = [
  "deepseek-v4-flash",
  "gpt-5.5",
  "kimi-k2.6",
  "qwen3.6-flash",
  "glm-5.1"
];

function App() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenario, setScenario] = useState("dangerous-db");
  const [prompt, setPrompt] = useState("Clean up test data from the database");
  const [mode, setMode] = useState("comparison");
  const [policyYaml, setPolicyYaml] = useState(FALLBACK_POLICY);
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [logs, setLogs] = useState<LogRecord[]>([]);
  const [world, setWorld] = useState<WorldSnapshot>(emptyWorld);
  const [comparisonWorlds, setComparisonWorlds] = useState<{ naive?: WorldSnapshot; kernel?: WorldSnapshot }>({});
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [manualAction, setManualAction] = useState("db.write");
  const [manualTarget, setManualTarget] = useState("prod/test_orders");
  const [manualParams, setManualParams] = useState('{"sql":"DELETE FROM prod.test_orders WHERE id LIKE \\"ord_test_%\\";"}');
  const [manualResult, setManualResult] = useState<ManualResult | null>(null);
  const [llmApiKey, setLlmApiKey] = useState("");
  const [llmBaseUrl, setLlmBaseUrl] = useState("https://api.openai-proxy.org");
  const [llmModel, setLlmModel] = useState("deepseek-v4-flash");
  const [llmTesting, setLlmTesting] = useState(false);
  const [llmTestResult, setLlmTestResult] = useState<LLMTestResult | null>(null);

  useEffect(() => {
    void hydrate();
  }, []);

  const selectedScenario = useMemo(
    () => scenarios.find((item) => item.id === scenario),
    [scenario, scenarios]
  );

  const latestDecision = useMemo(
    () => [...events].reverse().find((event) => event.type === "kernel-decision"),
    [events]
  );

  async function hydrate() {
    try {
      const [scenarioResponse, policyResponse, logsResponse, worldResponse] = await Promise.all([
        fetch(`${API_BASE}/api/scenarios`),
        fetch(`${API_BASE}/api/policy/default`),
        fetch(`${API_BASE}/api/logs`),
        fetch(`${API_BASE}/api/world`)
      ]);
      const scenarioData = (await scenarioResponse.json()) as Scenario[];
      setScenarios(scenarioData);
      if (scenarioData[0]) {
        setScenario(scenarioData[0].id);
        setPrompt(scenarioData[0].prompt);
      }
      setPolicyYaml((await policyResponse.json()).policyYaml);
      setLogs(await logsResponse.json());
      setWorld(await worldResponse.json());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Failed to load demo state");
    }
  }

  async function refreshLogsAndWorld() {
    const [logsResponse, worldResponse] = await Promise.all([
      fetch(`${API_BASE}/api/logs`),
      fetch(`${API_BASE}/api/world`)
    ]);
    setLogs(await logsResponse.json());
    setWorld(await worldResponse.json());
  }

  async function refreshLogs() {
    const logsResponse = await fetch(`${API_BASE}/api/logs`);
    setLogs(await logsResponse.json());
  }

  async function runScenario() {
    setRunning(true);
    setError(null);
    setEvents([]);
    setComparisonWorlds({});
    setManualResult(null);

    try {
      const response = await fetch(`${API_BASE}/api/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scenario,
          prompt,
          mode,
          policyYaml,
          resetWorld: true,
          llmApiKey,
          llmBaseUrl,
          llmModel
        })
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const { runId } = await response.json();
      const stream = new EventSource(`${API_BASE}/api/runs/${runId}/events`);

      stream.onmessage = (message) => {
        const event = JSON.parse(message.data) as TimelineEvent;
        setEvents((current) => [...current, event]);

        if (event.record) {
          setLogs((current) => [...current, event.record as LogRecord]);
        }
        if (event.world) {
          setWorld(event.world);
        }
        if (event.worlds) {
          setComparisonWorlds(event.worlds);
          setWorld(event.worlds.kernel);
        }
        if (event.type === "done") {
          stream.close();
          setRunning(false);
          void refreshLogs();
        }
      };

      stream.onerror = () => {
        stream.close();
        setRunning(false);
        setError("SSE stream closed unexpectedly");
      };
    } catch (exc) {
      setRunning(false);
      setError(exc instanceof Error ? exc.message : "Failed to start run");
    }
  }

  async function resetWorld() {
    setError(null);
    setEvents([]);
    setComparisonWorlds({});
    setManualResult(null);
    const response = await fetch(`${API_BASE}/api/world/reset`, { method: "POST" });
    const data = await response.json();
    setWorld(data.world);
    setLogs(data.logs);
  }

  async function submitManualAction() {
    setError(null);
    let params: Record<string, unknown>;
    try {
      params = JSON.parse(manualParams);
    } catch {
      setError("Manual params must be valid JSON");
      return;
    }

    const response = await fetch(`${API_BASE}/api/kernel/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: manualAction,
        target: manualTarget,
        params,
        policyYaml
      })
    });

    if (!response.ok) {
      setError(await response.text());
      return;
    }

    const data = (await response.json()) as ManualResult;
    setManualResult(data);
    setWorld(data.world);
    await refreshLogsAndWorld();
  }

  async function testLlmConfig() {
    setError(null);
    setLlmTesting(true);
    setLlmTestResult(null);
    try {
      const response = await fetch(`${API_BASE}/api/llm/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          apiKey: llmApiKey,
          baseUrl: llmBaseUrl,
          model: llmModel
        })
      });
      const data = (await response.json()) as LLMTestResult;
      setLlmTestResult(data);
    } catch (exc) {
      setLlmTestResult({
        ok: false,
        baseUrl: llmBaseUrl,
        model: llmModel,
        error: exc instanceof Error ? exc.message : "LLM test failed"
      });
    } finally {
      setLlmTesting(false);
    }
  }

  function chooseScenario(next: string) {
    const item = scenarios.find((candidate) => candidate.id === next);
    setScenario(next);
    if (item) {
      setPrompt(item.prompt);
    }
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand-row">
          <ShieldCheck size={24} />
          <div>
            <h1>Agent Kernel Workbench</h1>
            <span>Policy · Gate · Log</span>
          </div>
        </div>

        <section className="panel control-panel">
          <div className="panel-title">
            <Settings2 size={16} />
            <h2>Run</h2>
          </div>

          <label>
            Scenario
            <select value={scenario} onChange={(event) => chooseScenario(event.target.value)}>
              {scenarios.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
            </select>
          </label>

          <label>
            Mode
            <select value={mode} onChange={(event) => setMode(event.target.value)}>
              <option value="comparison">Naive vs Kernel</option>
              <option value="kernel">Kernel only</option>
              <option value="naive">Naive only</option>
              <option value="llm">LLM agent loop if configured</option>
            </select>
          </label>

          <label>
            Prompt
            <textarea
              className="prompt-input"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
            />
          </label>

          <div className="button-row">
            <button className="primary-button" onClick={runScenario} disabled={running}>
              <Play size={16} />
              {running ? "Running" : "Run"}
            </button>
            <button className="icon-button" onClick={resetWorld} title="Reset world and logs">
              <RotateCcw size={16} />
            </button>
          </div>

          {selectedScenario ? <p className="scenario-caption">{selectedScenario.title}</p> : null}
          {error ? <p className="error-line">{error}</p> : null}
        </section>

        <section className="panel llm-panel">
          <div className="panel-title">
            <KeyRound size={16} />
            <h2>LLM Config</h2>
          </div>
          <label>
            OPENAI_API_KEY
            <input
              type="password"
              value={llmApiKey}
              onChange={(event) => setLlmApiKey(event.target.value)}
              autoComplete="off"
              placeholder="sk-..."
            />
          </label>
          <label>
            OPENAI_BASE_URL
            <input
              value={llmBaseUrl}
              onChange={(event) => setLlmBaseUrl(event.target.value)}
              placeholder="https://api.openai-proxy.org"
            />
          </label>
          <label>
            OPENAI_MODEL
            <input
              list="llm-model-options"
              value={llmModel}
              onChange={(event) => setLlmModel(event.target.value)}
              placeholder="deepseek-v4-flash"
            />
            <datalist id="llm-model-options">
              {MODEL_OPTIONS.map((model) => (
                <option key={model} value={model} />
              ))}
            </datalist>
          </label>
          <button className="secondary-button" onClick={testLlmConfig} disabled={llmTesting}>
            <KeyRound size={15} />
            {llmTesting ? "Testing" : "Test LLM"}
          </button>
          {llmTestResult ? <LLMTestStatus result={llmTestResult} /> : null}
        </section>

        <section className="panel policy-panel">
          <div className="panel-title">
            <ScrollText size={16} />
            <h2>Policy YAML</h2>
          </div>
          <textarea
            className="policy-editor"
            value={policyYaml}
            onChange={(event) => setPolicyYaml(event.target.value)}
            spellCheck={false}
          />
        </section>
      </aside>

      <section className="workspace">
        <div className="top-strip">
          <Metric icon={<Database size={16} />} label="Tables" value={String(Object.keys(world.tables).length)} />
          <Metric icon={<ScrollText size={16} />} label="Audit Records" value={String(logs.length)} />
          <Metric icon={<Network size={16} />} label="HTTP Calls" value={String(world.httpCalls.length)} />
          <Metric icon={<Search size={16} />} label="MCP Calls" value={String(world.mcpCalls.length)} />
        </div>

        <section className="comparison-grid">
          <TimelineColumn
            title="Naive Agent"
            tone="danger"
            events={events.filter((event) => event.lane === "naive")}
            world={comparisonWorlds.naive}
          />
          <TimelineColumn
            title="Kernel Agent"
            tone="safe"
            events={events.filter((event) => event.lane === "kernel")}
            world={comparisonWorlds.kernel}
          />
        </section>
      </section>

      <aside className="inspector">
        <section className="panel gate-panel">
          <div className="panel-title">
            <ShieldCheck size={16} />
            <h2>Gate Decision</h2>
          </div>
          {latestDecision ? (
            <Decision event={latestDecision} />
          ) : manualResult ? (
            <ManualDecision result={manualResult} />
          ) : (
            <EmptyState text="No kernel decision yet." />
          )}
        </section>

        <section className="panel manual-panel">
          <div className="panel-title">
            <Send size={16} />
            <h2>Manual Action</h2>
          </div>
          <div className="manual-grid">
            <label>
              Action
              <input value={manualAction} onChange={(event) => setManualAction(event.target.value)} />
            </label>
            <label>
              Target
              <input value={manualTarget} onChange={(event) => setManualTarget(event.target.value)} />
            </label>
          </div>
          <label>
            Params JSON
            <textarea
              className="params-editor"
              value={manualParams}
              onChange={(event) => setManualParams(event.target.value)}
              spellCheck={false}
            />
          </label>
          <button className="secondary-button" onClick={submitManualAction}>
            <Send size={15} />
            Submit
          </button>
        </section>

        <section className="panel world-panel">
          <div className="panel-title">
            <Database size={16} />
            <h2>World State</h2>
          </div>
          <WorldState world={world} />
        </section>

        <section className="panel log-panel">
          <div className="panel-title">
            <ScrollText size={16} />
            <h2>Audit Log</h2>
          </div>
          <AuditLog records={logs} />
        </section>
      </aside>
    </main>
  );
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="metric">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function TimelineColumn({
  title,
  tone,
  events,
  world
}: {
  title: string;
  tone: "danger" | "safe";
  events: TimelineEvent[];
  world?: WorldSnapshot;
}) {
  return (
    <section className={`lane lane-${tone}`}>
      <div className="lane-header">
        {tone === "safe" ? <ShieldCheck size={18} /> : <AlertTriangle size={18} />}
        <h2>{title}</h2>
      </div>
      <div className="timeline">
        {events.length === 0 ? <EmptyState text="Run a scenario to populate this lane." /> : null}
        {events.map((event) => (
          <TimelineItem key={`${event.lane}-${event.seq}`} event={event} />
        ))}
      </div>
      {world ? (
        <div className="lane-world">
          <WorldState world={world} compact />
        </div>
      ) : null}
    </section>
  );
}

function TimelineItem({ event }: { event: TimelineEvent }) {
  const status = event.result?.status ?? event.record?.status;
  return (
    <article className="timeline-item">
      <div className="timeline-status">
        {status === "OK" ? <CheckCircle2 size={16} /> : status === "DENIED" ? <Ban size={16} /> : <Settings2 size={16} />}
      </div>
      <div className="timeline-body">
        <div className="event-title-row">
          <h3>{event.title}</h3>
          {status ? <span className={`status-pill status-${status.toLowerCase()}`}>{status}</span> : null}
        </div>
        {event.detail ? <p>{event.detail}</p> : null}
        {event.payloads?.length ? (
          <div className="payload-stack">
            {event.payloads.map((payload, index) => (
              <PayloadBlock key={`${event.seq}-${payload.label}-${index}`} label={payload.label} value={payload.value} />
            ))}
          </div>
        ) : (
          <>
            {event.request ? <JsonBlock value={event.request} /> : null}
            {event.result ? <JsonBlock value={event.result} /> : null}
          </>
        )}
      </div>
    </article>
  );
}

function PayloadBlock({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="payload-block">
      <div className="payload-label">{label}</div>
      {typeof value === "string" ? <pre className="text-block">{value}</pre> : <JsonBlock value={value} />}
    </div>
  );
}

function Decision({ event }: { event: TimelineEvent }) {
  return (
    <div className="decision-stack">
      <div className={`decision-badge decision-${event.result?.status?.toLowerCase() ?? "unknown"}`}>
        {event.result?.status === "OK" ? <CheckCircle2 size={18} /> : <Ban size={18} />}
        <strong>{event.result?.status ?? "UNKNOWN"}</strong>
      </div>
      {event.record ? <JsonBlock value={event.record} /> : null}
    </div>
  );
}

function ManualDecision({ result }: { result: ManualResult }) {
  return (
    <div className="decision-stack">
      <div className={`decision-badge decision-${result.result.status.toLowerCase()}`}>
        {result.result.status === "OK" ? <CheckCircle2 size={18} /> : <Ban size={18} />}
        <strong>{result.result.status}</strong>
      </div>
      {result.record ? <JsonBlock value={result.record} /> : null}
    </div>
  );
}

function LLMTestStatus({ result }: { result: LLMTestResult }) {
  return (
    <div className={`llm-test-result ${result.ok ? "llm-test-ok" : "llm-test-error"}`}>
      <div className="llm-test-heading">
        {result.ok ? <CheckCircle2 size={15} /> : <Ban size={15} />}
        <strong>{result.ok ? "Connection OK" : "Connection failed"}</strong>
      </div>
      <span>{result.model}</span>
      <span>{result.baseUrl}</span>
      {result.message ? <span>{result.message}</span> : null}
      {result.error ? <span>{result.error}</span> : null}
    </div>
  );
}

function WorldState({ world, compact = false }: { world: WorldSnapshot; compact?: boolean }) {
  const tables = Object.entries(world.tables);
  if (tables.length === 0) {
    return <EmptyState text="World state is empty." />;
  }
  return (
    <div className={compact ? "world-list compact" : "world-list"}>
      {tables.map(([name, table]) => (
        <div className="table-row" key={name}>
          <span>{name}</span>
          <strong className={table.dropped ? "dropped" : ""}>
            {table.dropped ? "dropped" : `${table.rows.length} rows`}
          </strong>
        </div>
      ))}
    </div>
  );
}

function AuditLog({ records }: { records: LogRecord[] }) {
  if (records.length === 0) {
    return <EmptyState text="No audit records." />;
  }
  return (
    <div className="audit-list">
      {[...records].reverse().slice(0, 12).map((record, index) => (
        <div className="audit-row" key={`${record.timestamp}-${index}`}>
          <span className={`status-dot dot-${record.status.toLowerCase()}`} />
          <div>
            <strong>{record.status}</strong>
            <span>
              {record.action} · {record.target}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

function JsonBlock({ value }: { value: unknown }) {
  return <pre className="json-block">{JSON.stringify(value, null, 2)}</pre>;
}

function EmptyState({ text }: { text: string }) {
  return <div className="empty-state">{text}</div>;
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
