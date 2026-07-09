import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import remarkGfm from "remark-gfm";
import rehypeKatex from "rehype-katex";
import type { PaperDetail } from "@/api/client";
import { paperFigureUrl } from "@/api/client";
import { splitPaperFrontMatter } from "@/lib/paperFrontMatter";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { TopicBadges } from "@/components/shared/TopicBadges";

function toSlug(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-");
}

// The paper body embeds figures as `![Figure N](figures/<name>)` — a relative
// path that the browser can't resolve. Rewrite it to the backend figure endpoint.
function resolveFigureSrc(paperId: string, src?: string): string | undefined {
  if (!src) return src;
  if (/^(https?:|data:)/i.test(src)) return src; // already absolute / inline
  const marker = "figures/";
  const idx = src.lastIndexOf(marker);
  const name = idx >= 0 ? src.slice(idx + marker.length) : src.replace(/^\.?\//, "");
  return paperFigureUrl(paperId, name);
}

function makeFigureImg(paperId: string) {
  return function FigureImg({ src, alt }: { src?: string; alt?: string }) {
    return (
      <img
        src={resolveFigureSrc(paperId, src)}
        alt={alt ?? ""}
        loading="lazy"
        className="mx-auto my-4 max-w-full rounded-md border border-border"
      />
    );
  };
}

function headingWithId(level: number) {
  const Tag = `h${level}` as "h1" | "h2" | "h3" | "h4" | "h5" | "h6";
  return function HeadingComponent({ children }: { children?: ReactNode }) {
    const text = typeof children === "string" ? children : String(children ?? "");
    return <Tag id={toSlug(text)}>{children}</Tag>;
  };
}

interface PaperViewerProps {
  paper: PaperDetail;
}

export function PaperViewer({ paper }: PaperViewerProps) {
  // Dedupe the body's own title/abstract against the styled header — and
  // prefer the body's abstract (the DB column is truncated at 1000 chars).
  const front = splitPaperFrontMatter(paper.body);
  const abstract = front.abstract || paper.abstract;
  return (
    <article className="max-w-none">
      {/* Title and metadata */}
      <div className="mb-6">
        <div className="flex items-start justify-between gap-3 mb-2">
          <h1 className="text-2xl font-bold">{front.title || paper.title}</h1>
          <StatusBadge status={paper.status} />
        </div>
        {paper.authors.length > 0 && (
          <p className="text-sm text-muted-foreground mb-2">
            {paper.authors.join(", ")}
          </p>
        )}
        <TopicBadges topics={paper.topics} className="mb-3" />
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
        {abstract && (
          <div className="rounded-md border border-border bg-muted/30 p-4">
            <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1">
              Abstract
            </h3>
            <div className="text-sm leading-relaxed [&_p]:mb-2 last:[&_p]:mb-0">
              <ReactMarkdown remarkPlugins={[remarkMath, remarkGfm]} rehypePlugins={[rehypeKatex]}>
                {abstract}
              </ReactMarkdown>
            </div>
          </div>
        )}
      </div>

      {/* Body — front matter stripped (it renders in the styled header above) */}
      <div className="prose-paper">
        <ReactMarkdown
          remarkPlugins={[remarkMath, remarkGfm]}
          rehypePlugins={[rehypeKatex]}
          components={{
            h2: headingWithId(2),
            h3: headingWithId(3),
            img: makeFigureImg(paper.paper_id),
          }}
        >
          {front.rest}
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
