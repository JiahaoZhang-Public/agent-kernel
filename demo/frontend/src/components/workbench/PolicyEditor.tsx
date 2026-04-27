import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { ShieldCheck } from "lucide-react";

export function PolicyEditor({
  value,
  onChange,
  rows = 14,
  description,
}: {
  value: string;
  onChange: (next: string) => void;
  rows?: number;
  description?: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="h-3.5 w-3.5 text-muted-foreground" /> Capability
          policy (YAML)
        </CardTitle>
        <CardDescription>
          {description ??
            "Default-deny allow-list. Each rule binds an action + glob resource (+ optional constraint)."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <Label>policy.yaml</Label>
        <Textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={rows}
          className="text-xs"
          spellCheck={false}
        />
      </CardContent>
    </Card>
  );
}
