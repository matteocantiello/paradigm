import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as api from "@/api/client";

export function useAgents() {
  return useQuery({
    queryKey: ["agents"],
    queryFn: () => api.listAgents(),
  });
}

export function useAgentConfig(agentType: string | undefined) {
  return useQuery({
    queryKey: ["agent-config", agentType],
    queryFn: () => api.getAgentConfig(agentType!),
    enabled: !!agentType,
  });
}

export function useUpdateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      agentType,
      body,
    }: {
      agentType: string;
      body: api.AgentConfigUpdate;
    }) => api.updateAgentConfig(agentType, body),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["agent-config", variables.agentType] });
      qc.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}

// Model catalog for the per-agent picker. `refresh` swaps the curated list for a
// live pull from each provider's API (cached server-side). Keyed by `refresh` so
// the two are cached separately and toggling re-fetches.
export function useModelCatalog(refresh: boolean) {
  return useQuery({
    queryKey: ["model-catalog", refresh],
    queryFn: () => api.getModelCatalog(refresh),
    staleTime: 5 * 60 * 1000,
  });
}
