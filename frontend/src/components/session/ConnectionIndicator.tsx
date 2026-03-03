import { cn } from "@/lib/utils";
import type { ConnectionStatus } from "@/api/websocket";

const STATUS_MAP: Record<ConnectionStatus, { color: string; label: string }> = {
  connected: { color: "bg-green-500", label: "Connected" },
  connecting: { color: "bg-yellow-500 animate-pulse", label: "Connecting" },
  reconnecting: { color: "bg-yellow-500 animate-pulse", label: "Reconnecting" },
  disconnected: { color: "bg-red-500", label: "Disconnected" },
};

export function ConnectionIndicator({ status }: { status: ConnectionStatus }) {
  const { color, label } = STATUS_MAP[status];
  return (
    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <div className={cn("h-2 w-2 rounded-full", color)} />
      <span>{label}</span>
    </div>
  );
}
