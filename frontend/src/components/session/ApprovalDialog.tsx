import { useState } from "react";
import type { ApprovalRequestMsg } from "@/api/ws-types";
import { useSessionStore } from "@/stores/sessionStore";
import { PHASE_ICONS, PHASE_LABELS } from "@/lib/constants";
import { ArrowRight } from "lucide-react";

interface ApprovalDialogProps {
  approval: ApprovalRequestMsg;
}

export function ApprovalDialog({ approval }: ApprovalDialogProps) {
  const [notes, setNotes] = useState("");
  const sendApprovalResponse = useSessionStore((s) => s.sendApprovalResponse);

  const handleDecision = (decision: "continue" | "pause" | "abort") => {
    sendApprovalResponse(approval.request_id, decision, notes);
    setNotes("");
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-xl">
        <h2 className="text-lg font-semibold mb-1">
          {approval.title || "Phase Transition Approval"}
        </h2>
        {approval.description && (
          <p className="text-sm text-muted-foreground mb-4">{approval.description}</p>
        )}

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

        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Optional notes..."
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm mb-4 resize-none h-16 placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        />

        <div className="flex gap-2 justify-end">
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
            className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            Continue
          </button>
        </div>
      </div>
    </div>
  );
}
