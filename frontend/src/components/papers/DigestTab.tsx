import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Newspaper } from "lucide-react";
import { usePaperDigest } from "@/hooks/usePapers";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { EmptyState } from "@/components/shared/EmptyState";

interface DigestTabProps {
  paperId: string;
}

export function DigestTab({ paperId }: DigestTabProps) {
  const { data: digest, isLoading } = usePaperDigest(paperId);

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <LoadingSpinner />
      </div>
    );
  }

  if (!digest?.content) {
    return (
      <EmptyState
        icon={Newspaper}
        title="No digest"
        description="No plain-language summary is available for this paper."
      />
    );
  }

  return (
    <div className="max-w-3xl">
      <p className="mb-4 text-sm text-muted-foreground">
        A plain-language summary of this paper for non-specialists.
      </p>
      <div className="prose-paper">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{digest.content}</ReactMarkdown>
      </div>
    </div>
  );
}
