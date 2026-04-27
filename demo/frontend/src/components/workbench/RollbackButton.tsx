import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { RotateCcw, Loader2 } from "lucide-react";
import { toast } from "sonner";
import * as api from "@/lib/api";
import type { LogRecord, WorldSnapshot } from "@/lib/types";

export function RollbackButton({
  recordId,
  policyYaml,
  actionLabel,
  onRolledBack,
  size = "xs",
  variant = "outline",
}: {
  recordId: string;
  policyYaml: string;
  actionLabel?: string;
  onRolledBack: (payload: {
    world: WorldSnapshot;
    record: LogRecord | null;
    recordId: string;
  }) => void;
  size?: "xs" | "sm" | "default";
  variant?: "outline" | "ghost" | "default" | "secondary" | "destructive";
}) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);

  const handleConfirm = async () => {
    setPending(true);
    try {
      const out = await api.rollback({ recordId, policyYaml });
      if (out.result.status === "OK") {
        onRolledBack({
          world: out.world,
          record: out.record,
          recordId,
        });
        toast.success("Action rolled back", {
          description: actionLabel ?? "World state restored.",
        });
        setOpen(false);
      } else {
        toast.error("Rollback failed", {
          description: out.result.error ?? out.result.status,
        });
      }
    } catch (e) {
      toast.error("Rollback request failed", {
        description: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setPending(false);
    }
  };

  return (
    <>
      <Button
        size={size}
        variant={variant}
        onClick={(e) => {
          e.stopPropagation();
          setOpen(true);
        }}
        className="border-warning/50 text-warning hover:bg-warning/10 hover:text-warning"
      >
        <RotateCcw />
        Rollback
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rollback this action?</DialogTitle>
            <DialogDescription>
              The kernel will restore the table to its prior state and append a
              new audit record for the rollback. The original action remains
              logged.
            </DialogDescription>
          </DialogHeader>
          {actionLabel ? (
            <div className="rounded border border-border bg-muted/40 px-3 py-2 font-mono text-xs">
              {actionLabel}
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)} disabled={pending}>
              Cancel
            </Button>
            <Button onClick={handleConfirm} disabled={pending} variant="default">
              {pending ? <Loader2 className="animate-spin" /> : <RotateCcw />}
              {pending ? "Rolling back..." : "Confirm rollback"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
