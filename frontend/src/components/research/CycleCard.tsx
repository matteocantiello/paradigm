import { useNavigate } from "react-router-dom";
import { Trash2 } from "lucide-react";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { truncate } from "@/lib/utils";
import type { ResearchCycleResponse } from "@/api/client";

interface CycleCardProps {
  cycle: ResearchCycleResponse;
  onDelete: (id: string) => void;
}

export function CycleCard({ cycle, onDelete }: CycleCardProps) {
  const navigate = useNavigate();
  const isClickable = !!cycle.session_id;

  function handleCardClick() {
    if (isClickable) {
      navigate(`/session/${cycle.session_id}`);
    }
  }

  return (
    <div
      className={`rounded-lg border border-border bg-card p-4 transition-colors ${
        isClickable ? "cursor-pointer hover:border-primary/50 hover:bg-accent/50" : ""
      }`}
      onClick={handleCardClick}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <StatusBadge status={cycle.status} />
        <span className="text-xs text-muted-foreground capitalize">{cycle.mode}</span>
      </div>
      <p className="text-sm mb-3 line-clamp-3">{truncate(cycle.seed_prompt, 200)}</p>
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          {new Date(cycle.created_at).toLocaleDateString()}
        </span>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete(cycle.cycle_id);
          }}
          className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive-foreground"
          title="Delete"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
