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

export function usePaperArtifacts(paperId: string | undefined) {
  return useQuery({
    queryKey: ["paper-artifacts", paperId],
    queryFn: () => api.getPaperArtifacts(paperId!),
    enabled: !!paperId,
  });
}

export function usePaperLiterature(paperId: string | undefined) {
  return useQuery({
    queryKey: ["paper-literature", paperId],
    queryFn: () => api.getPaperLiterature(paperId!),
    enabled: !!paperId,
  });
}

export function usePaperReviews(paperId: string | undefined) {
  return useQuery({
    queryKey: ["paper-reviews", paperId],
    queryFn: () => api.getPaperReviews(paperId!),
    enabled: !!paperId,
  });
}

export function usePaperDigest(paperId: string | undefined) {
  return useQuery({
    queryKey: ["paper-digest", paperId],
    queryFn: () => api.getPaperDigest(paperId!),
    enabled: !!paperId,
  });
}

export function usePaperTranscript(paperId: string | undefined) {
  return useQuery({
    queryKey: ["paper-transcript", paperId],
    queryFn: () => api.getPaperTranscript(paperId!),
    enabled: !!paperId,
  });
}
