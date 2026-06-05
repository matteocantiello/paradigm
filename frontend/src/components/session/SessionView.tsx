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

const TERMINAL_STATUSES = new Set(["completed", "failed", "aborted"]);
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
}

export function SessionView(props: SessionViewProps) {
  const [showLiterature, setShowLiterature] = useState(false);

  return (
    <div className="flex h-full flex-col">
      {/* Header bar */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border">
        <div className="flex items-center gap-2">
          <StatusPill />
          <ConnectionIndicator status={props.connectionStatus} />
        </div>
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
          Shown above the panels so the transcript stays available for reference. */}
      {TERMINAL_STATUSES.has(props.status) && (
        <TerminalScreen
          status={props.status}
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

      {/* Interaction bar */}
      <InteractionBar />

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
