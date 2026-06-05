import { memo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { cn } from "@/lib/utils";

/**
 * Shared markdown renderer for agent output. Agents emit GitHub-flavored
 * markdown with LaTeX math (per SPEC), so we give it real structure —
 * headings, lists, code, tables, blockquotes, and KaTeX — styled for the
 * "Observatory" dark theme. Tailwind's typography plugin isn't installed, so
 * every element is styled explicitly here (Tailwind preflight otherwise resets
 * headings/lists to look like plain text).
 *
 * `throwOnError: false` keeps half-typed math during streaming from crashing
 * the render — KaTeX shows the partial expression instead of throwing.
 */
const COMPONENTS: Components = {
  h1: ({ node: _n, ...p }) => (
    <h1 className="mt-3 mb-1.5 font-serif text-[15px] font-semibold text-foreground first:mt-0" {...p} />
  ),
  h2: ({ node: _n, ...p }) => (
    <h2 className="mt-3 mb-1.5 text-[14px] font-semibold text-foreground first:mt-0" {...p} />
  ),
  h3: ({ node: _n, ...p }) => (
    <h3 className="mt-2.5 mb-1 text-[13px] font-semibold text-foreground/90 first:mt-0" {...p} />
  ),
  h4: ({ node: _n, ...p }) => (
    <h4 className="mt-2 mb-1 text-[12px] font-semibold uppercase tracking-wide text-muted-foreground first:mt-0" {...p} />
  ),
  p: ({ node: _n, ...p }) => (
    <p className="my-1.5 leading-relaxed text-foreground/85 first:mt-0 last:mb-0" {...p} />
  ),
  ul: ({ node: _n, ...p }) => (
    <ul className="my-1.5 ml-4 list-disc space-y-1 marker:text-muted-foreground/60" {...p} />
  ),
  ol: ({ node: _n, ...p }) => (
    <ol className="my-1.5 ml-4 list-decimal space-y-1 marker:text-muted-foreground/50" {...p} />
  ),
  li: ({ node: _n, ...p }) => <li className="leading-relaxed text-foreground/85 [&>p]:my-0.5" {...p} />,
  strong: ({ node: _n, ...p }) => <strong className="font-semibold text-foreground" {...p} />,
  em: ({ node: _n, ...p }) => <em className="italic text-foreground/90" {...p} />,
  a: ({ node: _n, ...p }) => (
    <a
      className="text-cyan-400 underline decoration-cyan-400/40 underline-offset-2 hover:decoration-cyan-400"
      target="_blank"
      rel="noreferrer"
      {...p}
    />
  ),
  blockquote: ({ node: _n, ...p }) => (
    <blockquote className="my-2 border-l-2 border-primary/40 pl-3 italic text-foreground/70" {...p} />
  ),
  hr: () => <hr className="my-3 border-border/60" />,
  code: ({ node: _n, className, children, ...p }) => {
    const isBlock = /language-/.test(className || "") || String(children).includes("\n");
    if (!isBlock) {
      return (
        <code
          className="rounded bg-muted/60 px-1 py-0.5 font-mono text-[0.85em] text-amber-200/90"
          {...p}
        >
          {children}
        </code>
      );
    }
    return (
      <code className={cn("font-mono", className)} {...p}>
        {children}
      </code>
    );
  },
  pre: ({ node: _n, ...p }) => (
    <pre
      className="my-2 overflow-x-auto rounded-lg border border-border/60 bg-[#0b0d18] p-3 text-[11px] leading-relaxed"
      {...p}
    />
  ),
  table: ({ node: _n, ...p }) => (
    <div className="my-2 overflow-x-auto">
      <table className="w-full border-collapse text-[11px]" {...p} />
    </div>
  ),
  thead: ({ node: _n, ...p }) => <thead className="border-b border-border" {...p} />,
  th: ({ node: _n, ...p }) => (
    <th className="px-2 py-1 text-left font-semibold text-foreground/90" {...p} />
  ),
  td: ({ node: _n, ...p }) => (
    <td className="border-t border-border/40 px-2 py-1 align-top text-foreground/80" {...p} />
  ),
};

function MarkdownImpl({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("min-w-0 break-words", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false }]]}
        components={COMPONENTS}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}

/**
 * Memoized: re-parses only when the markdown source changes. Critical for the
 * live message stream — the panel re-renders ~2×/s while streaming, but settled
 * messages keep the same `children` string and skip re-parsing entirely.
 */
export const Markdown = memo(MarkdownImpl);
