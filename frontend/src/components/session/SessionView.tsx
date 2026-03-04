import { useState } from "react";
import { PhaseTracker } from "./PhaseTracker";
import { StatsBar } from "./StatsBar";
import { AgentPanel } from "./AgentPanel";
import { MessagesPanel } from "./MessagesPanel";
import { RightPanel } from "./RightPanel";
import { InteractionBar } from "./InteractionBar";
import { ApprovalDialog } from "./ApprovalDialog";
import { ConnectionIndicator } from "./ConnectionIndicator";
import { LiteraturePanel } from "./LiteraturePanel";
import { StatusBadge } from "@/components/shared/StatusBadge";
import type { ConnectionStatus } from "@/api/websocket";
import type { AgentOutput, Notification, KnowledgeState } from "@/stores/sessionStore";
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
  agentOutputs: AgentOutput[];
  notifications: Notification[];
  knowledge: KnowledgeState;
  pendingApproval: ApprovalRequestMsg | null;
  paperId?: string;
}

export function SessionView(props: SessionViewProps) {
  const [showLiterature, setShowLiterature] = useState(false);

  return (
    <div className="flex h-full flex-col">
      {/* Header bar */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border">
        <div className="flex items-center gap-2">
          <StatusBadge status={props.status || "starting"} />
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

      {/* 3-column layout */}
      <div className="flex-1 grid grid-cols-[180px_1fr_1fr] gap-0 overflow-hidden border-b border-border">
        <div className="border-r border-border overflow-y-auto">
          <AgentPanel activeAgents={props.activeAgents} />
        </div>
        <div className="border-r border-border overflow-hidden">
          <MessagesPanel outputs={props.agentOutputs} />
        </div>
        <div className="overflow-hidden">
          <RightPanel notifications={props.notifications} knowledge={props.knowledge} />
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
          onClose={() => setShowLiterature(false)}
        />
      )}
    </div>
  );
}
