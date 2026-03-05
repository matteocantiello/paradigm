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
    <div ref={containerRef} className="flex flex-col gap-1.5 overflow-y-auto p-2 h-full">
      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-[0.1em] px-1 mb-1 sticky top-0 bg-background/90 backdrop-blur-sm z-10 py-1">
        Messages
      </h3>
      {recentOutputs.length === 0 && (
        <p className="text-xs text-muted-foreground/50 px-1">Waiting for agent output...</p>
      )}
      {recentOutputs.map((out) => {
        const role = getAgentRole(out.agentId);
        const theme = AGENT_THEMES[role];
        const Icon = theme?.icon ?? User;
        const borderColor = theme?.color
          ? theme.color.replace("text-", "border-")
          : "border-muted-foreground/30";
        return (
          <div
            key={out.id}
            className={cn(
              "rounded-lg border-l-2 bg-card/50 p-3 text-xs animate-fade-in",
              borderColor
            )}
          >
            <div className="flex items-center gap-1.5 mb-1.5">
              <Icon className={cn("h-3.5 w-3.5", theme?.color ?? "text-muted-foreground")} />
              <span className="font-semibold text-foreground">{theme?.label ?? role}</span>
              {out.model && (
                <span className="text-muted-foreground/60 font-mono text-[10px]">({out.model})</span>
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
