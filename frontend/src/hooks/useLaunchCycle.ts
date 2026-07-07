import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { createCycle, startSession, uploadCycleDataset } from "@/api/client";

export interface LaunchRequest {
  prompt: string;
  mode?: string;
  teamRoles?: string[] | null;
  files?: File[];
  interactive?: boolean;
  /** "premium" | "open" | null (null = server default). */
  modelTier?: string | null;
}

export type LaunchStage = "idle" | "creating" | "uploading" | "starting";

/**
 * Shared create → upload datasets → start-session flow (hero console + wizard).
 *
 * The created cycle id and the count of files already uploaded survive a failed
 * attempt, so retrying resumes where it broke instead of creating a duplicate
 * cycle or re-uploading finished files.
 */
export function useLaunchCycle() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [stage, setStage] = useState<LaunchStage>("idle");
  const [uploadIndex, setUploadIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [cycleId, setCycleId] = useState<string | null>(null);
  const uploadedRef = useRef(0);

  const launch = async (req: LaunchRequest) => {
    setError(null);
    const files = req.files ?? [];
    try {
      let cid = cycleId;
      if (!cid) {
        setStage("creating");
        const cycle = await createCycle({
          seed_prompt: req.prompt.trim(),
          mode: req.mode ?? "directed",
          team_roles: req.teamRoles ?? null,
          interactive: req.interactive ?? false,
          model_tier: req.modelTier ?? null,
        });
        cid = cycle.cycle_id;
        setCycleId(cid);
      }
      for (let i = uploadedRef.current; i < files.length; i++) {
        setStage("uploading");
        setUploadIndex(i);
        await uploadCycleDataset(cid, files[i]);
        uploadedRef.current = i + 1;
      }
      setStage("starting");
      const session = await startSession(cid);
      queryClient.invalidateQueries({ queryKey: ["cycles"] });
      queryClient.invalidateQueries({ queryKey: ["research-stats"] });
      navigate(`/session/${session.session_id}`);
    } catch (err) {
      setStage("idle");
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return {
    launch,
    stage,
    error,
    busy: stage !== "idle",
    uploadIndex,
    /** True when a cycle was already created — a retry resumes it. */
    isRetry: cycleId !== null,
  };
}
