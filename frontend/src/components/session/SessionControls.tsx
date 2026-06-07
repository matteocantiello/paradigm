import { Pause, Play } from "lucide-react";
import { useSessionStore } from "@/stores/sessionStore";

/**
 * Always-visible run controls in the session header. Pause holds the cycle at the
 * next round boundary (and checkpoints, so it can be resumed later — even after a
 * backend restart, from the research list); Resume continues it.
 */
export function SessionControls() {
  const status = useSessionStore((s) => s.status);
  const sendSessionControl = useSessionStore((s) => s.sendSessionControl);

  if (status !== "running" && status !== "paused") return null;

  if (status === "paused") {
    return (
      <button
        onClick={() => sendSessionControl("resume")}
        className="flex shrink-0 items-center gap-1.5 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-300 transition-colors hover:bg-emerald-500/20"
        title="Resume this paused research cycle"
      >
        <Play className="h-3.5 w-3.5" />
        Resume
      </button>
    );
  }

  return (
    <button
      onClick={() => sendSessionControl("pause")}
      className="flex shrink-0 items-center gap-1.5 rounded-md border border-border bg-card/60 px-2.5 py-1 text-xs font-medium text-muted-foreground transition-colors hover:border-amber-500/40 hover:text-amber-300"
      title="Pause at the next round boundary — you can resume later from here"
    >
      <Pause className="h-3.5 w-3.5" />
      Pause
    </button>
  );
}
