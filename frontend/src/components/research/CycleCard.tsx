import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2, RotateCcw } from "lucide-react";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { TopicBadges } from "@/components/shared/TopicBadges";
import { truncate } from "@/lib/utils";
import { resumeCycle, type ResearchCycleResponse } from "@/api/client";

interface CycleCardProps {
  cycle: ResearchCycleResponse;
  onDelete: (id: string) => void;
}

// Terminal/orphaned states that can be continued from a checkpoint.
const RESUMABLE = new Set(["interrupted", "failed", "aborted", "completed"]);

export function CycleCard({ cycle, onDelete }: CycleCardProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isClickable = !!cycle.session_id;
  const canResume = RESUMABLE.has(cycle.status);

  const resume = useMutation({
    mutationFn: () => resumeCycle(cycle.cycle_id),
    onSuccess: (cont) => {
      queryClient.invalidateQueries({ queryKey: ["cycles"] });
      if (cont.session_id) navigate(`/session/${cont.session_id}`);
    },
  });

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
      {cycle.resumed_from && (
        <p className="mb-1 flex items-center gap-1 text-[10px] text-muted-foreground/70">
          <RotateCcw className="h-3 w-3" /> continues an earlier run
        </p>
      )}
      <p className="text-sm mb-2 line-clamp-3">{truncate(cycle.seed_prompt, 200)}</p>
      <TopicBadges topics={cycle.topics} size="xs" className="mb-3" />
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground font-mono">
          {new Date(cycle.created_at).toLocaleDateString()}
          {cycle.current_phase ? ` · ${cycle.current_phase.replace(/_/g, " ")}` : ""}
        </span>
        <div className="flex items-center gap-1">
          {canResume && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                resume.mutate();
              }}
              disabled={resume.isPending}
              className="flex items-center gap-1 rounded-md px-1.5 py-1 text-xs text-amber-400/80 opacity-0 transition-all hover:bg-amber-500/10 hover:text-amber-300 group-hover:opacity-100 disabled:opacity-50"
              title="Resume from the last checkpoint"
            >
              <RotateCcw className={resume.isPending ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} />
              {resume.isPending ? "Resuming…" : "Resume"}
            </button>
          )}
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
    </div>
  );
}
