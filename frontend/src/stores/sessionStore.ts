import { create } from "zustand";
import { ParadigmWebSocket } from "@/api/websocket";
import type { ConnectionStatus } from "@/api/websocket";
import type {
  ServerMessage,
  ApprovalRequestMsg,
  KnowledgeEntity,
  KnowledgeHypothesis,
  KnowledgeEvidence,
  KnowledgeConflict,
  KnowledgeAssumption,
  KnowledgeResearchGoal,
  KnowledgeOpenQuestion,
  TournamentRanking,
  TournamentMatchup,
  LiteraturePaper,
  LiteratureSearch,
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
  // Live-streaming metadata (Phase A). streamId groups chunks into one bubble.
  streamId: string;
  streaming: boolean;
  startedAt: number; // ms epoch when the turn opened
  firstChunkAt: number | null; // ms epoch of first token (null = still "thinking")
};

export type Notification = {
  id: string;
  level: string;
  category: string;
  message: string;
  timestamp: string;
};

export type ActivityEvent = {
  id: string;
  category: string;
  phase: string;
  agentId: string;
  severity: string;
  title: string;
  detail: string;
  narration: string;
  durationMs: number | null;
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
  // Elo rating per hypothesis id from the PREVIOUS update, so the tournament
  // board can show rank movement (▲/▼) without the backend tracking deltas.
  previousElo: Record<string, number>;
};

export type LiveLiterature = {
  searches: LiteratureSearch[];
  uniquePapers: LiteraturePaper[];
  totalSearches: number;
};

export type DraftSection = {
  section: string;
  title: string;
  content: string;
  author: string;
  status: string; // drafting | drafted
  charCount: number;
};

export type LiveDraft = {
  sections: DraftSection[]; // in arrival/writing order
};

export type ExperimentRun = {
  id: string;
  name: string;
  agentId: string;
  code: string;
  stdout: string;
  status: string; // running | success | failure | timeout | error
  results: Record<string, number>;
  hasFigures: boolean;
  figures: string[]; // data-dir-relative figure paths
};

const EMPTY_DRAFT: LiveDraft = { sections: [] };

const EMPTY_LITERATURE: LiveLiterature = {
  searches: [],
  uniquePapers: [],
  totalSearches: 0,
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
  previousElo: {},
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
  topics: string[];
  avgStepMs: number;
  phaseElapsedSeconds: number;
  // ms-epoch of the last inbound server message — drives stalled-detection.
  lastActivityAt: number;

  // Rolling buffers
  agentOutputs: AgentOutput[];
  notifications: Notification[];
  activityEvents: ActivityEvent[];

  // Live literature (during cycle)
  literature: LiveLiterature;

  // Knowledge architecture
  knowledge: KnowledgeState;

  // Live paper draft (Phase C)
  draft: LiveDraft;

  // Live experiments (Phase C)
  experiments: ExperimentRun[];

  // Approval
  pendingApproval: ApprovalRequestMsg | null;

  // Actions
  connect: (sessionId: string) => void;
  disconnect: () => void;
  sendApprovalResponse: (
    requestId: string,
    decision: "continue" | "pause" | "abort",
    notes?: string,
    modifications?: Record<string, unknown> | null
  ) => void;
  sendSessionControl: (action: "pause" | "resume" | "checkpoint" | "rewind" | "abort") => void;
  sendUserMessage: (content: string, targetAgent?: string | null) => void;
  sendIntervention: (action: "redirect" | "constrain" | "inform", content: string, targetAgent?: string | null) => void;
}

let outputCounter = 0;
let notifCounter = 0;
let activityCounter = 0;

function nextOutputId() {
  return `out-${++outputCounter}`;
}
function nextNotifId() {
  return `ntf-${++notifCounter}`;
}
function nextActivityId() {
  return `act-local-${++activityCounter}`;
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
  topics: [],
  avgStepMs: 0,
  phaseElapsedSeconds: 0,
  lastActivityAt: 0,
  agentOutputs: [],
  notifications: [],
  activityEvents: [],
  literature: { ...EMPTY_LITERATURE },
  knowledge: { ...EMPTY_KNOWLEDGE },
  draft: { ...EMPTY_DRAFT },
  experiments: [],
  pendingApproval: null,

  connect: (sessionId: string) => {
    const existing = get().ws;
    if (existing) existing.disconnect();

    const ws = new ParadigmWebSocket({
      onStatusChange: (status) => set({ connectionStatus: status }),
      onMessage: (msg) => handleServerMessage(msg, set, get),
    });
    // Reset all session-specific state before connecting
    set({
      ws,
      sessionId,
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
      topics: [],
      avgStepMs: 0,
      phaseElapsedSeconds: 0,
      lastActivityAt: Date.now(),
      agentOutputs: [],
      notifications: [],
      activityEvents: [],
      literature: { ...EMPTY_LITERATURE },
      knowledge: { ...EMPTY_KNOWLEDGE },
      draft: { ...EMPTY_DRAFT },
      experiments: [],
      pendingApproval: null,
    });
    ws.connect(sessionId);
  },

  disconnect: () => {
    const { ws } = get();
    if (ws) ws.disconnect();
    set({ ws: null, sessionId: null, connectionStatus: "disconnected" });
  },

  sendApprovalResponse: (requestId, decision, notes, modifications) => {
    get().ws?.send({
      type: "approval_response",
      request_id: requestId,
      decision,
      notes: notes ?? "",
      modifications: modifications ?? null,
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
  // Every inbound message counts as activity — this is what lets the UI tell
  // "working" from "stalled" (no messages for a while).
  set({ lastActivityAt: Date.now() });

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
        // Only overwrite topics when the snapshot actually carries them, so a
        // state sync between the initial/final classifications can't wipe a badge.
        ...(msg.topics && msg.topics.length > 0 ? { topics: msg.topics } : {}),
        avgStepMs: msg.avg_step_ms ?? 0,
        phaseElapsedSeconds: msg.phase_elapsed_seconds ?? 0,
      });
      break;

    case "topics_update":
      set({ topics: msg.topics });
      break;

    case "agent_output_stream": {
      const m = msg;
      const now = Date.now();
      set((s) => {
        const outputs = s.agentOutputs;
        const idx = m.stream_id
          ? outputs.findIndex((o) => o.streamId === m.stream_id)
          : -1;
        const activeAgents = { ...s.activeAgents, [m.agent_id]: m.role || "active" };

        if (idx === -1) {
          // New bubble: a "start" event (empty content), a legacy chunk with no
          // stream_id, or a lone final on reconnect (carries full content).
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
            streamId: m.stream_id,
            streaming: !m.is_final,
            startedAt: now,
            firstChunkAt: m.content ? now : null,
          };
          return { agentOutputs: [...outputs.slice(-199), output], activeAgents };
        }

        // Accumulate into the existing bubble (in place — chunk volume no longer
        // grows the array, so the 200-cap counts turns).
        const existing = outputs[idx];
        const updated: AgentOutput = m.is_final
          ? {
              ...existing,
              // Final carries the full content (used verbatim on reconnect).
              content: m.content.length >= existing.content.length ? m.content : existing.content,
              tokens: m.tokens || existing.tokens,
              model: m.model || existing.model,
              isFinal: true,
              streaming: false,
            }
          : {
              ...existing,
              content: existing.content + m.content,
              firstChunkAt: existing.firstChunkAt ?? (m.content ? now : null),
            };
        const next = outputs.slice();
        next[idx] = updated;
        return { agentOutputs: next, activeAgents };
      });
      break;
    }

    case "agent_step_complete": {
      // Structured step marker. The chat bubble + token total are already handled
      // by agent_output_stream/session_state, so this only feeds the timeline.
      const m = msg;
      if (m.summary) {
        const ev: ActivityEvent = {
          id: nextActivityId(),
          category: "agent_step",
          phase: m.phase,
          agentId: m.agent_id,
          severity: "info",
          title: `${m.role || m.agent_id} finished a step`,
          detail: m.summary,
          narration: "",
          durationMs: null,
          timestamp: m.timestamp,
        };
        set((s) => ({ activityEvents: [...s.activityEvents.slice(-299), ev] }));
      }
      break;
    }

    case "activity_event": {
      const m = msg;
      const ev: ActivityEvent = {
        id: m.event_id,
        category: m.category,
        phase: m.phase,
        agentId: m.agent_id,
        severity: m.severity,
        title: m.title,
        detail: m.detail,
        narration: m.narration,
        durationMs: m.duration_ms ?? null,
        timestamp: m.timestamp,
      };
      set((s) => ({ activityEvents: [...s.activityEvents.slice(-299), ev] }));
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
      const m = msg;
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
        streamId: "",
        streaming: false,
        startedAt: Date.now(),
        firstChunkAt: Date.now(),
      };
      set((s) => ({
        notifications: [...s.notifications.slice(-99), notif],
        agentOutputs: [...s.agentOutputs.slice(-199), errOut],
      }));
      break;
    }

    case "literature_update": {
      set({
        literature: {
          searches: msg.searches,
          uniquePapers: msg.unique_papers,
          totalSearches: msg.total_searches,
        },
      });
      break;
    }

    case "knowledge_update": {
      const k = msg;
      // Sort hypotheses by Elo rating descending
      const sortedHypotheses = [...k.hypotheses].sort(
        (a, b) => (b.elo_rating ?? 0) - (a.elo_rating ?? 0)
      );
      // Snapshot the prior Elo per hypothesis so the tournament board can show
      // rank movement on this update.
      const prev = get().knowledge;
      const previousElo: Record<string, number> = {};
      for (const h of prev.hypotheses) {
        if (h.elo_rating != null) previousElo[h.id] = h.elo_rating;
      }
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
          previousElo,
        },
      });
      break;
    }

    case "draft_update": {
      const d = msg;
      const sections = [...get().draft.sections];
      const idx = sections.findIndex((s) => s.section === d.section);
      const entry: DraftSection = {
        section: d.section,
        title: d.title,
        content: d.content,
        author: d.author,
        status: d.status,
        charCount: d.char_count,
      };
      if (idx >= 0) {
        // Don't let a stray "drafting" clobber already-drafted content.
        entry.content = d.status === "drafted" ? d.content : sections[idx].content || d.content;
        sections[idx] = { ...sections[idx], ...entry };
      } else {
        sections.push(entry);
      }
      set({ draft: { sections } });
      break;
    }

    case "experiment_update": {
      const e = msg;
      const items = [...get().experiments];
      const idx = items.findIndex((x) => x.id === e.experiment_id);
      const prev = idx >= 0 ? items[idx] : null;
      const entry: ExperimentRun = {
        id: e.experiment_id,
        name: e.name,
        agentId: e.agent_id,
        code: e.code || prev?.code || "",
        stdout: e.stdout || prev?.stdout || "",
        status: e.status,
        results: Object.keys(e.results).length ? e.results : (prev?.results ?? {}),
        hasFigures: e.has_figures || prev?.hasFigures || false,
        figures: e.figures?.length ? e.figures : (prev?.figures ?? []),
      };
      if (idx >= 0) items[idx] = entry;
      else items.push(entry);
      set({ experiments: items });
      break;
    }
  }
}
