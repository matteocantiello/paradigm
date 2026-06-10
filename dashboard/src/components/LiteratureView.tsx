import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import { useEffect, useRef, useState } from "react";
import type { DashboardState } from "../types";

interface SimNode extends SimulationNodeDatum {
  id: string;
  read: boolean;
  via: string;
  degree: number;
  title: string;
  bornAt: number;
}
type SimLink = SimulationLinkDatum<SimNode> & { id: string };

const W = 1200;
const H = 800;

/**
 * Literature as a constellation: papers are stars (read = bright gold with a
 * halo, unread = dim blue), citations are light-lines. Rendered as SVG so it
 * reliably paints and glows; d3-force lays it out. New stars pop in with a
 * gentle reheat. Degrades gracefully to a single star or an empty sky.
 */
export function LiteratureView({ state }: { state: DashboardState; fastMode?: boolean }) {
  const simRef = useRef<Simulation<SimNode, SimLink> | null>(null);
  const nodesRef = useRef<Map<string, SimNode>>(new Map());
  const linksRef = useRef<Map<string, SimLink>>(new Map());
  const [, setTick] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const tickCounter = useRef(0);

  // One persistent simulation
  useEffect(() => {
    const sim = forceSimulation<SimNode>([])
      .force("charge", forceManyBody().strength(-130))
      .force("center", forceCenter(W / 2, H / 2))
      .force("collide", forceCollide<SimNode>((d) => 8 + d.degree * 1.5))
      .force(
        "link",
        forceLink<SimNode, SimLink>([])
          .id((d) => d.id)
          .distance(80)
          .strength(0.35),
      )
      .on("tick", () => {
        // throttle React re-render to ~30fps
        tickCounter.current += 1;
        if (tickCounter.current % 2 === 0) setTick((t) => t + 1);
      });
    simRef.current = sim;
    return () => {
      sim.stop();
      simRef.current = null;
    };
  }, []);

  // Sync graph with reducer state
  useEffect(() => {
    const sim = simRef.current;
    if (!sim) return;
    const nodes = nodesRef.current;
    const links = linksRef.current;
    let changed = false;

    const sorted = [...state.papers.values()].sort((a, b) => a.firstSeq - b.firstSeq);
    for (const p of sorted) {
      const existing = nodes.get(p.id);
      if (!existing) {
        nodes.set(p.id, {
          id: p.id,
          read: p.read,
          via: p.discoveredVia,
          degree: 0,
          title: p.title,
          bornAt: performance.now(),
          x: W / 2 + (Math.random() - 0.5) * 120,
          y: H / 2 + (Math.random() - 0.5) * 120,
        });
        changed = true;
      } else {
        existing.read = p.read;
        if (p.title) existing.title = p.title;
      }
    }
    for (const e of state.citationEdges) {
      const key = `${e.source}->${e.target}`;
      if (links.has(key)) continue;
      const s = nodes.get(e.source);
      const t = nodes.get(e.target);
      if (s && t) {
        links.set(key, { id: key, source: s, target: t });
        s.degree += 1;
        t.degree += 1;
        changed = true;
      }
    }
    // Drop nodes that no longer exist (scrub backward)
    for (const id of [...nodes.keys()]) {
      if (!state.papers.has(id)) {
        nodes.delete(id);
        changed = true;
      }
    }
    if (changed) {
      for (const id of [...links.keys()]) {
        const [s, t] = id.split("->");
        if (!nodes.has(s) || !nodes.has(t)) links.delete(id);
      }
      sim.nodes([...nodes.values()]);
      (sim.force("link") as any)?.links([...links.values()]);
      sim.alpha(0.6).restart();
      setTick((t) => t + 1);
    }
  }, [state]);

  const nodes = [...nodesRef.current.values()];
  const links = [...linksRef.current.values()];
  const sel = selected ? state.papers.get(selected) : null;
  const now = performance.now();

  return (
    <div className="lit-wrap">
      <svg
        className="lit-svg"
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="xMidYMid meet"
        onClick={() => setSelected(null)}
      >
        <defs>
          <radialGradient id="star-read" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#fbe9b8" />
            <stop offset="100%" stopColor="#e9c977" />
          </radialGradient>
          <radialGradient id="star-unread" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#7fb0fb" />
            <stop offset="100%" stopColor="#3f6dc4" />
          </radialGradient>
        </defs>
        <g>
          {links.map((l) => {
            const s = l.source as SimNode;
            const t = l.target as SimNode;
            if (s.x == null || t.x == null) return null;
            return (
              <line
                key={l.id}
                className="lit-edge"
                x1={s.x}
                y1={s.y}
                x2={t.x}
                y2={t.y}
              />
            );
          })}
        </g>
        <g>
          {nodes.map((n) => {
            if (n.x == null) return null;
            const r = 5 + Math.min(n.degree, 8) * 1.4;
            const showLabel = nodes.length <= 36 || n.id === selected;
            const fresh = now - n.bornAt < 600;
            return (
              <g
                key={n.id}
                className={`lit-node ${n.read ? "lit-node-read" : ""} ${n.id === selected ? "sel" : ""} ${fresh ? "lit-node-enter" : ""}`}
                transform={`translate(${n.x} ${n.y})`}
                onClick={(ev) => {
                  ev.stopPropagation();
                  setSelected(n.id);
                }}
                style={{ cursor: "pointer" }}
              >
                {n.via === "seed" && (
                  <circle r={r + 5} fill="none" stroke="rgba(233,201,119,0.5)" strokeWidth={1} />
                )}
                <circle
                  r={r}
                  fill={n.read ? "url(#star-read)" : "url(#star-unread)"}
                  stroke={n.read ? "#fff2cf" : "#5a83cf"}
                  strokeWidth={0.6}
                  strokeOpacity={0.5}
                />
                {showLabel && (
                  <text x={r + 5} y={3.5}>
                    {n.id.length > 16 ? n.id.slice(0, 16) + "…" : n.id}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>

      <div className="lit-hud">
        <div>
          <span className="n">{state.stats.resultsScanned}</span> scanned ·{" "}
          <span className="n">{nodes.length}</span> on graph ·{" "}
          <span className="n">{state.stats.papersRead}</span> read
        </div>
        <div className="lit-legend">
          <span>
            <i style={{ background: "#e9c977", boxShadow: "0 0 6px #e9c977" }} />
            read
          </span>
          <span>
            <i style={{ background: "#3f6dc4" }} />
            discovered
          </span>
          <span>
            <i style={{ background: "transparent", boxShadow: "0 0 0 1px #e9c977" }} />
            seed
          </span>
        </div>
      </div>

      {nodes.length === 0 && (
        <div className="lit-empty-overlay">
          <div className="empty-note">
            <span className="big">An empty sky</span>
            No papers have entered the graph yet. Stars appear as agents read papers
            and follow citations during ideation &amp; planning.
          </div>
        </div>
      )}

      {sel && (
        <aside className="lit-panel" onClick={(e) => e.stopPropagation()}>
          <div className="lit-panel-id">{sel.id}</div>
          <div className="lit-panel-title">{sel.title || "(title unknown)"}</div>
          <div className="muted" style={{ fontSize: 11, marginTop: 7 }}>
            via {sel.discoveredVia}
            {sel.read ? ` · read (${((sel.charsRead ?? 0) / 1000).toFixed(0)}k chars)` : " · not read"}
          </div>
          <button className="scrub-btn lit-close" onClick={() => setSelected(null)}>
            ✕
          </button>
        </aside>
      )}
    </div>
  );
}
