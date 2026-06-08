import { useEffect, useRef } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useResearchSession } from "@/hooks/useResearchSession";
import { SessionView } from "@/components/session/SessionView";
import { TerminalSessionView } from "@/components/session/TerminalSessionView";
import { listCycles } from "@/api/client";
import { isCycleTerminal, isTerminalStatus, isTerminalPhase } from "@/lib/cycleStatus";

export function SessionPage() {
  const { id } = useParams<{ id: string }>();

  // Fetch cycles to find this session's cycle (status, paper_id, phase). We need
  // its status BEFORE deciding whether to open the live WebSocket.
  const { data: cycles, refetch } = useQuery({
    queryKey: ["cycles"],
    queryFn: () => listCycles(0, 100),
  });
  const cycle = cycles?.items.find((c) => c.session_id === id);

  // A finished cycle's in-memory session is gone — don't open a socket (it would
  // spin on "reconnecting"); render the terminal summary from persisted data instead.
  const cycleTerminal = cycle ? isCycleTerminal(cycle) : false;
  const session = useResearchSession(id, !cycleTerminal);

  // Latch whether we ever had a LIVE socket here. If a run is watched to completion,
  // keep the live view (transcript stays readable) even after it turns terminal; the
  // standalone summary is only for a cycle that was already finished when opened. A
  // dead session never reaches "connected", so this stays false for those.
  const everConnected = useRef(false);
  useEffect(() => {
    if (session.connectionStatus === "connected") everConnected.current = true;
  }, [session.connectionStatus]);

  // Refetch the cycle (for the enriched paper_id) when a terminal status/phase
  // arrives during a LIVE run, so the "View paper" button gets its id.
  const phaseTerminal = isTerminalPhase(session.currentPhase);
  useEffect(() => {
    if (isTerminalStatus(session.status) || phaseTerminal) {
      void refetch();
    }
  }, [session.status, phaseTerminal, refetch]);

  // A cycle that was already finished when opened has no live session — render the
  // standalone end-of-run summary instead of empty live panels. (If we watched it
  // finish live, everConnected keeps the live view + transcript.)
  if (cycle && cycleTerminal && !everConnected.current) {
    return (
      <div className="h-[calc(100vh-5rem)]">
        <TerminalSessionView cycle={cycle} />
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-5rem)]">
      <SessionView
        {...session}
        paperId={cycle?.paper_id ?? undefined}
        cycleId={cycle?.cycle_id}
        topic={cycle?.seed_prompt}
      />
    </div>
  );
}
