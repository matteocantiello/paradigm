import { useState } from "react";
import { PhaseTracker } from "./PhaseTracker";
import { NowPlaying } from "./NowPlaying";
import { StatsBar } from "./StatsBar";
import { AgentPanel } from "./AgentPanel";
import { MessagesPanel } from "./MessagesPanel";
import { RightPanel } from "./RightPanel";
import { InteractionBar } from "./InteractionBar";
import { ApprovalDialog } from "./ApprovalDialog";
import { ConnectionIndicator } from "./ConnectionIndicator";
import { LiteraturePanel } from "./LiteraturePanel";
import { StatusPill } from "./StatusPill";
import { TerminalScreen } from "./TerminalScreen";
import { TopicBadges } from "@/components/shared/TopicBadges";

const TERMINAL_STATUSES = new Set(["completed", "failed", "aborted"]);
// A terminal phase means the outcome is decided even if the session status is
// still "running" (backend finalizing). Show the end-of-run screen regardless.
const TERMINAL_PHASES = new Set(["published", "rejected"]);

// Demo: hide the steering/control bar to foreground the autonomous flow.
// Flip to true to bring back live steering + pause/abort.
const SHOW_INTERACTION_BAR = false;
import type { ConnectionStatus } from "@/api/websocket";
import type {
  ActivityEvent,
  AgentOutput,
  Notification,
  KnowledgeState,
  LiveLiterature,
  LiveDraft,
  ExperimentRun,
} from "@/stores/sessionStore";
import type { ApprovalRequestMsg } from "@/api/ws-types";

interface SessionViewProps {
  connectionStatus: ConnectionStatus;
  status: string;
  currentPhase: string | null;
  completedPhases: string[];
  topics: string[];
  roundNum: number;
  maxRounds: number;
  activeAgents: Record<string, string>;
  totalTokens: number;
  totalSearches: number;
  papersFound: number;
  elapsedSeconds: number;
  avgStepMs: number;
  phaseElapsedSeconds: number;
  agentOutputs: AgentOutput[];
  notifications: Notification[];
  activityEvents: ActivityEvent[];
  literature: LiveLiterature;
  knowledge: KnowledgeState;
  draft: LiveDraft;
  experiments: ExperimentRun[];
  pendingApproval: ApprovalRequestMsg | null;
  paperId?: string;
  cycleId?: string;
  topic?: string;
}

export function SessionView(props: SessionViewProps) {
  const [showLiterature, setShowLiterature] = useState(false);

  return (
    <div className="flex h-full flex-col">
      {/* Header bar */}
      <div className="flex items-center justify-between gap-3 px-3 py-1.5 border-b border-border">
        <div className="flex items-center gap-2 shrink-0">
          <StatusPill />
          <ConnectionIndicator status={props.connectionStatus} />
          <TopicBadges topics={props.topics} size="xs" />
        </div>
        {props.topic && (
          <p
            className="truncate text-xs text-muted-foreground/80 max-w-[60%]"
            title={props.topic}
          >
            {props.topic}
          </p>
        )}
      </div>

      {/* Phase tracker */}
      <div className="border-b border-border">
        <PhaseTracker
          currentPhase={props.currentPhase}
          completedPhases={props.completedPhases}
        />
      </div>

      {/* Now playing: current phase · active agent · live elapsed · rough ETA.
          Keyed by phase so the in-phase timer resets on each transition. */}
      <NowPlaying
        key={props.currentPhase ?? "none"}
        currentPhase={props.currentPhase}
        activeAgents={props.activeAgents}
        roundNum={props.roundNum}
        maxRounds={props.maxRounds}
        avgStepMs={props.avgStepMs}
      />

      {/* Stats bar */}
      <StatsBar
        roundNum={props.roundNum}
        maxRounds={props.maxRounds}
        papersFound={props.papersFound}
        totalSearches={props.totalSearches}
        totalTokens={props.totalTokens}
        elapsedSeconds={props.elapsedSeconds}
        onPapersClick={() => setShowLiterature(true)}
      />

      {/* Terminal screen — a clear end-of-run action (View paper / summary).
          Shown above the panels so the transcript stays available for reference.
          Triggered by a terminal status OR a terminal phase (the latter renders
          the outcome immediately, before the backend finishes finalizing). */}
      {(TERMINAL_STATUSES.has(props.status) ||
        (props.currentPhase != null && TERMINAL_PHASES.has(props.currentPhase))) && (
        <TerminalScreen
          status={TERMINAL_STATUSES.has(props.status) ? props.status : "completed"}
          cycleId={props.cycleId}
          paperId={props.paperId}
          currentPhase={props.currentPhase}
          roundNum={props.roundNum}
          totalTokens={props.totalTokens}
          papersFound={props.papersFound}
          elapsedSeconds={props.elapsedSeconds}
        />
      )}

      {/* 3-column layout */}
      <div className="flex-1 grid grid-cols-[180px_1fr_1fr] gap-0 overflow-hidden border-b border-border">
        <div className="border-r border-border overflow-y-auto">
          <AgentPanel activeAgents={props.activeAgents} />
        </div>
        <div className="border-r border-border overflow-hidden">
          <MessagesPanel outputs={props.agentOutputs} />
        </div>
        <div className="overflow-hidden">
          <RightPanel
            activityEvents={props.activityEvents}
            notifications={props.notifications}
            knowledge={props.knowledge}
            draft={props.draft}
            experiments={props.experiments}
          />
        </div>
      </div>

      {/* Interaction bar (hidden for the demo — see SHOW_INTERACTION_BAR) */}
      {SHOW_INTERACTION_BAR && <InteractionBar />}

      {/* Approval dialog overlay */}
      {props.pendingApproval && <ApprovalDialog approval={props.pendingApproval} />}

      {/* Literature panel overlay */}
      {showLiterature && (
        <LiteraturePanel
          paperId={props.paperId}
          papersFound={props.papersFound}
          liveLiterature={props.literature}
          onClose={() => setShowLiterature(false)}
        />
      )}
    </div>
  );
}
