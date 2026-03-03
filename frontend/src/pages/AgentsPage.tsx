import { AgentGrid } from "@/components/agents/AgentGrid";

export function AgentsPage() {
  return (
    <div className="max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-semibold">Agents</h1>
        <p className="text-sm text-muted-foreground">
          View and configure agent model settings
        </p>
      </div>
      <AgentGrid />
    </div>
  );
}
