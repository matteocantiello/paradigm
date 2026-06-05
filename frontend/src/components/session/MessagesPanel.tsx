import { useEffect, useRef, useState } from "react";
import type { AgentOutput } from "@/stores/sessionStore";
import { AGENT_THEMES, getAgentRole } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { User } from "lucide-react";

interface MessagesPanelProps {
  outputs: AgentOutput[];
}

export function MessagesPanel({ outputs }: MessagesPanelProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const recentOutputs = outputs.slice(-50);
  const anyStreaming = recentOutputs.some((o) => o.streaming);

  // Tick while anything is streaming so the "thinking" timer + cursor update.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!anyStreaming) return;
    const id = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(id);
  }, [anyStreaming]);

  // Auto-scroll on new bubbles AND as streaming content grows.
  const streamingChars = recentOutputs.reduce(
    (n, o) => n + (o.streaming ? o.content.length : 0),
    0
  );
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    if (isNearBottom) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [outputs.length, streamingChars]);

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
        const thinking = out.streaming && out.firstChunkAt === null;
        const thinkingSecs = Math.max(0, Math.round((now - out.startedAt) / 1000));
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
              {thinking && (
                <span className="ml-auto text-[10px] text-muted-foreground/70 animate-pulse">
                  thinking… {thinkingSecs}s
                </span>
              )}
            </div>
            <p className="text-muted-foreground leading-relaxed whitespace-pre-wrap break-words">
              {out.content}
              {out.streaming && !thinking && <span className="stream-caret text-primary" />}
            </p>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
