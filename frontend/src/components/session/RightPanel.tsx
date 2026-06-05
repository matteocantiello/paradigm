import { EventLog } from "./EventLog";
import { KnowledgePanel } from "./KnowledgePanel";
import { useUiStore } from "@/stores/uiStore";
import type { ActivityEvent, Notification, KnowledgeState } from "@/stores/sessionStore";
import { cn } from "@/lib/utils";

interface RightPanelProps {
  activityEvents: ActivityEvent[];
  notifications: Notification[];
  knowledge: KnowledgeState;
}

export function RightPanel({ activityEvents, notifications, knowledge }: RightPanelProps) {
  const tab = useUiStore((s) => s.rightPanelTab);
  const setTab = useUiStore((s) => s.setRightPanelTab);

  const hypothesisCount = knowledge.hypotheses.length;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Pill-style tab bar */}
      <div className="flex gap-1 p-2 bg-background shrink-0">
        <button
          onClick={() => setTab("events")}
          className={cn(
            "px-3 py-1.5 text-xs font-medium rounded-full transition-all",
            tab === "events"
              ? "bg-primary/15 text-primary"
              : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
          )}
        >
          Events
        </button>
        <button
          onClick={() => setTab("knowledge")}
          className={cn(
            "px-3 py-1.5 text-xs font-medium rounded-full transition-all flex items-center gap-1.5",
            tab === "knowledge"
              ? "bg-primary/15 text-primary"
              : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
          )}
        >
          Knowledge
          {hypothesisCount > 0 && (
            <span className="text-[10px] bg-primary/20 text-primary px-1.5 py-0 rounded-full tabular-nums">
              {hypothesisCount}
            </span>
          )}
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {tab === "events" ? (
          <EventLog activityEvents={activityEvents} notifications={notifications} />
        ) : (
          <KnowledgePanel knowledge={knowledge} />
        )}
      </div>
    </div>
  );
}
