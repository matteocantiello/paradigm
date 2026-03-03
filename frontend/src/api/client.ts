const BASE = import.meta.env.VITE_API_BASE_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init?.headers as Record<string, string>) ?? {}),
  };
  const apiKey = localStorage.getItem("paradigm_api_key");
  if (apiKey) headers["X-API-Key"] = apiKey;

  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (res.status === 204) return undefined as T;
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

// --- Health ---
export function healthCheck() {
  return request<{ status: string; service: string }>("/health");
}

// --- Research Cycles ---
export interface ResearchCycleCreate {
  seed_prompt: string;
  mode?: string;
  team_roles?: string[] | null;
  config_overrides?: Record<string, unknown> | null;
}

export interface ResearchCycleResponse {
  cycle_id: string;
  seed_prompt: string;
  mode: string;
  status: string;
  team_roles?: string[] | null;
  thread_id?: string | null;
  paper_id?: string | null;
  current_phase?: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface ResearchCycleList {
  items: ResearchCycleResponse[];
  total: number;
  offset: number;
  limit: number;
}

export function listCycles(offset = 0, limit = 20) {
  return request<ResearchCycleList>(
    `/api/v1/research?offset=${offset}&limit=${limit}`
  );
}

export function getCycle(cycleId: string) {
  return request<ResearchCycleResponse>(`/api/v1/research/${cycleId}`);
}

export function createCycle(body: ResearchCycleCreate) {
  return request<ResearchCycleResponse>("/api/v1/research", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function deleteCycle(cycleId: string) {
  return request<void>(`/api/v1/research/${cycleId}`, { method: "DELETE" });
}

// --- Sessions ---
export interface SessionResponse {
  session_id: string;
  cycle_id: string;
  status: string;
  thread_id?: string | null;
  current_phase?: string | null;
  created_at: string;
}

export interface SessionList {
  items: SessionResponse[];
  total: number;
}

export interface SessionState {
  session_id: string;
  cycle_id: string;
  status: string;
  current_phase?: string | null;
  round_num: number;
  max_rounds: number;
  thread_id?: string | null;
  active_agents: Record<string, string>;
  total_tokens: number;
  total_searches: number;
  papers_found: number;
  elapsed_seconds: number;
  created_at: string;
  updated_at?: string | null;
}

export function startSession(cycleId: string) {
  return request<SessionResponse>(
    `/api/v1/research/${cycleId}/sessions`,
    { method: "POST", body: JSON.stringify({}) }
  );
}

export function listSessions(cycleId: string) {
  return request<SessionList>(`/api/v1/research/${cycleId}/sessions`);
}

export function getSession(sessionId: string) {
  return request<SessionState>(`/api/v1/sessions/${sessionId}`);
}

export interface KnowledgeSnapshot {
  session_id: string;
  knowledge: Record<string, unknown> | null;
}

export function fetchKnowledgeState(sessionId: string) {
  return request<KnowledgeSnapshot>(`/api/v1/sessions/${sessionId}/knowledge`);
}

// --- Papers ---
export interface PaperSummary {
  paper_id: string;
  title: string;
  status: string;
  abstract: string;
  created_at?: string | null;
  published_at?: string | null;
}

export interface PaperDetail {
  paper_id: string;
  title: string;
  abstract: string;
  authors: string[];
  body: string;
  status: string;
  keywords: string[];
  citations: string[];
  review_scores?: Record<string, unknown> | null;
  citation_count: number;
  created_at?: string | null;
  published_at?: string | null;
}

export interface PaperList {
  items: PaperSummary[];
  total: number;
  offset: number;
  limit: number;
}

export function listPapers(status?: string, offset = 0, limit = 20) {
  const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
  if (status) params.set("status", status);
  return request<PaperList>(`/api/v1/papers?${params}`);
}

export function getPaper(paperId: string) {
  return request<PaperDetail>(`/api/v1/papers/${paperId}`);
}

// --- Agents ---
export interface AgentInfo {
  agent_type: string;
  description: string;
  default_model: string;
  default_provider: string;
}

export interface AgentList {
  items: AgentInfo[];
  total: number;
}

export interface AgentConfigUpdate {
  model?: string | null;
  provider?: string | null;
  max_tokens?: number | null;
  token_budget?: number | null;
}

export interface AgentOverrideResponse {
  agent_type: string;
  provider?: string | null;
  model?: string | null;
  max_tokens?: number | null;
  token_budget?: number | null;
  active: boolean;
}

export function listAgents() {
  return request<AgentList>("/api/v1/agents");
}

export function getAgentConfig(agentType: string) {
  return request<AgentOverrideResponse>(`/api/v1/agents/${agentType}`);
}

export function updateAgentConfig(agentType: string, body: AgentConfigUpdate) {
  return request<AgentOverrideResponse>(`/api/v1/agents/${agentType}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}
