import { useState } from "react";
import { useAgents } from "@/hooks/useAgents";
import { AgentCard } from "./AgentCard";
import { AgentConfig } from "./AgentConfig";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { ErrorState } from "@/components/shared/ErrorState";
import { EmptyState } from "@/components/shared/EmptyState";
import { Users } from "lucide-react";

export function AgentGrid() {
  const { data, isLoading, error, refetch } = useAgents();
  const [configuring, setConfiguring] = useState<string | null>(null);

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
        icon={Users}
        title="No agents available"
        description="Agent types will appear when the backend is configured."
      />
    );
  }

  return (
    <div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {data.items.map((agent) => (
          <AgentCard
            key={agent.agent_type}
            agent={agent}
            onConfigure={() =>
              setConfiguring(
                configuring === agent.agent_type ? null : agent.agent_type
              )
            }
          />
        ))}
      </div>
      {configuring && (
        <div className="mt-4 max-w-lg">
          <AgentConfig
            agentType={configuring}
            onClose={() => setConfiguring(null)}
          />
        </div>
      )}
    </div>
  );
}
