import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { MessageSquare } from "lucide-react";
import { usePaperReviews } from "@/hooks/usePapers";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { EmptyState } from "@/components/shared/EmptyState";

interface ReviewsTabProps {
  paperId: string;
}

export function ReviewsTab({ paperId }: ReviewsTabProps) {
  const { data: reviews, isLoading } = usePaperReviews(paperId);

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <LoadingSpinner />
      </div>
    );
  }

  if (!reviews?.content) {
    return (
      <EmptyState
        icon={MessageSquare}
        title="No reviews"
        description="No review data is available for this paper."
      />
    );
  }

  return (
    <div className="max-w-3xl prose-paper">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {reviews.content}
      </ReactMarkdown>
    </div>
  );
}
