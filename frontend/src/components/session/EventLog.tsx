import { useEffect, useRef } from "react";
import type { Notification } from "@/stores/sessionStore";
import { EVENT_COLORS } from "@/lib/constants";
import { cn } from "@/lib/utils";

interface EventLogProps {
  notifications: Notification[];
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "";
  }
}

export function EventLog({ notifications }: EventLogProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    if (isNearBottom) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [notifications.length]);

  const recent = notifications.slice(-50);

  return (
    <div ref={containerRef} className="flex flex-col gap-0.5 overflow-y-auto p-2 h-full font-mono text-[11px]">
      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-[0.1em] px-1 mb-1 font-sans sticky top-0 bg-background/90 backdrop-blur-sm z-10 py-1">
        Events
      </h3>
      {recent.length === 0 && (
        <p className="text-xs text-muted-foreground/50 px-1 font-sans">No events yet</p>
      )}
      {recent.map((n) => (
        <div key={n.id} className="leading-tight px-1 py-0.5 hover:bg-accent/20 rounded transition-colors">
          <span className="text-muted-foreground/60">[{formatTime(n.timestamp)}]</span>{" "}
          <span className={cn(
            "font-medium",
            EVENT_COLORS[n.category] ?? EVENT_COLORS[n.level] ?? "text-muted-foreground"
          )}>
            [{n.category ?? n.level}]
          </span>{" "}
          <span className="text-foreground/80">
            {n.message}
          </span>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
