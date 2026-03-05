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
    <div className="flex items-center gap-2 border-t border-border px-3 py-2.5 bg-background/80 backdrop-blur-sm">
      <select
        value={target}
        onChange={(e) => setTarget(e.target.value)}
        className="rounded-lg border border-input bg-card px-2.5 py-2 text-xs font-medium appearance-none cursor-pointer hover:border-primary/40 transition-colors"
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
        className="flex-1 rounded-lg border border-input bg-card px-4 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 transition-all"
      />
      <button
        onClick={handleSend}
        disabled={!message.trim()}
        className="rounded-lg bg-gradient-to-r from-primary to-primary/80 p-2 text-primary-foreground hover:shadow-md hover:shadow-primary/20 disabled:opacity-40 transition-all"
      >
        <Send className="h-4 w-4" />
      </button>
      <div className="flex items-center gap-1 border-l border-border pl-2">
        {status === "running" ? (
          <button
            onClick={() => sendSessionControl("pause")}
            className="rounded-lg p-2 text-yellow-400 hover:bg-yellow-500/10 transition-colors"
            title="Pause"
          >
            <Pause className="h-4 w-4" />
          </button>
        ) : status === "paused" ? (
          <button
            onClick={() => sendSessionControl("resume")}
            className="rounded-lg p-2 text-emerald-400 hover:bg-emerald-500/10 transition-colors"
            title="Resume"
          >
            <Play className="h-4 w-4" />
          </button>
        ) : null}
        <button
          onClick={() => sendSessionControl("abort")}
          className="rounded-lg p-2 text-red-400 hover:bg-red-500/10 transition-colors"
          title="Abort"
        >
          <Square className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
