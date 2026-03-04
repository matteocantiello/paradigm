import { useState } from "react";
import { ExternalLink, BookOpen, ChevronDown, ChevronRight } from "lucide-react";
import { usePaperLiterature } from "@/hooks/usePapers";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { EmptyState } from "@/components/shared/EmptyState";
import type { LiteratureSearchEntry, LiteratureSearchPaper } from "@/api/client";
import { cn } from "@/lib/utils";

interface LiteratureTabProps {
  paperId: string;
}

export function LiteratureTab({ paperId }: LiteratureTabProps) {
  const { data: literature, isLoading } = usePaperLiterature(paperId);
  const [expandedSearches, setExpandedSearches] = useState<Set<number>>(new Set());

  const toggleSearch = (num: number) => {
    setExpandedSearches((prev) => {
      const next = new Set(prev);
      if (next.has(num)) next.delete(num);
      else next.add(num);
      return next;
    });
  };

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <LoadingSpinner />
      </div>
    );
  }

  if (!literature) {
    return (
      <EmptyState
        icon={BookOpen}
        title="No literature data"
        description="No literature searches were recorded for this paper."
      />
    );
  }

  return (
    <div className="max-w-3xl">
      {/* Summary stats */}
      <div className="flex items-center gap-4 mb-6 text-sm text-muted-foreground">
        <span>{literature.total_searches} searches performed</span>
        <span className="h-3 w-px bg-border" />
        <span>{literature.unique_papers.length} unique papers found</span>
      </div>

      {/* Unique papers */}
      <div className="mb-8">
        <h3 className="text-sm font-semibold mb-3">Referenced Papers</h3>
        <div className="space-y-2">
          {literature.unique_papers.map((paper) => (
            <PaperRow key={paper.arxiv_id} paper={paper} />
          ))}
        </div>
      </div>

      {/* Search detail */}
      {literature.searches.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold mb-3">Search History</h3>
          <div className="space-y-1">
            {literature.searches.map((search) => (
              <SearchBlock
                key={search.search_num}
                search={search}
                expanded={expandedSearches.has(search.search_num)}
                onToggle={() => toggleSearch(search.search_num)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function PaperRow({ paper }: { paper: LiteratureSearchPaper }) {
  return (
    <div className="flex items-start gap-3 rounded-md border border-border p-3 hover:border-indigo-500/40 transition-colors">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium leading-tight">{paper.title}</p>
        <p className="text-xs text-muted-foreground mt-0.5">
          {paper.authors} ({paper.year})
        </p>
      </div>
      {paper.arxiv_id && (
        <div className="flex items-center gap-2 shrink-0">
          <a
            href={paper.arxiv_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 hover:underline"
          >
            <ExternalLink className="h-3 w-3" />
            Abstract
          </a>
          <a
            href={`https://arxiv.org/pdf/${paper.arxiv_id}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-muted-foreground hover:text-foreground hover:underline"
          >
            PDF
          </a>
        </div>
      )}
    </div>
  );
}

function SearchBlock({
  search,
  expanded,
  onToggle,
}: {
  search: LiteratureSearchEntry;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="rounded-md border border-border">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-muted/50 transition-colors"
      >
        {expanded ? (
          <ChevronDown className="h-3 w-3 shrink-0" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0" />
        )}
        <span className="text-xs font-medium">Search {search.search_num}</span>
        <span className={cn(
          "text-[10px] px-1.5 rounded-full",
          "bg-muted text-muted-foreground"
        )}>
          {search.phase}
        </span>
        <span className="text-xs text-muted-foreground truncate flex-1">{search.query}</span>
        <span className="text-[10px] text-muted-foreground shrink-0">
          {search.papers.length} results
        </span>
      </button>
      {expanded && (
        <div className="px-3 pb-2 space-y-1">
          {search.papers.map((paper) => (
            <div key={`${search.search_num}-${paper.rank}`} className="flex items-start gap-2 text-xs">
              <span className="text-muted-foreground shrink-0 w-4 text-right">{paper.rank}.</span>
              <div className="min-w-0">
                <span className="font-medium">{paper.title}</span>
                <span className="text-muted-foreground"> — {paper.authors} ({paper.year})</span>
                {paper.arxiv_id && (
                  <a
                    href={paper.arxiv_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ml-1 text-indigo-400 hover:underline"
                  >
                    [{paper.arxiv_id}]
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
