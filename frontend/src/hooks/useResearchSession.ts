import { useEffect } from "react";
import { useSessionStore } from "@/stores/sessionStore";

export function useResearchSession(sessionId: string | undefined) {
  const connect = useSessionStore((s) => s.connect);
  const disconnect = useSessionStore((s) => s.disconnect);
  const connectionStatus = useSessionStore((s) => s.connectionStatus);
  const status = useSessionStore((s) => s.status);
  const currentPhase = useSessionStore((s) => s.currentPhase);
  const roundNum = useSessionStore((s) => s.roundNum);
  const maxRounds = useSessionStore((s) => s.maxRounds);
  const activeAgents = useSessionStore((s) => s.activeAgents);
  const totalTokens = useSessionStore((s) => s.totalTokens);
  const totalSearches = useSessionStore((s) => s.totalSearches);
  const papersFound = useSessionStore((s) => s.papersFound);
  const elapsedSeconds = useSessionStore((s) => s.elapsedSeconds);
  const completedPhases = useSessionStore((s) => s.completedPhases);
  const avgStepMs = useSessionStore((s) => s.avgStepMs);
  const phaseElapsedSeconds = useSessionStore((s) => s.phaseElapsedSeconds);
  const agentOutputs = useSessionStore((s) => s.agentOutputs);
  const notifications = useSessionStore((s) => s.notifications);
  const activityEvents = useSessionStore((s) => s.activityEvents);
  const literature = useSessionStore((s) => s.literature);
  const knowledge = useSessionStore((s) => s.knowledge);
  const pendingApproval = useSessionStore((s) => s.pendingApproval);

  useEffect(() => {
    if (sessionId) {
      connect(sessionId);
      return () => disconnect();
    }
  }, [sessionId, connect, disconnect]);

  return {
    connectionStatus,
    status,
    currentPhase,
    roundNum,
    maxRounds,
    activeAgents,
    totalTokens,
    totalSearches,
    papersFound,
    elapsedSeconds,
    completedPhases,
    avgStepMs,
    phaseElapsedSeconds,
    agentOutputs,
    notifications,
    activityEvents,
    literature,
    knowledge,
    pendingApproval,
  };
}
