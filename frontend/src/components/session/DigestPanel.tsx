import { useSessionStore } from "@/stores/sessionStore";
import { useSystemState } from "@/hooks/useSystemState";
import {
  AGENT_THEMES,
  PHASE_DISPLAY_ORDER,
  PHASE_ICONS,
  PHASE_LABELS,
  getAgentRole,
} from "@/lib/constants";
import { cn } from "@/lib/utils";
import { Check, CircleDot, Hand, Trophy } from "lucide-react";

/**
 * Mission digest — the "what is going on and when should I step in" panel.
 *
 * Everything here is derived from state the store already holds (no extra
 * backend calls, no LLM cost): the live activity feed, the knowledge snapshot,
 * experiments, and the phase roadmap with per-phase intervention hints.
 */

// How the operator can act during each phase — shown for the CURRENT phase.
const INTERVENTION_HINTS: Record<string, string> = {
  seeding: "The brief is being framed — steering sent now shapes the whole run.",
  ideation:
    "Hypotheses form here and the tournament locks them at the end — steer NOW to add constraints or angles.",
  planning:
    "The experiment plan is being drawn up — say what data or methods you want (interactive runs will ask you to approve it).",
  literature: "Papers are being gathered — suggest sources or topics to chase.",
  execution:
    "Experiments are running — messages become directives picked up between runs; Pause parks between experiments.",
  post_execution: "Results are being interpreted — challenge or redirect the reading now.",
  writing: "The paper is being drafted from the verified results.",
  internal: "The editor is reviewing — revisions may loop before submission.",
  submitted: "Submitted — peer review is next.",
  peer_review: "Peer reviewers are judging the paper.",
  revision: "The team is revising to answer the reviews.",
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-3">
      <h4 className="mb-1.5 px-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground/70">
        {title}
      </h4>
      {children}
    </div>
  );
}

export function DigestPanel() {
  const currentPhase = useSessionStore((s) => s.currentPhase);
  const completedPhases = useSessionStore((s) => s.completedPhases);
  const roundNum = useSessionStore((s) => s.roundNum);
  const maxRounds = useSessionStore((s) => s.maxRounds);
  const agentOutputs = useSessionStore((s) => s.agentOutputs);
  const activityEvents = useSessionStore((s) => s.activityEvents);
  const knowledge = useSessionStore((s) => s.knowledge);
  const experiments = useSessionStore((s) => s.experiments);
  const papersFound = useSessionStore((s) => s.papersFound);
  const draft = useSessionStore((s) => s.draft);
  const pendingApproval = useSessionStore((s) => s.pendingApproval);
  const { state } = useSystemState();

  const streamingOut = [...agentOutputs].reverse().find((o) => o.streaming);
  const speakerRole = streamingOut ? getAgentRole(streamingOut.agentId) : null;
  const speaker = speakerRole ? (AGENT_THEMES[speakerRole]?.label ?? speakerRole) : null;
  const lastEvent = activityEvents[activityEvents.length - 1];

  const topHypotheses = knowledge.hypotheses.slice(0, 3);
  const expOk = experiments.filter((e) => e.status === "success").length;
  const expBad = experiments.filter((e) =>
    ["failure", "timeout", "error"].includes(e.status)
  ).length;
  const sectionsDrafted = draft.sections.filter((s) => s.status === "drafted").length;

  const phaseIdx = currentPhase ? PHASE_DISPLAY_ORDER.indexOf(currentPhase as never) : -1;
  const hint = currentPhase ? INTERVENTION_HINTS[currentPhase] : null;

  return (
    <div className="flex flex-col p-2 text-xs">
      <h3 className="mb-2 px-1 text-xs font-semibold uppercase tracking-[0.1em] text-muted-foreground">
        Mission Digest
      </h3>

      {/* Your move? — the single most important cue. */}
      {pendingApproval ? (
        <div className="mb-3 flex items-start gap-2 rounded-lg border border-indigo-400/40 bg-indigo-500/15 p-2.5 animate-pulse">
          <Hand className="mt-0.5 h-3.5 w-3.5 shrink-0 text-indigo-300" />
          <p className="text-indigo-100">
            <span className="font-semibold">Decision waiting for you</span> — the run is
            holding until you answer (or 5 min pass).
          </p>
        </div>
      ) : state === "pausing" ? (
        <div className="mb-3 rounded-lg border border-amber-400/30 bg-amber-500/10 p-2.5 text-amber-200">
          Pausing — finishing the current agent turn…
        </div>
      ) : state === "paused" ? (
        <div className="mb-3 rounded-lg border border-border bg-muted/40 p-2.5 text-muted-foreground">
          Parked. The team resumes where it stopped.
        </div>
      ) : null}

      {/* Now */}
      <Section title="Now">
        <div className="rounded-lg bg-card/60 p-2.5">
          <p className="font-medium text-foreground">
            {currentPhase ? (
              <>
                {PHASE_ICONS[currentPhase] ?? ""} {PHASE_LABELS[currentPhase] ?? currentPhase}
                {maxRounds > 0 && roundNum > 0 && (
                  <span className="text-muted-foreground"> · round {roundNum}/{maxRounds}</span>
                )}
              </>
            ) : (
              "Starting up…"
            )}
          </p>
          {speaker && (
            <p className="mt-1 text-muted-foreground">
              <span className={AGENT_THEMES[speakerRole!]?.color}>{speaker}</span> is speaking…
            </p>
          )}
          {lastEvent && (
            <p className="mt-1 leading-snug text-muted-foreground/80" title={lastEvent.narration}>
              {lastEvent.title}
            </p>
          )}
        </div>
      </Section>

      {/* So far */}
      <Section title="So far">
        <div className="space-y-1.5">
          {topHypotheses.length > 0 && (
            <div className="rounded-lg bg-card/60 p-2.5">
              <p className="mb-1 flex items-center gap-1 text-[10px] uppercase tracking-wider text-muted-foreground/60">
                <Trophy className="h-3 w-3 text-primary/70" /> Leading hypotheses
              </p>
              {topHypotheses.map((h, i) => (
                <p key={h.id} className="mb-1 leading-snug text-muted-foreground last:mb-0">
                  <span className="text-foreground/90">{i + 1}.</span>{" "}
                  {String(h.statement).slice(0, 90)}
                  {String(h.statement).length > 90 ? "…" : ""}
                  {h.elo_rating != null && (
                    <span className="ml-1 font-mono text-[10px] text-primary/70">
                      {Math.round(h.elo_rating)}
                    </span>
                  )}
                </p>
              ))}
            </div>
          )}
          <div className="flex flex-wrap gap-x-3 gap-y-1 rounded-lg bg-card/60 p-2.5 font-mono text-[11px] text-muted-foreground">
            <span>{papersFound} papers</span>
            {(expOk > 0 || expBad > 0) && (
              <span>
                experiments <span className="text-emerald-400">{expOk}✓</span>
                {expBad > 0 && <span className="text-red-400"> {expBad}✗</span>}
              </span>
            )}
            {sectionsDrafted > 0 && <span>{sectionsDrafted} sections drafted</span>}
          </div>
        </div>
      </Section>

      {/* Ahead */}
      <Section title="Ahead">
        {hint && (
          <p className="mb-2 rounded-lg border border-primary/25 bg-primary/5 p-2.5 leading-snug text-foreground/90">
            {hint}
          </p>
        )}
        <ol className="space-y-0.5 px-1">
          {PHASE_DISPLAY_ORDER.map((p, i) => {
            const done = completedPhases.includes(p) || (phaseIdx >= 0 && i < phaseIdx);
            const current = p === currentPhase;
            return (
              <li
                key={p}
                className={cn(
                  "flex items-center gap-1.5",
                  current
                    ? "font-semibold text-foreground"
                    : done
                      ? "text-muted-foreground/50 line-through decoration-muted-foreground/30"
                      : "text-muted-foreground/60"
                )}
              >
                {done ? (
                  <Check className="h-3 w-3 text-emerald-500/70" />
                ) : current ? (
                  <CircleDot className="h-3 w-3 animate-pulse text-primary" />
                ) : (
                  <span className="inline-block h-3 w-3 text-center leading-3 text-muted-foreground/30">·</span>
                )}
                {PHASE_LABELS[p] ?? p}
              </li>
            );
          })}
        </ol>
      </Section>
    </div>
  );
}
