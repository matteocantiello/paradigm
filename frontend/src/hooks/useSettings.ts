import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as api from "@/api/client";

export function useSettings() {
  return useQuery({
    queryKey: ["settings"],
    queryFn: () => api.getSettings(),
  });
}

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      section,
      body,
    }: {
      section: string;
      body: Record<string, unknown>;
    }) => api.updateSettings(section, body),
    onSuccess: (data) => {
      qc.setQueryData(["settings"], data);
    },
  });
}
