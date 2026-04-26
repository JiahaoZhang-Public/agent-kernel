import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Play, RotateCcw, Loader2 } from "lucide-react";
import type { Scenario, RunMode } from "@/lib/types";

export function ScenarioPanel({
  scenarios,
  scenario,
  onScenarioChange,
  prompt,
  onPromptChange,
  mode,
  onModeChange,
  running,
  onRun,
  onReset,
}: {
  scenarios: Scenario[];
  scenario: string;
  onScenarioChange: (id: string) => void;
  prompt: string;
  onPromptChange: (next: string) => void;
  mode: RunMode;
  onModeChange: (next: RunMode) => void;
  running: boolean;
  onRun: () => void;
  onReset: () => void;
}) {
  return (
    <Card>
      <CardContent className="grid gap-3 p-4 lg:grid-cols-[200px_180px_1fr_auto]">
        <div className="space-y-1">
          <Label>Scenario</Label>
          <Select value={scenario} onValueChange={onScenarioChange}>
            <SelectTrigger>
              <SelectValue placeholder="Choose scenario" />
            </SelectTrigger>
            <SelectContent>
              {scenarios.map((s) => (
                <SelectItem key={s.id} value={s.id}>
                  {s.title}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label>Mode</Label>
          <Select value={mode} onValueChange={(v) => onModeChange(v as RunMode)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="comparison">Comparison</SelectItem>
              <SelectItem value="kernel">Kernel only</SelectItem>
              <SelectItem value="naive">Naive only</SelectItem>
              <SelectItem value="llm">LLM-driven</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label>Prompt</Label>
          <Input
            value={prompt}
            onChange={(e) => onPromptChange(e.target.value)}
            placeholder="What should the agent attempt?"
          />
        </div>
        <div className="flex items-end gap-2">
          <Button onClick={onRun} disabled={running} size="default">
            {running ? <Loader2 className="animate-spin" /> : <Play />}
            {running ? "Running..." : "Run"}
          </Button>
          <Button variant="outline" onClick={onReset} disabled={running}>
            <RotateCcw /> Reset
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
