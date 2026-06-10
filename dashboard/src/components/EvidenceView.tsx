import { useMemo, useRef } from "react";
import { agentColor, STATUS_COLORS } from "../colors";
import type { DashboardState } from "../types";

/**
 * Bipartite hypotheses ↔ claims view. Green edges support, red contradict.
 * A hypothesis whose status changed recently flashes — "watch the system
 * change its mind".
 */
export function EvidenceView({ state }: { state: DashboardState }) {
  const hyps = [...state.hypotheses.values()].sort((a, b) => a.createdSeq - b.createdSeq);
  const claims = [...state.claims.values()].sort((a, b) => a.seq - b.seq);
  const lastSeq = state.ticker.length ? state.ticker[state.ticker.length - 1].seq : 0;

  const rowRefs = useRef<Map<string, HTMLElement>>(new Map());

  const edges = useMemo(() => {
    return state.evidenceEdges
      .map((e, i) => ({ ...e, key: i }))
      .filter((e) => state.hypotheses.has(e.hypothesisId) && state.claims.has(e.claimId));
  }, [state]);

  if (hyps.length === 0 && claims.length === 0) {
    return (
      <div className="empty-note">
        Hypotheses and extracted claims appear here as the team forms beliefs.
      </div>
    );
  }

  const ROW_H = 76;
  const height = Math.max(hyps.length, claims.length) * ROW_H + 20;

  return (
    <div className="evidence-wrap" style={{ position: "relative" }}>
      {edges.length > 0 && (
        <svg className="evidence-svg" width="100%" height={height}>
          {edges.map((e) => {
            const hi = hyps.findIndex((h) => h.id === e.hypothesisId);
            const ci = claims.findIndex((c) => c.id === e.claimId);
            if (hi < 0 || ci < 0) return null;
            const y1 = hi * ROW_H + 40;
            const y2 = ci * ROW_H + 40;
            return (
              <path
                key={e.key}
                d={`M 38% ${y1} C 50% ${y1}, 50% ${y2}, 62% ${y2}`}
                fill="none"
                stroke={e.relation === "supports" ? "var(--green)" : "var(--red)"}
                strokeWidth={1.5 + (e.weight ?? 1)}
                strokeOpacity={0.55}
              />
            );
          })}
        </svg>
      )}
      <div className="evidence-cols">
        <section className="evidence-col">
          <h3>Hypotheses ({hyps.length})</h3>
          {hyps.map((h) => {
            const lastChange = h.history[h.history.length - 1];
            const flash = lastChange && lastSeq - lastChange.seq < 5 && h.history.length > 1;
            return (
              <article
                key={h.id}
                ref={(el) => el && rowRefs.current.set(h.id, el)}
                className={`evidence-item ${flash ? "flash" : ""}`}
                style={{ borderLeftColor: STATUS_COLORS[h.status] ?? "var(--border)" }}
              >
                <div className="evidence-text">{h.statement}</div>
                <div className="evidence-meta">
                  <span style={{ color: STATUS_COLORS[h.status] }}>{h.status}</span>
                  {h.elo !== undefined && <span className="elo">Elo {h.elo.toFixed(0)}</span>}
                </div>
              </article>
            );
          })}
        </section>
        <section className="evidence-col">
          <h3>Claims ({claims.length})</h3>
          {claims.map((c) => (
            <article key={c.id} className="evidence-item claim">
              <div className="evidence-text">{c.statement}</div>
              <div className="evidence-meta">
                <span
                  className="agent-dot"
                  style={{ background: agentColor(c.author), display: "inline-block" }}
                />
                <span className="muted">{c.source}</span>
              </div>
            </article>
          ))}
        </section>
      </div>
      {edges.length === 0 && claims.length > 0 && (
        <div className="muted" style={{ fontSize: 11, marginTop: 12, textAlign: "center" }}>
          No explicit claim→hypothesis links recorded yet (evidence.linked events).
        </div>
      )}
    </div>
  );
}
