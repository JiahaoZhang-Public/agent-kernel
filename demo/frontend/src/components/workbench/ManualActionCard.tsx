import { useState } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Send } from "lucide-react";
import { toast } from "sonner";
import * as api from "@/lib/api";
import type { ManualResult } from "@/lib/types";
import { CodeBlock } from "./CodeBlock";
import { StatusBadge } from "./StatusBadge";

export function ManualActionCard({
  policyYaml,
  onResult,
}: {
  policyYaml: string;
  onResult?: (r: ManualResult) => void;
}) {
  const [action, setAction] = useState("db.write");
  const [target, setTarget] = useState("prod/test_orders");
  const [params, setParams] = useState(
    '{"sql":"DELETE FROM prod.test_orders WHERE id LIKE \\"ord_test_%\\";"}',
  );
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<ManualResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setPending(true);
    setError(null);
    try {
      const parsed = params.trim() ? JSON.parse(params) : {};
      const out = await api.submitManual({
        action,
        target,
        params: parsed,
        policyYaml,
      });
      setResult(out);
      onResult?.(out);
      toast.success(
        `Kernel returned ${out.result.status}`,
        out.result.error ? { description: out.result.error } : undefined,
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      toast.error("Manual action failed", { description: msg });
    } finally {
      setPending(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Manual kernel.submit</CardTitle>
        <CardDescription>
          Send a single ActionRequest through the kernel without running an
          agent.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-2 sm:grid-cols-2">
          <div className="space-y-1">
            <Label>Action</Label>
            <Input
              value={action}
              onChange={(e) => setAction(e.target.value)}
              placeholder="db.write"
              className="font-mono text-sm"
            />
          </div>
          <div className="space-y-1">
            <Label>Target</Label>
            <Input
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              placeholder="prod/test_*"
              className="font-mono text-sm"
            />
          </div>
        </div>
        <div className="space-y-1">
          <Label>Params (JSON)</Label>
          <Textarea
            value={params}
            onChange={(e) => setParams(e.target.value)}
            rows={3}
          />
        </div>
        <div className="flex items-center justify-between gap-2">
          <Button onClick={submit} disabled={pending}>
            <Send /> {pending ? "Submitting..." : "Submit"}
          </Button>
          {result?.result?.status ? (
            <StatusBadge status={result.result.status} />
          ) : null}
        </div>
        {error ? (
          <div className="rounded border border-destructive/30 bg-destructive/5 px-2 py-1.5 text-xs text-destructive">
            {error}
          </div>
        ) : null}
        {result ? (
          <div className="space-y-2">
            <div className="space-y-1">
              <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                Result
              </div>
              <CodeBlock value={result.result} />
            </div>
            {result.record ? (
              <div className="space-y-1">
                <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                  Audit record
                </div>
                <CodeBlock value={result.record} />
              </div>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
