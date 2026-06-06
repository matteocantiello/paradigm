import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useResearchSession } from "@/hooks/useResearchSession";
import { SessionView } from "@/components/session/SessionView";
import { listCycles } from "@/api/client";

const TERMINAL_STATUSES = new Set(["completed", "failed", "aborted"]);
const TERMINAL_PHASES = new Set(["published", "rejected"]);

export function SessionPage() {
  const { id } = useParams<{ id: string }>();
  const session = useResearchSession(id);

  // Fetch cycles to find the paper_id + cycle_id for this session.
  const { data: cycles, refetch } = useQuery({
    queryKey: ["cycles"],
    queryFn: () => listCycles(0, 100),
  });
  const cycle = cycles?.items.find((c) => c.session_id === id);

  // The cycle's paper_id is enriched from the thread's draft. Refetch when the
  // session ends — OR as soon as a terminal phase (published/rejected) arrives,
  // since the terminal screen now renders then (before the backend finalizes) and
  // needs paper_id for its "View paper" button. Works for rejected papers too.
  const phaseTerminal = session.currentPhase != null && TERMINAL_PHASES.has(session.currentPhase);
  useEffect(() => {
    if (TERMINAL_STATUSES.has(session.status) || phaseTerminal) {
      void refetch();
    }
  }, [session.status, phaseTerminal, refetch]);

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
