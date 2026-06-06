import { StatusBadge } from "@/components/shared/StatusBadge";
import { TopicBadges } from "@/components/shared/TopicBadges";
import { truncate } from "@/lib/utils";
import type { PaperSummary } from "@/api/client";

interface PaperCardProps {
  paper: PaperSummary;
  onClick: () => void;
}

export function PaperCard({ paper, onClick }: PaperCardProps) {
  return (
    <button
      onClick={onClick}
      className="group w-full rounded-lg border border-border/50 bg-card/80 backdrop-blur-sm p-4 text-left transition-all duration-200 hover:border-primary/40 hover:bg-card hover:-translate-y-0.5 hover:shadow-lg hover:shadow-primary/5"
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <h3 className="text-sm font-medium line-clamp-2">{paper.title}</h3>
        <StatusBadge status={paper.status} />
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
