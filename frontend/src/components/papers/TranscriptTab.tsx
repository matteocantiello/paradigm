import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ScrollText } from "lucide-react";
import { usePaperTranscript } from "@/hooks/usePapers";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { EmptyState } from "@/components/shared/EmptyState";

interface TranscriptTabProps {
  paperId: string;
}

export function TranscriptTab({ paperId }: TranscriptTabProps) {
  const { data: transcript, isLoading } = usePaperTranscript(paperId);

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <LoadingSpinner />
      </div>
    );
  }

  if (!transcript?.content) {
    return (
      <EmptyState
        icon={ScrollText}
        title="No transcript"
        description="No conversation transcript is available for this paper."
      />
    );
  }

  return (
    <div className="max-w-3xl prose-paper">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {transcript.content}
      </ReactMarkdown>
    </div>
  );
}
