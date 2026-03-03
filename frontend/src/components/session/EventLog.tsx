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
    <div ref={containerRef} className="flex flex-col gap-0.5 overflow-y-auto p-2 h-full font-mono">
      <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider px-1 mb-1 font-sans sticky top-0 bg-background z-10">
        Events
      </h3>
      {recent.length === 0 && (
        <p className="text-xs text-muted-foreground/50 px-1 font-sans">No events yet</p>
      )}
      {recent.map((n) => (
        <div key={n.id} className="text-[11px] leading-tight px-1">
          <span className="text-muted-foreground">[{formatTime(n.timestamp)}]</span>{" "}
          <span className={cn(EVENT_COLORS[n.category] ?? EVENT_COLORS[n.level] ?? "text-muted-foreground")}>
            {n.message}
          </span>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
