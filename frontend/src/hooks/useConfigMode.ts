import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as api from "@/api/client";

export function useConfigMode() {
  return useQuery({
    queryKey: ["config-mode"],
    queryFn: () => api.getConfigMode(),
  });
}

export function useSetConfigMode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (mode: string) => api.setConfigMode(mode),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["config-mode"] });
      qc.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}
