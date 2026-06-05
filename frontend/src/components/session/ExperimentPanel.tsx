import { useState } from "react";
import type { ExperimentRun } from "@/stores/sessionStore";
import { cn } from "@/lib/utils";

interface ExperimentPanelProps {
  experiments: ExperimentRun[];
}

const STATUS_STYLE: Record<string, { dot: string; text: string; label: string }> = {
  running: { dot: "bg-amber-400", text: "text-amber-400", label: "running" },
  success: { dot: "bg-emerald-400", text: "text-emerald-400", label: "success" },
  failure: { dot: "bg-red-400", text: "text-red-400", label: "failure" },
  timeout: { dot: "bg-orange-400", text: "text-orange-400", label: "timeout" },
  error: { dot: "bg-red-400", text: "text-red-400", label: "error" },
};

function ExperimentCard({ exp }: { exp: ExperimentRun }) {
  const [showCode, setShowCode] = useState(false);
  const [showStdout, setShowStdout] = useState(false);
  const running = exp.status === "running";
  const style = STATUS_STYLE[exp.status] ?? STATUS_STYLE.error;
  const resultEntries = Object.entries(exp.results);

  return (
    <div className="rounded border border-border/50 bg-muted/15 px-2 py-1.5">
      <div className="flex items-center gap-2">
        {running ? (
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400/70" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-400" />
          </span>
        ) : (
          <span className={cn("h-2 w-2 rounded-full", style.dot)} />
        )}
        <span className="text-[12px] font-medium text-foreground/90 truncate">{exp.name}</span>
        {exp.agentId && (
          <span className="text-[9px] font-mono text-muted-foreground/70">{exp.agentId}</span>
        )}
        <span className={cn("ml-auto text-[9px] uppercase tracking-wide", style.text)}>
          {style.label}
        </span>
      </div>

      {/* Parsed RESULT[...] values */}
      {resultEntries.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5">
          {resultEntries.map(([k, v]) => (
            <span
              key={k}
              className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-300"
            >
              {k} = <span className="tabular-nums font-semibold">{v}</span>
            </span>
          ))}
        </div>
      )}

      {/* Toggles */}
      <div className="flex items-center gap-3 mt-1.5 text-[10px]">
        {exp.code && (
          <button
            onClick={() => setShowCode((s) => !s)}
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            {showCode ? "▼" : "▶"} code
          </button>
        )}
        {exp.stdout && (
          <button
            onClick={() => setShowStdout((s) => !s)}
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            {showStdout ? "▼" : "▶"} stdout
          </button>
        )}
        {exp.hasFigures && <span className="text-violet-300">▣ figure</span>}
      </div>

      {showCode && exp.code && (
        <pre className="mt-1.5 max-h-48 overflow-auto rounded bg-background/60 p-2 text-[10px] leading-relaxed text-foreground/80 font-mono">
          {exp.code}
        </pre>
      )}
      {showStdout && exp.stdout && (
        <pre className="mt-1.5 max-h-40 overflow-auto rounded bg-background/60 p-2 text-[10px] leading-relaxed text-emerald-200/80 font-mono whitespace-pre-wrap">
          {exp.stdout}
        </pre>
      )}
    </div>
  );
}

export function ExperimentPanel({ experiments }: ExperimentPanelProps) {
  if (experiments.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground/50 text-sm font-sans">
        <p>No experiments yet</p>
        <p className="text-xs mt-1">Sandbox runs appear here during the execution phase</p>
      </div>
    );
  }

  const running = experiments.filter((e) => e.status === "running").length;
  const done = experiments.length - running;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center gap-1.5 px-2.5 py-1.5 border-b border-border/50 shrink-0">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
          Experiments
        </span>
        <span className="text-[10px] tabular-nums text-muted-foreground/70">
          {done} done{running > 0 ? ` · ${running} running` : ""}
        </span>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {[...experiments].reverse().map((e) => (
          <ExperimentCard key={e.id} exp={e} />
        ))}
      </div>
    </div>
  );
}
