import { useState } from "react";
import { artifactUrl } from "../api";
import { agentColor } from "../colors";
import type { DashboardState } from "../types";

export function ExperimentsView({
  state,
  threadId,
}: {
  state: DashboardState;
  threadId: string;
}) {
  const [lightbox, setLightbox] = useState<string | null>(null);
  const experiments = [...state.experiments.values()].sort((a, b) => a.startSeq - b.startSeq);

  if (experiments.length === 0) {
    return (
      <div className="empty-note">No experiments yet — they appear during the execution phase.</div>
    );
  }

  return (
    <>
      <div className="exp-grid">
        {experiments.map((x) => {
          const figures = x.artifacts.filter((a) => a.kind === "figure");
          const others = x.artifacts.filter((a) => a.kind !== "figure");
          const linked = x.hypothesisId ? state.hypotheses.get(x.hypothesisId) : null;
          return (
            <article className="exp-card" key={x.id}>
              <div className="exp-head">
                <span className="agent-dot" style={{ background: agentColor(x.agent) }} />
                <span className="exp-title" title={x.title}>
                  {x.title}
                </span>
                <span className={`chip ${x.status}`}>{x.status}</span>
              </div>
              {linked && (
                <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                  tests: {linked.statement.slice(0, 80)}…
                </div>
              )}
              {(figures.length > 0 || others.length > 0) && (
                <div className="exp-figs">
                  {figures.map((a) => (
                    <img
                      key={a.path}
                      className="exp-fig"
                      src={artifactUrl(threadId, a.path)}
                      alt={a.path}
                      loading="lazy"
                      onClick={() => setLightbox(a.path)}
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = "none";
                      }}
                    />
                  ))}
                  {others.map((a) => (
                    <span key={a.path} className="exp-artifact-pill">
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
        <div className="lightbox" onClick={() => setLightbox(null)}>
          <img src={artifactUrl(threadId, lightbox)} alt={lightbox} />
          <div className="caption">{lightbox}</div>
        </div>
      )}
    </>
  );
}
