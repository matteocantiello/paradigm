import { useState } from "react";
import { TopicBadges } from "@/components/shared/TopicBadges";
import { GeneratedCover } from "./GeneratedCover";
import { paperFigureUrl } from "@/api/client";
import { cn, truncate } from "@/lib/utils";
import type { PaperSummary } from "@/api/client";
import { ArrowRight, Gauge } from "lucide-react";

interface PaperCardProps {
  paper: PaperSummary;
  onClick: () => void;
}

/** Compact quality-ledger badge: the judge's composite (1-10). */
export function JudgeBadge({
  scores,
  className,
}: {
  scores?: Record<string, number | string> | null;
  className?: string;
}) {
  const composite = scores?.composite;
  if (typeof composite !== "number") return null;
  const tone =
    composite >= 7
      ? "text-emerald-300 bg-emerald-500/15"
      : composite >= 5
        ? "text-amber-300 bg-amber-500/15"
        : "text-red-300 bg-red-500/15";
  const title = ["novelty", "rigor", "clarity", "significance", "honesty"]
    .map((k) => `${k} ${scores?.[k] ?? "?"}`)
    .join(" · ");
  return (
    <span
      className={cn(
        "flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 font-mono text-[10px]",
        tone,
        className
      )}
      title={`Judge: ${title}`}
    >
      <Gauge className="h-3 w-3" />
      {composite.toFixed(1)}
    </span>
  );
}

// Cover-overlay status pill — translucent so it reads over figure or generated art.
const STATUS_TONE: Record<string, string> = {
  published: "text-emerald-200 bg-emerald-500/25 border-emerald-300/30",
  submitted: "text-purple-200 bg-purple-500/25 border-purple-300/30",
  rejected: "text-red-200 bg-red-500/25 border-red-300/30",
  review_rejected: "text-red-200 bg-red-500/25 border-red-300/30",
  writing_incomplete: "text-red-200 bg-red-500/25 border-red-300/30",
  execution_failed: "text-orange-200 bg-orange-500/25 border-orange-300/30",
  revision_exhausted: "text-amber-200 bg-amber-500/25 border-amber-300/30",
  interrupted: "text-amber-200 bg-amber-500/25 border-amber-300/30",
};

function StatusPill({ status }: { status: string }) {
  const tone = STATUS_TONE[status] ?? "text-slate-200 bg-slate-500/25 border-slate-300/25";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium capitalize backdrop-blur-md",
        tone
      )}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

export function PaperCard({ paper, onClick }: PaperCardProps) {
  const [figFailed, setFigFailed] = useState(false);
  const primaryTopic = (paper.topics ?? []).filter(Boolean)[0];
  const date = paper.published_at ?? paper.created_at;
  const showFigure = Boolean(paper.hero_figure) && !figFailed;

  return (
    <button
      onClick={onClick}
      className="group flex w-full flex-col overflow-hidden rounded-xl border border-border/50 bg-card/80 text-left backdrop-blur-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:bg-card hover:shadow-xl hover:shadow-primary/10"
    >
      {/* Cover band — figure hero when the paper has one, else generated art. */}
      <div className="relative aspect-[16/9] w-full overflow-hidden bg-[#0b0e1c]">
        {showFigure ? (
          <img
            src={paperFigureUrl(paper.paper_id, paper.hero_figure!)}
            alt=""
            loading="lazy"
            onError={() => setFigFailed(true)}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
          />
        ) : (
          <div className="h-full w-full transition-transform duration-300 group-hover:scale-[1.03]">
            <GeneratedCover seed={paper.paper_id} topic={primaryTopic} />
          </div>
        )}
        {/* Bottom scrim keeps overlays legible over busy figures. */}
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/45 via-transparent to-black/25" />
        <div className="absolute left-2.5 top-2.5">
          <StatusPill status={paper.status} />
        </div>
        <div className="absolute right-2.5 top-2.5">
          <JudgeBadge scores={paper.judge_scores} className="backdrop-blur-md" />
        </div>
      </div>

      {/* Body */}
      <div className="flex flex-1 flex-col gap-2 p-4">
        <TopicBadges topics={paper.topics} size="xs" />
        <h3 className="font-display text-base leading-snug text-foreground line-clamp-2 group-hover:text-primary">
          {paper.title}
        </h3>
        {paper.abstract && (
          <p className="text-xs leading-relaxed text-muted-foreground line-clamp-3">
            {truncate(paper.abstract, 200)}
          </p>
        )}
        <div className="mt-auto flex items-center justify-between pt-1 font-mono text-[11px] text-muted-foreground">
          <span>{date ? new Date(date).toLocaleDateString() : ""}</span>
          <span className="inline-flex items-center gap-1 text-muted-foreground/50 transition-colors group-hover:text-primary">
            Open <ArrowRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5" />
          </span>
        </div>
      </div>
    </button>
  );
}
