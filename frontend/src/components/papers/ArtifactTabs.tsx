import { useState } from "react";
import {
  FileText,
  Newspaper,
  BookOpen,
  MessageSquare,
  ScrollText,
  Code2,
  Image,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { PaperArtifactList, PaperDetail } from "@/api/client";
import { paperPdfUrl } from "@/api/client";
import { PaperViewer } from "./PaperViewer";
import { PaperTOC } from "./PaperTOC";
import { PaperExport } from "./PaperExport";
import { DigestTab } from "./DigestTab";
import { LiteratureTab } from "./LiteratureTab";
import { ReviewsTab } from "./ReviewsTab";
import { TranscriptTab } from "./TranscriptTab";
import { CodeTab } from "./CodeTab";
import { FiguresTab } from "./FiguresTab";
import { cn } from "@/lib/utils";

type TabId = "paper" | "digest" | "literature" | "reviews" | "transcript" | "code" | "figures";

interface TabDef {
  id: TabId;
  label: string;
  icon: LucideIcon;
  available: boolean;
}

interface ArtifactTabsProps {
  paper: PaperDetail;
  artifacts: PaperArtifactList;
}

export function ArtifactTabs({ paper, artifacts }: ArtifactTabsProps) {
  const tabs: TabDef[] = [
    { id: "paper", label: "Paper", icon: FileText, available: true },
    { id: "digest", label: "Digest", icon: Newspaper, available: artifacts.has_digest },
    { id: "literature", label: "Literature", icon: BookOpen, available: artifacts.has_literature },
    { id: "reviews", label: "Reviews", icon: MessageSquare, available: artifacts.has_reviews },
    { id: "transcript", label: "Transcript", icon: ScrollText, available: artifacts.has_transcript },
    { id: "code", label: "Code", icon: Code2, available: artifacts.has_experiments },
    { id: "figures", label: "Figures", icon: Image, available: artifacts.has_figures },
  ];

  const visibleTabs = tabs.filter((t) => t.available);
  const [activeTab, setActiveTab] = useState<TabId>("paper");

  return (
    <div>
      {/* Tab bar */}
      {visibleTabs.length > 1 && (
        <div className="flex border-b border-border mb-4">
          {visibleTabs.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-2 text-sm font-medium transition-colors",
                activeTab === id
                  ? "text-foreground border-b-2 border-indigo-500"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          ))}
        </div>
      )}

      {/* Tab content */}
      {activeTab === "paper" && (
        <div className="grid grid-cols-[200px_1fr] gap-6">
          <aside className="sticky top-0 self-start">
            <PaperTOC body={paper.body} />
            <div className="mt-4 border-t border-border pt-3">
              <PaperExport
                title={paper.title}
                body={paper.body}
                pdfUrl={paperPdfUrl(paper.paper_id)}
              />
            </div>
          </aside>
          <PaperViewer paper={paper} />
        </div>
      )}
      {activeTab === "digest" && <DigestTab paperId={paper.paper_id} />}
      {activeTab === "literature" && <LiteratureTab paperId={paper.paper_id} />}
      {activeTab === "reviews" && <ReviewsTab paperId={paper.paper_id} />}
      {activeTab === "transcript" && <TranscriptTab paperId={paper.paper_id} />}
      {activeTab === "code" && (
        <CodeTab paperId={paper.paper_id} files={artifacts.experiment_files} />
      )}
      {activeTab === "figures" && (
        <FiguresTab paperId={paper.paper_id} files={artifacts.figure_files} />
      )}
    </div>
  );
}
