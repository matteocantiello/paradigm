import { useState } from "react";
import { PaperList } from "@/components/papers/PaperList";
import { PaperViewer } from "@/components/papers/PaperViewer";
import { PaperTOC } from "@/components/papers/PaperTOC";
import { PaperExport } from "@/components/papers/PaperExport";
import { usePaper } from "@/hooks/usePapers";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { ArrowLeft } from "lucide-react";

export function PapersPage() {
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null);
  const { data: paper, isLoading } = usePaper(selectedPaperId ?? undefined);

  if (selectedPaperId) {
    return (
      <div className="max-w-6xl mx-auto">
        <button
          onClick={() => setSelectedPaperId(null)}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to papers
        </button>

        {isLoading ? (
          <div className="flex justify-center py-16">
            <LoadingSpinner />
          </div>
        ) : paper ? (
          <div className="grid grid-cols-[200px_1fr] gap-6">
            <aside className="sticky top-0 self-start">
              <PaperTOC body={paper.body} />
              <div className="mt-4 border-t border-border pt-3">
                <PaperExport title={paper.title} body={paper.body} />
              </div>
            </aside>
            <PaperViewer paper={paper} />
          </div>
        ) : (
          <p className="text-muted-foreground">Paper not found.</p>
        )}
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-semibold">Papers</h1>
        <p className="text-sm text-muted-foreground">Browse published research papers</p>
      </div>
      <PaperList onSelect={setSelectedPaperId} />
    </div>
  );
}
