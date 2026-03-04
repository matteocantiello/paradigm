import { useState, useCallback } from "react";
import { Send, Pause, Play, Square } from "lucide-react";
import { useSessionStore } from "@/stores/sessionStore";

export function InteractionBar() {
  const [message, setMessage] = useState("");
  const [target, setTarget] = useState<string>("orchestrator");
  const sendUserMessage = useSessionStore((s) => s.sendUserMessage);
  const sendSessionControl = useSessionStore((s) => s.sendSessionControl);
  const status = useSessionStore((s) => s.status);
  const activeAgents = useSessionStore((s) => s.activeAgents);

  const handleSend = useCallback(() => {
    const text = message.trim();
    if (!text) return;
    sendUserMessage(text, target === "orchestrator" ? null : target);
    setMessage("");
  }, [message, target, sendUserMessage]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleSend();
    }
  };

  const agentTargets = Object.keys(activeAgents);

  return (
    <div className="flex items-center gap-2 border-t border-border px-3 py-2 bg-background">
      <select
        value={target}
        onChange={(e) => setTarget(e.target.value)}
        className="rounded-md border border-input bg-background px-2 py-1.5 text-xs"
      >
        <option value="orchestrator">Orchestrator</option>
        {agentTargets.map((id) => (
          <option key={id} value={id}>
            {id}
          </option>
        ))}
      </select>
      <input
        type="text"
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Send a message... (Ctrl+Enter)"
        className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
      />
      <button
        onClick={handleSend}
        disabled={!message.trim()}
        className="rounded-md bg-primary p-1.5 text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
      >
        <Send className="h-4 w-4" />
      </button>
      <div className="flex items-center gap-1 border-l border-border pl-2">
        {status === "running" ? (
          <button
            onClick={() => sendSessionControl("pause")}
            className="rounded-md p-1.5 text-yellow-400 hover:bg-accent"
            title="Pause"
          >
            <Pause className="h-4 w-4" />
          </button>
        ) : status === "paused" ? (
          <button
            onClick={() => sendSessionControl("resume")}
            className="rounded-md p-1.5 text-green-400 hover:bg-accent"
            title="Resume"
          >
            <Play className="h-4 w-4" />
          </button>
        ) : null}
        <button
          onClick={() => sendSessionControl("abort")}
          className="rounded-md p-1.5 text-red-400 hover:bg-accent"
          title="Abort"
        >
          <Square className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
