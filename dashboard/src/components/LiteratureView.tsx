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
import type { DashboardState, PaperNode } from "../types";

interface SimNode extends SimulationNodeDatum {
  id: string;
  read: boolean;
  via: string;
  degree: number;
  title: string;
}
type SimLink = SimulationLinkDatum<SimNode>;

const NODE_BASE = 4;
const STAGGER_MS = 100;

/**
 * Force-directed citation graph on canvas. Nodes appear on paper.read /
 * citation.followed (never on raw search hits — those only feed the scanned
 * counter). Insertions are queued and staggered with a gentle alpha reheat;
 * at high replay speed the stagger collapses to batch adds.
 */
export function LiteratureView({
  state,
  fastMode,
}: {
  state: DashboardState;
  fastMode: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const simRef = useRef<Simulation<SimNode, SimLink> | null>(null);
  const nodesRef = useRef<Map<string, SimNode>>(new Map());
  const linksRef = useRef<SimLink[]>([]);
  const linkKeysRef = useRef<Set<string>>(new Set());
  const queueRef = useRef<PaperNode[]>([]);
  const queueTimerRef = useRef<number | null>(null);
  const hoverRef = useRef<SimNode | null>(null);
  const [selected, setSelected] = useState<SimNode | null>(null);

  // Keep the simulation in sync with reducer state
  useEffect(() => {
    const nodes = nodesRef.current;
    // queue new papers (insertion order = firstSeq order)
    const incoming = [...state.papers.values()]
      .filter((p) => !nodes.has(p.id) && !queueRef.current.some((q) => q.id === p.id))
      .sort((a, b) => a.firstSeq - b.firstSeq);
    queueRef.current.push(...incoming);

    // update read flags on existing nodes
    for (const p of state.papers.values()) {
      const n = nodes.get(p.id);
      if (n) {
        n.read = p.read;
        if (p.title) n.title = p.title;
      }
    }

    const drainOne = () => {
      const sim = simRef.current;
      if (!sim) return;
      const batch = fastMode ? queueRef.current.splice(0) : queueRef.current.splice(0, 1);
      if (batch.length === 0) return;
      for (const p of batch) {
        const node: SimNode = {
          id: p.id,
          read: p.read,
          via: p.discoveredVia,
          degree: 0,
          title: p.title,
          x: (canvasRef.current?.width ?? 600) / 2 + (Math.random() - 0.5) * 80,
          y: (canvasRef.current?.height ?? 400) / 2 + (Math.random() - 0.5) * 80,
        };
        nodes.set(p.id, node);
      }
      // add any links whose endpoints now exist
      for (const e of state.citationEdges) {
        const key = `${e.source}->${e.target}`;
        if (linkKeysRef.current.has(key)) continue;
        const s = nodes.get(e.source);
        const t = nodes.get(e.target);
        if (s && t) {
          linkKeysRef.current.add(key);
          linksRef.current.push({ source: s, target: t });
          s.degree += 1;
          t.degree += 1;
        }
      }
      sim.nodes([...nodes.values()]);
      (sim.force("link") as any)?.links(linksRef.current);
      sim.alphaTarget(0.25).restart();
      window.setTimeout(() => sim.alphaTarget(0), 350);
      if (queueRef.current.length > 0) {
        queueTimerRef.current = window.setTimeout(drainOne, fastMode ? 0 : STAGGER_MS);
      }
    };

    if (queueTimerRef.current == null && queueRef.current.length > 0) {
      drainOne();
    }
    return () => {
      if (queueTimerRef.current != null) {
        clearTimeout(queueTimerRef.current);
        queueTimerRef.current = null;
      }
    };
  }, [state, fastMode]);

  // Simulation + canvas lifecycle
  useEffect(() => {
    const canvas = canvasRef.current!;
    const parent = canvas.parentElement!;
    const resize = () => {
      canvas.width = parent.clientWidth;
      canvas.height = parent.clientHeight;
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(parent);

    const sim = forceSimulation<SimNode>([...nodesRef.current.values()])
      .force("charge", forceManyBody().strength(-60))
      .force("center", forceCenter(canvas.width / 2, canvas.height / 2))
      .force("collide", forceCollide<SimNode>((d) => NODE_BASE + d.degree + 3))
      .force(
        "link",
        forceLink<SimNode, SimLink>(linksRef.current).id((d) => d.id).distance(60).strength(0.4),
      );
    simRef.current = sim;

    let raf = 0;
    const draw = () => {
      const ctx = canvas.getContext("2d")!;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      // edges
      ctx.strokeStyle = "rgba(107, 163, 248, 0.18)";
      ctx.lineWidth = 1;
      for (const l of linksRef.current) {
        const s = l.source as SimNode;
        const t = l.target as SimNode;
        if (s.x == null || t.x == null) continue;
        ctx.beginPath();
        ctx.moveTo(s.x!, s.y!);
        ctx.lineTo(t.x!, t.y!);
        ctx.stroke();
      }
      // nodes
      const showLabels = nodesRef.current.size <= 40;
      for (const n of nodesRef.current.values()) {
        if (n.x == null) continue;
        const r = NODE_BASE + Math.min(n.degree, 10);
        if (n.via === "seed") {
          ctx.beginPath();
          ctx.arc(n.x!, n.y!, r + 3, 0, Math.PI * 2);
          ctx.strokeStyle = "rgba(227, 196, 85, 0.6)";
          ctx.stroke();
        }
        ctx.beginPath();
        ctx.arc(n.x!, n.y!, r, 0, Math.PI * 2);
        ctx.fillStyle = n.read ? "#6ba3f8" : "rgba(107, 163, 248, 0.25)";
        ctx.fill();
        ctx.strokeStyle = "#39435f";
        ctx.stroke();
        const hovered = hoverRef.current === n;
        if (showLabels || hovered || n === selected) {
          ctx.fillStyle = hovered || n === selected ? "#e7eaf3" : "#9aa1b4";
          ctx.font = "10px ui-monospace, monospace";
          ctx.fillText(n.id.slice(0, 14), n.x! + r + 4, n.y! + 3);
        }
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);

    const hit = (mx: number, my: number): SimNode | null => {
      let best: SimNode | null = null;
      let bestD = 14 * 14;
      for (const n of nodesRef.current.values()) {
        if (n.x == null) continue;
        const d = (n.x! - mx) ** 2 + (n.y! - my) ** 2;
        if (d < bestD) {
          bestD = d;
          best = n;
        }
      }
      return best;
    };
    const onMove = (ev: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      hoverRef.current = hit(ev.clientX - rect.left, ev.clientY - rect.top);
      canvas.style.cursor = hoverRef.current ? "pointer" : "default";
    };
    const onClick = (ev: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      setSelected(hit(ev.clientX - rect.left, ev.clientY - rect.top));
    };
    canvas.addEventListener("mousemove", onMove);
    canvas.addEventListener("click", onClick);

    return () => {
      cancelAnimationFrame(raf);
      canvas.removeEventListener("mousemove", onMove);
      canvas.removeEventListener("click", onClick);
      ro.disconnect();
      sim.stop();
      simRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedPaper = selected ? state.papers.get(selected.id) : null;

  return (
    <div className="lit-wrap">
      <canvas ref={canvasRef} className="lit-canvas" />
      <div className="lit-counter">
        {state.stats.resultsScanned} results scanned · {state.papers.size} papers on graph ·{" "}
        {state.stats.papersRead} read
      </div>
      {state.papers.size === 0 && (
        <div className="empty-note lit-empty">
          The citation graph grows as agents read papers and follow references.
        </div>
      )}
      {selectedPaper && (
        <aside className="lit-panel">
          <div className="lit-panel-id">{selectedPaper.id}</div>
          <div className="lit-panel-title">{selectedPaper.title || "(title unknown)"}</div>
          <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
            discovered via {selectedPaper.discoveredVia}
            {selectedPaper.read
              ? ` · read (${((selectedPaper.charsRead ?? 0) / 1000).toFixed(0)}k chars)`
              : " · not read"}
          </div>
          <button className="scrub-btn lit-close" onClick={() => setSelected(null)}>
            ✕
          </button>
        </aside>
      )}
    </div>
  );
}
