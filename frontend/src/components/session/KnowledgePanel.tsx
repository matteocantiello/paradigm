import { useState, type ReactNode } from "react";
import type { KnowledgeState } from "@/stores/sessionStore";
import {
  HYPOTHESIS_STATUS_COLORS,
  ENTITY_TYPE_COLORS,
  CONFLICT_TYPE_COLORS,
} from "@/lib/constants";
import { cn } from "@/lib/utils";
import { TournamentBoard } from "./TournamentBoard";
import { KnowledgeGraph } from "./KnowledgeGraph";
import { knowledgeGraphFromState } from "@/lib/knowledgeGraph";

interface KnowledgePanelProps {
  knowledge: KnowledgeState;
}

function CollapsibleSection({
  title,
  count,
  defaultOpen = false,
  children,
}: {
  title: string;
  count: number;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  if (count === 0) return null;
  return (
    <div className="mb-2">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 w-full text-left text-xs font-medium text-muted-foreground uppercase tracking-wider hover:text-foreground transition-colors px-1 py-0.5"
      >
        <span className="text-[10px]">{open ? "▼" : "▶"}</span>
        {title}
        <span className="ml-auto text-[10px] font-normal tabular-nums bg-muted/50 px-1.5 py-0.5 rounded">
          {count}
        </span>
      </button>
      {open && <div className="mt-1 space-y-1 pl-1">{children}</div>}
    </div>
  );
}

function EloBar({ rating, max = 2000, min = 1000 }: { rating: number; max?: number; min?: number }) {
  const pct = Math.max(0, Math.min(100, ((rating - min) / (max - min)) * 100));
  return (
    <div className="flex items-center gap-1.5">
      <div className="h-1.5 w-16 rounded-full bg-muted/50 overflow-hidden">
        <div
          className="h-full rounded-full bg-indigo-500 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[10px] tabular-nums text-muted-foreground">{Math.round(rating)}</span>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const color = HYPOTHESIS_STATUS_COLORS[status] ?? "text-muted-foreground";
  return (
    <span className={cn("text-[10px] font-medium", color)}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

export function KnowledgePanel({ knowledge }: KnowledgePanelProps) {
  const [view, setView] = useState<"list" | "graph">("list");

  if (!knowledge.lastUpdated) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground/50 text-sm font-sans">
        <p>No knowledge data yet</p>
        <p className="text-xs mt-1">Knowledge updates appear as the research progresses</p>
      </div>
    );
  }

  const toggle = (
    <div className="flex shrink-0 justify-end gap-1 border-b border-border/50 px-2 py-1">
      {(["list", "graph"] as const).map((v) => (
        <button
          key={v}
          onClick={() => setView(v)}
          className={cn(
            "rounded px-2 py-0.5 text-[10px] uppercase tracking-wide transition-colors",
            view === v ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {v}
        </button>
      ))}
    </div>
  );

  if (view === "graph") {
    return (
      <div className="flex h-full flex-col">
        {toggle}
        <div className="relative flex-1 overflow-hidden">
          <KnowledgeGraph graph={knowledgeGraphFromState(knowledge)} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {toggle}
      <div className="flex flex-1 flex-col gap-0.5 overflow-y-auto p-2 font-mono">
      {/* Research Goals */}
      <CollapsibleSection
        title="Research Goals"
        count={knowledge.researchGoals.length}
        defaultOpen
      >
        {knowledge.researchGoals.map((g) => (
          <div key={g.id} className="text-[11px] leading-tight px-1 py-0.5">
            <span className={cn(
              "inline-block px-1 py-0 rounded text-[9px] font-medium mr-1.5",
              g.status === "achieved"
                ? "bg-emerald-500/20 text-emerald-300"
                : "bg-blue-500/20 text-blue-300"
            )}>
              {g.status}
            </span>
            {g.description}
          </div>
        ))}
      </CollapsibleSection>

      {/* Tournament — Elo standings, rank movement, W–L, matchup feed */}
      <div className="mb-2">
        <TournamentBoard knowledge={knowledge} />
      </div>

      {/* Hypotheses (detailed cards; collapsed by default while the tournament ranks them) */}
      <CollapsibleSection
        title="Hypotheses"
        count={knowledge.hypotheses.length}
        defaultOpen={knowledge.tournamentRankings.length === 0}
      >
        {knowledge.hypotheses.map((h, i) => (
          <div key={h.id} className="text-[11px] leading-tight px-1 py-1 border-l-2 border-indigo-500/30 pl-2 mb-1">
            <div className="flex items-center gap-1.5 mb-0.5">
              <span className="text-[10px] font-bold text-indigo-400">#{i + 1}</span>
              <StatusBadge status={h.status} />
              {h.elo_rating != null && <EloBar rating={h.elo_rating} />}
            </div>
            <div className="text-foreground/90">{h.statement}</div>
            {(h.supporting_evidence?.length || h.contradicting_evidence?.length) ? (
              <div className="flex gap-2 mt-0.5 text-[10px] text-muted-foreground">
                {h.supporting_evidence?.length ? (
                  <span className="text-emerald-400">+{h.supporting_evidence.length} supporting</span>
                ) : null}
                {h.contradicting_evidence?.length ? (
                  <span className="text-red-400">-{h.contradicting_evidence.length} contradicting</span>
                ) : null}
              </div>
            ) : null}
          </div>
        ))}
      </CollapsibleSection>

      {/* Conflicts */}
      <CollapsibleSection
        title="Conflicts"
        count={knowledge.conflicts.length}
        defaultOpen={knowledge.conflicts.some((c) => c.conflict_type === "unresolved")}
      >
        {knowledge.conflicts.map((c) => (
          <div
            key={c.id}
            className={cn(
              "text-[11px] leading-tight px-1 py-0.5 border-l-2 pl-2",
              CONFLICT_TYPE_COLORS[c.conflict_type] ?? "text-muted-foreground border-border"
            )}
          >
            <span className="text-[9px] font-medium uppercase">{c.conflict_type}</span>
            <span className="mx-1">—</span>
            {c.description}
          </div>
        ))}
      </CollapsibleSection>

      {/* Entities */}
      <CollapsibleSection title="Entities" count={knowledge.entities.length}>
        {knowledge.entities.map((e) => (
          <div key={e.id} className="text-[11px] leading-tight px-1 py-0.5">
            <span className={cn(
              "inline-block px-1 py-0 rounded text-[9px] font-medium mr-1.5",
              ENTITY_TYPE_COLORS[e.entity_type] ?? "bg-muted/50 text-muted-foreground"
            )}>
              {e.entity_type}
            </span>
            <span className="font-medium text-foreground/90">{e.name}</span>
            {e.description && (
              <span className="text-muted-foreground"> — {e.description.slice(0, 80)}</span>
            )}
          </div>
        ))}
      </CollapsibleSection>

      {/* Evidence */}
      <CollapsibleSection title="Evidence" count={knowledge.evidence.length}>
        {knowledge.evidence.map((ev) => (
          <div key={ev.id} className="text-[11px] leading-tight px-1 py-0.5">
            <span className="inline-block px-1 py-0 rounded text-[9px] font-medium mr-1.5 bg-muted/50 text-muted-foreground">
              {ev.source}
            </span>
            <span className="text-foreground/90">{ev.content.slice(0, 120)}{ev.content.length > 120 ? "..." : ""}</span>
          </div>
        ))}
      </CollapsibleSection>

      {/* Open Questions */}
      <CollapsibleSection title="Open Questions" count={knowledge.openQuestions.length}>
        {knowledge.openQuestions.map((q) => (
          <div key={q.id} className="text-[11px] leading-tight px-1 py-0.5">
            {q.priority && (
              <span className={cn(
                "inline-block px-1 py-0 rounded text-[9px] font-medium mr-1.5",
                q.priority === "high" ? "bg-red-500/20 text-red-300" :
                q.priority === "medium" ? "bg-yellow-500/20 text-yellow-300" :
                "bg-muted/50 text-muted-foreground"
              )}>
                {q.priority}
              </span>
            )}
            {q.question}
          </div>
        ))}
      </CollapsibleSection>

      {/* Assumptions */}
      <CollapsibleSection title="Assumptions" count={knowledge.assumptions.length}>
        {knowledge.assumptions.map((a) => (
          <div key={a.id} className={cn(
            "text-[11px] leading-tight px-1 py-0.5",
            a.status === "invalidated" ? "line-through text-muted-foreground/50" : ""
          )}>
            <span className={cn(
              "inline-block px-1 py-0 rounded text-[9px] font-medium mr-1.5",
              a.status === "validated" ? "bg-emerald-500/20 text-emerald-300" :
              a.status === "invalidated" ? "bg-red-500/20 text-red-300" :
              "bg-muted/50 text-muted-foreground"
            )}>
              {a.status}
            </span>
            {a.statement}
          </div>
        ))}
      </CollapsibleSection>
      </div>
    </div>
  );
}
