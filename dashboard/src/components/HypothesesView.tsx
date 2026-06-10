import { useState } from "react";
import { agentColor, STATUS_COLORS } from "../colors";
import type { DashboardState, Hypothesis } from "../types";

const COLUMNS: { key: string; title: string; match: (h: Hypothesis) => boolean }[] = [
  { key: "proposed", title: "Proposed", match: (h) => h.status === "proposed" },
  {
    key: "testing",
    title: "Testing",
    match: (h) => h.status === "under_investigation" && !h.selected,
  },
  { key: "selected", title: "Selected", match: (h) => h.selected && h.status === "supported" },
  {
    key: "resolved",
    title: "Resolved",
    match: (h) =>
      ["contradicted", "refined", "abandoned"].includes(h.status) ||
      (h.status === "supported" && !h.selected),
  },
];

function HypCard({ h, state }: { h: Hypothesis; state: DashboardState }) {
  const [expanded, setExpanded] = useState(false);
  const matchups = state.tournament?.matchups.filter((m) => m.a === h.id || m.b === h.id) ?? [];
  return (
    <article
      className="hyp-card"
      style={{ ["--card-accent" as any]: STATUS_COLORS[h.status] ?? "var(--border)" }}
      onClick={() => setExpanded(!expanded)}
    >
      <div className={`statement ${expanded ? "" : "clamped"}`}>{h.statement}</div>
      <div className="hyp-meta">
        <span className="agent-dot" style={{ background: agentColor(h.author) }} />
        <span>{h.author ?? "team"}</span>
        {h.elo !== undefined && <span className="elo">Elo {h.elo.toFixed(0)}</span>}
      </div>
      {h.history.length > 1 && (
        <div className="history-strip" title={h.history.map((s) => s.status).join(" → ")}>
          {h.history.map((s, i) => (
            <span
              key={i}
              className="history-pip"
              style={{ background: STATUS_COLORS[s.status] ?? "#555" }}
            />
          ))}
        </div>
      )}
      {matchups.length > 0 && (
        <div className="matchup-chips">
          {matchups.map((m, i) => {
            const opponent = m.a === h.id ? m.b : m.a;
            const won = m.winner === h.id;
            return (
              <span key={i} className={`matchup-chip ${won ? "won" : "lost"}`} title={m.rationale}>
                {won ? "W" : "L"} vs {opponent.slice(0, 6)}
              </span>
            );
          })}
        </div>
      )}
    </article>
  );
}

export function HypothesesView({ state }: { state: DashboardState }) {
  const all = [...state.hypotheses.values()];
  if (all.length === 0) {
    return <div className="empty-note">No hypotheses yet — they appear during ideation.</div>;
  }
  return (
    <div className="kanban">
      {COLUMNS.map((col) => {
        const cards = all.filter(col.match);
        return (
          <section className="kanban-col" key={col.key}>
            <h3>
              {col.title} <span>{cards.length}</span>
            </h3>
            {cards.map((h) => (
              <HypCard key={h.id} h={h} state={state} />
            ))}
          </section>
        );
      })}
    </div>
  );
}
