import { useState } from "react";
import { usePapers } from "@/hooks/usePapers";
import { PaperCard } from "./PaperCard";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { ErrorState } from "@/components/shared/ErrorState";
import { EmptyState } from "@/components/shared/EmptyState";
import { FileText, ChevronLeft, ChevronRight } from "lucide-react";

const PAGE_SIZE = 12;
const STATUS_FILTERS = ["all", "draft", "submitted", "published", "rejected"];

interface PaperListProps {
  onSelect: (paperId: string) => void;
}

export function PaperList({ onSelect }: PaperListProps) {
  const [statusFilter, setStatusFilter] = useState("all");
  const [page, setPage] = useState(0);
  const { data, isLoading, error, refetch } = usePapers(
    statusFilter === "all" ? undefined : statusFilter,
    page * PAGE_SIZE,
    PAGE_SIZE
  );

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        {STATUS_FILTERS.map((s) => (
          <button
            key={s}
            onClick={() => {
              setStatusFilter(s);
              setPage(0);
            }}
            className={`rounded-md px-2.5 py-1 text-xs font-medium capitalize transition-colors ${
              statusFilter === s
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-accent"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {isLoading && (
        <div className="flex justify-center py-16">
          <LoadingSpinner />
        </div>
      )}

      {error && <ErrorState message={error.message} onRetry={() => refetch()} />}

      {data && data.items.length === 0 && (
        <EmptyState
          icon={FileText}
          title="No papers found"
          description="Papers will appear here once research cycles complete."
        />
      )}

      {data && data.items.length > 0 && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {data.items.map((paper) => (
              <PaperCard
                key={paper.paper_id}
                paper={paper}
                onClick={() => onSelect(paper.paper_id)}
              />
            ))}
          </div>
          {Math.ceil(data.total / PAGE_SIZE) > 1 && (
            <div className="flex items-center justify-center gap-2 mt-6">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-accent disabled:opacity-30"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <span className="text-sm text-muted-foreground">
                Page {page + 1} of {Math.ceil(data.total / PAGE_SIZE)}
              </span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={(page + 1) * PAGE_SIZE >= data.total}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-accent disabled:opacity-30"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
