import type { DashboardState, Ev } from "./types";

export function initialState(): DashboardState {
  return {
    run: {
      threadId: "",
      prompt: "",
      status: "running",
      phase: null,
      round: null,
      startedAt: null,
      completedAt: null,
      durationS: null,
      agents: [],
      totals: null,
    },
    stats: { searches: 0, resultsScanned: 0, papersRead: 0, experimentsDone: 0, debates: 0 },
    phases: [],
    hypotheses: new Map(),
    papers: new Map(),
    citationEdges: [],
    claims: new Map(),
    evidenceEdges: [],
    debates: new Map(),
    activeDebate: null,
    tournament: null,
    experiments: new Map(),
    paper: { id: null, title: "", wordCount: 0, nFigures: 0, sections: [] },
    review: { iterations: [], outcome: null },
    warnings: [],
    ticker: [],
  };
}

const TICKER_LIMIT = 50;

function notePaper(state: DashboardState, id: string, via: string, seq: number, title?: string) {
  if (!id) return;
  const existing = state.papers.get(id);
  if (existing) {
    if (title && !existing.title) existing.title = title;
    return;
  }
  state.papers.set(id, { id, title: title ?? "", read: false, discoveredVia: via, firstSeq: seq });
}

/** Apply one event to the state, mutating in place (callers manage identity). */
export function applyEvent(state: DashboardState, e: Ev): void {
  const p = e.payload ?? {};
  state.run.phase = e.phase ?? state.run.phase;
  state.run.round = e.round;

  switch (e.type) {
    case "run.started":
      state.run.threadId = p.thread_id ?? "";
      state.run.prompt = p.prompt ?? "";
      state.run.startedAt = e.ts;
      state.run.agents = p.config?.agents ?? [];
      break;

    case "run.completed":
      state.run.status = p.status ?? "completed";
      state.run.completedAt = e.ts;
      state.run.durationS = p.duration_s ?? null;
      state.run.totals = p.totals ?? null;
      break;

    case "phase.started": {
      const name = p.phase ?? e.phase ?? "?";
      if (!state.phases.some((ph) => ph.name === name)) {
        state.phases.push({ name, startSeq: e.seq, completed: false });
      }
      break;
    }

    case "phase.completed": {
      const ph = state.phases.find((x) => x.name === (p.phase ?? ""));
      if (ph) ph.completed = true;
      break;
    }

    case "search.performed":
      state.stats.searches += 1;
      state.stats.resultsScanned += p.n_results ?? 0;
      break;

    case "paper.read": {
      const id = p.paper_id ?? "";
      notePaper(state, id, "read", e.seq, p.title);
      const node = state.papers.get(id);
      if (node) {
        node.read = true;
        node.charsRead = p.chars_read;
        if (p.title) node.title = p.title;
      }
      state.stats.papersRead += 1;
      break;
    }

    case "citation.followed": {
      const src = p.source_paper_id ?? "";
      notePaper(state, src, "citation", e.seq);
      for (const target of p.paper_ids ?? []) {
        notePaper(state, target, "citation", e.seq);
        state.citationEdges.push({ source: src, target, direction: p.direction ?? "refs" });
      }
      break;
    }

    case "resource.ingested":
      if (p.kind === "paper") notePaper(state, p.url ?? "", "seed", e.seq, p.title);
      break;

    case "hypothesis.created": {
      const id = p.hypothesis_id ?? `h-${e.seq}`;
      if (!state.hypotheses.has(id)) {
        state.hypotheses.set(id, {
          id,
          statement: p.statement ?? "",
          rationale: p.rationale,
          author: e.agent,
          status: "proposed",
          selected: false,
          history: [{ seq: e.seq, status: "proposed" }],
          createdSeq: e.seq,
        });
      }
      break;
    }

    case "hypothesis.updated": {
      const h = state.hypotheses.get(p.hypothesis_id ?? "");
      if (h) {
        if (p.status && p.status !== h.status) {
          h.status = p.status;
          h.history.push({ seq: e.seq, status: p.status });
        }
        if (p.selected) h.selected = true;
        if (typeof p.elo === "number") h.elo = p.elo;
        if (typeof p.reason === "string" && p.reason) h.lastReason = p.reason;
        if (typeof p.source === "string" && p.source) h.lastSource = p.source;
      }
      break;
    }

    case "hypothesis.merged": {
      // A near-duplicate restatement was folded into an existing hypothesis at
      // creation time — don't add a node; just count the fold on the target.
      const h = state.hypotheses.get(p.into_id ?? "");
      if (h) h.mergedCount = (h.mergedCount ?? 0) + 1;
      break;
    }

    case "tournament.round": {
      const matchups = (p.matchups ?? []).map((m: string[], i: number) => ({
        a: m[0],
        b: m[1],
        winner: m[2],
        rationale: p.rationales?.[i],
      }));
      state.tournament = { matchups, seq: e.seq };
      break;
    }

    case "claim.extracted": {
      const id = p.claim_id ?? `c-${e.seq}`;
      state.claims.set(id, {
        id,
        statement: p.statement ?? "",
        source: p.source ?? "",
        author: e.agent,
        seq: e.seq,
      });
      break;
    }

    case "evidence.linked":
      state.evidenceEdges.push({
        claimId: p.claim_id ?? "",
        hypothesisId: p.hypothesis_id ?? "",
        relation: p.relation === "contradicts" ? "contradicts" : "supports",
        weight: p.weight,
      });
      break;

    case "debate.started": {
      const id = p.debate_id ?? `debate-${e.seq}`;
      state.debates.set(id, {
        id,
        challenger: p.challenger ?? "?",
        defender: p.defender ?? "?",
        topic: p.topic ?? "",
        turns: [],
        startSeq: e.seq,
      });
      state.activeDebate = id;
      break;
    }

    case "debate.turn": {
      const d = state.debates.get(p.debate_id ?? "");
      if (d) d.turns.push({ agent: e.agent, summary: p.summary ?? "", seq: e.seq });
      break;
    }

    case "debate.resolved": {
      const d = state.debates.get(p.debate_id ?? "");
      if (d) {
        d.outcome = p.outcome ?? "resolved";
        d.winner = p.winner ?? null;
        d.resolvedSeq = e.seq;
      }
      if (state.activeDebate === (p.debate_id ?? "")) state.activeDebate = null;
      state.stats.debates += 1;
      break;
    }

    case "experiment.started": {
      const id = p.experiment_id ?? `exp-${e.seq}`;
      state.experiments.set(id, {
        id,
        title: p.title ?? id,
        status: "running",
        agent: e.agent,
        artifacts: [],
        startSeq: e.seq,
        hypothesisId: p.hypothesis_id,
      });
      break;
    }

    case "experiment.completed": {
      const x = state.experiments.get(p.experiment_id ?? "");
      if (x) {
        x.status = p.status ?? "success";
        for (const a of p.artifacts ?? []) {
          if (!x.artifacts.some((b) => b.path === a.path)) x.artifacts.push(a);
        }
      }
      state.stats.experimentsDone += 1;
      break;
    }

    case "artifact.created": {
      const x = state.experiments.get(p.experiment_id ?? "");
      if (x && !x.artifacts.some((a) => a.path === p.path)) {
        x.artifacts.push({ path: p.path ?? "", kind: p.kind ?? "data" });
      }
      break;
    }

    case "section.drafted":
      state.paper.sections.push({
        name: p.section ?? "?",
        author: e.agent,
        wordCount: p.word_count ?? 0,
        seq: e.seq,
      });
      break;

    case "paper.assembled":
      state.paper.id = p.paper_id ?? null;
      state.paper.title = p.title ?? "";
      state.paper.wordCount = p.word_count ?? 0;
      state.paper.nFigures = p.n_figures ?? 0;
      break;

    case "review.iteration":
      state.review.iterations.push({
        iteration: p.iteration ?? null,
        recommendation: p.recommendation ?? "?",
        nRequiredChanges: p.n_required_changes ?? null,
        stage: p.stage ?? "internal",
        nReviewers: p.n_reviewers,
      });
      break;

    case "review.final":
      state.review.outcome = p.outcome ?? null;
      break;

    case "warning.emitted":
      state.warnings.push({ kind: p.kind ?? "?", message: p.message ?? "", seq: e.seq });
      break;
  }

  state.ticker.push(e);
  if (state.ticker.length > TICKER_LIMIT) state.ticker.splice(0, state.ticker.length - TICKER_LIMIT);
}

/** Rebuild state from scratch up to (and excluding) index `upto`. */
export function buildState(events: Ev[], upto: number): DashboardState {
  const state = initialState();
  for (let i = 0; i < upto && i < events.length; i++) applyEvent(state, events[i]);
  return state;
}
