import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-muted text-muted-foreground border-border",
  running: "bg-blue-500/15 text-blue-400 border-blue-500/25",
  starting: "bg-blue-500/15 text-blue-400 border-blue-500/25",
  paused: "bg-yellow-500/15 text-yellow-400 border-yellow-500/25",
  completed: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25",
  published: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25",
  aborted: "bg-red-500/15 text-red-400 border-red-500/25",
  failed: "bg-red-500/15 text-red-400 border-red-500/25",
  rejected: "bg-red-500/15 text-red-400 border-red-500/25",
  draft: "bg-muted text-muted-foreground border-border",
  submitted: "bg-purple-500/15 text-purple-400 border-purple-500/25",
};

const ANIMATED_STATUSES = new Set(["running", "starting"]);

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.pending;
  const isAnimated = ANIMATED_STATUSES.has(status);

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize",
        style,
        className
      )}
    >
      {isAnimated && (
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-50" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-current" />
        </span>
      )}
      {status}
    </span>
  );
}
