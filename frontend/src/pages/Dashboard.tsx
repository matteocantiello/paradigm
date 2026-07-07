import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCycles, useDeleteCycle, useResearchStats } from "@/hooks/useCycles";
import { usePapers } from "@/hooks/usePapers";
import { useLaunchCycle } from "@/hooks/useLaunchCycle";
import { CycleCard } from "@/components/research/CycleCard";
import { SetupWizard } from "@/components/research/SetupWizard";
import { DatasetPicker } from "@/components/research/DatasetPicker";
import { TopicBadges } from "@/components/shared/TopicBadges";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { isActiveStatus } from "@/lib/cycleStatus";
import type { PaperSummary } from "@/api/client";
import type { ReactNode } from "react";
import {
  ArrowRight,
  FileText,
  FlaskConical,
  Loader2,
  Radio,
  SlidersHorizontal,
  Sparkles,
  Zap,
} from "lucide-react";

const MIN_PROMPT_CHARS = 15;

function fmtCompact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(n >= 10_000 ? 0 : 1)}k`;
  return `${n}`;
}

function StatInline({ icon: Icon, value, label }: { icon: typeof Zap; value: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5 text-muted-foreground/80">
      <Icon className="h-3.5 w-3.5 text-primary/60" />
      <span className="font-mono text-sm text-foreground">{value}</span>
      <span className="text-xs">{label}</span>
    </span>
  );
}

function PaperRow({ paper }: { paper: PaperSummary }) {
  const navigate = useNavigate();
  return (
    <button
      onClick={() => navigate(`/papers?paper=${paper.paper_id}`)}
      className="group flex w-full items-center gap-3 rounded-lg border border-border/50 bg-card/60 px-4 py-3 text-left backdrop-blur-sm transition-all hover:border-primary/40 hover:bg-card"
    >
      <FileText className="h-4 w-4 shrink-0 text-primary/60" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">{paper.title}</p>
        <TopicBadges topics={paper.topics} size="xs" className="mt-1" />
      </div>
      <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground/40 transition-colors group-hover:text-primary" />
    </button>
  );
}

function SectionHeading({ children }: { children: ReactNode }) {
  return (
    <h2 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.1em] text-muted-foreground">
      <div className="h-px flex-1 bg-border" />
      {children}
      <div className="h-px flex-1 bg-border" />
    </h2>
  );
}

/** The prompt-first hero console: type a question, attach data, launch. */
function HeroConsole({
  onConfigure,
}: {
  onConfigure: (prompt: string, files: File[]) => void;
}) {
  const [prompt, setPrompt] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const { launch, stage, error, busy, uploadIndex, isRetry } = useLaunchCycle();

  const ready = prompt.trim().length >= MIN_PROMPT_CHARS;

  const handleLaunch = () => {
    if (!ready || busy) return;
    void launch({ prompt, files });
  };

  const stageLabel =
    stage === "creating"
      ? "Creating…"
      : stage === "uploading"
        ? `Uploading ${uploadIndex + 1}/${files.length}…`
        : stage === "starting"
          ? "Starting…"
          : null;

  return (
    <div className="mx-auto max-w-2xl">
      <div className="rounded-2xl border border-border/60 bg-card/70 p-4 backdrop-blur-sm panel-edge transition-all focus-within:border-primary/40 focus-within:glow-gold">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              handleLaunch();
            }
          }}
          placeholder="Pose a research question — the more specific, the better…"
          maxLength={10000}
          rows={3}
          className="w-full resize-none bg-transparent text-[15px] leading-relaxed placeholder:text-muted-foreground/40 focus:outline-none"
        />
        <div className="mt-2 flex flex-wrap items-end justify-between gap-2 border-t border-border/40 pt-3">
          <DatasetPicker files={files} onChange={setFiles} compact disabled={busy} />
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={() => onConfigure(prompt, files)}
              disabled={busy}
              className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-xs font-medium text-muted-foreground hover:border-primary/40 hover:text-foreground disabled:opacity-40 transition-all"
              title="Mode, team & supervision"
            >
              <SlidersHorizontal className="h-3.5 w-3.5" />
              Configure
            </button>
            <button
              type="button"
              onClick={handleLaunch}
              disabled={!ready || busy}
              className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-primary to-primary/80 px-4 py-2 text-sm font-semibold text-primary-foreground hover:shadow-lg hover:shadow-primary/20 disabled:opacity-40 transition-all"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              {stageLabel ?? (error && isRetry ? "Retry" : "Launch")}
            </button>
          </div>
        </div>
      </div>
      {error ? (
        <p className="mt-2 rounded-lg bg-red-500/10 p-2.5 text-center text-xs text-red-400">
          {error}
          {isRetry && " — Retry resumes the created cycle."}
        </p>
      ) : (
        <p className="mt-2 text-center font-mono text-[10px] uppercase tracking-[0.15em] text-muted-foreground/50">
          ⌘↵ to launch · Configure for mode, team & interactive supervision
        </p>
      )}
    </div>
  );
}

export function Dashboard() {
  const navigate = useNavigate();
  const [wizard, setWizard] = useState<{ prompt: string; files: File[] } | null>(null);
  const { data: cyclesData } = useCycles(0, 20);
  const { data: stats } = useResearchStats();
  const { data: papersData, isLoading: papersLoading } = usePapers("published", 0, 5);
  const deleteCycle = useDeleteCycle();

  const running = (cyclesData?.items ?? []).filter((c) => isActiveStatus(c.status));
  const papers = papersData?.items ?? [];

  return (
    <div className="mx-auto max-w-5xl space-y-10 stagger">
      {/* Hero — the question comes first. */}
      <section className="pt-6 text-center" style={{ "--i": 0 } as React.CSSProperties}>
        <p className="font-mono text-[11px] uppercase tracking-[0.35em] text-primary/70">
          ✦ Paradigm Observatory
        </p>
        <h1 className="mt-3 font-display text-[38px] font-semibold leading-tight tracking-tight bg-gradient-to-br from-foreground via-foreground to-primary/70 bg-clip-text text-transparent">
          What should we investigate?
        </h1>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-relaxed text-muted-foreground">
          A team of AI scientists will survey the literature, run experiments in a
          sandbox, and write a paper that faces peer review.
        </p>
        <div className="mt-6">
          <HeroConsole onConfigure={(prompt, files) => setWizard({ prompt, files })} />
        </div>
      </section>

      {/* Observatory ledger — one quiet line. */}
      <div
        className="flex items-center justify-center gap-6"
        style={{ "--i": 1 } as React.CSSProperties}
      >
        <StatInline icon={FlaskConical} value={fmtCompact(stats?.total_cycles ?? 0)} label="cycles" />
        <span className="h-3 w-px bg-border" />
        <StatInline icon={FileText} value={fmtCompact(stats?.papers_published ?? 0)} label="papers" />
        <span className="h-3 w-px bg-border" />
        <StatInline icon={Zap} value={fmtCompact(stats?.total_tokens ?? 0)} label="tokens" />
      </div>

      {/* Running now — the live work. */}
      <section style={{ "--i": 2 } as React.CSSProperties}>
        <SectionHeading>
          <span className="flex items-center gap-1.5">
            {running.length > 0 && (
              <Radio className="h-3.5 w-3.5 animate-pulse text-emerald-400" />
            )}
            Running now{running.length > 0 ? ` (${running.length})` : ""}
          </span>
        </SectionHeading>
        {running.length === 0 ? (
          <p className="px-1 py-2 text-center text-sm text-muted-foreground/70">
            Nothing running right now — the observatory is quiet.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {running.map((cycle) => (
              <CycleCard key={cycle.cycle_id} cycle={cycle} onDelete={(id) => deleteCycle.mutate(id)} />
            ))}
          </div>
        )}
      </section>

      {/* Latest papers — what came out. */}
      <section style={{ "--i": 3 } as React.CSSProperties}>
        <SectionHeading>Latest papers</SectionHeading>
        {papersLoading ? (
          <div className="flex justify-center py-8">
            <LoadingSpinner />
          </div>
        ) : papers.length === 0 ? (
          <p className="px-1 py-2 text-center text-sm text-muted-foreground/70">
            No published papers yet — they&apos;ll appear here as cycles finish.
          </p>
        ) : (
          <div className="space-y-2">
            {papers.map((paper) => (
              <PaperRow key={paper.paper_id} paper={paper} />
            ))}
            <button
              onClick={() => navigate("/papers")}
              className="mt-1 flex items-center gap-1 px-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              All papers
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </section>

      {wizard && (
        <SetupWizard
          onClose={() => setWizard(null)}
          initialPrompt={wizard.prompt}
          initialFiles={wizard.files}
        />
      )}
    </div>
  );
}
