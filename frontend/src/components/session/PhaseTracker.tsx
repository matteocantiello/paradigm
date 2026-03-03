import { PHASE_DISPLAY_ORDER, PHASE_ICONS, PHASE_LABELS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { Check } from "lucide-react";

interface PhaseTrackerProps {
  currentPhase: string | null;
  completedPhases: string[];
}

export function PhaseTracker({ currentPhase, completedPhases }: PhaseTrackerProps) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto px-2 py-2">
      {PHASE_DISPLAY_ORDER.map((phase, i) => {
        const isCompleted = completedPhases.includes(phase);
        const isCurrent = phase === currentPhase;
        return (
          <div key={phase} className="flex items-center">
            {i > 0 && (
              <div
                className={cn(
                  "h-px w-4 mx-0.5",
                  isCompleted ? "bg-green-500" : "bg-border"
                )}
              />
            )}
            <div
              className={cn(
                "flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium whitespace-nowrap transition-colors",
                isCurrent && "bg-primary/10 text-primary ring-1 ring-primary/30",
                isCompleted && !isCurrent && "text-green-400",
                !isCurrent && !isCompleted && "text-muted-foreground/50"
              )}
            >
              {isCompleted && !isCurrent ? (
                <Check className="h-3 w-3 text-green-500" />
              ) : (
                <span className="text-xs">{PHASE_ICONS[phase] ?? ""}</span>
              )}
              <span>{PHASE_LABELS[phase] ?? phase}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
