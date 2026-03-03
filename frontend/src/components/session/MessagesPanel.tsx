import { useEffect, useRef } from "react";
import type { AgentOutput } from "@/stores/sessionStore";
import { AGENT_THEMES, getAgentRole } from "@/lib/constants";
import { cn, truncate } from "@/lib/utils";
import { User } from "lucide-react";

interface MessagesPanelProps {
  outputs: AgentOutput[];
}

export function MessagesPanel({ outputs }: MessagesPanelProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    // Auto-scroll if user is near bottom
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
    if (isNearBottom) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [outputs.length]);

  const recentOutputs = outputs.slice(-50);

  return (
    <div ref={containerRef} className="flex flex-col gap-1 overflow-y-auto p-2 h-full">
      <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider px-1 mb-1 sticky top-0 bg-background z-10">
        Messages
      </h3>
      {recentOutputs.length === 0 && (
        <p className="text-xs text-muted-foreground/50 px-1">Waiting for agent output...</p>
      )}
      {recentOutputs.map((out) => {
        const role = getAgentRole(out.agentId);
        const theme = AGENT_THEMES[role];
        const Icon = theme?.icon ?? User;
        return (
          <div key={out.id} className="rounded-md border border-border/50 p-2 text-xs">
            <div className="flex items-center gap-1.5 mb-1">
              <Icon className={cn("h-3.5 w-3.5", theme?.color ?? "text-muted-foreground")} />
              <span className="font-medium">{theme?.label ?? role}</span>
              {out.model && (
                <span className="text-muted-foreground">({out.model})</span>
              )}
            </div>
            <p className="text-muted-foreground leading-relaxed whitespace-pre-wrap">
              {truncate(out.content, 500)}
            </p>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
