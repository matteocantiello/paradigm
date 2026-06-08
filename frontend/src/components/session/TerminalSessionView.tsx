import { Telescope } from "lucide-react";
import { TopicBadges } from "@/components/shared/TopicBadges";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { TerminalScreen } from "./TerminalScreen";
import type { ResearchCycleResponse } from "@/api/client";

// TerminalScreen styles completed/failed/aborted distinctly; any other terminal
// status (published, revision_exhausted, …) is coerced to "completed" for display.
const DISPLAY_STATUSES = new Set(["completed", "failed", "aborted"]);

// A readable one-line title from a (possibly long, multi-line) seed prompt — the
// first line, capped — so the header isn't a wall of text. The full prompt is
// shown formatted below.
function promptTitle(prompt: string): string {
  const base = (prompt.split("\n").find((l) => l.trim()) ?? prompt).trim();
  return base.length > 160 ? `${base.slice(0, 157).trimEnd()}…` : base;
}

/**
 * Standalone end-of-run summary for a FINISHED cycle opened from the research tab
 * or a refreshed /session/:id. There's no live WebSocket to attach to, so instead
 * of the empty live panels we render the outcome (TerminalScreen) from the
 * persisted cycle record — the reason it ended, the full (formatted) prompt, and
 * the View paper / Retry / Resume / Back actions.
 */
export function TerminalSessionView({ cycle }: { cycle: ResearchCycleResponse }) {
  const displayStatus = DISPLAY_STATUSES.has(cycle.status) ? cycle.status : "completed";
  return (
    <div className="flex h-full flex-col">
      {/* Header: outcome status + mode + date, mirroring the live session header. */}
      <div className="flex items-center justify-between gap-3 border-b border-border px-3 py-1.5">
        <div className="flex items-center gap-2">
          <StatusBadge status={cycle.status} />
          <span className="text-xs text-muted-foreground/70">finished session</span>
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground capitalize">
          <span className="font-medium">{cycle.mode}</span>
          <span className="font-mono normal-case text-muted-foreground/60">
            {new Date(cycle.created_at).toLocaleDateString()}
          </span>
        </div>
      </div>

      {/* Centered summary. Outcome (with the reason) first, then the prompt. */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-4 py-10">
          <div className="mb-3 flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-primary/70">
            <Telescope className="h-3.5 w-3.5" />
            Research cycle
          </div>
          <h1 className="text-balance text-lg font-semibold leading-snug text-foreground">
            {promptTitle(cycle.seed_prompt)}
          </h1>
          <TopicBadges topics={cycle.topics} size="sm" className="mt-3" />

          {/* Outcome + reason + actions — up top so a failed run isn't a dead end. */}
          <div className="mt-5">
            <TerminalScreen
              status={displayStatus}
              cycleId={cycle.cycle_id}
              paperId={cycle.paper_id ?? undefined}
              currentPhase={cycle.current_phase ?? null}
              roundNum={0}
              totalTokens={cycle.total_tokens ?? 0}
              papersFound={0}
              elapsedSeconds={cycle.elapsed_seconds ?? 0}
              statusDetail={cycle.status_detail ?? undefined}
              seedPrompt={cycle.seed_prompt}
            />
          </div>

          {/* The full prompt, formatted and contained (not a wall). */}
          <div className="mt-6">
            <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground/70">
              Prompt
            </div>
            <pre className="max-h-72 overflow-y-auto whitespace-pre-wrap break-words rounded-lg border border-border/70 bg-card/40 p-3.5 font-sans text-[13px] leading-relaxed text-foreground/90">
              {cycle.seed_prompt}
            </pre>
          </div>

          <p className="mt-4 text-center text-[11px] text-muted-foreground/50">
            This run has ended — its live view is no longer available, but the outcome
            above and any paper it produced are saved.
          </p>
        </div>
      </div>
    </div>
  );
}
