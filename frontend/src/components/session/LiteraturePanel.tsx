import { X, ExternalLink, BookOpen, ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import { usePaperLiterature } from "@/hooks/usePapers";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { EmptyState } from "@/components/shared/EmptyState";
import type { LiteratureSearchPaper, LiteratureSearchEntry } from "@/api/client";
import type { LiveLiterature } from "@/stores/sessionStore";
import { cn, formatByline } from "@/lib/utils";

// Normalized types for rendering (works with both live and API data)
type PaperInfo = {
  arxiv_id: string;
  title: string;
  authors: string;
  year: string;
  arxiv_url?: string;
};

type SearchInfo = {
  index: number;
  query: string;
  phase: string;
  papers: PaperInfo[];
};

function isValidArxivId(id: string): boolean {
  // Real arXiv IDs look like "2301.12345" or "hep-ph/0301234"
  // Synthetic IDs start with "ext-" or are hex hashes
  if (!id) return false;
  if (id.startsWith("ext-")) return false;
  if (/^[0-9a-f]{10,}$/.test(id)) return false;
  return true;
}

function makeArxivUrl(id: string): string | undefined {
  return isValidArxivId(id) ? `https://arxiv.org/abs/${id}` : undefined;
}

function makePdfUrl(id: string): string | undefined {
  return isValidArxivId(id) ? `https://arxiv.org/pdf/${id}` : undefined;
}

interface LiteraturePanelProps {
  paperId?: string;
  papersFound: number;
  liveLiterature?: LiveLiterature;
  onClose: () => void;
}

export function LiteraturePanel({ paperId, papersFound, liveLiterature, onClose }: LiteraturePanelProps) {
  const { data: apiLiterature, isLoading } = usePaperLiterature(paperId);
  const [expandedSearches, setExpandedSearches] = useState<Set<number>>(new Set());

  const toggleSearch = (idx: number) => {
    setExpandedSearches((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  // Normalize API data to common shape
  const apiData = apiLiterature ? {
    totalSearches: apiLiterature.total_searches,
    uniquePapers: apiLiterature.unique_papers.map((p: LiteratureSearchPaper): PaperInfo => ({
      arxiv_id: p.arxiv_id,
      title: p.title,
      authors: typeof p.authors === "string" ? p.authors : (p.authors as string[]).join(", "),
      year: p.year,
      arxiv_url: p.arxiv_url,
    })),
    searches: apiLiterature.searches.map((s: LiteratureSearchEntry, i: number): SearchInfo => ({
      index: i,
      query: s.query,
      phase: s.phase,
      papers: s.papers.map((p: LiteratureSearchPaper): PaperInfo => ({
        arxiv_id: p.arxiv_id,
        title: p.title,
        authors: typeof p.authors === "string" ? p.authors : (p.authors as string[]).join(", "),
        year: p.year,
        arxiv_url: p.arxiv_url,
      })),
    })),
  } : null;

  // Normalize live data to common shape
  const liveData = liveLiterature && liveLiterature.totalSearches > 0 ? {
    totalSearches: liveLiterature.totalSearches,
    uniquePapers: liveLiterature.uniquePapers.map((p): PaperInfo => ({
      arxiv_id: p.arxiv_id,
      title: p.title,
      authors: p.authors.join(", "),
      year: p.year,
    })),
    searches: liveLiterature.searches.map((s, i): SearchInfo => ({
      index: i,
      query: s.query,
      phase: s.phase,
      papers: s.papers.map((p): PaperInfo => ({
        arxiv_id: p.arxiv_id,
        title: p.title,
        authors: p.authors.join(", "),
        year: p.year,
      })),
    })),
  } : null;

  // Prefer API data (completed paper) over live data
  const data = apiData ?? liveData;

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
            {!apiData && liveData && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-green-500/20 text-green-400">
                LIVE
              </span>
            )}
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-muted transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {paperId && isLoading ? (
            <div className="flex justify-center py-12">
              <LoadingSpinner />
            </div>
          ) : !data ? (
            <EmptyState
              icon={BookOpen}
              title="No literature yet"
              description="Literature will appear here as searches are performed."
              className="py-12"
            />
          ) : (
            <>
              {/* Summary */}
              <div className="mb-4 text-xs text-muted-foreground">
                {data.totalSearches} searches, {data.uniquePapers.length} unique papers
              </div>

              {/* Unique papers list */}
              <div className="space-y-2 mb-6">
                <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                  Unique Papers
                </h3>
                {data.uniquePapers.map((paper) => (
                  <PaperCard key={paper.arxiv_id} paper={paper} />
                ))}
              </div>

              {/* Search-by-search detail */}
              {data.searches.length > 0 && (
                <div>
                  <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                    Search Details
                  </h3>
                  <div className="space-y-1">
                    {data.searches.map((search) => (
                      <SearchDetail
                        key={search.index}
                        search={search}
                        expanded={expandedSearches.has(search.index)}
                        onToggle={() => toggleSearch(search.index)}
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

function PaperCard({ paper }: { paper: PaperInfo }) {
  const absUrl = paper.arxiv_url || makeArxivUrl(paper.arxiv_id);
  const pdfUrl = makePdfUrl(paper.arxiv_id);

  return (
    <div className="rounded-md border border-border p-3 hover:border-indigo-500/40 transition-colors">
      <p className="text-sm font-medium leading-tight mb-1">{paper.title}</p>
      {formatByline(paper.authors, paper.year) && (
        <p className="text-xs text-muted-foreground mb-1.5">
          {formatByline(paper.authors, paper.year)}
        </p>
      )}
      {paper.arxiv_id && absUrl && (
        <div className="flex items-center gap-2">
          <a
            href={absUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 hover:underline"
          >
            <ExternalLink className="h-3 w-3" />
            arXiv:{paper.arxiv_id}
          </a>
          {pdfUrl && (
            <a
              href={pdfUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-muted-foreground hover:text-foreground hover:underline"
            >
              PDF
            </a>
          )}
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
  search: SearchInfo;
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
        <span className="text-xs font-medium">Search {search.index + 1}</span>
        {search.phase && (
          <span className={cn(
            "text-[10px] px-1.5 py-0 rounded-full",
            "bg-muted text-muted-foreground"
          )}>
            {search.phase}
          </span>
        )}
        <span className="text-xs text-muted-foreground truncate flex-1">
          {search.query}
        </span>
        <span className="text-[10px] text-muted-foreground shrink-0">
          {search.papers.length} papers
        </span>
      </button>
      {expanded && (
        <div className="px-3 pb-2 space-y-1.5">
          {search.papers.map((paper, rank) => (
            <div key={`${search.index}-${rank}`} className="flex items-start gap-2 text-xs">
              <span className="text-muted-foreground shrink-0 w-4 text-right">{rank + 1}.</span>
              <div className="min-w-0">
                <span className="font-medium">{paper.title}</span>
                {formatByline(paper.authors, paper.year) && (
                  <span className="text-muted-foreground">
                    {" "}
                    — {formatByline(paper.authors, paper.year)}
                  </span>
                )}
                {paper.arxiv_id && makeArxivUrl(paper.arxiv_id) && (
                  <a
                    href={makeArxivUrl(paper.arxiv_id)}
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
