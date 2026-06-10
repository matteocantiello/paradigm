import { useEffect, useRef, useState } from "react";
import { agentColor, agentShort } from "../colors";
import type { Ev } from "../types";

function tickLine(e: Ev): string {
  const p = e.payload ?? {};
  switch (e.type) {
    case "run.started": return `run started — ${String(p.prompt ?? "").slice(0, 60)}…`;
    case "run.completed": return `run completed: ${p.status}`;
    case "phase.started": return `phase → ${p.phase}`;
    case "phase.completed": return `phase ${p.phase} done`;
    case "round.started": return `round ${p.round} begins`;
    case "round.completed": return `round ${p.round} complete`;
    case "checkpoint.saved": return `checkpoint (${p.label ?? p.phase})`;
    case "search.performed": return `search "${String(p.query ?? "").slice(0, 40)}" → ${p.n_results} hits, ${p.n_new} new`;
    case "paper.read": return `read ${p.paper_id}: ${String(p.title ?? "").slice(0, 50)}`;
    case "citation.followed": return `followed ${p.direction} of ${p.source_paper_id} → ${p.n_found}`;
    case "resource.ingested": return `ingested ${p.kind}: ${String(p.title ?? p.url ?? "").slice(0, 50)}`;
    case "hypothesis.created": return `hypothesis: ${String(p.statement ?? "").slice(0, 60)}…`;
    case "hypothesis.updated": return `hypothesis ${p.hypothesis_id} → ${p.status}${p.selected ? " (selected)" : ""}`;
    case "tournament.round": return `tournament: ${(p.matchups ?? []).length} matchups judged`;
    case "claim.extracted": return `claim: ${String(p.statement ?? "").slice(0, 60)}`;
    case "evidence.linked": return `evidence ${p.relation} ${p.hypothesis_id}`;
    case "debate.started": return `⚔ debate: ${p.challenger} challenges ${p.defender}`;
    case "debate.turn": return `debate turn`;
    case "debate.resolved": return `debate resolved (${p.outcome})`;
    case "experiment.started": return `experiment ${p.experiment_id} running`;
    case "experiment.completed": return `experiment ${p.experiment_id}: ${p.status}`;
    case "artifact.created": return `figure ${String(p.path ?? "").split("/").pop()}`;
    case "section.drafted": return `drafted ${p.section} (${p.word_count}w)`;
    case "paper.assembled": return `paper assembled: ${p.word_count}w, ${p.n_figures} figures`;
    case "review.iteration": return `${p.stage} review → ${p.recommendation}${p.n_required_changes != null ? ` (${p.n_required_changes} changes)` : ""}`;
    case "review.final": return `review final: ${p.outcome}`;
    case "warning.emitted": return `⚠ ${p.kind}: ${String(p.message ?? "").slice(0, 60)}`;
    default: return e.type;
  }
}

export function Ticker({ events, live }: { events: Ev[]; live?: boolean }) {
  const [collapsed, setCollapsed] = useState(false);
  const [hover, setHover] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!hover && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [events, hover]);

  return (
    <aside className={`ticker ${collapsed ? "collapsed" : ""}`}>
      <div className="ticker-head" onClick={() => setCollapsed(!collapsed)}>
        {collapsed ? (
          "‹"
        ) : (
          <>
            {live && <span className="live-dot" />}
            Event feed ›
          </>
        )}
      </div>
      {!collapsed && (
        <div
          ref={bodyRef}
          className="ticker-body"
          onMouseEnter={() => setHover(true)}
          onMouseLeave={() => setHover(false)}
        >
          {events.map((e) => (
            <div className="tick" key={e.seq}>
              <span className="t">{e.ts.slice(11, 19)}</span>
              <span className="msg">
                <span className="who" style={{ color: agentColor(e.agent) }}>
                  {agentShort(e.agent)}
                </span>{" "}
                {tickLine(e)}
              </span>
            </div>
          ))}
        </div>
      )}
    </aside>
  );
}
