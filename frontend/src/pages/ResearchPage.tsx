import { useState } from "react";
import { useSearchParams, useLocation } from "react-router-dom";
import { CycleList } from "@/components/research/CycleList";
import { SetupWizard } from "@/components/research/SetupWizard";
import { Plus } from "lucide-react";

export function ResearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  // "Retry with this prompt" from a finished cycle navigates here with the prompt
  // in router state; open the wizard pre-filled.
  const prefillPrompt = (location.state as { prefillPrompt?: string } | null)?.prefillPrompt;
  const [showWizard, setShowWizard] = useState(
    searchParams.get("new") === "1" || !!prefillPrompt
  );

  const handleOpenWizard = () => {
    setShowWizard(true);
    setSearchParams({});
  };

  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold">Research Cycles</h1>
          <p className="text-sm text-muted-foreground">
            Create and manage research cycles
          </p>
        </div>
        <button
          onClick={handleOpenWizard}
          className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          <Plus className="h-4 w-4" />
          New Cycle
        </button>
      </div>
      <CycleList />
      {showWizard && (
        <SetupWizard onClose={() => setShowWizard(false)} initialPrompt={prefillPrompt} />
      )}
    </div>
  );
}
