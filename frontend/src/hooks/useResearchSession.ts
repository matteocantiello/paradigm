import { useEffect } from "react";
import { useSessionStore } from "@/stores/sessionStore";

export function useResearchSession(sessionId: string | undefined, shouldConnect = true) {
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
  const topics = useSessionStore((s) => s.topics);
  const avgStepMs = useSessionStore((s) => s.avgStepMs);
  const phaseElapsedSeconds = useSessionStore((s) => s.phaseElapsedSeconds);
  const agentOutputs = useSessionStore((s) => s.agentOutputs);
  const notifications = useSessionStore((s) => s.notifications);
  const activityEvents = useSessionStore((s) => s.activityEvents);
  const literature = useSessionStore((s) => s.literature);
  const knowledge = useSessionStore((s) => s.knowledge);
  const draft = useSessionStore((s) => s.draft);
  const experiments = useSessionStore((s) => s.experiments);
  const pendingApproval = useSessionStore((s) => s.pendingApproval);

  useEffect(() => {
    // Never open a socket for a finished cycle — the in-memory session is gone and
    // it would just spin on "reconnecting". The caller passes shouldConnect=false
    // once it knows the cycle is terminal.
    if (sessionId && shouldConnect) {
      connect(sessionId);
      return () => disconnect();
    }
  }, [sessionId, shouldConnect, connect, disconnect]);

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
    topics,
    avgStepMs,
    phaseElapsedSeconds,
    agentOutputs,
    notifications,
    activityEvents,
    literature,
    knowledge,
    draft,
    experiments,
    pendingApproval,
  };
}
