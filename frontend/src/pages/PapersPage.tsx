import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { PaperList } from "@/components/papers/PaperList";
import { ArtifactTabs } from "@/components/papers/ArtifactTabs";
import { usePaper, usePaperArtifacts } from "@/hooks/usePapers";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { ArrowLeft } from "lucide-react";

export function PapersPage() {
  // Deep-linkable: /papers?paper=<id> opens that paper directly (used by the
  // end-of-run "View paper" action).
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedPaperId, setSelectedPaperIdState] = useState<string | null>(
    () => searchParams.get("paper")
  );
  const setSelectedPaperId = (id: string | null) => {
    setSelectedPaperIdState(id);
    setSearchParams(id ? { paper: id } : {}, { replace: true });
  };
  const { data: paper, isLoading: paperLoading } = usePaper(selectedPaperId ?? undefined);
  const { data: artifacts, isLoading: artifactsLoading } = usePaperArtifacts(
    selectedPaperId ?? undefined
  );

  const isLoading = paperLoading || artifactsLoading;

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
        ) : paper && artifacts ? (
          <ArtifactTabs paper={paper} artifacts={artifacts} />
        ) : paper ? (
          // Fallback: artifacts fetch failed but paper is available
          <ArtifactTabs
            paper={paper}
            artifacts={{
              paper_id: paper.paper_id,
              has_paper: true,
              has_literature: false,
              has_reviews: false,
              has_transcript: false,
              has_experiments: false,
              has_figures: false,
              has_pdf: false,
              has_digest: false,
              experiment_files: [],
              figure_files: [],
            }}
          />
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
