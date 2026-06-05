import { useEffect, useMemo, useRef } from "react";
import type { ActivityEvent, Notification } from "@/stores/sessionStore";
import { PHASE_LABELS } from "@/lib/constants";
import { cn } from "@/lib/utils";

interface EventLogProps {
  activityEvents: ActivityEvent[];
  notifications: Notification[];
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString("en-US", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "";
  }
}

function formatDuration(ms: number | null): string {
  if (ms == null) return "";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

const CATEGORY_COLOR: Record<string, string> = {
  phase_transition: "bg-blue-400",
  round_start: "bg-blue-300",
  convergence_detected: "bg-emerald-400",
  debate_start: "bg-amber-400",
  debate_complete: "bg-amber-400",
  experiment_running: "bg-emerald-400",
  experiment_result: "bg-emerald-400",
  peer_review_decision: "bg-purple-400",
  paper_saved: "bg-cyan-400",
  paper_published: "bg-cyan-400",
  seed_discovery: "bg-yellow-400",
  citation_grounding: "bg-yellow-400",
  agent_step: "bg-muted-foreground/50",
};

function dotColor(severity: string, category: string): string {
  if (severity === "error") return "bg-red-400";
  if (severity === "warning") return "bg-yellow-400";
  if (severity === "success") return "bg-emerald-400";
  return CATEGORY_COLOR[category] ?? "bg-muted-foreground/50";
}

// Unified timeline item: a rich activity, or an error/warning notification.
// phaseHeader is precomputed (pure) so render does not mutate state.
type Item = (
  | { kind: "activity"; ts: string; data: ActivityEvent }
  | { kind: "notif"; ts: string; data: Notification }
) & { phaseHeader: string | null };

export function EventLog({ activityEvents, notifications }: EventLogProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const items = useMemo<Item[]>(() => {
    const acts = activityEvents.map(
      (a) => ({ kind: "activity" as const, ts: a.timestamp, data: a })
    );
    // Only surface error/warning notifications here (info-level are toasts).
    const notifs = notifications
      .filter((n) => n.level === "error" || n.level === "warning")
      .map((n) => ({ kind: "notif" as const, ts: n.timestamp, data: n }));
    const sorted = [...acts, ...notifs]
      .sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0))
      .slice(-120);

    // Phase header when the phase differs from the most recent phased item.
    return sorted.map((it, i) => {
      const phase = it.kind === "activity" ? it.data.phase : "";
      const prev = sorted
        .slice(0, i)
        .reverse()
        .find((p) => p.kind === "activity" && p.data.phase);
      const prevPhase = prev && prev.kind === "activity" ? prev.data.phase : "";
      const phaseHeader = phase && phase !== prevPhase ? phase : null;
      return { ...it, phaseHeader };
    });
  }, [activityEvents, notifications]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
    if (isNearBottom) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [items.length]);

  return (
    <div ref={containerRef} className="flex flex-col gap-0.5 overflow-y-auto p-2 h-full text-[11px]">
      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-[0.1em] px-1 mb-1 sticky top-0 bg-background/90 backdrop-blur-sm z-10 py-1">
        Activity
      </h3>
      {items.length === 0 && (
        <p className="text-xs text-muted-foreground/50 px-1">No activity yet</p>
      )}
      {items.map((item) => {
        const ph = item.phaseHeader;
        return (
          <div key={item.kind === "activity" ? item.data.id : `n-${item.data.id}`}>
            {ph && (
              <div className="mt-2 mb-1 px-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                {PHASE_LABELS[ph] ?? ph.replace(/_/g, " ")}
              </div>
            )}
            {item.kind === "activity" ? (
              <div className="flex gap-2 px-1 py-1 hover:bg-accent/20 rounded transition-colors">
                <span
                  className={cn(
                    "mt-1 h-1.5 w-1.5 shrink-0 rounded-full",
                    dotColor(item.data.severity, item.data.category)
                  )}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-1.5">
                    <span className="font-medium text-foreground/90 truncate">
                      {item.data.title}
                    </span>
                    {item.data.durationMs != null && (
                      <span className="text-[10px] tabular-nums text-muted-foreground/60 shrink-0">
                        {formatDuration(item.data.durationMs)}
                      </span>
                    )}
                    <span className="ml-auto text-[10px] text-muted-foreground/40 shrink-0">
                      {formatTime(item.data.timestamp)}
                    </span>
                  </div>
                  {item.data.narration && (
                    <p className="text-[10px] leading-snug text-muted-foreground/70 italic">
                      {item.data.narration}
                    </p>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex gap-2 px-1 py-0.5 font-mono">
                <span
                  className={cn(
                    "mt-1 h-1.5 w-1.5 shrink-0 rounded-full",
                    item.data.level === "error" ? "bg-red-400" : "bg-yellow-400"
                  )}
                />
                <span className="text-foreground/70 leading-tight">{item.data.message}</span>
              </div>
            )}
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
