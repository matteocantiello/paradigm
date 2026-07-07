import { useEffect, useState } from "react";
import type { ApprovalRequestMsg } from "@/api/ws-types";
import { useSessionStore } from "@/stores/sessionStore";
import { PHASE_ICONS, PHASE_LABELS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { ArrowRight, Check, Trophy } from "lucide-react";

interface ApprovalDialogProps {
  approval: ApprovalRequestMsg;
}

/**
 * Approval + decision dialog. Plain phase-transition approvals show the
 * from→to phases; structured decisions (interactive mode) additionally render
 * selectable choice cards (e.g. tournament-ranked hypotheses) whose selection
 * is sent back as `modifications.selected_ids`.
 */
export function ApprovalDialog({ approval }: ApprovalDialogProps) {
  const [notes, setNotes] = useState("");
  const [selected, setSelected] = useState<string[]>(approval.default_ids ?? []);
  const [secondsLeft, setSecondsLeft] = useState<number | null>(
    approval.timeout_seconds ?? null
  );
  const sendApprovalResponse = useSessionStore((s) => s.sendApprovalResponse);

  const choices = approval.choices ?? [];
  const hasChoices = choices.length > 0;

  // Countdown to the backend's auto-continue, so the operator knows the run
  // won't wait forever.
  useEffect(() => {
    if (secondsLeft === null) return;
    const t = setInterval(() => {
      setSecondsLeft((s) => (s === null || s <= 0 ? s : s - 1));
    }, 1000);
    return () => clearInterval(t);
  }, [secondsLeft === null]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = (id: string) => {
    if (approval.multi_select) {
      setSelected((prev) =>
        prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
      );
    } else {
      setSelected([id]);
    }
  };

  const handleDecision = (decision: "continue" | "pause" | "abort") => {
    const modifications =
      decision === "continue" && hasChoices ? { selected_ids: selected } : null;
    sendApprovalResponse(approval.request_id, decision, notes, modifications);
    setNotes("");
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className={cn(
        "w-full rounded-xl border border-primary/25 bg-card p-6 shadow-xl glow-sm",
        hasChoices ? "max-w-lg" : "max-w-md"
      )}>
        <div className="mb-1 flex items-start justify-between gap-3">
          <h2 className="text-lg font-semibold font-display">
            {approval.title || "Phase Transition Approval"}
          </h2>
          {secondsLeft !== null && secondsLeft > 0 && (
            <span
              className="shrink-0 rounded-full border border-border px-2 py-0.5 font-mono text-[11px] text-muted-foreground"
              title="The run continues automatically when this reaches zero"
            >
              auto in {Math.floor(secondsLeft / 60)}:{String(secondsLeft % 60).padStart(2, "0")}
            </span>
          )}
        </div>
        {approval.description && (
          <p className="mb-4 max-h-40 overflow-y-auto whitespace-pre-wrap text-sm text-muted-foreground">
            {approval.description}
          </p>
        )}

        {!hasChoices && (approval.from_phase || approval.to_phase) && (
          <div className="flex items-center justify-center gap-3 py-4 rounded-md bg-muted/50 mb-4">
            <div className="text-center">
              <div className="text-2xl">{PHASE_ICONS[approval.from_phase] ?? ""}</div>
              <div className="text-xs font-medium mt-1">
                {PHASE_LABELS[approval.from_phase] ?? approval.from_phase}
              </div>
            </div>
            <ArrowRight className="h-5 w-5 text-muted-foreground" />
            <div className="text-center">
              <div className="text-2xl">{PHASE_ICONS[approval.to_phase] ?? ""}</div>
              <div className="text-xs font-medium mt-1">
                {PHASE_LABELS[approval.to_phase] ?? approval.to_phase}
              </div>
            </div>
          </div>
        )}

        {hasChoices && (
          <div className="mb-4 max-h-72 space-y-2 overflow-y-auto pr-1">
            {choices.map((c, i) => {
              const isSelected = selected.includes(c.id);
              return (
                <button
                  key={c.id}
                  onClick={() => toggle(c.id)}
                  aria-pressed={isSelected}
                  className={cn(
                    "flex w-full items-start gap-2.5 rounded-lg border p-3 text-left transition-all",
                    isSelected
                      ? "border-primary/50 bg-primary/5"
                      : "border-border bg-muted/20 hover:border-primary/30"
                  )}
                >
                  <div
                    className={cn(
                      "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border transition-all",
                      isSelected
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-border"
                    )}
                  >
                    {isSelected && <Check className="h-3 w-3" />}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className={cn("text-sm leading-snug", !isSelected && "text-muted-foreground")}>
                      {c.label}
                    </p>
                    {c.detail && (
                      <p className="mt-1 text-xs leading-snug text-muted-foreground/70">{c.detail}</p>
                    )}
                  </div>
                  {c.score != null && (
                    <span className="flex shrink-0 items-center gap-1 rounded-full bg-muted/60 px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
                      {i === 0 && <Trophy className="h-3 w-3 text-primary" />}
                      {Math.round(c.score)}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        )}

        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder={
            hasChoices
              ? "Optional guidance for the agents (they'll see it next round)…"
              : "Optional notes…"
          }
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm mb-4 resize-none h-16 placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        />

        <div className="flex items-center justify-between gap-2">
          {hasChoices ? (
            <span className="text-xs text-muted-foreground">
              {selected.length}/{choices.length} selected
            </span>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <button
              onClick={() => handleDecision("abort")}
              className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-sm font-medium text-red-400 hover:bg-red-500/20"
            >
              Abort
            </button>
            <button
              onClick={() => handleDecision("pause")}
              className="rounded-md border border-yellow-500/30 bg-yellow-500/10 px-3 py-1.5 text-sm font-medium text-yellow-400 hover:bg-yellow-500/20"
            >
              Pause
            </button>
            <button
              onClick={() => handleDecision("continue")}
              disabled={hasChoices && selected.length === 0}
              className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-40"
            >
              {hasChoices ? "Confirm selection" : "Continue"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
