import { useEffect, useState } from "react";
import { useSessionStore } from "@/stores/sessionStore";

/**
 * A single, derived "what is the system doing right now" signal.
 *
 * It collapses connection status, run status, pending approval, and — crucially
 * — *time since the last server message* into one of a few human-legible states,
 * so the operator can always tell whether something is happening, nothing is
 * happening, or their input is needed.
 */
export type SystemState =
  | "disconnected"
  | "connecting"
  | "starting"
  | "working"
  | "thinking"
  | "awaiting"
  | "paused"
  | "stalled"
  | "done"
  | "stopped"
  | "failed";

export type StatusTone =
  | "live"
  | "think"
  | "attention"
  | "paused"
  | "stalled"
  | "ok"
  | "bad"
  | "idle";

export interface SystemStatus {
  state: SystemState;
  label: string;
  hint: string;
  tone: StatusTone;
  /** Seconds since the last inbound message (only meaningful while running). */
  idleSeconds: number;
}

// A live operation (model call, literature search, code run) can be silent for
// a while. Below WORKING we're clearly active; between WORKING and STALL we're
// presumed mid-step ("thinking"); beyond STALL it's probably stuck. STALL is
// generous (120s) because a single long agent turn or search can run that long.
const WORKING_MS = 12_000;
const STALL_MS = 120_000;

// Once the run reaches a terminal PHASE the outcome is decided; the backend may
// still be doing best-effort bookkeeping (reflections, file saves) before it
// flips the session status to "completed". Treat these as done so we never show
// a false "Stalled" after the result is in.
const TERMINAL_PHASES = new Set(["published", "rejected"]);

export function useSystemState(): SystemStatus {
  const connectionStatus = useSessionStore((s) => s.connectionStatus);
  const status = useSessionStore((s) => s.status);
  const currentPhase = useSessionStore((s) => s.currentPhase);
  const pendingApproval = useSessionStore((s) => s.pendingApproval);
  const lastActivityAt = useSessionStore((s) => s.lastActivityAt);
  const streaming = useSessionStore((s) => s.agentOutputs.some((o) => o.streaming));

  // 1s heartbeat: re-evaluate even when no new message arrives, so "stalled"
  // actually appears after a quiet stretch.
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => setTick((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, []);

  const idleMs = lastActivityAt ? Date.now() - lastActivityAt : 0;
  const idleSeconds = Math.floor(idleMs / 1000);

  if (connectionStatus === "disconnected")
    return { state: "disconnected", tone: "bad", label: "Disconnected", hint: "Trying to reconnect…", idleSeconds };
  if (connectionStatus === "connecting" || connectionStatus === "reconnecting")
    return { state: "connecting", tone: "idle", label: "Connecting…", hint: "Establishing the live link", idleSeconds };

  if (pendingApproval)
    return { state: "awaiting", tone: "attention", label: "Waiting for you", hint: "Approve, pause, or abort to continue", idleSeconds };

  // A terminal phase wins over a still-"running" status: the research is done,
  // even if the session hasn't formally finalized yet. Never show "stalled" here.
  if (status === "running" && currentPhase && TERMINAL_PHASES.has(currentPhase)) {
    const rejected = currentPhase === "rejected";
    return {
      state: "done",
      tone: rejected ? "attention" : "ok",
      label: rejected ? "Not accepted" : "Completed",
      hint: rejected ? "The paper was not accepted — see the outcome below" : "The research cycle finished",
      idleSeconds,
    };
  }

  switch (status) {
    case "paused":
      return { state: "paused", tone: "paused", label: "Paused", hint: "Resume from the bar below when ready", idleSeconds };
    case "completed":
      return { state: "done", tone: "ok", label: "Completed", hint: "The research cycle finished", idleSeconds };
    case "aborted":
      return { state: "stopped", tone: "idle", label: "Stopped", hint: "The cycle was aborted", idleSeconds };
    case "failed":
      return { state: "failed", tone: "bad", label: "Failed", hint: "The cycle ended with an error", idleSeconds };
    case "running": {
      if (streaming || idleMs < WORKING_MS)
        return { state: "working", tone: "live", label: "Working", hint: "Agents are actively researching", idleSeconds };
      if (idleMs < STALL_MS)
        return { state: "thinking", tone: "think", label: "Thinking…", hint: "A long step is running (model call or search)", idleSeconds };
      return {
        state: "stalled",
        tone: "stalled",
        label: "Stalled",
        hint: `No activity for ${idleSeconds}s — it may be stuck (try Pause/Abort)`,
        idleSeconds,
      };
    }
    default:
      return { state: "starting", tone: "idle", label: "Starting…", hint: "Spinning up the research cycle", idleSeconds };
  }
}
