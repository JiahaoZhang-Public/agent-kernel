import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Topbar, type LlmStatus } from "@/components/workbench/Topbar";
import { LeftNav, MobileNav, type NavKey } from "@/components/workbench/LeftNav";
import { SummaryHeader } from "@/components/workbench/SummaryHeader";
import { ScenarioPanel } from "@/components/workbench/ScenarioPanel";
import { TimelineGantt } from "@/components/workbench/TimelineGantt";
import { TimelineList } from "@/components/workbench/TimelineList";
import { InspectorPanel } from "@/components/workbench/InspectorPanel";
import { PolicyEditor } from "@/components/workbench/PolicyEditor";
import { PolicyRuleTrace } from "@/components/workbench/PolicyRuleTrace";
import { ManualActionCard } from "@/components/workbench/ManualActionCard";
import { AuditLogTable } from "@/components/workbench/AuditLogTable";
import { LLMConfigSheet, type LlmCreds } from "@/components/workbench/LLMConfigSheet";
import { RollbackButton } from "@/components/workbench/RollbackButton";
import { useScenarioRun } from "@/hooks/useScenarioRun";
import { useWorld } from "@/hooks/useWorld";
import { useLogs } from "@/hooks/useLogs";
import * as api from "@/lib/api";
import type { RunMode, Scenario, TimelineEvent } from "@/lib/types";
import { FALLBACK_POLICY } from "@/lib/policyMatch";

const SS_LLM_KEY = "akw.llm";

function readSessionCreds(): LlmCreds {
  try {
    const raw = sessionStorage.getItem(SS_LLM_KEY);
    if (!raw) throw new Error();
    const parsed = JSON.parse(raw) as Partial<LlmCreds>;
    return {
      apiKey: parsed.apiKey ?? "",
      baseUrl: parsed.baseUrl ?? "https://api.openai-proxy.org",
      model: parsed.model ?? "deepseek-v4-flash",
    };
  } catch {
    return {
      apiKey: "",
      baseUrl: "https://api.openai-proxy.org",
      model: "deepseek-v4-flash",
    };
  }
}

export default function App() {
  const [activeTab, setActiveTab] = useState<NavKey>("run");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenario, setScenario] = useState("dangerous-db");
  const [prompt, setPrompt] = useState("Clean up test data from the database");
  const [mode, setMode] = useState<RunMode>("comparison");
  const [policyYaml, setPolicyYaml] = useState<string>(FALLBACK_POLICY);
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);
  const [llmOpen, setLlmOpen] = useState(false);
  const [llmCreds, setLlmCreds] = useState<LlmCreds>(() => readSessionCreds());
  const [llmStatus, setLlmStatus] = useState<LlmStatus>("untested");
  const [resetting, setResetting] = useState(false);

  const world = useWorld();
  const logs = useLogs();
  const run = useScenarioRun({
    onWorld: (w) => world.setWorld(w),
    onLog: (r) => logs.append(r),
  });

  // Persist creds
  useEffect(() => {
    try {
      sessionStorage.setItem(SS_LLM_KEY, JSON.stringify(llmCreds));
    } catch {
      // ignore
    }
  }, [llmCreds]);

  // Hydrate scenarios + default policy
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [list, policy] = await Promise.all([
          api.getScenarios(),
          api.getDefaultPolicy(),
        ]);
        if (cancelled) return;
        setScenarios(list);
        if (policy?.policyYaml) setPolicyYaml(policy.policyYaml);
        if (list.length && !list.some((s) => s.id === scenario)) {
          setScenario(list[0].id);
          setPrompt(list[0].prompt);
        }
      } catch (e) {
        toast.error("Failed to load scenarios", {
          description: e instanceof Error ? e.message : String(e),
        });
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleScenarioChange = (id: string) => {
    setScenario(id);
    const found = scenarios.find((s) => s.id === id);
    if (found) setPrompt(found.prompt);
  };

  const handleRun = useCallback(() => {
    setSelectedSeq(null);
    run.runScenario({
      scenario,
      prompt,
      mode,
      policyYaml,
      llm: llmCreds.apiKey
        ? {
            apiKey: llmCreds.apiKey,
            baseUrl: llmCreds.baseUrl,
            model: llmCreds.model,
          }
        : undefined,
    });
  }, [scenario, prompt, mode, policyYaml, llmCreds, run]);

  const handleResetWorld = useCallback(async () => {
    setResetting(true);
    try {
      const out = await world.reset();
      if (out) {
        logs.replace(out.logs);
        run.reset();
        setSelectedSeq(null);
        toast.success("World reset", {
          description: "Tables, calls and audit log cleared.",
        });
      }
    } finally {
      setResetting(false);
    }
  }, [world, logs, run]);

  const selectEvent = useCallback((ev: TimelineEvent | null) => {
    setSelectedSeq(ev?.seq ?? null);
  }, []);

  const selectedEvent = useMemo<TimelineEvent | null>(
    () =>
      selectedSeq !== null
        ? run.events.find((e) => e.seq === selectedSeq) ?? null
        : null,
    [selectedSeq, run.events],
  );

  const policyTraceRequest =
    selectedEvent?.lane === "kernel" ? selectedEvent.request ?? null : null;

  const trailingFor = useCallback(
    (ev: TimelineEvent): React.ReactNode => {
      const recordId = ev.record_id ?? ev.result?.record_id ?? null;
      if (
        ev.lane !== "kernel" ||
        ev.result?.status !== "OK" ||
        !recordId
      ) {
        return null;
      }
      const label =
        ev.request?.action && ev.request?.target
          ? `${ev.request.action} ${ev.request.target}`
          : undefined;
      return (
        <RollbackButton
          recordId={recordId}
          policyYaml={policyYaml}
          actionLabel={label}
          onRolledBack={({ world: nextWorld, record }) => {
            world.setWorld(nextWorld);
            if (record) logs.append(record);
            run.pushEvent({
              seq: (run.lastSeq ?? 0) + 1,
              lane: "kernel",
              type: "rollback",
              title: "Action rolled back via reversible layer",
              detail: label
                ? `${label} restored from snapshot.`
                : "Snapshot restored.",
              result: { status: "OK" },
              record: record ?? undefined,
              world: nextWorld,
            });
          }}
        />
      );
    },
    [policyYaml, world, logs, run],
  );

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      <Topbar
        running={run.running}
        lastSeq={run.lastSeq}
        durationMs={run.durationMs}
        llmStatus={llmStatus}
        llmModel={llmCreds.model}
        onOpenSettings={() => setLlmOpen(true)}
        onResetWorld={handleResetWorld}
        resetting={resetting}
      />
      <MobileNav active={activeTab} onChange={(k) => setActiveTab(k)} />
      <div className="flex flex-1 min-h-0">
        <LeftNav active={activeTab} onChange={(k) => setActiveTab(k)} />
        <main className="flex flex-1 min-w-0 overflow-hidden">
          <div className="flex flex-1 min-w-0 flex-col overflow-y-auto">
            <div className="space-y-3 p-4">
              <SummaryHeader
                events={run.events}
                logs={logs.logs}
                comparison={run.comparisonWorlds}
              />

              <Tabs
                value={activeTab}
                onValueChange={(v) => setActiveTab(v as NavKey)}
              >
                <TabsContent value="run" className="space-y-3 mt-0">
                  <ScenarioPanel
                    scenarios={scenarios}
                    scenario={scenario}
                    onScenarioChange={handleScenarioChange}
                    prompt={prompt}
                    onPromptChange={setPrompt}
                    mode={mode}
                    onModeChange={setMode}
                    running={run.running}
                    onRun={handleRun}
                    onReset={() => {
                      run.reset();
                      setSelectedSeq(null);
                    }}
                  />
                  {run.error ? (
                    <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
                      {run.error}
                    </div>
                  ) : null}
                  <TimelineGantt
                    events={run.events}
                    selectedSeq={selectedSeq}
                    onSelect={selectEvent}
                  />
                  <TimelineList
                    events={run.events}
                    selectedSeq={selectedSeq}
                    onSelect={selectEvent}
                    trailingFor={trailingFor}
                  />
                </TabsContent>
                <TabsContent value="policy" className="space-y-3 mt-0">
                  <div className="grid gap-3 lg:grid-cols-2">
                    <PolicyEditor
                      value={policyYaml}
                      onChange={setPolicyYaml}
                      rows={20}
                    />
                    <PolicyRuleTrace
                      policyYaml={policyYaml}
                      request={policyTraceRequest}
                      verdict={selectedEvent?.result?.status}
                    />
                  </div>
                </TabsContent>
                <TabsContent value="manual" className="space-y-3 mt-0">
                  <div className="grid gap-3 lg:grid-cols-2">
                    <ManualActionCard
                      policyYaml={policyYaml}
                      onResult={(r) => {
                        world.setWorld(r.world);
                        logs.append(r.record);
                        toast.message("Manual action complete", {
                          description: `${r.request.action} ${r.request.target} → ${r.result.status}`,
                        });
                      }}
                    />
                    <PolicyRuleTrace
                      policyYaml={policyYaml}
                      request={policyTraceRequest}
                      verdict={selectedEvent?.result?.status}
                    />
                  </div>
                </TabsContent>
                <TabsContent value="history" className="space-y-3 mt-0">
                  <AuditLogTable logs={logs.logs} />
                  <div className="flex justify-end">
                    <Button variant="outline" size="sm" onClick={logs.refresh}>
                      Refresh
                    </Button>
                  </div>
                </TabsContent>
              </Tabs>
            </div>
          </div>
          <aside className="hidden w-[360px] shrink-0 overflow-hidden border-l border-border bg-card xl:flex xl:flex-col">
            <div className="shrink-0 border-b border-border px-4 py-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Inspector
            </div>
            <div className="flex-1 min-h-0 min-w-0 overflow-hidden">
              <InspectorPanel
                events={run.events}
                selectedSeq={selectedSeq}
                policyYaml={policyYaml}
                worldKernel={world.world}
                trailingFor={trailingFor}
              />
            </div>
          </aside>
        </main>
      </div>
      <LLMConfigSheet
        open={llmOpen}
        onOpenChange={setLlmOpen}
        creds={llmCreds}
        onCredsChange={setLlmCreds}
        status={llmStatus}
        onStatusChange={setLlmStatus}
      />
    </div>
  );
}
