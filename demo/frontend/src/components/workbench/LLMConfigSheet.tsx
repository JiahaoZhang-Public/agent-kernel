import { useState } from "react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { Beaker, KeyRound, Loader2 } from "lucide-react";
import * as api from "@/lib/api";
import type { LLMTestResult } from "@/lib/types";
import { MODEL_OPTIONS } from "@/lib/types";

export type LlmCreds = {
  apiKey: string;
  baseUrl: string;
  model: string;
};

export function LLMConfigSheet({
  open,
  onOpenChange,
  creds,
  onCredsChange,
  status,
  onStatusChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  creds: LlmCreds;
  onCredsChange: (next: LlmCreds) => void;
  status: "untested" | "ok" | "error";
  onStatusChange: (next: "untested" | "ok" | "error") => void;
}) {
  const [pending, setPending] = useState(false);
  const [lastResult, setLastResult] = useState<LLMTestResult | null>(null);

  const handleTest = async () => {
    setPending(true);
    try {
      const result = await api.testLlm({
        apiKey: creds.apiKey || undefined,
        baseUrl: creds.baseUrl || undefined,
        model: creds.model || undefined,
      });
      setLastResult(result);
      if (result.ok) {
        onStatusChange("ok");
        toast.success("LLM connection OK", {
          description:
            result.message ?? `${result.model} via ${result.baseUrl}`,
        });
      } else {
        onStatusChange("error");
        toast.error("LLM test failed", { description: result.error });
      }
    } catch (e) {
      onStatusChange("error");
      const msg = e instanceof Error ? e.message : String(e);
      setLastResult({ ok: false, baseUrl: creds.baseUrl, model: creds.model, error: msg });
      toast.error("LLM test failed", { description: msg });
    } finally {
      setPending(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <KeyRound className="h-4 w-4" /> LLM configuration
          </SheetTitle>
          <SheetDescription>
            Used by the LLM-driven scenario mode and the planner. Credentials
            are kept in this session only — not stored to disk.
          </SheetDescription>
        </SheetHeader>
        <div className="mt-6 space-y-4">
          <div className="space-y-1">
            <Label>API key</Label>
            <Input
              type="password"
              autoComplete="off"
              value={creds.apiKey}
              onChange={(e) =>
                onCredsChange({ ...creds, apiKey: e.target.value })
              }
              placeholder="sk-..."
            />
          </div>
          <div className="space-y-1">
            <Label>Base URL</Label>
            <Input
              value={creds.baseUrl}
              onChange={(e) =>
                onCredsChange({ ...creds, baseUrl: e.target.value })
              }
              placeholder="https://api.openai-proxy.org"
            />
          </div>
          <div className="space-y-1">
            <Label>Model</Label>
            <Select
              value={creds.model}
              onValueChange={(v) => onCredsChange({ ...creds, model: v })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MODEL_OPTIONS.map((m) => (
                  <SelectItem key={m} value={m}>
                    {m}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center justify-between gap-2">
            <Button
              onClick={handleTest}
              disabled={pending}
              data-testid="llm-test-button"
            >
              {pending ? (
                <Loader2 className="animate-spin" />
              ) : (
                <Beaker />
              )}
              {pending ? "Testing..." : "Test connection"}
            </Button>
            <Badge
              variant={
                status === "ok"
                  ? "success"
                  : status === "error"
                    ? "destructive"
                    : "secondary"
              }
            >
              {status === "ok"
                ? "Verified"
                : status === "error"
                  ? "Failed"
                  : "Untested"}
            </Badge>
          </div>
          {lastResult ? (
            <div
              className="rounded-md border border-border bg-muted/30 p-3 text-xs"
              data-testid="llm-test-result"
            >
              <div className="font-medium">
                {lastResult.ok ? "Success" : "Error"}
              </div>
              <div className="mt-1 text-muted-foreground">
                {lastResult.message ?? lastResult.error ?? "No details"}
              </div>
              <div className="mt-2 font-mono text-[11px] text-muted-foreground">
                {lastResult.baseUrl} · {lastResult.model}
              </div>
            </div>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
