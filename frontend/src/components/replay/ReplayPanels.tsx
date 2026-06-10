import { agentColor, agentShort, PHASE_LABELS, STATUS_COLORS } from "@/lib/replay/colors";
import type { DashboardState, Ev, Hypothesis } from "@/lib/replay/types";
import { useState } from "react";

/** Phase stepper + headline counters for the replay header. */
export function ReplayStatusBar({ state }: { state: DashboardState }) {
  const aliveHyps = [...state.hypotheses.values()].filter(
    (h) => !["contradicted", "abandoned"].includes(h.status),
  ).length;
  return (
    <header className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-border bg-card/40 px-4 py-2.5">
      <nav className="flex items-center gap-1">
        {state.phases.map((ph, i) => (
          <span key={ph.name} className="flex items-center">
            {i > 0 && <span className="px-0.5 text-[9px] text-muted-foreground/50">▸</span>}
            <span
              className={`rounded-full px-2.5 py-1 text-[10px] uppercase tracking-wide ${
                ph.completed
                  ? "text-emerald-400"
                  : state.run.phase === ph.name
                    ? "bg-primary text-background"
                    : "text-muted-foreground"
              }`}
            >
              {ph.completed ? "✓ " : ""}
              {PHASE_LABELS[ph.name] ?? ph.name}
            </span>
          </span>
        ))}
      </nav>
      <div className="ml-auto flex items-center gap-5 text-[10px] uppercase tracking-wide text-muted-foreground">
        {state.run.round != null && (
          <Counter label="round" value={String(state.run.round)} />
        )}
        <Counter label="read" value={String(state.stats.papersRead)} />
        <Counter label="hypotheses" value={String(aliveHyps)} />
        <Counter label="experiments" value={String(state.stats.experimentsDone)} />
        {state.run.status && state.run.completedAt && (
          <span
            className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase ${
              state.run.status === "published"
                ? "bg-emerald-500/15 text-emerald-400"
                : "bg-red-500/10 text-red-400"
            }`}
          >
            {state.run.status}
          </span>
        )}
      </div>
    </header>
  );
}

function Counter({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex flex-col leading-tight">
      <b className="text-base font-medium tabular-nums text-foreground">{value}</b>
      {label}
    </span>
  );
}

const COLUMNS: { key: string; title: string; match: (h: Hypothesis) => boolean }[] = [
  { key: "proposed", title: "Proposed", match: (h) => h.status === "proposed" },
  {
    key: "testing",
    title: "Testing",
    match: (h) => h.status === "under_investigation" && !h.selected,
  },
  { key: "selected", title: "Selected", match: (h) => h.selected },
  {
    key: "resolved",
    title: "Resolved",
    match: (h) => ["contradicted", "refined", "abandoned"].includes(h.status),
  },
];

export function ReplayHypotheses({ state }: { state: DashboardState }) {
  const all = [...state.hypotheses.values()];
  if (all.length === 0) {
    return <Empty>No hypotheses yet — they form during ideation.</Empty>;
  }
  return (
    <div className="flex h-full gap-3 overflow-x-auto p-4">
      {COLUMNS.map((col) => {
        const cards = all.filter(col.match);
        return (
          <section key={col.key} className="min-w-[200px] flex-1">
            <h3 className="mb-2 flex justify-between border-b border-border pb-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
              {col.title} <span>{cards.length}</span>
            </h3>
            {cards.map((h) => {
              const matchups =
                state.tournament?.matchups.filter((m) => m.a === h.id || m.b === h.id) ?? [];
              return (
                <article
                  key={h.id}
                  className="mb-2 rounded-lg border border-border bg-card p-2.5"
                  style={{ borderLeft: `2px solid ${STATUS_COLORS[h.status] ?? "var(--border)"}` }}
                >
                  <div className="line-clamp-4 text-[12.5px] leading-snug">{h.statement}</div>
                  <div className="mt-2 flex items-center gap-2 text-[10.5px] text-muted-foreground">
                    <span
                      className="h-2 w-2 flex-none rounded-full"
                      style={{ background: agentColor(h.author) }}
                    />
                    <span>{agentShort(h.author)}</span>
                    {h.elo !== undefined && (
                      <span className="ml-auto tabular-nums text-primary">Elo {h.elo.toFixed(0)}</span>
                    )}
                  </div>
                  {matchups.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {matchups.map((m, i) => {
                        const won = m.winner === h.id;
                        const opp = m.a === h.id ? m.b : m.a;
                        return (
                          <span
                            key={i}
                            className={`rounded-full border px-1.5 text-[9.5px] ${
                              won
                                ? "border-emerald-500/40 text-emerald-400"
                                : "border-border text-muted-foreground"
                            }`}
                          >
                            {won ? "W" : "L"} vs {opp.slice(0, 6)}
                          </span>
                        );
                      })}
                    </div>
                  )}
                </article>
              );
            })}
          </section>
        );
      })}
    </div>
  );
}

export function ReplayExperiments({
  state,
  artifactUrl,
}: {
  state: DashboardState;
  artifactUrl?: (path: string) => string | null;
}) {
  const experiments = [...state.experiments.values()].sort((a, b) => a.startSeq - b.startSeq);
  const [lightbox, setLightbox] = useState<string | null>(null);
  if (experiments.length === 0) {
    return <Empty>No experiments yet — they run during the execution phase.</Empty>;
  }
  const chip = (s: string) =>
    s === "success"
      ? "bg-emerald-500/15 text-emerald-400"
      : s === "running"
        ? "bg-primary/15 text-primary"
        : "bg-red-500/15 text-red-400";
  return (
    <div className="h-full overflow-auto">
      <div className="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-3 p-4">
      {experiments.map((x) => {
        const figures = x.artifacts.filter((a) => a.kind === "figure");
        return (
          <article key={x.id} className="rounded-xl border border-border bg-card p-3.5">
            <div className="flex items-center gap-2">
              <span
                className="h-2 w-2 flex-none rounded-full"
                style={{ background: agentColor(x.agent) }}
              />
              <span className="flex-1 truncate text-[12.5px] font-medium" title={x.title}>
                {x.title}
              </span>
              <span className={`rounded-full px-2 py-0.5 text-[9px] uppercase ${chip(x.status)}`}>
                {x.status}
              </span>
            </div>
            {x.artifacts.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {figures.map((a) => {
                  const url = artifactUrl?.(a.path);
                  return url ? (
                    <img
                      key={a.path}
                      src={url}
                      alt={a.path}
                      loading="lazy"
                      onClick={() => setLightbox(url)}
                      className="h-20 w-28 cursor-zoom-in rounded-md border border-border object-cover transition-transform hover:scale-105"
                      onError={(e) => ((e.target as HTMLImageElement).style.display = "none")}
                    />
                  ) : (
                    <span
                      key={a.path}
                      className="rounded-md border border-dashed border-border px-1.5 py-0.5 text-[9.5px] text-muted-foreground"
                    >
                      {a.kind}: {a.path.split("/").pop()}
                    </span>
                  );
                })}
                {x.artifacts
                  .filter((a) => a.kind !== "figure")
                  .map((a) => (
                    <span
                      key={a.path}
                      className="rounded-md border border-dashed border-border px-1.5 py-0.5 text-[9.5px] text-muted-foreground"
                    >
                      {a.kind}: {a.path.split("/").pop()}
                    </span>
                  ))}
              </div>
            )}
          </article>
        );
      })}
      </div>
      {lightbox && (
        <div
          className="fixed inset-0 z-50 flex cursor-zoom-out items-center justify-center bg-black/85 backdrop-blur-sm"
          onClick={() => setLightbox(null)}
        >
          <img src={lightbox} alt="figure" className="max-h-[88vh] max-w-[92vw] rounded-lg" />
        </div>
      )}
    </div>
  );
}

function recColor(rec: string): string {
  if (rec === "accept" || rec === "accepted") return "text-emerald-400";
  if (rec.includes("reject")) return "text-red-400";
  return "text-primary";
}

export function ReplayPaper({ state }: { state: DashboardState }) {
  const { paper, review } = state;
  const maxWords = Math.max(...paper.sections.map((s) => s.wordCount), 1);
  if (paper.sections.length === 0 && review.iterations.length === 0) {
    return <Empty>The paper outline appears as sections are drafted during writing.</Empty>;
  }
  return (
    <div className="mx-auto max-w-3xl p-4">
      {review.outcome && (
        <div
          className={`mb-5 rounded-lg border border-border px-4 py-3 text-center text-[13px] font-semibold uppercase tracking-wider ${recColor(review.outcome)}`}
        >
          {review.outcome.replace(/_/g, " ")}
        </div>
      )}
      {paper.title && (
        <h2 className="mb-1 font-serif text-2xl">{paper.title}</h2>
      )}
      {(paper.wordCount > 0 || paper.nFigures > 0) && (
        <div className="mb-5 text-[11px] text-muted-foreground">
          {paper.wordCount.toLocaleString()} words · {paper.nFigures} figures
        </div>
      )}
      {paper.sections.length > 0 && (
        <section className="mb-7">
          <h3 className="mb-2 text-[10px] uppercase tracking-wider text-muted-foreground">Outline</h3>
          {paper.sections.map((s, i) => (
            <div key={`${s.name}-${i}`} className="flex items-center gap-3 py-1.5">
              <span
                className="h-2 w-2 flex-none rounded-full"
                style={{ background: agentColor(s.author) }}
              />
              <span className="w-32 text-[12px] capitalize">{s.name.replace(/_/g, " ")}</span>
              <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-card">
                <span
                  className="block h-full rounded-full"
                  style={{
                    width: `${(s.wordCount / maxWords) * 100}%`,
                    background: agentColor(s.author),
                  }}
                />
              </span>
              <span className="w-12 text-right text-[10.5px] tabular-nums text-muted-foreground">
                {s.wordCount}w
              </span>
            </div>
          ))}
        </section>
      )}
      {review.iterations.length > 0 && (
        <section>
          <h3 className="mb-2 text-[10px] uppercase tracking-wider text-muted-foreground">
            Review trajectory
          </h3>
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-left text-[9.5px] uppercase tracking-wide text-muted-foreground">
                <th className="border-b border-border py-1.5 pr-3">#</th>
                <th className="border-b border-border py-1.5 pr-3">stage</th>
                <th className="border-b border-border py-1.5 pr-3">recommendation</th>
                <th className="border-b border-border py-1.5">changes</th>
              </tr>
            </thead>
            <tbody>
              {review.iterations.map((it, i) => (
                <tr key={i}>
                  <td className="border-b border-border/50 py-2 pr-3">{it.iteration ?? "—"}</td>
                  <td className="border-b border-border/50 py-2 pr-3">
                    {it.stage}
                    {it.nReviewers ? ` (${it.nReviewers})` : ""}
                  </td>
                  <td className={`border-b border-border/50 py-2 pr-3 ${recColor(it.recommendation)}`}>
                    {it.recommendation}
                  </td>
                  <td className="border-b border-border/50 py-2">{it.nRequiredChanges ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}

function tickLine(e: Ev): string {
  const p = e.payload ?? {};
  switch (e.type) {
    case "run.started": return "run started";
    case "run.completed": return `run completed: ${p.status}`;
    case "phase.started": return `phase → ${p.phase}`;
    case "round.started": return `round ${p.round} begins`;
    case "search.performed": return `search "${String(p.query ?? "").slice(0, 36)}" → ${p.n_results} hits`;
    case "paper.read": return `read ${p.paper_id}: ${String(p.title ?? "").slice(0, 44)}`;
    case "citation.followed": return `${p.direction} of ${p.source_paper_id} → ${p.n_found}`;
    case "hypothesis.created": return `hypothesis: ${String(p.statement ?? "").slice(0, 52)}…`;
    case "hypothesis.updated": return `hypothesis → ${p.status}${p.selected ? " (selected)" : ""}`;
    case "tournament.round": return `tournament: ${(p.matchups ?? []).length} matchups`;
    case "claim.extracted": return `claim: ${String(p.statement ?? "").slice(0, 52)}`;
    case "debate.started": return `⚔ ${p.challenger} challenges ${p.defender}`;
    case "debate.resolved": return `debate resolved (${p.outcome})`;
    case "experiment.started": return `experiment ${p.experiment_id} running`;
    case "experiment.completed": return `experiment ${p.experiment_id}: ${p.status}`;
    case "artifact.created": return `figure ${String(p.path ?? "").split("/").pop()}`;
    case "section.drafted": return `drafted ${p.section} (${p.word_count}w)`;
    case "paper.assembled": return `paper assembled: ${p.word_count}w`;
    case "review.iteration": return `${p.stage} review → ${p.recommendation}`;
    case "review.final": return `review final: ${p.outcome}`;
    case "warning.emitted": return `⚠ ${p.kind}: ${String(p.message ?? "").slice(0, 48)}`;
    default: return e.type;
  }
}

export function ReplayTicker({ events }: { events: Ev[] }) {
  return (
    <div className="h-full overflow-y-auto p-3">
      {events.length === 0 && <Empty>No events yet.</Empty>}
      {events.map((e) => (
        <div key={e.seq} className="flex gap-2 px-1 py-1 text-[11.5px] leading-snug">
          <span className="flex-none pt-px text-[10px] tabular-nums text-muted-foreground/70">
            {e.ts.slice(11, 19)}
          </span>
          <span className="text-muted-foreground">
            <b className="font-semibold" style={{ color: agentColor(e.agent) }}>
              {agentShort(e.agent)}
            </b>{" "}
            {tickLine(e)}
          </span>
        </div>
      ))}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center p-10 text-center text-xs text-muted-foreground">
      {children}
    </div>
  );
}
