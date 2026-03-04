import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import remarkGfm from "remark-gfm";
import rehypeKatex from "rehype-katex";
import type { PaperDetail } from "@/api/client";
import { StatusBadge } from "@/components/shared/StatusBadge";

function toSlug(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-");
}

function headingWithId(level: number) {
  const Tag = `h${level}` as const;
  return function HeadingComponent({ children }: { children?: ReactNode }) {
    const text = typeof children === "string" ? children : String(children ?? "");
    return <Tag id={toSlug(text)}>{children}</Tag>;
  };
}

interface PaperViewerProps {
  paper: PaperDetail;
}

export function PaperViewer({ paper }: PaperViewerProps) {
  return (
    <article className="max-w-none">
      {/* Title and metadata */}
      <div className="mb-6">
        <div className="flex items-start justify-between gap-3 mb-2">
          <h1 className="text-2xl font-bold">{paper.title}</h1>
          <StatusBadge status={paper.status} />
        </div>
        {paper.authors.length > 0 && (
          <p className="text-sm text-muted-foreground mb-2">
            {paper.authors.join(", ")}
          </p>
        )}
        {paper.keywords.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-3">
            {paper.keywords.map((kw) => (
              <span
                key={kw}
                className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
              >
                {kw}
              </span>
            ))}
          </div>
        )}
        {paper.abstract && (
          <div className="rounded-md border border-border bg-muted/30 p-4">
            <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1">
              Abstract
            </h3>
            <p className="text-sm leading-relaxed">{paper.abstract}</p>
          </div>
        )}
      </div>

      {/* Body */}
      <div className="prose-paper">
        <ReactMarkdown
          remarkPlugins={[remarkMath, remarkGfm]}
          rehypePlugins={[rehypeKatex]}
          components={{ h2: headingWithId(2), h3: headingWithId(3) }}
        >
          {paper.body}
        </ReactMarkdown>
      </div>

      {/* Citations */}
      {paper.citations.length > 0 && (
        <div className="mt-8 border-t border-border pt-4">
          <h3 className="text-sm font-medium mb-2">References</h3>
          <ol className="list-decimal pl-5 text-xs text-muted-foreground space-y-1">
            {paper.citations.map((cite, i) => (
              <li key={i}>{cite}</li>
            ))}
          </ol>
        </div>
      )}
    </article>
  );
}
