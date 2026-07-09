import { StatusBadge } from "@/components/shared/StatusBadge";
import { TopicBadges } from "@/components/shared/TopicBadges";
import { truncate } from "@/lib/utils";
import type { PaperSummary } from "@/api/client";
import { Gauge } from "lucide-react";

interface PaperCardProps {
  paper: PaperSummary;
  onClick: () => void;
}

/** Compact quality-ledger badge: the judge's composite (1-10). */
export function JudgeBadge({
  scores,
}: {
  scores?: Record<string, number | string> | null;
}) {
  const composite = scores?.composite;
  if (typeof composite !== "number") return null;
  const tone =
    composite >= 7
      ? "text-emerald-300 bg-emerald-500/15"
      : composite >= 5
        ? "text-amber-300 bg-amber-500/15"
        : "text-red-300 bg-red-500/15";
  const title = ["novelty", "rigor", "clarity", "significance", "honesty"]
    .map((k) => `${k} ${scores?.[k] ?? "?"}`)
    .join(" · ");
  return (
    <span
      className={`flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 font-mono text-[10px] ${tone}`}
      title={`Judge: ${title}`}
    >
      <Gauge className="h-3 w-3" />
      {composite.toFixed(1)}
    </span>
  );
}

export function PaperCard({ paper, onClick }: PaperCardProps) {
  return (
    <button
      onClick={onClick}
      className="group w-full rounded-lg border border-border/50 bg-card/80 backdrop-blur-sm p-4 text-left transition-all duration-200 hover:border-primary/40 hover:bg-card hover:-translate-y-0.5 hover:shadow-lg hover:shadow-primary/5"
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <h3 className="text-sm font-medium line-clamp-2">{paper.title}</h3>
        <div className="flex items-center gap-1.5">
          <JudgeBadge scores={paper.judge_scores} />
          <StatusBadge status={paper.status} />
        </div>
      </div>
      {paper.abstract && (
        <p className="text-xs text-muted-foreground line-clamp-3 mb-2">
          {truncate(paper.abstract, 200)}
        </p>
      )}
      <TopicBadges topics={paper.topics} size="xs" className="mb-2" />
      <div className="flex items-center gap-3 text-xs text-muted-foreground font-mono">
        {paper.created_at && (
          <span>{new Date(paper.created_at).toLocaleDateString()}</span>
        )}
        {paper.published_at && (
          <span>Published: {new Date(paper.published_at).toLocaleDateString()}</span>
        )}
      </div>
    </button>
  );
}
