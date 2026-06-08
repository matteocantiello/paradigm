import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useCycles, useDeleteCycle, useResearchStats } from "@/hooks/useCycles";
import { usePapers } from "@/hooks/usePapers";
import { CycleCard } from "@/components/research/CycleCard";
import { SetupWizard } from "@/components/research/SetupWizard";
import { TopicBadges } from "@/components/shared/TopicBadges";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { isActiveStatus } from "@/lib/cycleStatus";
import type { PaperSummary } from "@/api/client";
import { Plus, Radio, FlaskConical, FileText, Zap, ArrowRight } from "lucide-react";

function fmtCompact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(n >= 10_000 ? 0 : 1)}k`;
  return `${n}`;
}

function StatTile({ icon: Icon, value, label }: { icon: typeof Zap; value: string; label: string }) {
  return (
    <div className="rounded-xl border border-border/60 bg-card/60 p-4 backdrop-blur-sm">
      <div className="flex items-center gap-2 text-muted-foreground/70">
        <Icon className="h-4 w-4 text-primary/70" />
        <span className="text-[11px] font-medium uppercase tracking-[0.12em]">{label}</span>
      </div>
      <div className="mt-2 font-display text-3xl font-semibold leading-none tracking-tight text-foreground">
        {value}
      </div>
    </div>
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

export function Dashboard() {
  const navigate = useNavigate();
  const [showWizard, setShowWizard] = useState(false);
  const { data: cyclesData } = useCycles(0, 20);
  const { data: stats } = useResearchStats();
  const { data: papersData, isLoading: papersLoading } = usePapers("published", 0, 5);
  const deleteCycle = useDeleteCycle();

  const running = (cyclesData?.items ?? []).filter((c) => isActiveStatus(c.status));
  const papers = papersData?.items ?? [];

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      {/* Header + the one true call to action. */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-[30px] font-semibold leading-none tracking-tight bg-gradient-to-br from-foreground via-foreground to-primary/70 bg-clip-text text-transparent">
            Mission Control
          </h1>
          <p className="mt-2 font-mono text-[11px] uppercase tracking-[0.2em] text-muted-foreground/80">
            what&apos;s running · what came out
          </p>
        </div>
        <button
          onClick={() => setShowWizard(true)}
          className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-primary to-primary/80 px-4 py-2 text-sm font-medium text-primary-foreground transition-all hover:shadow-lg hover:shadow-primary/20"
        >
          <Plus className="h-4 w-4" />
          New Research
        </button>
      </div>

      {/* Headline stats. */}
      <div className="grid grid-cols-3 gap-4">
        <StatTile icon={FlaskConical} value={fmtCompact(stats?.total_cycles ?? 0)} label="Cycles run" />
        <StatTile icon={FileText} value={fmtCompact(stats?.papers_published ?? 0)} label="Papers published" />
        <StatTile icon={Zap} value={fmtCompact(stats?.total_tokens ?? 0)} label="Tokens used" />
      </div>

      {/* Running now — the live work. */}
      <section>
        <SectionHeading>
          <span className="flex items-center gap-1.5">
            {running.length > 0 && (
              <Radio className="h-3.5 w-3.5 animate-pulse text-emerald-400" />
            )}
            Running now{running.length > 0 ? ` (${running.length})` : ""}
          </span>
        </SectionHeading>
        {running.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border/60 px-4 py-8 text-center">
            <p className="text-sm text-muted-foreground">Nothing running right now.</p>
            <button
              onClick={() => setShowWizard(true)}
              className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-primary/40 px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/10"
            >
              <Plus className="h-3.5 w-3.5" />
              Start a research cycle
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {running.map((cycle) => (
              <CycleCard key={cycle.cycle_id} cycle={cycle} onDelete={(id) => deleteCycle.mutate(id)} />
            ))}
          </div>
        )}
      </section>

      {/* Latest papers — what came out. */}
      <section>
        <SectionHeading>Latest papers</SectionHeading>
        {papersLoading ? (
          <div className="flex justify-center py-8">
            <LoadingSpinner />
          </div>
        ) : papers.length === 0 ? (
          <p className="px-1 py-4 text-sm text-muted-foreground/70">
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

      {showWizard && <SetupWizard onClose={() => setShowWizard(false)} />}
    </div>
  );
}
