import { useNavigate } from "react-router-dom";
import { Trash2, ExternalLink } from "lucide-react";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { truncate } from "@/lib/utils";
import type { ResearchCycleResponse } from "@/api/client";

interface CycleCardProps {
  cycle: ResearchCycleResponse;
  onDelete: (id: string) => void;
}

export function CycleCard({ cycle, onDelete }: CycleCardProps) {
  const navigate = useNavigate();

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-start justify-between gap-2 mb-2">
        <StatusBadge status={cycle.status} />
        <span className="text-xs text-muted-foreground capitalize">{cycle.mode}</span>
      </div>
      <p className="text-sm mb-3 line-clamp-3">{truncate(cycle.seed_prompt, 200)}</p>
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          {new Date(cycle.created_at).toLocaleDateString()}
        </span>
        <div className="flex items-center gap-1">
          {cycle.status === "running" && cycle.thread_id && (
            <button
              onClick={() => navigate(`/session/${cycle.thread_id}`)}
              className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              title="Open session"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </button>
          )}
          <button
            onClick={() => onDelete(cycle.cycle_id)}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive-foreground"
            title="Delete"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
