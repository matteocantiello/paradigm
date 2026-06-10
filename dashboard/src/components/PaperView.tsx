import { agentColor } from "../colors";
import type { DashboardState, ReviewIteration } from "../types";

function recColor(rec: string): string {
  if (rec === "accept" || rec === "accepted") return "var(--green)";
  if (rec === "reject" || rec === "rejected" || rec === "desk_rejected") return "var(--red)";
  return "var(--gold)";
}

function Sparkline({ iters }: { iters: ReviewIteration[] }) {
  const vals = iters
    .filter((i) => i.nRequiredChanges != null)
    .map((i) => i.nRequiredChanges as number);
  if (vals.length < 2) return null;
  const max = Math.max(...vals, 1);
  const w = 90;
  const h = 24;
  const pts = vals
    .map((v, i) => `${(i / (vals.length - 1)) * w},${h - (v / max) * (h - 4) - 2}`)
    .join(" ");
  return (
    <svg width={w} height={h} className="sparkline">
      <polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth="1.5" />
    </svg>
  );
}

export function PaperView({ state }: { state: DashboardState }) {
  const { paper, review } = state;
  const maxWords = Math.max(...paper.sections.map((s) => s.wordCount), 1);

  if (paper.sections.length === 0 && review.iterations.length === 0) {
    return (
      <div className="empty-note">
        The paper outline appears as sections are drafted during the writing phase.
      </div>
    );
  }

  return (
    <div className="paper-wrap">
      {review.outcome && (
        <div
          className="outcome-banner"
          style={{
            borderColor: recColor(review.outcome),
            color: recColor(review.outcome),
          }}
        >
          {review.outcome.replace(/_/g, " ").toUpperCase()}
        </div>
      )}

      {paper.title && (
        <h2 className="paper-title">
          {paper.title}
          <span className="muted" style={{ fontSize: 12, marginLeft: 10 }}>
            {paper.wordCount.toLocaleString()} words · {paper.nFigures} figures
            {paper.id ? ` · ${paper.id}` : ""}
          </span>
        </h2>
      )}

      {paper.sections.length > 0 && (
        <section className="paper-outline">
          <h3>Outline</h3>
          {paper.sections.map((s, i) => (
            <div className="outline-row" key={`${s.name}-${i}`}>
              <span className="agent-dot" style={{ background: agentColor(s.author) }} />
              <span className="outline-name">{s.name.replace(/_/g, " ")}</span>
              <span className="outline-bar">
                <span
                  className="outline-fill"
                  style={{
                    width: `${(s.wordCount / maxWords) * 100}%`,
                    background: agentColor(s.author),
                  }}
                />
              </span>
              <span className="outline-words">{s.wordCount}w</span>
            </div>
          ))}
        </section>
      )}

      {review.iterations.length > 0 && (
        <section className="review-panel">
          <h3>
            Review trajectory <Sparkline iters={review.iterations} />
          </h3>
          <table className="review-table">
            <thead>
              <tr>
                <th>#</th>
                <th>stage</th>
                <th>recommendation</th>
                <th>required changes</th>
              </tr>
            </thead>
            <tbody>
              {review.iterations.map((it, i) => (
                <tr key={i}>
                  <td>{it.iteration ?? "—"}</td>
                  <td>{it.stage}{it.nReviewers ? ` (${it.nReviewers} reviewers)` : ""}</td>
                  <td style={{ color: recColor(it.recommendation) }}>{it.recommendation}</td>
                  <td>{it.nRequiredChanges ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
