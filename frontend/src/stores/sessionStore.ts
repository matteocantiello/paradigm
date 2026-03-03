import { create } from "zustand";
import { ParadigmWebSocket } from "@/api/websocket";
import type { ConnectionStatus } from "@/api/websocket";
import type {
  ServerMessage,
  ApprovalRequestMsg,
  AgentOutputStreamMsg,
  AgentStepCompleteMsg,
  NotificationMsg,
  KnowledgeUpdateMsg,
  KnowledgeEntity,
  KnowledgeHypothesis,
  KnowledgeEvidence,
  KnowledgeConflict,
  KnowledgeAssumption,
  KnowledgeResearchGoal,
  KnowledgeOpenQuestion,
  TournamentRanking,
  TournamentMatchup,
} from "@/api/ws-types";

export type AgentOutput = {
  id: string;
  agentId: string;
  role: string;
  content: string;
  model: string;
  tokens: number;
  phase: string;
  timestamp: string;
  isFinal: boolean;
};

export type Notification = {
  id: string;
  level: string;
  category: string;
  message: string;
  timestamp: string;
};

export type KnowledgeState = {
  entities: KnowledgeEntity[];
  relationships: Record<string, unknown>[];
  hypotheses: KnowledgeHypothesis[];
  evidence: KnowledgeEvidence[];
  openQuestions: KnowledgeOpenQuestion[];
  researchGoals: KnowledgeResearchGoal[];
  conflicts: KnowledgeConflict[];
  assumptions: KnowledgeAssumption[];
  provenanceChains: Record<string, unknown>[];
  tournamentRankings: TournamentRanking[];
  matchupResults: TournamentMatchup[];
  tournamentStatus: string;
  worldModelSummary: string;
  evidenceLandscapeSummary: string;
  tournamentSummary: string;
  lastUpdated: string | null;
};

const EMPTY_KNOWLEDGE: KnowledgeState = {
  entities: [],
  relationships: [],
  hypotheses: [],
  evidence: [],
  openQuestions: [],
  researchGoals: [],
  conflicts: [],
  assumptions: [],
  provenanceChains: [],
  tournamentRankings: [],
  matchupResults: [],
  tournamentStatus: "",
  worldModelSummary: "",
  evidenceLandscapeSummary: "",
  tournamentSummary: "",
  lastUpdated: null,
};

interface SessionStoreState {
  // Connection
  connectionStatus: ConnectionStatus;
  ws: ParadigmWebSocket | null;

  // Session state
  sessionId: string | null;
  status: string;
  currentPhase: string | null;
  roundNum: number;
  maxRounds: number;
  activeAgents: Record<string, string>;
  totalTokens: number;
  totalSearches: number;
  papersFound: number;
  elapsedSeconds: number;
  completedPhases: string[];

  // Rolling buffers
  agentOutputs: AgentOutput[];
  notifications: Notification[];

  // Knowledge architecture
  knowledge: KnowledgeState;

  // Approval
  pendingApproval: ApprovalRequestMsg | null;

  // Actions
  connect: (sessionId: string) => void;
  disconnect: () => void;
  sendApprovalResponse: (requestId: string, decision: "continue" | "pause" | "abort", notes?: string) => void;
  sendSessionControl: (action: "pause" | "resume" | "checkpoint" | "rewind") => void;
  sendUserMessage: (content: string, targetAgent?: string | null) => void;
  sendIntervention: (action: "redirect" | "constrain" | "inform", content: string, targetAgent?: string | null) => void;
}

let outputCounter = 0;
let notifCounter = 0;

function nextOutputId() {
  return `out-${++outputCounter}`;
}
function nextNotifId() {
  return `ntf-${++notifCounter}`;
}

export const useSessionStore = create<SessionStoreState>((set, get) => ({
  connectionStatus: "disconnected",
  ws: null,
  sessionId: null,
  status: "",
  currentPhase: null,
  roundNum: 0,
  maxRounds: 0,
  activeAgents: {},
  totalTokens: 0,
  totalSearches: 0,
  papersFound: 0,
  elapsedSeconds: 0,
  completedPhases: [],
  agentOutputs: [],
  notifications: [],
  knowledge: { ...EMPTY_KNOWLEDGE },
  pendingApproval: null,

  connect: (sessionId: string) => {
    const existing = get().ws;
    if (existing) existing.disconnect();

    const ws = new ParadigmWebSocket({
      onStatusChange: (status) => set({ connectionStatus: status }),
      onMessage: (msg) => handleServerMessage(msg, set, get),
    });
    set({ ws, sessionId });
    ws.connect(sessionId);
  },

  disconnect: () => {
    const { ws } = get();
    if (ws) ws.disconnect();
    set({ ws: null, sessionId: null, connectionStatus: "disconnected" });
  },

  sendApprovalResponse: (requestId, decision, notes) => {
    get().ws?.send({
      type: "approval_response",
      request_id: requestId,
      decision,
      notes: notes ?? "",
    });
    set({ pendingApproval: null });
  },

  sendSessionControl: (action) => {
    get().ws?.send({ type: "session_control", action });
  },

  sendUserMessage: (content, targetAgent) => {
    get().ws?.send({
      type: "user_message",
      content,
      target_agent: targetAgent ?? null,
    });
  },

  sendIntervention: (action, content, targetAgent) => {
    get().ws?.send({
      type: "user_intervention",
      action,
      content,
      target_agent: targetAgent ?? null,
    });
  },
}));

function handleServerMessage(
  msg: ServerMessage,
  set: (partial: Partial<SessionStoreState> | ((s: SessionStoreState) => Partial<SessionStoreState>)) => void,
  get: () => SessionStoreState
) {
  switch (msg.type) {
    case "session_state":
      set({
        sessionId: msg.session_id,
        status: msg.status,
        currentPhase: msg.current_phase,
        roundNum: msg.round_num,
        maxRounds: msg.max_rounds,
        activeAgents: msg.active_agents,
        totalTokens: msg.total_tokens,
        totalSearches: msg.total_searches,
        papersFound: msg.papers_found,
        elapsedSeconds: msg.elapsed_seconds,
        completedPhases: msg.completed_phases,
      });
      break;

    case "agent_output_stream": {
      const m = msg as AgentOutputStreamMsg;
      const output: AgentOutput = {
        id: nextOutputId(),
        agentId: m.agent_id,
        role: m.role,
        content: m.content,
        model: m.model,
        tokens: m.tokens,
        phase: m.phase,
        timestamp: m.timestamp,
        isFinal: m.is_final,
      };
      set((s) => ({
        agentOutputs: [...s.agentOutputs.slice(-199), output],
        activeAgents: { ...s.activeAgents, [m.agent_id]: m.role || "active" },
      }));
      break;
    }

    case "agent_step_complete": {
      const m = msg as AgentStepCompleteMsg;
      const output: AgentOutput = {
        id: nextOutputId(),
        agentId: m.agent_id,
        role: m.role,
        content: m.summary,
        model: "",
        tokens: m.tokens,
        phase: m.phase,
        timestamp: m.timestamp,
        isFinal: true,
      };
      set((s) => ({
        agentOutputs: [...s.agentOutputs.slice(-199), output],
        totalTokens: s.totalTokens + m.tokens,
      }));
      break;
    }

    case "phase_transition":
      set((s) => ({
        currentPhase: msg.to_phase,
        completedPhases: msg.from_phase
          ? [...new Set([...s.completedPhases, msg.from_phase])]
          : s.completedPhases,
      }));
      break;

    case "round_update":
      set({ roundNum: msg.round_num, maxRounds: msg.max_rounds });
      break;

    case "approval_request":
      set({ pendingApproval: msg });
      break;

    case "notification": {
      const m = msg as NotificationMsg;
      const notif: Notification = {
        id: nextNotifId(),
        level: m.level,
        category: m.category,
        message: m.message,
        timestamp: m.timestamp,
      };
      set((s) => ({
        notifications: [...s.notifications.slice(-99), notif],
      }));
      break;
    }

    case "error": {
      const notif: Notification = {
        id: nextNotifId(),
        level: "error",
        category: "error",
        message: `[${msg.code}] ${msg.message}`,
        timestamp: msg.timestamp,
      };
      set((s) => ({
        notifications: [...s.notifications.slice(-99), notif],
      }));
      // Also add to agentOutputs so it's visible
      const errOut: AgentOutput = {
        id: nextOutputId(),
        agentId: "system",
        role: "system",
        content: msg.message,
        model: "",
        tokens: 0,
        phase: get().currentPhase ?? "",
        timestamp: msg.timestamp,
        isFinal: true,
      };
      set((s) => ({
        agentOutputs: [...s.agentOutputs.slice(-199), errOut],
      }));
      break;
    }

    case "knowledge_update": {
      const k = msg as KnowledgeUpdateMsg;
      // Sort hypotheses by Elo rating descending
      const sortedHypotheses = [...k.hypotheses].sort(
        (a, b) => (b.elo_rating ?? 0) - (a.elo_rating ?? 0)
      );
      set({
        knowledge: {
          entities: k.entities,
          relationships: k.relationships,
          hypotheses: sortedHypotheses,
          evidence: k.evidence,
          openQuestions: k.open_questions,
          researchGoals: k.research_goals,
          conflicts: k.conflicts,
          assumptions: k.assumptions,
          provenanceChains: k.provenance_chains,
          tournamentRankings: k.tournament_rankings,
          matchupResults: k.matchup_results,
          tournamentStatus: k.tournament_status,
          worldModelSummary: k.world_model_summary,
          evidenceLandscapeSummary: k.evidence_landscape_summary,
          tournamentSummary: k.tournament_summary,
          lastUpdated: k.timestamp,
        },
      });
      break;
    }
  }
}
