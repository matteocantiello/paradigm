import { AGENT_THEMES, getAgentRole } from "@/lib/constants";
import { cn, formatTokens } from "@/lib/utils";
import { useSessionStore } from "@/stores/sessionStore";
import { Coins, RefreshCw, User } from "lucide-react";

interface AgentPanelProps {
  activeAgents: Record<string, string>;
}

export function AgentPanel({ activeAgents }: AgentPanelProps) {
  // Per-agent usage, summed from each agent's messages: one message ≈ one call.
  const agentOutputs = useSessionStore((s) => s.agentOutputs);
  const tokensByAgent: Record<string, number> = {};
  const callsByAgent: Record<string, number> = {};
  for (const o of agentOutputs) {
    tokensByAgent[o.agentId] = (tokensByAgent[o.agentId] ?? 0) + (o.tokens || 0);
    callsByAgent[o.agentId] = (callsByAgent[o.agentId] ?? 0) + 1;
  }
  const entries = Object.entries(activeAgents);

  return (
    <div className="flex flex-col gap-1 p-2">
      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-[0.1em] px-1 mb-1">
        Agents
      </h3>
      {entries.length === 0 && (
        <p className="text-xs text-muted-foreground/50 px-1">No active agents</p>
      )}
      {entries.map(([agentId, activity]) => {
        const role = getAgentRole(agentId);
        const theme = AGENT_THEMES[role];
        const Icon = theme?.icon ?? User;
        const calls = callsByAgent[agentId] ?? 0;
        const tokens = tokensByAgent[agentId] ?? 0;
        return (
          <div
            key={agentId}
            className={cn(
              "flex items-center gap-2 rounded-lg px-2 py-2 border-l-2 transition-all",
              theme?.color
                ? `${theme.color.replace("text-", "border-")} hover:bg-accent/30`
                : "border-muted-foreground/30 hover:bg-accent/30"
            )}
          >
            <div
              className={cn(
                "flex items-center justify-center h-7 w-7 rounded-full bg-accent/50",
                activity && "animate-breathe"
              )}
            >
              <Icon className={cn("h-4 w-4 shrink-0", theme?.color ?? "text-muted-foreground")} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-xs font-semibold truncate">{theme?.label ?? role}</div>
              <div className="flex items-center gap-2 text-[10px] tabular-nums text-muted-foreground/80">
                <span className="flex items-center gap-0.5" title={`${calls} agent calls`}>
                  <RefreshCw className="h-2.5 w-2.5" />
                  {calls} {calls === 1 ? "call" : "calls"}
                </span>
                {tokens > 0 && (
                  <span
                    className="flex items-center gap-0.5"
                    title={`${tokens.toLocaleString()} tokens used`}
                  >
                    <Coins className="h-2.5 w-2.5" />
                    {formatTokens(tokens)}
                  </span>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
