import { X, ExternalLink, BookOpen, ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import { usePaperLiterature } from "@/hooks/usePapers";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { EmptyState } from "@/components/shared/EmptyState";
import type { LiteratureSearchPaper, LiteratureSearchEntry } from "@/api/client";
import { cn } from "@/lib/utils";

interface LiteraturePanelProps {
  paperId?: string;
  papersFound: number;
  onClose: () => void;
}

export function LiteraturePanel({ paperId, papersFound, onClose }: LiteraturePanelProps) {
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

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />

      {/* Panel */}
      <div className="relative w-full max-w-lg bg-background border-l border-border shadow-xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
          <div className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-indigo-400" />
            <h2 className="text-sm font-semibold">Literature Found</h2>
            <span className="text-xs text-muted-foreground">({papersFound} total)</span>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-muted transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {!paperId ? (
            <EmptyState
              icon={BookOpen}
              title="Not yet available"
              description="Literature data will be available after paper completion."
              className="py-12"
            />
          ) : isLoading ? (
            <div className="flex justify-center py-12">
              <LoadingSpinner />
            </div>
          ) : !literature ? (
            <EmptyState
              icon={BookOpen}
              title="No literature data"
              description="No literature searches were recorded for this paper."
              className="py-12"
            />
          ) : (
            <>
              {/* Summary */}
              <div className="mb-4 text-xs text-muted-foreground">
                {literature.total_searches} searches, {literature.unique_papers.length} unique papers
              </div>

              {/* Unique papers list */}
              <div className="space-y-2 mb-6">
                <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                  Unique Papers
                </h3>
                {literature.unique_papers.map((paper) => (
                  <PaperCard key={paper.arxiv_id} paper={paper} />
                ))}
              </div>

              {/* Search-by-search detail */}
              {literature.searches.length > 0 && (
                <div>
                  <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                    Search Details
                  </h3>
                  <div className="space-y-1">
                    {literature.searches.map((search) => (
                      <SearchDetail
                        key={search.search_num}
                        search={search}
                        expanded={expandedSearches.has(search.search_num)}
                        onToggle={() => toggleSearch(search.search_num)}
                      />
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function PaperCard({ paper }: { paper: LiteratureSearchPaper }) {
  return (
    <div className="rounded-md border border-border p-3 hover:border-indigo-500/40 transition-colors">
      <p className="text-sm font-medium leading-tight mb-1">{paper.title}</p>
      <p className="text-xs text-muted-foreground mb-1.5">
        {paper.authors} ({paper.year})
      </p>
      {paper.arxiv_id && (
        <div className="flex items-center gap-2">
          <a
            href={paper.arxiv_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 hover:underline"
          >
            <ExternalLink className="h-3 w-3" />
            arXiv:{paper.arxiv_id}
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

function SearchDetail({
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
          "text-[10px] px-1.5 py-0 rounded-full",
          "bg-muted text-muted-foreground"
        )}>
          {search.phase}
        </span>
        <span className="text-xs text-muted-foreground truncate flex-1">
          {search.query}
        </span>
        <span className="text-[10px] text-muted-foreground shrink-0">
          {search.papers.length} papers
        </span>
      </button>
      {expanded && (
        <div className="px-3 pb-2 space-y-1.5">
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
