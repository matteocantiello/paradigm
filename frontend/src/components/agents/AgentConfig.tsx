import { useState, useEffect } from "react";
import { useAgentConfig, useUpdateAgent, useModelCatalog } from "@/hooks/useAgents";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { cn } from "@/lib/utils";
import { X, Save, RotateCcw, Loader2, RefreshCw, ChevronDown } from "lucide-react";

interface AgentConfigProps {
  agentType: string;
  onClose: () => void;
}

const SELECT_CLS =
  "w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

// model + provider are encoded together in the <select> value (a model implies its
// provider). Model ids contain "/" but never "::", so it's a safe separator.
const SEP = "::";

export function AgentConfig({ agentType, onClose }: AgentConfigProps) {
  const { data, isLoading } = useAgentConfig(agentType);
  const updateAgent = useUpdateAgent();

  const [refresh, setRefresh] = useState(false);
  const { data: catalog, isFetching: catalogLoading } = useModelCatalog(refresh);

  const [model, setModel] = useState("");
  const [provider, setProvider] = useState("");
  const [maxTokens, setMaxTokens] = useState("");
  const [tokenBudget, setTokenBudget] = useState("");
  const [advanced, setAdvanced] = useState(false);

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
    setModel("");
    setProvider("");
    setMaxTokens("");
    setTokenBudget("");
    updateAgent.mutate({
      agentType,
      body: { model: null, provider: null, max_tokens: null, token_budget: null },
    });
  };

  const providers = catalog?.providers ?? [];
  const available = providers.filter((p) => p.available);
  const unavailable = providers.filter((p) => !p.available);
  const source = providers.find((p) => p.source === "live") ? "live" : "curated";

  // Is the current (provider, model) selectable from the catalog? If not (a custom
  // or stale value), surface it as its own option so the dropdown reflects reality.
  const selectValue = provider && model ? `${provider}${SEP}${model}` : "";
  const known = new Set(
    available.flatMap((p) => p.models.map((m) => `${p.name}${SEP}${m.id}`))
  );
  const isCustom = !!selectValue && !known.has(selectValue);

  const onSelect = (value: string) => {
    if (!value) {
      setProvider("");
      setModel("");
      return;
    }
    const i = value.indexOf(SEP);
    setProvider(value.slice(0, i));
    setModel(value.slice(i + SEP.length));
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
        <h3 className="text-sm font-medium capitalize">Configure: {agentType}</h3>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="space-y-3">
        {/* Model dropdown — grouped by provider; selecting a model sets its provider too. */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs text-muted-foreground">Model</label>
            <button
              onClick={() => setRefresh(true)}
              disabled={catalogLoading}
              className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-50"
              title="Pull the full live model list from each provider's API"
            >
              {catalogLoading ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <RefreshCw className="h-3 w-3" />
              )}
              {source === "live" ? "Live" : "Refresh from API"}
            </button>
          </div>
          <select value={selectValue} onChange={(e) => onSelect(e.target.value)} className={SELECT_CLS}>
            <option value="">Default (use config)</option>
            {isCustom && (
              <optgroup label="Current (custom)">
                <option value={selectValue}>{model}</option>
              </optgroup>
            )}
            {available.map((p) => (
              <optgroup key={p.name} label={p.label}>
                {p.models.map((m) => (
                  <option key={`${p.name}${SEP}${m.id}`} value={`${p.name}${SEP}${m.id}`}>
                    {m.label}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
          {unavailable.length > 0 && (
            <p className="mt-1 text-[10px] text-muted-foreground/70">
              Hidden (no API key):{" "}
              {unavailable.map((p) => p.label).join(", ")}
            </p>
          )}
          {providers.some((p) => p.error) && (
            <p className="mt-1 text-[10px] text-amber-400/80">
              Live refresh failed for some providers — showing curated list.
            </p>
          )}
        </div>

        {/* Max tokens + token budget. */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-muted-foreground mb-1">Max Tokens</label>
            <input
              type="number"
              value={maxTokens}
              onChange={(e) => setMaxTokens(e.target.value)}
              placeholder="8192"
              className={SELECT_CLS}
            />
          </div>
          <div>
            <label className="block text-xs text-muted-foreground mb-1">Token Budget</label>
            <input
              type="number"
              value={tokenBudget}
              onChange={(e) => setTokenBudget(e.target.value)}
              placeholder="100000"
              className={SELECT_CLS}
            />
          </div>
        </div>

        {/* Advanced: type any model id / provider not in the catalog. */}
        <div>
          <button
            onClick={() => setAdvanced((v) => !v)}
            className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
          >
            <ChevronDown className={cn("h-3 w-3 transition-transform", advanced && "rotate-180")} />
            Advanced (custom model / provider)
          </button>
          {advanced && (
            <div className="mt-2 grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Model id</label>
                <input
                  type="text"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder="e.g. claude-opus-4-8"
                  className={SELECT_CLS}
                />
              </div>
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Provider</label>
                <input
                  type="text"
                  value={provider}
                  onChange={(e) => setProvider(e.target.value)}
                  placeholder="anthropic / gemini / together"
                  className={SELECT_CLS}
                />
              </div>
            </div>
          )}
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
