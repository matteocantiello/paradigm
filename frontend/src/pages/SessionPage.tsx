import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useResearchSession } from "@/hooks/useResearchSession";
import { SessionView } from "@/components/session/SessionView";
import { listCycles } from "@/api/client";

const TERMINAL_STATUSES = new Set(["completed", "failed", "aborted"]);

export function SessionPage() {
  const { id } = useParams<{ id: string }>();
  const session = useResearchSession(id);

  // Fetch cycles to find the paper_id + cycle_id for this session.
  const { data: cycles, refetch } = useQuery({
    queryKey: ["cycles"],
    queryFn: () => listCycles(0, 100),
  });
  const cycle = cycles?.items.find((c) => c.session_id === id);

  // The cycle's paper_id is only resolved once the run finalizes (it's enriched
  // from the thread). Refetch when the session ends so the terminal screen's
  // "View paper" button works — including for rejected papers.
  useEffect(() => {
    if (TERMINAL_STATUSES.has(session.status)) {
      void refetch();
    }
  }, [session.status, refetch]);

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
