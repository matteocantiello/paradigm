import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useResearchSession } from "@/hooks/useResearchSession";
import { SessionView } from "@/components/session/SessionView";
import { listCycles } from "@/api/client";

export function SessionPage() {
  const { id } = useParams<{ id: string }>();
  const session = useResearchSession(id);

  // Fetch cycles to find paper_id for this session
  const { data: cycles } = useQuery({
    queryKey: ["cycles"],
    queryFn: () => listCycles(0, 100),
  });
  const paperId = cycles?.items.find((c) => c.session_id === id)?.paper_id ?? undefined;

  return (
    <div className="h-[calc(100vh-5rem)]">
      <SessionView {...session} paperId={paperId} />
    </div>
  );
}
