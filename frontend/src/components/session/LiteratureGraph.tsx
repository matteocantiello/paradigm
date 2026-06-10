import { getSessionEventStream, type ThreadEvent } from "@/api/client";
import { buildLitGraph, type LitGraph } from "@/lib/litGraph";
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
  read: boolean;
  via: string;
  degree: number;
  title: string;
  author: string;
  year: string;
}
type SimLink = SimulationLinkDatum<SimNode> & { id: string };

const W = 1000;
const H = 700;
const EMPTY: LitGraph = { nodes: [], edges: [], scanned: 0, read: 0 };

const ARXIV_RE = /^(\d{4}\.\d{4,5}|[a-z-]+\/\d{7})(v\d+)?$/i;

/** A direct PDF link for a paper, from its url or a constructed arXiv link. */
function pdfHref(node: { id: string; url: string }): string | null {
  if (node.url) return node.url.includes("/abs/") ? node.url.replace("/abs/", "/pdf/") : node.url;
  if (ARXIV_RE.test(node.id)) return `https://arxiv.org/pdf/${node.id}`;
  return null;
}

/** "First Author · Year" provenance line, omitting blanks. */
function provenance(node: { author: string; year: string }): string {
  if (node.author && node.year) return `${node.author} · ${node.year}`;
  return node.author || node.year || "";
}

/**
 * Presentational literature constellation: papers are stars (read = gold w/ halo,
 * unread = cyan), citations are light-lines. Pure function of the `graph` it's
 * given — used both live (polled) and in replay (rebuilt at the scrub cursor).
 * Handles node ADDITION (forward) and REMOVAL (backward scrub) against the sim.
 */
export function LiteratureConstellation({
  graph,
  showEmpty = true,
}: {
  graph: LitGraph;
  showEmpty?: boolean;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const simRef = useRef<Simulation<SimNode, SimLink> | null>(null);
  const nodesRef = useRef<Map<string, SimNode>>(new Map());
  const linksRef = useRef<Map<string, SimLink>>(new Map());
  const [, setTick] = useState(0);
  const tc = useRef(0);

  // Pan/zoom: an affine transform {x, y, k} on the inner <g>. Hand-rolled (no
  // extra dep), mapping client pixels → viewBox units via the rendered scale.
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const panRef = useRef<{ sx: number; sy: number; vx: number; vy: number } | null>(null);

  // pixels-per-viewBox-unit + letterbox offset under preserveAspectRatio=meet
  const metrics = useCallback(() => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return { s: 1, ox: 0, oy: 0, rect: null as DOMRect | null };
    const s = Math.min(rect.width / W, rect.height / H);
    return { s, ox: (rect.width - W * s) / 2, oy: (rect.height - H * s) / 2, rect };
  }, []);

  const zoomAt = useCallback((ux: number, uy: number, factor: number) => {
    setView((v) => {
      const k = Math.max(0.2, Math.min(6, v.k * factor));
      // keep the point (ux,uy) in viewBox space fixed under the transform
      const pgx = (ux - v.x) / v.k;
      const pgy = (uy - v.y) / v.k;
      return { k, x: ux - pgx * k, y: uy - pgy * k };
    });
  }, []);

  const onWheel = useCallback(
    (e: React.WheelEvent) => {
      const { s, ox, oy, rect } = metrics();
      if (!rect) return;
      const ux = (e.clientX - rect.left - ox) / s;
      const uy = (e.clientY - rect.top - oy) / s;
      zoomAt(ux, uy, e.deltaY < 0 ? 1.12 : 1 / 1.12);
    },
    [metrics, zoomAt],
  );

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      // Only pan when grabbing empty space — let clicks on a star select it.
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

  /** Frame all current nodes (or reset when empty). */
  const fit = useCallback(() => {
    const ns = [...nodesRef.current.values()].filter((n) => n.x != null);
    if (ns.length === 0) {
      setView({ x: 0, y: 0, k: 1 });
      return;
    }
    const xs = ns.map((n) => n.x as number);
    const ys = ns.map((n) => n.y as number);
    const pad = 40;
    const minX = Math.min(...xs) - pad;
    const maxX = Math.max(...xs) + pad;
    const minY = Math.min(...ys) - pad;
    const maxY = Math.max(...ys) + pad;
    const k = Math.max(0.2, Math.min(6, Math.min(W / (maxX - minX), H / (maxY - minY))));
    setView({
      k,
      x: (W - (minX + maxX) * k) / 2,
      y: (H - (minY + maxY) * k) / 2,
    });
  }, []);

  useEffect(() => {
    const sim = forceSimulation<SimNode>([])
      .force("charge", forceManyBody().strength(-120))
      .force("center", forceCenter(W / 2, H / 2))
      .force("collide", forceCollide<SimNode>((d) => 8 + d.degree * 1.4))
      // Gently corral disconnected clusters toward center so they don't drift
      // off-frame (pan/zoom can still reach anything that does).
      .force("x", forceX(W / 2).strength(0.05))
      .force("y", forceY(H / 2).strength(0.05))
      .force(
        "link",
        forceLink<SimNode, SimLink>([])
          .id((d) => d.id)
          .distance(78)
          .strength(0.35),
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
    const wanted = new Set(graph.nodes.map((p) => p.id));

    // Remove nodes/links no longer present (backward scrub).
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

    for (const p of graph.nodes) {
      const existing = nodes.get(p.id);
      if (!existing) {
        nodes.set(p.id, {
          id: p.id,
          read: p.read,
          via: p.via,
          degree: 0,
          title: p.title,
          author: p.author,
          year: p.year,
          x: W / 2 + (Math.random() - 0.5) * 120,
          y: H / 2 + (Math.random() - 0.5) * 120,
        });
        changed = true;
      } else {
        existing.read = p.read;
        if (p.title) existing.title = p.title;
        if (p.author) existing.author = p.author;
        if (p.year) existing.year = p.year;
      }
    }
    for (const e of graph.edges) {
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
    if (changed) {
      sim.nodes([...nodes.values()]);
      (sim.force("link") as ReturnType<typeof forceLink<SimNode, SimLink>>).links([
        ...links.values(),
      ]);
      sim.alpha(0.6).restart();
      setTick((t) => t + 1);
    }
  }, [graph]);

  const nodes = [...nodesRef.current.values()];
  const links = [...linksRef.current.values()];
  const sel = selected ? graph.nodes.find((n) => n.id === selected) : null;

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
        <defs>
          <radialGradient id="lg-read" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="oklch(0.95 0.08 90)" />
            <stop offset="100%" stopColor="var(--primary)" />
          </radialGradient>
          <filter id="lg-glow" x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur stdDeviation="3.2" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
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
                stroke="var(--accent-cyan)"
                strokeOpacity={0.22}
                strokeWidth={1}
              />
            );
          })}
        </g>
        <g>
          {nodes.map((n) => {
            if (n.x == null) return null;
            const r = 5 + Math.min(n.degree, 8) * 1.3;
            const showLabel = nodes.length <= 32 || n.id === selected;
            return (
              <g
                key={n.id}
                transform={`translate(${n.x} ${n.y})`}
                className="cursor-pointer"
                filter={n.read ? "url(#lg-glow)" : undefined}
                onClick={(ev) => {
                  ev.stopPropagation();
                  setSelected(n.id);
                }}
              >
                <title>{[n.title || n.id, provenance(n)].filter(Boolean).join("\n")}</title>
                {n.via === "seed" && (
                  <circle r={r + 5} fill="none" stroke="var(--primary)" strokeOpacity={0.5} />
                )}
                <circle
                  r={r}
                  fill={n.read ? "url(#lg-read)" : "var(--accent-cyan)"}
                  fillOpacity={n.read ? 1 : 0.45}
                  stroke={n.id === selected ? "var(--primary)" : "transparent"}
                  strokeWidth={1.5}
                />
                {showLabel && (
                  <text x={r + 5} y={3.5} className="fill-muted-foreground" style={{ fontSize: 9.5 }}>
                    {n.id.length > 16 ? n.id.slice(0, 16) + "…" : n.id}
                  </text>
                )}
              </g>
            );
          })}
        </g>
        </g>
      </svg>

      {/* zoom / fit controls */}
      <div className="absolute right-3 top-3 flex flex-col gap-1">
        {[
          { label: "+", title: "Zoom in", fn: () => zoomAt(W / 2, H / 2, 1.3) },
          { label: "−", title: "Zoom out", fn: () => zoomAt(W / 2, H / 2, 1 / 1.3) },
          { label: "⤢", title: "Fit all to view", fn: fit },
        ].map((b) => (
          <button
            key={b.label}
            title={b.title}
            onClick={(e) => {
              e.stopPropagation();
              b.fn();
            }}
            className="flex h-7 w-7 items-center justify-center rounded-md border border-border bg-background/70 text-sm text-muted-foreground backdrop-blur transition-colors hover:border-primary hover:text-primary"
          >
            {b.label}
          </button>
        ))}
      </div>

      <div className="absolute left-3 top-3 rounded-lg border border-border bg-background/70 px-3 py-2 text-[10.5px] text-muted-foreground backdrop-blur">
        <div>
          <span className="text-primary tabular-nums">{graph.scanned}</span> scanned ·{" "}
          <span className="text-primary tabular-nums">{nodes.length}</span> on graph ·{" "}
          <span className="text-primary tabular-nums">{graph.read}</span> read
        </div>
        <div className="mt-1.5 flex gap-3 text-[9.5px]">
          <span className="flex items-center gap-1.5">
            <i className="inline-block h-2 w-2 rounded-full bg-primary" />
            read
          </span>
          <span className="flex items-center gap-1.5">
            <i
              className="inline-block h-2 w-2 rounded-full"
              style={{ background: "var(--accent-cyan)", opacity: 0.5 }}
            />
            discovered
          </span>
        </div>
      </div>

      {showEmpty && nodes.length === 0 && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="max-w-xs text-center text-xs leading-relaxed text-muted-foreground">
            <div className="mb-2 font-serif text-lg text-foreground">An empty sky</div>
            Stars appear as agents read papers and follow citations. Runs with little
            literature search stay sparse.
          </div>
        </div>
      )}

      {sel && (
        <aside
          className="absolute bottom-3 right-3 w-72 rounded-xl border border-border bg-card p-3.5 shadow-xl"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="text-[11px] text-accent-cyan">{sel.id}</div>
          <div className="mt-1 text-[13px] leading-snug">{sel.title || "(title unknown)"}</div>
          {provenance(sel) && (
            <div className="mt-1 text-[12px] text-foreground/90">{provenance(sel)}</div>
          )}
          <div className="mt-1.5 flex items-center gap-2 text-[11px] text-muted-foreground">
            <span>
              via {sel.via}
              {sel.read ? " · read" : " · not read"}
            </span>
            {pdfHref(sel) && (
              <a
                href={pdfHref(sel)!}
                target="_blank"
                rel="noopener noreferrer"
                className="ml-auto rounded-md border border-primary/40 bg-primary/10 px-2 py-0.5 text-primary hover:bg-primary/20"
              >
                PDF ↗
              </a>
            )}
          </div>
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

/**
 * Live literature constellation for the session view: polls the durable event
 * stream until the run completes, then renders the constellation.
 */
export function LiteratureGraph({ sessionId }: { sessionId: string }) {
  const [graph, setGraph] = useState<LitGraph>(EMPTY);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const { events } = await getSessionEventStream(sessionId);
        if (!alive) return;
        setGraph(buildLitGraph(events));
        setLoaded(true);
        const done = events.some((e: ThreadEvent) => e.type === "run.completed");
        if (!done) timer = window.setTimeout(tick, 4000);
      } catch {
        if (alive) timer = window.setTimeout(tick, 6000);
      }
    };
    void tick();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [sessionId]);

  return <LiteratureConstellation graph={graph} showEmpty={loaded} />;
}
