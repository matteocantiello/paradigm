import { useEffect, useState } from "react";
import { agentColor } from "../colors";
import type { DashboardState, Debate } from "../types";

function DebateCard({ d, onClose }: { d: Debate; onClose: () => void }) {
  return (
    <div className="debate-overlay">
      <h4>⚔ Debate{d.outcome ? ` — ${d.outcome.replace(/_/g, " ")}` : ""}</h4>
      <div className="debate-vs">
        <span style={{ color: agentColor(d.challenger) }}>{d.challenger}</span>
        <span className="muted">vs</span>
        <span style={{ color: agentColor(d.defender) }}>{d.defender}</span>
        {d.winner && (
          <span className="muted" style={{ marginLeft: "auto", fontSize: 11 }}>
            prevails: <b style={{ color: agentColor(d.winner) }}>{d.winner}</b>
          </span>
        )}
      </div>
      <div className="debate-topic">{d.topic}</div>
      <div className="debate-turns">
        {d.turns.map((t, i) => (
          <div className="debate-turn-row" key={i}>
            <span className="agent-dot" style={{ background: agentColor(t.agent), marginTop: 4 }} />
            <span>{t.summary}</span>
          </div>
        ))}
      </div>
      <button className="scrub-btn" style={{ marginTop: 10 }} onClick={onClose}>
        ✕
      </button>
    </div>
  );
}

/** Live debate overlay + collapsed pills for resolved debates. */
export function DebateOverlay({ state }: { state: DashboardState }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState<string | null>(null);

  // A newly active debate takes over (unless the user dismissed that one)
  const active = state.activeDebate;
  useEffect(() => {
    if (active && active !== dismissed) setOpenId(active);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  const open = openId ? state.debates.get(openId) : null;
  const resolved = [...state.debates.values()].filter((d) => d.outcome);

  return (
    <>
      {open && (
        <DebateCard
          d={open}
          onClose={() => {
            setDismissed(open.id);
            setOpenId(null);
          }}
        />
      )}
      {!open && resolved.length > 0 && (
        <div className="debate-pills">
          {resolved.map((d) => (
            <button key={d.id} className="debate-pill" onClick={() => setOpenId(d.id)}>
              ⚔ {d.challenger.replace(/-\d+$/, "")} vs {d.defender.replace(/-\d+$/, "")}
            </button>
          ))}
        </div>
      )}
    </>
  );
}
