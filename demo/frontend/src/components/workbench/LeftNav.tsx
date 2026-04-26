import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import {
  Play,
  ScrollText,
  Send,
  History,
  ShieldCheck,
} from "lucide-react";

export type NavKey = "run" | "policy" | "manual" | "history";

const NAV_ITEMS: Array<{ key: NavKey; label: string; Icon: typeof Play }> = [
  { key: "run", label: "Run", Icon: Play },
  { key: "policy", label: "Policy", Icon: ShieldCheck },
  { key: "manual", label: "Manual", Icon: Send },
  { key: "history", label: "Audit log", Icon: ScrollText },
];

export function LeftNav({
  active,
  onChange,
}: {
  active: NavKey;
  onChange: (next: NavKey) => void;
}) {
  return (
    <TooltipProvider delayDuration={150}>
      <nav
        data-testid="left-nav"
        className="hidden h-full w-16 shrink-0 flex-col items-center gap-1 border-r border-border bg-card py-3 lg:flex"
      >
        {NAV_ITEMS.map(({ key, label, Icon }) => {
          const isActive = active === key;
          return (
            <Tooltip key={key}>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  aria-label={label}
                  aria-current={isActive ? "page" : undefined}
                  onClick={() => onChange(key)}
                  className={cn(
                    "relative flex h-10 w-10 items-center justify-center rounded-md transition-colors focus-visible:outline-none focus-visible:shadow-focus",
                    isActive
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {isActive ? (
                    <span
                      aria-hidden
                      className="absolute right-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-l bg-primary"
                    />
                  ) : null}
                </button>
              </TooltipTrigger>
              <TooltipContent side="right">{label}</TooltipContent>
            </Tooltip>
          );
        })}
        <div className="mt-auto" />
        <div className="flex flex-col items-center gap-1 border-t border-border pt-2 text-[10px] text-muted-foreground">
          <History className="h-3.5 w-3.5" />
        </div>
      </nav>
    </TooltipProvider>
  );
}

export function MobileNav({
  active,
  onChange,
}: {
  active: NavKey;
  onChange: (next: NavKey) => void;
}) {
  return (
    <nav
      aria-label="Workbench navigation"
      className="flex w-full items-center gap-1 overflow-x-auto border-b border-border bg-card px-2 py-1 lg:hidden"
    >
      {NAV_ITEMS.map(({ key, label, Icon }) => {
        const isActive = active === key;
        return (
          <button
            key={key}
            type="button"
            onClick={() => onChange(key)}
            className={cn(
              "flex shrink-0 items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium",
              isActive
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        );
      })}
    </nav>
  );
}
