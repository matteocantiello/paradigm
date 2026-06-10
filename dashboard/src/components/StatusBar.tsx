import { PHASE_LABELS } from "../colors";
import type { DashboardState } from "../types";

function fmtElapsed(state: DashboardState, lastTs: string | null): string {
  if (!state.run.startedAt || !lastTs) return "—";
  const ms = Date.parse(lastTs) - Date.parse(state.run.startedAt);
  if (!Number.isFinite(ms) || ms < 0) return "—";
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m ${s % 60}s`;
}

export function StatusBar({
  state,
  live,
  onBack,
  onToggleTheme,
}: {
  state: DashboardState;
  live: boolean;
  onBack?: () => void;
  onToggleTheme?: () => void;
}) {
  const aliveHyps = [...state.hypotheses.values()].filter(
    (h) => !["contradicted", "abandoned"].includes(h.status),
  ).length;
  const lastTs = state.ticker.length ? state.ticker[state.ticker.length - 1].ts : null;
  const finished = state.run.completedAt !== null;
  const chipClass = finished
    ? state.run.status === "published"
      ? "published"
      : "other"
    : live
      ? "live"
      : "running";

  return (
    <header className="statusbar">
      {onBack && (
        <button className="back-btn" onClick={onBack} title="Back to all threads">
          ‹
        </button>
      )}
      <span className="brand">Paradigm</span>
      <span className="thread-id">{state.run.threadId || "—"}</span>
      <span className={`status-chip ${chipClass}`}>
        {finished ? state.run.status : live ? "live" : "replay"}
      </span>
      <nav className="phase-stepper">
        {state.phases.map((ph, i) => (
          <span key={ph.name} style={{ display: "inline-flex", alignItems: "center" }}>
            {i > 0 && <span className="phase-sep">▸</span>}
            <span
              className={`phase-pip ${ph.completed ? "done" : state.run.phase === ph.name ? "current" : ""}`}
            >
              {ph.completed ? "✓ " : ""}
              {PHASE_LABELS[ph.name] ?? ph.name}
            </span>
          </span>
        ))}
      </nav>
      <div className="counters">
        {state.run.round != null && (
          <span className="counter">
            round <b>{state.run.round}</b>
          </span>
        )}
        <span className="counter">
          elapsed <b>{fmtElapsed(state, lastTs)}</b>
        </span>
        <span className="counter">
          papers read <b>{state.stats.papersRead}</b>
        </span>
        <span className="counter">
          hypotheses <b>{aliveHyps}</b>
        </span>
        <span className="counter">
          experiments <b>{state.stats.experimentsDone}</b>
        </span>
        {onToggleTheme && (
          <button className="theme-btn" onClick={onToggleTheme} title="Toggle light / dark">
            ◐
          </button>
        )}
      </div>
    </header>
  );
}
