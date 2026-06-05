import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import type { LiveDraft, DraftSection } from "@/stores/sessionStore";
import { cn } from "@/lib/utils";

interface DraftPanelProps {
  draft: LiveDraft;
}

function StatusDot({ status }: { status: string }) {
  if (status === "drafted") {
    return <span className="text-emerald-400 text-[11px]">✓</span>;
  }
  // drafting → pulsing indicator
  return (
    <span className="relative flex h-2 w-2">
      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400/70" />
      <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-400" />
    </span>
  );
}

function SectionCard({ section }: { section: DraftSection }) {
  const drafting = section.status !== "drafted";
  const [open, setOpen] = useState(false);
  return (
    <div
      className={cn(
        "rounded border px-2 py-1.5 transition-colors",
        drafting ? "border-amber-500/30 bg-amber-500/5" : "border-border/50 bg-muted/15"
      )}
    >
      <button
        onClick={() => !drafting && setOpen((o) => !o)}
        disabled={drafting}
        className="flex w-full items-center gap-2 text-left"
      >
        <StatusDot status={section.status} />
        <span className="text-[12px] font-medium text-foreground/90">{section.title}</span>
        {section.author && (
          <span className="text-[9px] text-muted-foreground/70 font-mono">{section.author}</span>
        )}
        <span className="ml-auto flex items-center gap-1.5">
          {drafting ? (
            <span className="text-[9px] text-amber-400 uppercase tracking-wide">writing…</span>
          ) : (
            <span className="text-[9px] tabular-nums text-muted-foreground/60">
              {section.charCount.toLocaleString()} ch
            </span>
          )}
          {!drafting && (
            <span className="text-[9px] text-muted-foreground/50">{open ? "▼" : "▶"}</span>
          )}
        </span>
      </button>
      {open && !drafting && (
        <div className="prose prose-invert prose-sm mt-2 max-w-none border-t border-border/40 pt-2 text-[12px] leading-relaxed prose-headings:text-sm prose-headings:font-semibold prose-p:my-1.5 prose-pre:text-[11px]">
          <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]}>{section.content}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}

export function DraftPanel({ draft }: DraftPanelProps) {
  const { sections } = draft;

  if (sections.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground/50 text-sm font-sans">
        <p>No draft yet</p>
        <p className="text-xs mt-1">Sections appear here as the team writes the paper</p>
      </div>
    );
  }

  const done = sections.filter((s) => s.status === "drafted").length;
  const totalChars = sections.reduce((n, s) => n + (s.status === "drafted" ? s.charCount : 0), 0);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center gap-1.5 px-2.5 py-1.5 border-b border-border/50 shrink-0">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
          Live Draft
        </span>
        <span className="text-[10px] tabular-nums text-muted-foreground/70">
          {done}/{sections.length} sections
        </span>
        <span className="ml-auto text-[10px] tabular-nums text-muted-foreground/60">
          {totalChars.toLocaleString()} chars
        </span>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {sections.map((s) => (
          <SectionCard key={s.section} section={s} />
        ))}
      </div>
    </div>
  );
}
