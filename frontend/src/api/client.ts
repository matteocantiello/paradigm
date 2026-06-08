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
  session_id?: string | null;
  thread_id?: string | null;
  paper_id?: string | null;
  current_phase?: string | null;
  topics?: string[] | null;
  resumed_from?: string | null;
  total_tokens?: number | null;
  elapsed_seconds?: number | null;
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

/** Continue a cycle from its checkpoint as a new run, with optional steering. */
export function resumeCycle(cycleId: string, comment?: string) {
  return request<ResearchCycleResponse>(`/api/v1/research/${cycleId}/resume`, {
    method: "POST",
    body: JSON.stringify({ comment: comment ?? null }),
  });
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
  completed_phases: string[];
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
  topics?: string[] | null;
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
  topics?: string[] | null;
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
  extra_body?: Record<string, unknown> | null;
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

// --- Model catalog (for the per-agent model picker) ---
export interface ModelOption {
  id: string;
  label: string;
}

export interface ProviderModels {
  name: string; // config provider name (stored in an override's `provider`)
  family: string; // anthropic | gemini | together | openai
  label: string; // display name, e.g. "TogetherAI"
  available: boolean; // API key present
  models: ModelOption[];
  source: string; // "curated" | "live"
  error: string;
}

export interface ModelCatalogResponse {
  providers: ProviderModels[];
}

export function getModelCatalog(refresh = false) {
  return request<ModelCatalogResponse>(`/api/v1/models${refresh ? "?refresh=true" : ""}`);
}

// --- Config Mode ---
export interface ConfigModeResponse {
  mode: string;
  testing_available: boolean;
}

export function getConfigMode() {
  return request<ConfigModeResponse>("/api/v1/config/mode");
}

export function setConfigMode(mode: string) {
  return request<ConfigModeResponse>("/api/v1/config/mode", {
    method: "PUT",
    body: JSON.stringify({ mode }),
  });
}

// --- Settings ---
export interface OrchestratorSettings {
  max_rounds_per_phase: number;
  enable_checkpointing: boolean;
  enable_writing: boolean;
  max_review_iterations: number;
  enable_peer_review: boolean;
  num_reviewers: number;
  enable_experimentation: boolean;
  enable_debates: boolean;
  max_debate_exchanges: number;
  enable_convergence_detection: boolean;
  convergence_confidence_threshold: number;
  enable_execution_sprints: boolean;
  num_execution_sprints: number;
  // Correctness kernel (Phase 1) + output quality (Phase 2)
  enable_verification: boolean;
  verification_tolerance: number;
  abort_on_verification_failure: boolean;
  enable_best_first_nodes: boolean;
  enable_step_restart: boolean;
  human_gate_mode: string; // off | advisory | blocking
  enable_multimodal_review: boolean;
  max_review_figures: number;
}

export interface SandboxSettings {
  enabled: boolean;
  network_mode: string;
  cpu_limit: number;
  memory_limit: string;
  execution_timeout: number;
}

export interface LiteratureSettings {
  max_results_per_search: number;
  enable_pdf_fetch: boolean;
  follow_budget_per_round: number;
  cited_by_budget_per_round: number;
  read_budget_per_round: number;
  max_read_chars: number;
}

export interface KnowledgeSettings {
  enable_world_model: boolean;
  enable_evidence_graph: boolean;
  enable_hypothesis_tournament: boolean;
  enable_preregistration: boolean;
  prereg_require_refutation: boolean;
  prereg_on_empty: string; // advisory | blocking
}

export interface JournalSettings {
  enable_latex_output: boolean;
  latex_journal: string; // none | arxiv | neurips
  compile_pdf: boolean;
}

export interface MemorySettings {
  enabled: boolean;
  max_memories_per_prompt: number;
}

export interface CitationSettings {
  enable_citation_grounding: boolean;
  enable_novelty_check: boolean;
  enable_seed_discovery: boolean;
  drop_unresolved_citations: boolean;
}

export interface AllSettings {
  orchestrator: OrchestratorSettings;
  sandbox: SandboxSettings;
  literature: LiteratureSettings;
  knowledge: KnowledgeSettings;
  memory: MemorySettings;
  citation: CitationSettings;
  journal: JournalSettings;
}

export function getSettings() {
  return request<AllSettings>("/api/v1/settings");
}

export function updateSettings(section: string, body: Record<string, unknown>) {
  return request<AllSettings>(`/api/v1/settings/${section}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

// --- Paper Artifacts ---
export interface LiteratureSearchPaper {
  rank: number;
  title: string;
  authors: string;
  year: string;
  arxiv_id: string;
  arxiv_url: string;
}

export interface LiteratureSearchEntry {
  search_num: number;
  phase: string;
  agent_id: string;
  query: string;
  papers: LiteratureSearchPaper[];
}

export interface LiteratureSearchLog {
  thread_id: string;
  total_searches: number;
  searches: LiteratureSearchEntry[];
  unique_papers: LiteratureSearchPaper[];
}

export interface PaperArtifactList {
  paper_id: string;
  has_paper: boolean;
  has_literature: boolean;
  has_reviews: boolean;
  has_transcript: boolean;
  has_experiments: boolean;
  has_figures: boolean;
  has_pdf: boolean;
  experiment_files: string[];
  figure_files: string[];
}

export interface PaperArtifactContent {
  paper_id: string;
  filename: string;
  content_type: string;
  content: string;
}

export function getPaperArtifacts(paperId: string) {
  return request<PaperArtifactList>(`/api/v1/papers/${paperId}/artifacts`);
}

export function getPaperLiterature(paperId: string) {
  return request<LiteratureSearchLog>(`/api/v1/papers/${paperId}/literature`);
}

export function getPaperReviews(paperId: string) {
  return request<PaperArtifactContent>(`/api/v1/papers/${paperId}/reviews`);
}

export function getPaperTranscript(paperId: string) {
  return request<PaperArtifactContent>(`/api/v1/papers/${paperId}/transcript`);
}

export function getPaperExperiment(paperId: string, filename: string) {
  return request<PaperArtifactContent>(
    `/api/v1/papers/${paperId}/experiments/${encodeURIComponent(filename)}`
  );
}

export function paperFigureUrl(paperId: string, filename: string) {
  return `${BASE}/api/v1/papers/${paperId}/figures/${encodeURIComponent(filename)}`;
}

export function paperPdfUrl(paperId: string) {
  return `${BASE}/api/v1/papers/${paperId}/pdf`;
}
