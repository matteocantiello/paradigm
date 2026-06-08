import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as api from "@/api/client";

export function useCycles(offset = 0, limit = 20) {
  return useQuery({
    queryKey: ["cycles", offset, limit],
    queryFn: () => api.listCycles(offset, limit),
  });
}

export function useResearchStats() {
  return useQuery({
    queryKey: ["research-stats"],
    queryFn: () => api.getResearchStats(),
  });
}

export function useCycle(cycleId: string | undefined) {
  return useQuery({
    queryKey: ["cycle", cycleId],
    queryFn: () => api.getCycle(cycleId!),
    enabled: !!cycleId,
  });
}

export function useCreateCycle() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: api.ResearchCycleCreate) => api.createCycle(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cycles"] });
    },
  });
}

export function useDeleteCycle() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (cycleId: string) => api.deleteCycle(cycleId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cycles"] });
    },
  });
}

export function useStartSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (cycleId: string) => api.startSession(cycleId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cycles"] });
    },
  });
}
