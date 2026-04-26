import { Badge } from "@/components/ui/badge";
import { statusTone } from "@/lib/format";
import { CheckCircle2, Ban, AlertTriangle, Circle } from "lucide-react";

export function StatusBadge({
  status,
  showIcon = true,
}: {
  status: string | null | undefined;
  showIcon?: boolean;
}) {
  const tone = statusTone(status);
  const variant = tone === "muted" ? "secondary" : tone;
  const Icon =
    tone === "success"
      ? CheckCircle2
      : tone === "destructive"
        ? Ban
        : tone === "warning"
          ? AlertTriangle
          : Circle;
  return (
    <Badge variant={variant as never}>
      {showIcon ? <Icon className="h-3 w-3" /> : null}
      <span>{status ?? "—"}</span>
    </Badge>
  );
}
