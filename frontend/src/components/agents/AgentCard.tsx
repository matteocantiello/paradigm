import { AGENT_THEMES } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { User, Settings } from "lucide-react";
import type { AgentInfo } from "@/api/client";

interface AgentCardProps {
  agent: AgentInfo;
  onConfigure: () => void;
}

export function AgentCard({ agent, onConfigure }: AgentCardProps) {
  const theme = AGENT_THEMES[agent.agent_type];
  const Icon = theme?.icon ?? User;

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <div
            className="flex items-center justify-center h-8 w-8 rounded-md bg-muted"
          >
            <Icon className={cn("h-4 w-4", theme?.color ?? "text-muted-foreground")} />
          </div>
          <div>
            <h3 className="text-sm font-medium">{theme?.label ?? agent.agent_type}</h3>
            <p className="text-xs text-muted-foreground">{agent.agent_type}</p>
          </div>
        </div>
        <button
          onClick={onConfigure}
          className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <Settings className="h-4 w-4" />
        </button>
      </div>
      {agent.description && (
        <p className="text-xs text-muted-foreground mb-3 line-clamp-2">
          {agent.description}
        </p>
      )}
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        {agent.default_model && (
          <span>Model: <span className="text-foreground">{agent.default_model}</span></span>
        )}
        {agent.default_provider && (
          <span>Provider: <span className="text-foreground">{agent.default_provider}</span></span>
        )}
      </div>
    </div>
  );
}
