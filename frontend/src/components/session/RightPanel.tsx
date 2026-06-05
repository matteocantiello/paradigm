import { EventLog } from "./EventLog";
import { KnowledgePanel } from "./KnowledgePanel";
import { DraftPanel } from "./DraftPanel";
import { ExperimentPanel } from "./ExperimentPanel";
import { useUiStore, type RightPanelTab } from "@/stores/uiStore";
import type {
  ActivityEvent,
  Notification,
  KnowledgeState,
  LiveDraft,
  ExperimentRun,
} from "@/stores/sessionStore";
import { cn } from "@/lib/utils";

interface RightPanelProps {
  activityEvents: ActivityEvent[];
  notifications: Notification[];
  knowledge: KnowledgeState;
  draft: LiveDraft;
  experiments: ExperimentRun[];
}

function TabButton({
  id,
  label,
  count,
  active,
  onClick,
}: {
  id: RightPanelTab;
  label: string;
  count?: number;
  active: boolean;
  onClick: (id: RightPanelTab) => void;
}) {
  return (
    <button
      onClick={() => onClick(id)}
      className={cn(
        "px-3 py-1.5 text-xs font-medium rounded-full transition-all flex items-center gap-1.5",
        active
          ? "bg-primary/15 text-primary"
          : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
      )}
    >
      {label}
      {count != null && count > 0 && (
        <span className="text-[10px] bg-primary/20 text-primary px-1.5 py-0 rounded-full tabular-nums">
          {count}
        </span>
      )}
    </button>
  );
}

export function RightPanel({
  activityEvents,
  notifications,
  knowledge,
  draft,
  experiments,
}: RightPanelProps) {
  const tab = useUiStore((s) => s.rightPanelTab);
  const setTab = useUiStore((s) => s.setRightPanelTab);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Pill-style tab bar */}
      <div className="flex flex-wrap gap-1 p-2 bg-background shrink-0">
        <TabButton id="events" label="Events" active={tab === "events"} onClick={setTab} />
        <TabButton
          id="knowledge"
          label="Knowledge"
          count={knowledge.hypotheses.length}
          active={tab === "knowledge"}
          onClick={setTab}
        />
        <TabButton
          id="draft"
          label="Draft"
          count={draft.sections.length}
          active={tab === "draft"}
          onClick={setTab}
        />
        <TabButton
          id="experiments"
          label="Experiments"
          count={experiments.length}
          active={tab === "experiments"}
          onClick={setTab}
        />
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {tab === "events" && (
          <EventLog activityEvents={activityEvents} notifications={notifications} />
        )}
        {tab === "knowledge" && <KnowledgePanel knowledge={knowledge} />}
        {tab === "draft" && <DraftPanel draft={draft} />}
        {tab === "experiments" && <ExperimentPanel experiments={experiments} />}
      </div>
    </div>
  );
}
