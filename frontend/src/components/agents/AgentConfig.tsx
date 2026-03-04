import { useState, useEffect } from "react";
import { useAgentConfig, useUpdateAgent } from "@/hooks/useAgents";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { X, Save, RotateCcw, Loader2 } from "lucide-react";

interface AgentConfigProps {
  agentType: string;
  onClose: () => void;
}

export function AgentConfig({ agentType, onClose }: AgentConfigProps) {
  const { data, isLoading } = useAgentConfig(agentType);
  const updateAgent = useUpdateAgent();

  const [model, setModel] = useState("");
  const [provider, setProvider] = useState("");
  const [maxTokens, setMaxTokens] = useState("");
  const [tokenBudget, setTokenBudget] = useState("");

  useEffect(() => {
    if (data) {
      setModel(data.model ?? "");
      setProvider(data.provider ?? "");
      setMaxTokens(data.max_tokens != null ? String(data.max_tokens) : "");
      setTokenBudget(data.token_budget != null ? String(data.token_budget) : "");
    }
  }, [data]);

  const handleSave = () => {
    updateAgent.mutate({
      agentType,
      body: {
        model: model || null,
        provider: provider || null,
        max_tokens: maxTokens ? parseInt(maxTokens, 10) : null,
        token_budget: tokenBudget ? parseInt(tokenBudget, 10) : null,
      },
    });
  };

  const handleReset = () => {
    updateAgent.mutate({
      agentType,
      body: { model: null, provider: null, max_tokens: null, token_budget: null },
    });
  };

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <LoadingSpinner />
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium">Configure: {agentType}</h3>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="space-y-3">
        <div>
          <label className="block text-xs text-muted-foreground mb-1">Model</label>
          <input
            type="text"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="e.g. claude-sonnet-4-5-20250929"
            className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
        <div>
          <label className="block text-xs text-muted-foreground mb-1">Provider</label>
          <input
            type="text"
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            placeholder="e.g. anthropic"
            className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-muted-foreground mb-1">Max Tokens</label>
            <input
              type="number"
              value={maxTokens}
              onChange={(e) => setMaxTokens(e.target.value)}
              placeholder="4096"
              className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
          <div>
            <label className="block text-xs text-muted-foreground mb-1">Token Budget</label>
            <input
              type="number"
              value={tokenBudget}
              onChange={(e) => setTokenBudget(e.target.value)}
              placeholder="50000"
              className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
        </div>
      </div>

      {updateAgent.isError && (
        <p className="text-xs text-red-400 mt-2">{updateAgent.error.message}</p>
      )}

      <div className="flex items-center justify-end gap-2 mt-4">
        <button
          onClick={handleReset}
          className="flex items-center gap-1 rounded-md px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-accent"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          Reset
        </button>
        <button
          onClick={handleSave}
          disabled={updateAgent.isPending}
          className="flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {updateAgent.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Save className="h-3.5 w-3.5" />
          )}
          Save
        </button>
      </div>
    </div>
  );
}
