// WebSocket message types — mirrors backend/api/models/messages.py

// --- Server → Client ---

export interface AgentOutputStreamMsg {
  type: "agent_output_stream";
  agent_id: string;
  role: string;
  content: string;
  phase: string;
  stream_id: string;
  is_final: boolean;
  tokens: number;
  model: string;
  timestamp: string;
}

export interface AgentStepCompleteMsg {
  type: "agent_step_complete";
  agent_id: string;
  role: string;
  summary: string;
  output_id?: string | null;
  next_agent?: string | null;
  phase: string;
  tokens: number;
  timestamp: string;
}

export interface ActivityEventMsg {
  type: "activity_event";
  event_id: string;
  category: string;
  phase: string;
  agent_id: string;
  severity: string;
  title: string;
  detail: string;
  narration: string;
  duration_ms?: number | null;
  timestamp: string;
}

/** A selectable option inside a structured decision request. */
export interface DecisionChoice {
  id: string;
  label: string;
  detail?: string;
  score?: number;
}

export interface ApprovalRequestMsg {
  type: "approval_request";
  request_id: string;
  title: string;
  description: string;
  from_phase: string;
  to_phase: string;
  options: string[];
  // Structured decisions (interactive mode); empty for plain approvals.
  decision_type?: string;
  choices?: DecisionChoice[];
  multi_select?: boolean;
  default_ids?: string[];
  timeout_seconds?: number | null;
  timestamp: string;
}

export interface SessionStateMsg {
  type: "session_state";
  session_id: string;
  status: string;
  current_phase: string | null;
  round_num: number;
  max_rounds: number;
  thread_id?: string | null;
  active_agents: Record<string, string>;
  total_tokens: number;
  total_searches: number;
  papers_found: number;
  elapsed_seconds: number;
  completed_phases: string[];
  topics?: string[];
  avg_step_ms?: number;
  phase_elapsed_seconds?: number;
  protocol_version: string;
  timestamp: string;
}

export interface PhaseTransitionMsg {
  type: "phase_transition";
  from_phase: string | null;
  to_phase: string;
  max_rounds?: number | null;
  active_agents?: number | null;
  total_agents?: number | null;
  timestamp: string;
}

export interface TopicsUpdateMsg {
  type: "topics_update";
  topics: string[];
  stage: string;
  timestamp: string;
}

export interface RoundUpdateMsg {
  type: "round_update";
  round_num: number;
  max_rounds: number;
  phase: string;
  timestamp: string;
}

export interface ErrorMsg {
  type: "error";
  code: string;
  message: string;
  recoverable: boolean;
  timestamp: string;
}

export interface NotificationMsg {
  type: "notification";
  level: string;
  category: string;
  message: string;
  metadata: Record<string, unknown>;
  timestamp: string;
}

// --- Knowledge Architecture ---

export interface KnowledgeEntity {
  id: string;
  name: string;
  entity_type: string;
  description: string;
  [key: string]: unknown;
}

export interface KnowledgeHypothesis {
  id: string;
  statement: string;
  status: string;
  elo_rating?: number;
  rationale?: string;
  supporting_evidence?: string[];
  contradicting_evidence?: string[];
  [key: string]: unknown;
}

export interface KnowledgeEvidence {
  id: string;
  content: string;
  source: string;
  supports?: string[];
  contradicts?: string[];
  [key: string]: unknown;
}

export interface KnowledgeConflict {
  id: string;
  conflict_type: string;
  description: string;
  hypothesis_ids?: string[];
  [key: string]: unknown;
}

export interface KnowledgeAssumption {
  id: string;
  statement: string;
  status: string;
  [key: string]: unknown;
}

export interface KnowledgeResearchGoal {
  id: string;
  description: string;
  status: string;
  [key: string]: unknown;
}

export interface KnowledgeOpenQuestion {
  id: string;
  question: string;
  priority?: string;
  [key: string]: unknown;
}

export interface TournamentRanking {
  hypothesis_id: string;
  statement: string;
  elo_rating: number;
  status: string;
  [key: string]: unknown;
}

export interface TournamentMatchup {
  hypothesis_a_id: string;
  hypothesis_b_id: string;
  winner_id: string;
  judge_reasoning: string;
  margin: number;
  [key: string]: unknown;
}

export interface LiteraturePaper {
  arxiv_id: string;
  title: string;
  authors: string[];
  year: string;
}

export interface LiteratureSearch {
  query: string;
  agent_id: string;
  phase: string;
  papers: LiteraturePaper[];
}

export interface LiteratureUpdateMsg {
  type: "literature_update";
  searches: LiteratureSearch[];
  unique_papers: LiteraturePaper[];
  total_searches: number;
  timestamp: string;
}

export interface KnowledgeUpdateMsg {
  type: "knowledge_update";
  entities: KnowledgeEntity[];
  relationships: Record<string, unknown>[];
  hypotheses: KnowledgeHypothesis[];
  evidence: KnowledgeEvidence[];
  open_questions: KnowledgeOpenQuestion[];
  research_goals: KnowledgeResearchGoal[];
  conflicts: KnowledgeConflict[];
  assumptions: KnowledgeAssumption[];
  provenance_chains: Record<string, unknown>[];
  tournament_rankings: TournamentRanking[];
  matchup_results: TournamentMatchup[];
  tournament_status: string;
  world_model_summary: string;
  evidence_landscape_summary: string;
  tournament_summary: string;
  timestamp: string;
}

export interface DraftUpdateMsg {
  type: "draft_update";
  section: string;
  title: string;
  content: string;
  author: string;
  status: string; // drafting | drafted
  char_count: number;
  phase: string;
  timestamp: string;
}

export interface ExperimentUpdateMsg {
  type: "experiment_update";
  experiment_id: string;
  name: string;
  agent_id: string;
  code: string;
  stdout: string;
  status: string; // running | success | failure | timeout | error
  results: Record<string, number>;
  has_figures: boolean;
  figures?: string[];
  phase: string;
  timestamp: string;
}

export type ServerMessage =
  | AgentOutputStreamMsg
  | AgentStepCompleteMsg
  | ActivityEventMsg
  | ApprovalRequestMsg
  | SessionStateMsg
  | PhaseTransitionMsg
  | TopicsUpdateMsg
  | RoundUpdateMsg
  | ErrorMsg
  | NotificationMsg
  | KnowledgeUpdateMsg
  | LiteratureUpdateMsg
  | DraftUpdateMsg
  | ExperimentUpdateMsg;

// --- Client → Server ---

export interface UserInterventionMsg {
  type: "user_intervention";
  target_agent?: string | null;
  action: "redirect" | "constrain" | "inform";
  content: string;
}

export interface ApprovalResponseMsg {
  type: "approval_response";
  request_id: string;
  decision: "continue" | "pause" | "abort";
  notes?: string;
  modifications?: Record<string, unknown> | null;
}

export interface UserMessageMsg {
  type: "user_message";
  target_agent?: string | null;
  content: string;
}

export interface SessionControlMsg {
  type: "session_control";
  action: "pause" | "resume" | "checkpoint" | "rewind" | "abort";
  checkpoint_id?: string | null;
}

export type ClientMessage =
  | UserInterventionMsg
  | ApprovalResponseMsg
  | UserMessageMsg
  | SessionControlMsg;
