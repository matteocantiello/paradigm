import { StatusBadge } from "@/components/shared/StatusBadge";
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
      className="w-full rounded-lg border border-border bg-card p-4 text-left hover:border-primary/30 transition-colors"
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
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
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
