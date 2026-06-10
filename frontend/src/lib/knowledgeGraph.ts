import type { ThreadEvent } from "@/api/client";

/** Minimal structural shape shared by the live store + ws-types KnowledgeState. */
export interface KnowledgeSnapshot {
  entities?: { id: string; name: string }[];
  hypotheses?: {
    id: string;
    statement: string;
    status?: string;
    elo_rating?: number;
    supporting_evidence?: string[];
    contradicting_evidence?: string[];
  }[];
  evidence?: { id: string; content: string }[];
  relationships?: Record<string, unknown>[];
}

export type KNodeKind = "entity" | "hypothesis" | "claim";

export interface KNode {
  id: string;
  kind: KNodeKind;
  label: string;
  status?: string; // hypothesis status
  elo?: number;
  changedSeq?: number; // last status change (for flash, replay)
}

export interface KEdge {
  source: string;
  target: string;
  relation: "supports" | "contradicts" | "relation";
  label?: string;
}

export interface KGraph {
  nodes: KNode[];
  edges: KEdge[];
  lastSeq: number;
  counts: { entities: number; hypotheses: number; claims: number; links: number };
}

function pack(nodes: Map<string, KNode>, edges: KEdge[], lastSeq: number): KGraph {
  const present = new Set(nodes.keys());
  const valid = edges.filter((e) => present.has(e.source) && present.has(e.target));
  const list = [...nodes.values()];
  return {
    nodes: list,
    edges: valid,
    lastSeq,
    counts: {
      entities: list.filter((n) => n.kind === "entity").length,
      hypotheses: list.filter((n) => n.kind === "hypothesis").length,
      claims: list.filter((n) => n.kind === "claim").length,
      links: valid.length,
    },
  };
}

/** Build the knowledge graph from the live world-model snapshot. */
export function knowledgeGraphFromState(k: KnowledgeSnapshot): KGraph {
  const nodes = new Map<string, KNode>();
  const edges: KEdge[] = [];
  for (const e of k.entities ?? []) {
    nodes.set(e.id, { id: e.id, kind: "entity", label: e.name });
  }
  for (const h of k.hypotheses ?? []) {
    nodes.set(h.id, {
      id: h.id,
      kind: "hypothesis",
      label: h.statement,
      status: h.status,
      elo: h.elo_rating,
    });
  }
  for (const c of k.evidence ?? []) {
    nodes.set(c.id, { id: c.id, kind: "claim", label: c.content });
  }
  for (const r of (k.relationships ?? []) as { source_id?: string; target_id?: string; relationship_type?: string }[]) {
    if (r.source_id && r.target_id) {
      edges.push({ source: r.source_id, target: r.target_id, relation: "relation", label: r.relationship_type });
    }
  }
  for (const h of k.hypotheses ?? []) {
    for (const evId of h.supporting_evidence ?? []) {
      edges.push({ source: evId, target: h.id, relation: "supports" });
    }
    for (const evId of h.contradicting_evidence ?? []) {
      edges.push({ source: evId, target: h.id, relation: "contradicts" });
    }
  }
  return pack(nodes, edges, 0);
}

/** Build the knowledge graph from the durable event stream (replay, ≤ cursor). */
export function buildKnowledgeGraph(events: ThreadEvent[]): KGraph {
  const nodes = new Map<string, KNode>();
  const edges: KEdge[] = [];
  const edgeKeys = new Set<string>();
  let lastSeq = 0;

  for (const e of events) {
    const p = e.payload as Record<string, any>;
    lastSeq = e.seq;
    switch (e.type) {
      case "entity.added":
        if (p.entity_id && !nodes.has(p.entity_id)) {
          nodes.set(p.entity_id, { id: p.entity_id, kind: "entity", label: p.name ?? p.entity_id });
        }
        break;
      case "hypothesis.created":
        if (p.hypothesis_id && !nodes.has(p.hypothesis_id)) {
          nodes.set(p.hypothesis_id, {
            id: p.hypothesis_id,
            kind: "hypothesis",
            label: p.statement ?? p.hypothesis_id,
            status: "proposed",
          });
        }
        break;
      case "hypothesis.updated": {
        const n = nodes.get(p.hypothesis_id);
        if (n) {
          if (p.status) {
            n.status = p.status;
            n.changedSeq = e.seq;
          }
          if (typeof p.elo === "number") n.elo = p.elo;
        }
        break;
      }
      case "claim.extracted":
        if (p.claim_id && !nodes.has(p.claim_id)) {
          nodes.set(p.claim_id, { id: p.claim_id, kind: "claim", label: p.statement ?? p.claim_id });
        }
        break;
      case "relationship.added": {
        const key = `r:${p.source_id}->${p.target_id}`;
        if (p.source_id && p.target_id && !edgeKeys.has(key)) {
          edgeKeys.add(key);
          edges.push({ source: p.source_id, target: p.target_id, relation: "relation", label: p.relation });
        }
        break;
      }
      case "evidence.linked": {
        const key = `e:${p.claim_id}->${p.hypothesis_id}`;
        if (p.claim_id && p.hypothesis_id && !edgeKeys.has(key)) {
          edgeKeys.add(key);
          edges.push({
            source: p.claim_id,
            target: p.hypothesis_id,
            relation: p.relation === "contradicts" ? "contradicts" : "supports",
          });
        }
        break;
      }
    }
  }
  return pack(nodes, edges, lastSeq);
}
