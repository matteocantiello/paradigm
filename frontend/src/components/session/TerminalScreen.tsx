import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { CheckCircle2, AlertTriangle, OctagonX, FileText, RotateCcw, ArrowRight } from "lucide-react";
import { PHASE_LABELS } from "@/lib/constants";
import { resumeCycle } from "@/api/client";
import { cn } from "@/lib/utils";

interface TerminalScreenProps {
  status: string; // "completed" | "failed" | "aborted"
  cycleId?: string;
  paperId?: string;
  currentPhase: string | null;
  roundNum: number;
  totalTokens: number;
  papersFound: number;
  elapsedSeconds: number;
}

function fmtDuration(secs: number): string {
  if (secs <= 0) return "—";
  if (secs < 60) return `${secs}s`;
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return s ? `${m}m ${s}s` : `${m}m`;
}

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return `${n}`;
}

const TONES = {
  ok: { wrap: "border-emerald-500/30 bg-emerald-500/[0.07]", icon: "text-emerald-400", title: "text-emerald-200" },
  warn: { wrap: "border-amber-500/30 bg-amber-500/[0.07]", icon: "text-amber-400", title: "text-amber-200" },
  bad: { wrap: "border-red-500/30 bg-red-500/[0.07]", icon: "text-red-400", title: "text-red-200" },
  idle: { wrap: "border-border bg-muted/20", icon: "text-muted-foreground", title: "text-foreground" },
} as const;

export function TerminalScreen({
  status,
  cycleId,
  paperId,
  currentPhase,
  roundNum,
  totalTokens,
  papersFound,
  elapsedSeconds,
}: TerminalScreenProps) {
  const navigate = useNavigate();
  const [resuming, setResuming] = useState(false);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function doResume() {
    if (!cycleId || busy) return;
    setBusy(true);
    setError(null);
    try {
      const cont = await resumeCycle(cycleId, comment.trim() || undefined);
      if (cont.session_id) navigate(`/session/${cont.session_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to resume");
    } finally {
      setBusy(false);
    }
  }

  const phaseLabel = currentPhase
    ? (PHASE_LABELS[currentPhase] ?? currentPhase.replace(/_/g, " "))
    : "—";
  const converged = status === "completed" && !!paperId;

  let tone: keyof typeof TONES;
  let Icon = CheckCircle2;
  let title = "Research complete";
  let line = "The team converged and produced a paper.";
  if (converged) {
    tone = "ok";
  } else if (status === "completed") {
    tone = "warn";
    Icon = AlertTriangle;
    title = "Finished without a paper";
    line = `The cycle ran to the end (${phaseLabel}) but didn't converge on a publishable paper.`;
  } else if (status === "failed") {
    tone = "bad";
    Icon = OctagonX;
    title = "The cycle hit an error";
    line = `It stopped during the ${phaseLabel} phase and couldn't continue. Your work up to here is saved.`;
  } else {
    tone = "idle";
    Icon = OctagonX;
    title = "Cycle stopped";
    line = `Stopped during the ${phaseLabel} phase.`;
  }
  const t = TONES[tone];

  return (
    <div className={cn("border-y px-4 py-3", t.wrap)}>
      <div className="flex items-start gap-3">
        <Icon className={cn("mt-0.5 h-5 w-5 shrink-0", t.icon)} />
        <div className="min-w-0 flex-1">
          <h2 className={cn("text-sm font-semibold", t.title)}>{title}</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">{line}</p>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] tabular-nums text-muted-foreground/80">
            <span>Reached: <span className="text-foreground/80">{phaseLabel}</span></span>
            {roundNum > 0 && <span>Rounds: <span className="text-foreground/80">{roundNum}</span></span>}
            {elapsedSeconds > 0 && (
              <span>Elapsed: <span className="text-foreground/80">{fmtDuration(elapsedSeconds)}</span></span>
            )}
            {totalTokens > 0 && (
              <span>Tokens: <span className="text-foreground/80">{fmtTokens(totalTokens)}</span></span>
            )}
            {papersFound > 0 && (
              <span>Papers read: <span className="text-foreground/80">{papersFound}</span></span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-stretch gap-1.5">
          {paperId && (
            <button
              onClick={() => navigate(`/papers?paper=${paperId}`)}
              className="flex items-center justify-center gap-1.5 rounded-lg bg-gradient-to-r from-primary to-primary/80 px-3 py-1.5 text-xs font-semibold text-primary-foreground transition-all hover:shadow-md hover:shadow-primary/20"
            >
              <FileText className="h-3.5 w-3.5" />
              View paper
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          )}
          {cycleId && (
            <button
              onClick={() => setResuming((v) => !v)}
              className={cn(
                "flex items-center justify-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
                resuming
                  ? "border-primary/50 bg-primary/10 text-foreground"
                  : "border-border text-muted-foreground hover:text-foreground hover:border-primary/40"
              )}
              title="Continue this research from its last checkpoint"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              {converged ? "Continue research" : "Resume"}
            </button>
          )}
          <button
            onClick={() => navigate("/research")}
            className="rounded-lg px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            Back to research
          </button>
        </div>
      </div>

      {resuming && (
        <div className="mt-3 rounded-lg border border-border/70 bg-background/40 p-3">
          <p className="mb-1.5 text-xs text-muted-foreground">
            Continues from the last checkpoint as a new run. Add optional steering for the team:
          </p>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            rows={2}
            placeholder="e.g. focus on the LMC sample; the X-ray nondetection is the key tension to address…"
            className="w-full resize-y rounded-md border border-input bg-card px-3 py-2 text-xs placeholder:text-muted-foreground/50 focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
          {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
          <div className="mt-2 flex items-center gap-2">
            <button
              onClick={doResume}
              disabled={busy}
              className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-primary to-primary/80 px-3 py-1.5 text-xs font-semibold text-primary-foreground transition-all hover:shadow-md hover:shadow-primary/20 disabled:opacity-50"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              {busy ? "Starting…" : "Continue research"}
            </button>
            <button
              onClick={() => setResuming(false)}
              className="rounded-lg px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
