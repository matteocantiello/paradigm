import { PHASE_DISPLAY_ORDER, PHASE_LABELS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { Check } from "lucide-react";

interface PhaseTrackerProps {
  currentPhase: string | null;
  completedPhases: string[];
}

export function PhaseTracker({ currentPhase, completedPhases }: PhaseTrackerProps) {
  return (
    <div className="flex items-center gap-0 overflow-x-auto px-3 py-3">
      {PHASE_DISPLAY_ORDER.map((phase, i) => {
        const isCompleted = completedPhases.includes(phase);
        const isCurrent = phase === currentPhase;
        const isPast = isCompleted && !isCurrent;
        return (
          <div key={phase} className="flex items-center">
            {i > 0 && (
              <div
                className={cn(
                  "h-0.5 w-6 mx-0",
                  isPast
                    ? "bg-gradient-to-r from-emerald-500 to-emerald-500"
                    : isCurrent
                      ? "bg-gradient-to-r from-emerald-500 to-primary"
                      : "bg-border"
                )}
              />
            )}
            <div
              className={cn(
                "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium whitespace-nowrap transition-all",
                isCurrent && "bg-primary/15 text-primary ring-2 ring-primary/30 shadow-sm shadow-primary/10",
                isPast && "text-emerald-400",
                !isCurrent && !isCompleted && "text-muted-foreground/40"
              )}
            >
              {isPast ? (
                <div className="flex items-center justify-center h-4 w-4 rounded-full bg-emerald-500/20">
                  <Check className="h-2.5 w-2.5 text-emerald-500" />
                </div>
              ) : isCurrent ? (
                <div className="relative flex items-center justify-center h-4 w-4">
                  <div className="h-2 w-2 rounded-full bg-primary" />
                  <div className="absolute inset-0 rounded-full border border-primary/50 animate-ping" style={{ animationDuration: "2s" }} />
                </div>
              ) : (
                <div className="h-4 w-4 rounded-full border border-muted-foreground/20" />
              )}
              <span>{PHASE_LABELS[phase] ?? phase}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
