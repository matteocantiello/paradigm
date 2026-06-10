/** Event envelope written by paradigm's ResearchEventStream. */
export interface Ev {
  seq: number;
  ts: string;
  type: string;
  phase: string | null;
  round: number | null;
  agent: string | null;
  payload: Record<string, any>;
}

export interface StatusChange {
  seq: number;
  status: string;
}

export interface Hypothesis {
  id: string;
  statement: string;
  rationale?: string;
  author: string | null;
  status: string; // proposed | under_investigation | supported | contradicted | refined | abandoned
  selected: boolean;
  elo?: number;
  history: StatusChange[];
  createdSeq: number;
}

export interface PaperNode {
  id: string;
  title: string;
  read: boolean;
  charsRead?: number;
  discoveredVia: string; // read | citation | seed
  firstSeq: number;
}

export interface CitationEdge {
  source: string;
  target: string;
  direction: string;
}

export interface Claim {
  id: string;
  statement: string;
  source: string;
  author: string | null;
  seq: number;
}

export interface EvidenceEdge {
  claimId: string;
  hypothesisId: string;
  relation: "supports" | "contradicts";
  weight?: number;
}

export interface DebateTurn {
  agent: string | null;
  summary: string;
  seq: number;
}

export interface Debate {
  id: string;
  challenger: string;
  defender: string;
  topic: string;
  turns: DebateTurn[];
  outcome?: string;
  winner?: string | null;
  startSeq: number;
  resolvedSeq?: number;
}

export interface Artifact {
  path: string;
  kind: string;
}

export interface Experiment {
  id: string;
  title: string;
  status: string; // running | success | failure | timeout ...
  agent: string | null;
  artifacts: Artifact[];
  startSeq: number;
  hypothesisId?: string;
}

export interface Section {
  name: string;
  author: string | null;
  wordCount: number;
  seq: number;
}

export interface ReviewIteration {
  iteration: number | null;
  recommendation: string;
  nRequiredChanges: number | null;
  stage: string; // internal | peer
  nReviewers?: number;
}

export interface TournamentMatchup {
  a: string;
  b: string;
  winner: string;
  rationale?: string;
}

export interface RunInfo {
  threadId: string;
  prompt: string;
  status: string; // running | published | rejected | ...
  phase: string | null;
  round: number | null;
  startedAt: string | null;
  completedAt: string | null;
  durationS: number | null;
  agents: string[];
  totals: Record<string, number> | null;
}

export interface Stats {
  searches: number;
  resultsScanned: number;
  papersRead: number;
  experimentsDone: number;
  debates: number;
}

export interface PaperState {
  id: string | null;
  title: string;
  wordCount: number;
  nFigures: number;
  sections: Section[];
}

export interface DashboardState {
  run: RunInfo;
  stats: Stats;
  phases: { name: string; startSeq: number; completed: boolean }[];
  hypotheses: Map<string, Hypothesis>;
  papers: Map<string, PaperNode>;
  citationEdges: CitationEdge[];
  claims: Map<string, Claim>;
  evidenceEdges: EvidenceEdge[];
  debates: Map<string, Debate>;
  activeDebate: string | null;
  tournament: { matchups: TournamentMatchup[]; seq: number } | null;
  experiments: Map<string, Experiment>;
  paper: PaperState;
  review: { iterations: ReviewIteration[]; outcome: string | null };
  warnings: { kind: string; message: string; seq: number }[];
  ticker: Ev[];
}
