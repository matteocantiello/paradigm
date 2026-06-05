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
      className={`group rounded-lg border border-border/50 bg-card/80 backdrop-blur-sm p-4 transition-all duration-200 ${
        isClickable
          ? "cursor-pointer hover:border-primary/40 hover:bg-card hover:-translate-y-0.5 hover:shadow-lg hover:shadow-primary/5"
          : ""
      }`}
      onClick={handleCardClick}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <StatusBadge status={cycle.status} />
        <span className="text-xs text-muted-foreground capitalize font-medium">{cycle.mode}</span>
      </div>
      <p className="text-sm mb-3 line-clamp-3">{truncate(cycle.seed_prompt, 200)}</p>
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground font-mono">
          {new Date(cycle.created_at).toLocaleDateString()}
          {cycle.current_phase ? ` · ${cycle.current_phase.replace(/_/g, " ")}` : ""}
        </span>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete(cycle.cycle_id);
          }}
          className="rounded-md p-1.5 text-muted-foreground/50 opacity-0 group-hover:opacity-100 hover:bg-destructive/10 hover:text-destructive-foreground transition-all"
          title="Delete"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
