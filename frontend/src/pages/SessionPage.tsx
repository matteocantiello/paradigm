import { useParams } from "react-router-dom";
import { useResearchSession } from "@/hooks/useResearchSession";
import { SessionView } from "@/components/session/SessionView";

export function SessionPage() {
  const { id } = useParams<{ id: string }>();
  const session = useResearchSession(id);

  return (
    <div className="h-[calc(100vh-5rem)]">
      <SessionView {...session} />
    </div>
  );
}
