import type { ThreadEvent } from "@/api/client";

/** A paper node in the literature constellation. */
export interface LitNode {
  id: string;
  title: string;
  author: string;
  year: string;
  url: string;
  read: boolean;
  via: "read" | "citation" | "seed" | "search";
  firstSeq: number;
}

interface PaperMeta {
  title?: string;
  author?: string;
  year?: string;
  url?: string;
}

export interface LitEdge {
  source: string;
  target: string;
  direction: string;
}

export interface LitGraph {
  nodes: LitNode[];
  edges: LitEdge[];
  scanned: number;
  read: number;
}

/**
 * Project the durable event stream into the literature graph. Nodes appear on
 * paper.read / citation.followed / seed resource ingestion — NOT on raw search
 * hits, which only bump the "scanned" counter. Pure function of the events.
 */
export function buildLitGraph(events: ThreadEvent[]): LitGraph {
  const nodes = new Map<string, LitNode>();
  const edgeKeys = new Set<string>();
  const edges: LitEdge[] = [];
  let scanned = 0;
  let read = 0;

  const note = (id: string, via: LitNode["via"], seq: number, meta?: PaperMeta) => {
    if (!id) return;
    const existing = nodes.get(id);
    if (existing) {
      // Fill any metadata we didn't have yet (e.g. a paper first seen as a bare
      // citation id, later enriched by a search/follow that carries its card).
      if (meta?.title && !existing.title) existing.title = meta.title;
      if (meta?.author && !existing.author) existing.author = meta.author;
      if (meta?.year && !existing.year) existing.year = meta.year;
      if (meta?.url && !existing.url) existing.url = meta.url;
      return;
    }
    nodes.set(id, {
      id,
      title: meta?.title ?? "",
      author: meta?.author ?? "",
      year: meta?.year ?? "",
      url: meta?.url ?? "",
      read: false,
      via,
      firstSeq: seq,
    });
  };

  for (const e of events) {
    const p = e.payload as Record<string, any>;
    switch (e.type) {
      case "search.performed":
        scanned += (p.n_results as number) ?? 0;
        // Papers surfaced by a search become "discovered" stars (the system is
        // aware of them) even if no agent explicitly [READ] them.
        for (const paper of (p.papers as (PaperMeta & { id: string })[]) ?? []) {
          note(paper.id, "search", e.seq, paper);
        }
        break;
      case "paper.read": {
        const id = (p.paper_id as string) ?? "";
        note(id, "read", e.seq, { title: p.title as string });
        const n = nodes.get(id);
        if (n) {
          n.read = true;
          if (p.title) n.title = p.title as string;
        }
        read += 1;
        break;
      }
      case "citation.followed": {
        const src = (p.source_paper_id as string) ?? "";
        note(src, "citation", e.seq);
        // Metadata cards for the cited papers (when carried).
        for (const paper of (p.papers as (PaperMeta & { id: string })[]) ?? []) {
          note(paper.id, "citation", e.seq, paper);
        }
        for (const target of (p.paper_ids as string[]) ?? []) {
          note(target, "citation", e.seq);
          const key = `${src}->${target}`;
          if (!edgeKeys.has(key)) {
            edgeKeys.add(key);
            edges.push({ source: src, target, direction: (p.direction as string) ?? "refs" });
          }
        }
        break;
      }
      case "resource.ingested":
        if (p.kind === "paper") {
          note((p.url as string) ?? "", "seed", e.seq, {
            title: p.title as string,
            url: p.url as string,
          });
        }
        break;
    }
  }

  return {
    nodes: [...nodes.values()].sort((a, b) => a.firstSeq - b.firstSeq),
    edges: edges.filter((e) => nodes.has(e.source) && nodes.has(e.target)),
    scanned,
    read,
  };
}
