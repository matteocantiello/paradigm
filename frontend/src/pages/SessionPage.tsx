import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useResearchSession } from "@/hooks/useResearchSession";
import { SessionView } from "@/components/session/SessionView";
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

  // Refetch the cycle (for the enriched paper_id) when a terminal status/phase
  // arrives during a LIVE run, so the "View paper" button gets its id.
  const phaseTerminal = isTerminalPhase(session.currentPhase);
  useEffect(() => {
    if (isTerminalStatus(session.status) || phaseTerminal) {
      void refetch();
    }
  }, [session.status, phaseTerminal, refetch]);

  // When terminal (no live socket), drive the view from the persisted cycle record
  // so the TerminalScreen still renders its outcome + "View paper".
  const status = cycleTerminal ? (cycle?.status ?? session.status) : session.status;
  const currentPhase = cycleTerminal
    ? (cycle?.current_phase ?? session.currentPhase)
    : session.currentPhase;

  return (
    <div className="h-[calc(100vh-5rem)]">
      <SessionView
        {...session}
        status={status}
        currentPhase={currentPhase}
        paperId={cycle?.paper_id ?? undefined}
        cycleId={cycle?.cycle_id}
        topic={cycle?.seed_prompt}
      />
    </div>
  );
}
