import { useSystemState, type StatusTone } from "@/hooks/useSystemState";
import { cn } from "@/lib/utils";

const TONE: Record<
  StatusTone,
  { dot: string; text: string; bg: string; ring: string; pulse: boolean }
> = {
  live: { dot: "bg-emerald-400", text: "text-emerald-300", bg: "bg-emerald-500/10", ring: "ring-emerald-500/30", pulse: true },
  think: { dot: "bg-amber-400", text: "text-amber-300", bg: "bg-amber-500/10", ring: "ring-amber-500/30", pulse: true },
  attention: { dot: "bg-indigo-400", text: "text-indigo-100", bg: "bg-indigo-500/20", ring: "ring-indigo-400/60", pulse: true },
  paused: { dot: "bg-slate-300", text: "text-slate-200", bg: "bg-slate-500/10", ring: "ring-slate-400/30", pulse: false },
  stalled: { dot: "bg-red-400", text: "text-red-300", bg: "bg-red-500/10", ring: "ring-red-500/40", pulse: true },
  ok: { dot: "bg-emerald-400", text: "text-emerald-300", bg: "bg-emerald-500/10", ring: "ring-emerald-500/30", pulse: false },
  bad: { dot: "bg-red-500", text: "text-red-300", bg: "bg-red-500/10", ring: "ring-red-500/40", pulse: false },
  idle: { dot: "bg-zinc-400", text: "text-zinc-300", bg: "bg-zinc-500/10", ring: "ring-zinc-500/20", pulse: false },
};

/**
 * The single most important "is anything happening?" indicator. Always tells the
 * operator one of: Working / Thinking / Waiting for you / Paused / Stalled / done.
 */
export function StatusPill({ className }: { className?: string }) {
  const { label, hint, tone, state } = useSystemState();
  const c = TONE[tone];
  return (
    <div
      className={cn(
        "flex items-center gap-2.5 rounded-lg px-3 py-1.5 ring-1 transition-colors",
        c.bg,
        c.ring,
        state === "awaiting" && "animate-[pulse_1.6s_ease-in-out_infinite]",
        className
      )}
      role="status"
      aria-live="polite"
    >
      <span className="relative flex h-2.5 w-2.5 shrink-0">
        {c.pulse && (
          <span className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-70", c.dot)} />
        )}
        <span className={cn("relative inline-flex h-2.5 w-2.5 rounded-full", c.dot)} />
      </span>
      <span className={cn("text-sm font-semibold tracking-tight", c.text)}>{label}</span>
      <span className="hidden sm:block truncate text-xs text-muted-foreground/70">{hint}</span>
    </div>
  );
}
