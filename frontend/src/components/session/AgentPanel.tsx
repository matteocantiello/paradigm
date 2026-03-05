import { AGENT_THEMES, getAgentRole } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { User } from "lucide-react";

interface AgentPanelProps {
  activeAgents: Record<string, string>;
}

export function AgentPanel({ activeAgents }: AgentPanelProps) {
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
            <div className={cn(
              "flex items-center justify-center h-7 w-7 rounded-full bg-accent/50",
              activity && "animate-breathe"
            )}>
              <Icon className={cn("h-4 w-4 shrink-0", theme?.color ?? "text-muted-foreground")} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-xs font-semibold truncate">
                {theme?.label ?? role}
              </div>
              <div className="text-[10px] text-muted-foreground truncate">
                {activity}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
