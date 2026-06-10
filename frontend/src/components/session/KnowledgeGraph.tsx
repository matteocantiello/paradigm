import type { KGraph, KNodeKind } from "@/lib/knowledgeGraph";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import { useCallback, useEffect, useRef, useState } from "react";

interface SimNode extends SimulationNodeDatum {
  id: string;
  kind: KNodeKind;
  label: string;
  status?: string;
  elo?: number;
  changedSeq?: number;
  deg: number;
}
type SimLink = SimulationLinkDatum<SimNode> & { id: string; relation: string };

const W = 1000;
const H = 700;

// Hypothesis status → color (CSS tokens / oklch).
const STATUS_FILL: Record<string, string> = {
  proposed: "var(--muted-foreground)",
  under_investigation: "var(--primary)",
  supported: "oklch(0.72 0.15 150)",
  contradicted: "oklch(0.62 0.2 25)",
  refined: "var(--primary)",
  abandoned: "var(--muted-foreground)",
};

function nodeFill(n: SimNode): string {
  if (n.kind === "hypothesis") return STATUS_FILL[n.status ?? "proposed"] ?? "var(--primary)";
  if (n.kind === "claim") return "var(--accent-cyan)";
  return "oklch(0.7 0.04 260)"; // entity — neutral slate
}
function nodeRadius(n: SimNode): number {
  const base = n.kind === "hypothesis" ? 8 : n.kind === "entity" ? 6 : 5;
  return base + Math.min(n.deg, 6) * 0.8;
}

/**
 * The world model as a graph: entities (slate), hypotheses (colored by status),
 * and claims (cyan), with supports (green) / contradicts (red) / relation
 * (neutral) edges. Pan/zoom/fit like the literature constellation. In replay,
 * a hypothesis flashes when its status just changed.
 */
export function KnowledgeGraph({ graph }: { graph: KGraph }) {
  const simRef = useRef<Simulation<SimNode, SimLink> | null>(null);
  const nodesRef = useRef<Map<string, SimNode>>(new Map());
  const linksRef = useRef<Map<string, SimLink>>(new Map());
  const [, setTick] = useState(0);
  const tc = useRef(0);
  const [selected, setSelected] = useState<string | null>(null);

  const svgRef = useRef<SVGSVGElement | null>(null);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const panRef = useRef<{ sx: number; sy: number; vx: number; vy: number } | null>(null);

  const metrics = useCallback(() => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return { s: 1, ox: 0, oy: 0, rect: null as DOMRect | null };
    const s = Math.min(rect.width / W, rect.height / H);
    return { s, ox: (rect.width - W * s) / 2, oy: (rect.height - H * s) / 2, rect };
  }, []);
  const zoomAt = useCallback((ux: number, uy: number, f: number) => {
    setView((v) => {
      const k = Math.max(0.2, Math.min(6, v.k * f));
      const pgx = (ux - v.x) / v.k;
      const pgy = (uy - v.y) / v.k;
      return { k, x: ux - pgx * k, y: uy - pgy * k };
    });
  }, []);
  const onWheel = useCallback(
    (e: React.WheelEvent) => {
      const { s, ox, oy, rect } = metrics();
      if (!rect) return;
      zoomAt((e.clientX - rect.left - ox) / s, (e.clientY - rect.top - oy) / s, e.deltaY < 0 ? 1.12 : 1 / 1.12);
    },
    [metrics, zoomAt],
  );
  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (e.target !== e.currentTarget) return;
      panRef.current = { sx: e.clientX, sy: e.clientY, vx: view.x, vy: view.y };
      (e.currentTarget as SVGSVGElement).setPointerCapture(e.pointerId);
    },
    [view.x, view.y],
  );
  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      const p = panRef.current;
      if (!p) return;
      const { s } = metrics();
      setView((v) => ({ ...v, x: p.vx + (e.clientX - p.sx) / s, y: p.vy + (e.clientY - p.sy) / s }));
    },
    [metrics],
  );
  const endPan = useCallback(() => {
    panRef.current = null;
  }, []);
  const fit = useCallback(() => {
    const ns = [...nodesRef.current.values()].filter((n) => n.x != null);
    if (ns.length === 0) return setView({ x: 0, y: 0, k: 1 });
    const xs = ns.map((n) => n.x as number);
    const ys = ns.map((n) => n.y as number);
    const pad = 40;
    const [minX, maxX, minY, maxY] = [
      Math.min(...xs) - pad,
      Math.max(...xs) + pad,
      Math.min(...ys) - pad,
      Math.max(...ys) + pad,
    ];
    const k = Math.max(0.2, Math.min(6, Math.min(W / (maxX - minX), H / (maxY - minY))));
    setView({ k, x: (W - (minX + maxX) * k) / 2, y: (H - (minY + maxY) * k) / 2 });
  }, []);

  useEffect(() => {
    const sim = forceSimulation<SimNode>([])
      .force("charge", forceManyBody().strength(-140))
      .force("center", forceCenter(W / 2, H / 2))
      .force("collide", forceCollide<SimNode>((d) => nodeRadius(d) + 6))
      .force("x", forceX(W / 2).strength(0.05))
      .force("y", forceY(H / 2).strength(0.05))
      .force(
        "link",
        forceLink<SimNode, SimLink>([])
          .id((d) => d.id)
          .distance(70)
          .strength(0.3),
      )
      .on("tick", () => {
        tc.current += 1;
        if (tc.current % 2 === 0) setTick((t) => t + 1);
      });
    simRef.current = sim;
    return () => {
      sim.stop();
      simRef.current = null;
    };
  }, []);

  useEffect(() => {
    const sim = simRef.current;
    if (!sim) return;
    const nodes = nodesRef.current;
    const links = linksRef.current;
    let changed = false;
    const wanted = new Set(graph.nodes.map((n) => n.id));
    for (const id of [...nodes.keys()]) {
      if (!wanted.has(id)) {
        nodes.delete(id);
        changed = true;
      }
    }
    for (const [key, l] of [...links.entries()]) {
      const s = (l.source as SimNode).id ?? (l.source as unknown as string);
      const t = (l.target as SimNode).id ?? (l.target as unknown as string);
      if (!wanted.has(s) || !wanted.has(t)) {
        links.delete(key);
        changed = true;
      }
    }
    for (const n of graph.nodes) {
      const ex = nodes.get(n.id);
      if (!ex) {
        nodes.set(n.id, {
          id: n.id,
          kind: n.kind,
          label: n.label,
          status: n.status,
          elo: n.elo,
          changedSeq: n.changedSeq,
          deg: 0,
          x: W / 2 + (Math.random() - 0.5) * 140,
          y: H / 2 + (Math.random() - 0.5) * 140,
        });
        changed = true;
      } else {
        ex.status = n.status;
        ex.elo = n.elo;
        ex.label = n.label;
        ex.changedSeq = n.changedSeq;
      }
    }
    for (const e of graph.edges) {
      const key = `${e.relation}:${e.source}->${e.target}`;
      if (links.has(key)) continue;
      const s = nodes.get(e.source);
      const t = nodes.get(e.target);
      if (s && t) {
        links.set(key, { id: key, source: s, target: t, relation: e.relation });
        s.deg += 1;
        t.deg += 1;
        changed = true;
      }
    }
    if (changed) {
      sim.nodes([...nodes.values()]);
      (sim.force("link") as ReturnType<typeof forceLink<SimNode, SimLink>>).links([...links.values()]);
      sim.alpha(0.6).restart();
      setTick((t) => t + 1);
    }
  }, [graph]);

  const nodes = [...nodesRef.current.values()];
  const links = [...linksRef.current.values()];
  const sel = selected ? graph.nodes.find((n) => n.id === selected) : null;
  const edgeColor = (r: string) =>
    r === "supports" ? "oklch(0.72 0.15 150)" : r === "contradicts" ? "oklch(0.62 0.2 25)" : "var(--border)";

  if (graph.nodes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-10 text-center text-xs text-muted-foreground">
        <div>
          <div className="mb-2 font-serif text-lg text-foreground">No world model yet</div>
          Entities, hypotheses and evidence appear here as agents reason. Links form when
          evidence supports/contradicts a hypothesis.
        </div>
      </div>
    );
  }

  return (
    <div className="relative h-full w-full overflow-hidden">
      <svg
        ref={svgRef}
        className="h-full w-full cursor-grab touch-none active:cursor-grabbing"
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="xMidYMid meet"
        onClick={() => setSelected(null)}
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endPan}
        onPointerLeave={endPan}
      >
        <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
          <g>
            {links.map((l) => {
              const s = l.source as SimNode;
              const t = l.target as SimNode;
              if (s.x == null || t.x == null) return null;
              return (
                <line
                  key={l.id}
                  x1={s.x}
                  y1={s.y}
                  x2={t.x}
                  y2={t.y}
                  stroke={edgeColor(l.relation)}
                  strokeOpacity={l.relation === "relation" ? 0.3 : 0.55}
                  strokeWidth={l.relation === "relation" ? 1 : 1.5}
                />
              );
            })}
          </g>
          <g>
            {nodes.map((n) => {
              if (n.x == null) return null;
              const r = nodeRadius(n);
              const flash = n.changedSeq != null && graph.lastSeq - n.changedSeq < 4;
              const label = n.label.length > 28 ? n.label.slice(0, 28) + "…" : n.label;
              return (
                <g
                  key={n.id}
                  transform={`translate(${n.x} ${n.y})`}
                  className="cursor-pointer"
                  onClick={(ev) => {
                    ev.stopPropagation();
                    setSelected(n.id);
                  }}
                >
                  <title>{n.label}</title>
                  {flash && (
                    <circle r={r + 6} fill="none" stroke="var(--primary)" strokeWidth={2}>
                      <animate attributeName="opacity" from="1" to="0" dur="1.2s" />
                      <animate attributeName="r" from={r + 2} to={r + 14} dur="1.2s" />
                    </circle>
                  )}
                  {n.kind === "hypothesis" ? (
                    <rect
                      x={-r}
                      y={-r}
                      width={r * 2}
                      height={r * 2}
                      rx={3}
                      fill={nodeFill(n)}
                      stroke={n.id === selected ? "var(--primary)" : "transparent"}
                      strokeWidth={1.5}
                    />
                  ) : (
                    <circle
                      r={r}
                      fill={nodeFill(n)}
                      fillOpacity={n.kind === "claim" ? 0.5 : 0.85}
                      stroke={n.id === selected ? "var(--primary)" : "transparent"}
                      strokeWidth={1.5}
                    />
                  )}
                  {(nodes.length <= 30 || n.id === selected) && (
                    <text x={r + 4} y={3.5} className="fill-muted-foreground" style={{ fontSize: 9 }}>
                      {label}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        </g>
      </svg>

      {/* HUD + zoom controls */}
      <div className="absolute left-3 top-3 rounded-lg border border-border bg-background/70 px-3 py-2 text-[10.5px] text-muted-foreground backdrop-blur">
        <div>
          <span className="text-foreground tabular-nums">{graph.counts.hypotheses}</span> hypotheses ·{" "}
          <span className="text-foreground tabular-nums">{graph.counts.entities}</span> entities ·{" "}
          <span className="text-foreground tabular-nums">{graph.counts.claims}</span> claims ·{" "}
          <span className="text-foreground tabular-nums">{graph.counts.links}</span> links
        </div>
        <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[9px]">
          <Legend swatch="oklch(0.7 0.04 260)" label="entity" />
          <Legend swatch="var(--primary)" label="hypothesis" square />
          <Legend swatch="var(--accent-cyan)" label="claim" />
          <Legend swatch="oklch(0.72 0.15 150)" label="supports" line />
          <Legend swatch="oklch(0.62 0.2 25)" label="contradicts" line />
        </div>
      </div>
      <div className="absolute right-3 top-3 flex flex-col gap-1">
        {[
          { l: "+", t: "Zoom in", fn: () => zoomAt(W / 2, H / 2, 1.3) },
          { l: "−", t: "Zoom out", fn: () => zoomAt(W / 2, H / 2, 1 / 1.3) },
          { l: "⤢", t: "Fit all", fn: fit },
        ].map((b) => (
          <button
            key={b.l}
            title={b.t}
            onClick={(e) => {
              e.stopPropagation();
              b.fn();
            }}
            className="flex h-7 w-7 items-center justify-center rounded-md border border-border bg-background/70 text-sm text-muted-foreground backdrop-blur hover:border-primary hover:text-primary"
          >
            {b.l}
          </button>
        ))}
      </div>

      {sel && (
        <aside
          className="absolute bottom-3 right-3 w-72 rounded-xl border border-border bg-card p-3.5 shadow-xl"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{sel.kind}</div>
          <div className="mt-1 text-[13px] leading-snug">{sel.label}</div>
          {sel.kind === "hypothesis" && (
            <div className="mt-1.5 text-[11px] text-muted-foreground">
              {sel.status}
              {sel.elo != null ? ` · Elo ${sel.elo.toFixed(0)}` : ""}
            </div>
          )}
          <button
            className="absolute right-2 top-2 rounded-md border border-border px-1.5 text-[11px] text-muted-foreground hover:text-foreground"
            onClick={() => setSelected(null)}
          >
            ✕
          </button>
        </aside>
      )}
    </div>
  );
}

function Legend({ swatch, label, square, line }: { swatch: string; label: string; square?: boolean; line?: boolean }) {
  return (
    <span className="flex items-center gap-1.5">
      {line ? (
        <i className="inline-block h-0.5 w-3" style={{ background: swatch }} />
      ) : (
        <i
          className={`inline-block h-2 w-2 ${square ? "rounded-sm" : "rounded-full"}`}
          style={{ background: swatch }}
        />
      )}
      {label}
    </span>
  );
}
