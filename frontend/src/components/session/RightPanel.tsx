import { EventLog } from "./EventLog";
import { KnowledgePanel } from "./KnowledgePanel";
import { useUiStore } from "@/stores/uiStore";
import type { Notification, KnowledgeState } from "@/stores/sessionStore";
import { cn } from "@/lib/utils";

interface RightPanelProps {
  notifications: Notification[];
  knowledge: KnowledgeState;
}

export function RightPanel({ notifications, knowledge }: RightPanelProps) {
  const tab = useUiStore((s) => s.rightPanelTab);
  const setTab = useUiStore((s) => s.setRightPanelTab);

  const hypothesisCount = knowledge.hypotheses.length;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Tab bar */}
      <div className="flex border-b border-border bg-background shrink-0">
        <button
          onClick={() => setTab("events")}
          className={cn(
            "px-3 py-1.5 text-xs font-medium transition-colors",
            tab === "events"
              ? "text-foreground border-b-2 border-indigo-500"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          Events
        </button>
        <button
          onClick={() => setTab("knowledge")}
          className={cn(
            "px-3 py-1.5 text-xs font-medium transition-colors flex items-center gap-1.5",
            tab === "knowledge"
              ? "text-foreground border-b-2 border-indigo-500"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          Knowledge
          {hypothesisCount > 0 && (
            <span className="text-[10px] bg-indigo-500/20 text-indigo-300 px-1.5 py-0 rounded-full tabular-nums">
              {hypothesisCount}
            </span>
          )}
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {tab === "events" ? (
          <EventLog notifications={notifications} />
        ) : (
          <KnowledgePanel knowledge={knowledge} />
        )}
      </div>
    </div>
  );
}
