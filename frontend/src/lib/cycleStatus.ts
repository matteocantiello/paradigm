// Centralized cycle status → routing/terminal logic.
//
// A research cycle's WebSocket session lives only while the run is active and dies
// when the run ends (sessions are in-memory). So clicking a FINISHED cycle must not
// re-open that socket — it would spin forever on "reconnecting". These helpers give
// every caller one consistent answer to "is this cycle terminal?" and "where should
// clicking it go?", instead of the terminal-status sets that were duplicated across
// SessionPage / SessionView / useSystemState.

import type { ResearchCycleResponse } from "@/api/client";

// Run is still live → the WebSocket should connect (the one case it's for).
export const ACTIVE_STATUSES = new Set(["running", "starting", "paused"]);

// Run is over → the in-memory session is gone; never open a socket for these.
export const TERMINAL_STATUSES = new Set([
  "completed",
  "failed",
  "aborted",
  "interrupted",
  "published",
  "rejected",
  "reviewed",
  "review_rejected",
  "revision_exhausted",
  "execution_failed",
  "verification_failed",
  "writing_failed",
  "writing_incomplete",
  "planning_complete",
]);

// The outcome is decided even if status still says "running" (backend finalizing).
export const TERMINAL_PHASES = new Set(["published", "rejected"]);

export function isActiveStatus(status: string | null | undefined): boolean {
  return !!status && ACTIVE_STATUSES.has(status);
}

export function isTerminalStatus(status: string | null | undefined): boolean {
  return !!status && TERMINAL_STATUSES.has(status);
}

export function isTerminalPhase(phase: string | null | undefined): boolean {
  return !!phase && TERMINAL_PHASES.has(phase);
}

type CycleLike = Pick<
  ResearchCycleResponse,
  "status" | "current_phase" | "session_id" | "paper_id"
>;

// A cycle is terminal if its status is terminal OR its phase signals a decided outcome.
export function isCycleTerminal(c: CycleLike): boolean {
  return isTerminalStatus(c.status) || isTerminalPhase(c.current_phase);
}

// Where clicking a cycle should navigate — or null if it has nowhere to go yet
// (e.g. created but never started, so no session to attach to).
export function cycleDestination(c: CycleLike): string | null {
  // Still running → the live session view (where the WebSocket actually belongs).
  if (isActiveStatus(c.status) && c.session_id) {
    return `/session/${c.session_id}`;
  }
  // Finished WITH a paper → straight to the paper (deep-linkable, no live session).
  if (c.paper_id) {
    return `/papers?paper=${c.paper_id}`;
  }
  // Finished without a paper but we have the session record → the session view
  // renders a terminal summary from persisted data (and does NOT open a socket).
  if (c.session_id) {
    return `/session/${c.session_id}`;
  }
  return null;
}
