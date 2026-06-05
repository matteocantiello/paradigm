import { useEffect, useRef, useState } from "react";
import { User } from "lucide-react";
import { AGENT_THEMES, getAgentRole, PHASE_LABELS } from "@/lib/constants";
import { useSystemState } from "@/hooks/useSystemState";
import { cn } from "@/lib/utils";

interface NowPlayingProps {
  currentPhase: string | null;
  activeAgents: Record<string, string>;
  roundNum: number;
  maxRounds: number;
  avgStepMs: number;
}

function fmtDuration(secs: number): string {
  if (secs < 60) return `${secs}s`;
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}m ${s}s`;
}

export function NowPlaying({
  currentPhase,
  activeAgents,
  roundNum,
  maxRounds,
  avgStepMs,
}: NowPlayingProps) {
  // Live "elapsed in phase" ticker. The parent remounts this component per
  // phase (key={currentPhase}), so mount-time is the phase start — no reset
  // effect needed.
  const { tone } = useSystemState();
  const liveDot = tone === "live"; // only ping when work is actually flowing
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef<number>(0);
  useEffect(() => {
    startRef.current = Date.now();
    const id = window.setInterval(
      () => setElapsed(Math.floor((Date.now() - startRef.current) / 1000)),
      1000
    );
    return () => window.clearInterval(id);
  }, []);

  if (!currentPhase) return null;

  const phaseLabel = PHASE_LABELS[currentPhase] ?? currentPhase.replace(/_/g, " ");
  const agentIds = Object.keys(activeAgents);
  const agentRoles = [...new Set(agentIds.map((id) => getAgentRole(id)))];
  const agentLabel =
    agentRoles.length === 0
      ? "—"
      : agentRoles.map((r) => AGENT_THEMES[r]?.label ?? r).join(", ");

  // Rough ETA: remaining rounds × active agents × avg turn duration.
  const remainingRounds = Math.max(0, maxRounds - roundNum);
  const etaSecs =
    avgStepMs > 0 && remainingRounds > 0
      ? Math.round((remainingRounds * Math.max(1, agentIds.length) * avgStepMs) / 1000)
      : 0;

  return (
    <div className="flex items-center gap-2 px-3 py-1 text-[11px] border-b border-border bg-background/60">
      <span className="relative flex h-2 w-2 shrink-0">
        {liveDot && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary/60" />
        )}
        <span
          className={cn(
            "relative inline-flex h-2 w-2 rounded-full",
            liveDot ? "bg-primary" : "bg-muted-foreground/40"
          )}
        />
      </span>
      <span className="font-semibold text-foreground">{phaseLabel}</span>
      <span className="text-muted-foreground/50">·</span>
      <span
        className={cn(
          "flex items-center gap-1 truncate",
          agentRoles.length ? "text-foreground/80" : "text-muted-foreground/50"
        )}
      >
        {agentRoles.map((r) => {
          const Ic = AGENT_THEMES[r]?.icon ?? User;
          return (
            <Ic
              key={r}
              className={cn("h-3 w-3 shrink-0", AGENT_THEMES[r]?.color ?? "text-muted-foreground")}
            />
          );
        })}
        <span className="truncate">{agentLabel}</span>
      </span>
      <span className="ml-auto flex items-center gap-3 tabular-nums text-muted-foreground/70 shrink-0">
        <span>{fmtDuration(elapsed)} in phase</span>
        {etaSecs > 0 && <span>≈ {fmtDuration(etaSecs)} left</span>}
      </span>
    </div>
  );
}
