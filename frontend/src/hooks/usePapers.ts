import { useQuery } from "@tanstack/react-query";
import * as api from "@/api/client";

export function usePapers(status?: string, offset = 0, limit = 20) {
  return useQuery({
    queryKey: ["papers", status, offset, limit],
    queryFn: () => api.listPapers(status, offset, limit),
  });
}

export function usePaper(paperId: string | undefined) {
  return useQuery({
    queryKey: ["paper", paperId],
    queryFn: () => api.getPaper(paperId!),
    enabled: !!paperId,
  });
}
