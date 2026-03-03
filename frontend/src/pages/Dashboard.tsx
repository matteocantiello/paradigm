import { useNavigate } from "react-router-dom";
import { useCycles } from "@/hooks/useCycles";
import { CycleCard } from "@/components/research/CycleCard";
import { useDeleteCycle } from "@/hooks/useCycles";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { EmptyState } from "@/components/shared/EmptyState";
import { Plus, Beaker } from "lucide-react";

export function Dashboard() {
  const navigate = useNavigate();
  const { data, isLoading } = useCycles(0, 5);
  const deleteCycle = useDeleteCycle();

  const runningCycles = data?.items.filter((c) => c.status === "running") ?? [];
  const recentCycles = data?.items ?? [];

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Dashboard</h1>
          <p className="text-sm text-muted-foreground">Overview of your research activity</p>
        </div>
        <button
          onClick={() => navigate("/research?new=1")}
          className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          <Plus className="h-4 w-4" />
          Quick Start
        </button>
      </div>

      {/* Running sessions */}
      {runningCycles.length > 0 && (
        <section>
          <h2 className="text-sm font-medium text-muted-foreground mb-3">Running Sessions</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {runningCycles.map((cycle) => (
              <CycleCard
                key={cycle.cycle_id}
                cycle={cycle}
                onDelete={(id) => deleteCycle.mutate(id)}
              />
            ))}
          </div>
        </section>
      )}

      {/* Recent cycles */}
      <section>
        <h2 className="text-sm font-medium text-muted-foreground mb-3">Recent Cycles</h2>
        {isLoading ? (
          <div className="flex justify-center py-8">
            <LoadingSpinner />
          </div>
        ) : recentCycles.length === 0 ? (
          <EmptyState
            icon={Beaker}
            title="No research cycles yet"
            description="Start your first research cycle to see it here."
            action={
              <button
                onClick={() => navigate("/research?new=1")}
                className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
              >
                <Plus className="h-4 w-4" />
                New Research Cycle
              </button>
            }
          />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {recentCycles.map((cycle) => (
              <CycleCard
                key={cycle.cycle_id}
                cycle={cycle}
                onDelete={(id) => deleteCycle.mutate(id)}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
