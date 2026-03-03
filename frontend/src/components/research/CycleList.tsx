import { useState } from "react";
import { useCycles, useDeleteCycle } from "@/hooks/useCycles";
import { CycleCard } from "./CycleCard";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { ErrorState } from "@/components/shared/ErrorState";
import { EmptyState } from "@/components/shared/EmptyState";
import { Beaker, ChevronLeft, ChevronRight } from "lucide-react";

const PAGE_SIZE = 12;

export function CycleList() {
  const [page, setPage] = useState(0);
  const { data, isLoading, error, refetch } = useCycles(page * PAGE_SIZE, PAGE_SIZE);
  const deleteCycle = useDeleteCycle();

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <LoadingSpinner />
      </div>
    );
  }

  if (error) {
    return <ErrorState message={error.message} onRetry={() => refetch()} />;
  }

  if (!data || data.items.length === 0) {
    return (
      <EmptyState
        icon={Beaker}
        title="No research cycles"
        description="Create a new research cycle to get started."
      />
    );
  }

  const totalPages = Math.ceil(data.total / PAGE_SIZE);

  return (
    <div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {data.items.map((cycle) => (
          <CycleCard
            key={cycle.cycle_id}
            cycle={cycle}
            onDelete={(id) => deleteCycle.mutate(id)}
          />
        ))}
      </div>
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-6">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-accent disabled:opacity-30"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="text-sm text-muted-foreground">
            Page {page + 1} of {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-accent disabled:opacity-30"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}
