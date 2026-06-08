import { useNavigate } from "react-router-dom";
import {
  Lightbulb,
  ListChecks,
  FlaskConical,
  PenLine,
  ClipboardCheck,
  BookOpen,
  Bot,
  ShieldCheck,
  Quote,
  ArrowRight,
  Plus,
} from "lucide-react";

// The aperture-rings + orbiting-star mark from the sidebar, scaled up for the hero.
function ObservatoryMark() {
  return (
    <div className="relative h-16 w-16 flex items-center justify-center shrink-0">
      <div className="absolute inset-0 rounded-full border-2 border-primary/60 glow-sm" />
      <div className="absolute inset-3 rounded-full border border-primary/40" />
      <div className="h-3 w-3 rounded-full bg-primary" />
      <div className="absolute h-1.5 w-1.5 rounded-full bg-accent-cyan top-1 right-2 animate-breathe" />
    </div>
  );
}

const PIPELINE = [
  { icon: Lightbulb, label: "Hypothesize" },
  { icon: ListChecks, label: "Plan" },
  { icon: FlaskConical, label: "Experiment" },
  { icon: PenLine, label: "Write" },
  { icon: ClipboardCheck, label: "Peer review" },
  { icon: BookOpen, label: "Publish" },
];

const STEPS = [
  {
    icon: Plus,
    title: "Start a research cycle",
    body: 'Hit "New Research" and give it a precise question ("directed") or a broad topic to explore. That seed is all it needs.',
  },
  {
    icon: Bot,
    title: "Watch the team work",
    body: "The live view streams each phase — agents proposing ideas, debating, running experiments, and drafting — as it happens.",
  },
  {
    icon: BookOpen,
    title: "Get a peer-reviewed paper",
    body: "The team writes a paper and puts it through review. Accepted papers are published; others come back with referee feedback.",
  },
  {
    icon: FlaskConical,
    title: "Explore & tune",
    body: "Browse published papers, swap the models behind each agent role, and adjust how runs behave — all from the GUI.",
  },
];

export function AboutPage() {
  const navigate = useNavigate();
  return (
    <div className="mx-auto max-w-3xl space-y-12 pb-16">
      {/* Hero */}
      <header className="flex flex-col items-center gap-5 pt-6 text-center">
        <ObservatoryMark />
        <div>
          <h1 className="font-display text-4xl font-semibold tracking-tight bg-gradient-to-br from-foreground via-foreground to-primary/70 bg-clip-text text-transparent">
            Paradigm
          </h1>
          <p className="mt-2 font-mono text-[11px] uppercase tracking-[0.24em] text-muted-foreground/70">
            an observatory for autonomous research
          </p>
        </div>
        <p className="max-w-2xl text-balance text-[15px] leading-relaxed text-muted-foreground">
          Paradigm is a platform where a team of AI agents does science the way a
          research group does — they form hypotheses, run real experiments, write
          up what they find, and put it through peer review. You give it a question;
          it gives you back a paper, with every claim traceable to an experiment or a
          citation.
        </p>
        <button
          onClick={() => navigate("/research?new=1")}
          className="mt-1 flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-primary to-primary/80 px-4 py-2 text-sm font-medium text-primary-foreground transition-all hover:shadow-lg hover:shadow-primary/20"
        >
          <Plus className="h-4 w-4" />
          Start a research cycle
        </button>
      </header>

      {/* The goal */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-[0.1em] text-primary/80">
          The idea
        </h2>
        <p className="text-[15px] leading-relaxed text-foreground/90">
          Most of the work in science is patient and cumulative — surveying the
          literature, forming a testable idea, running the analysis, and arguing
          about what it means. Paradigm&apos;s goal is to run that whole loop
          autonomously and transparently, so you can point it at a question and watch
          rigorous research happen end to end — not a chatbot&apos;s opinion, but
          experiments, evidence, and a reviewed result.
        </p>
      </section>

      {/* How it works */}
      <section className="space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-[0.1em] text-primary/80">
          How it works
        </h2>
        {/* Pipeline strip */}
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border/60 bg-card/50 p-4">
          {PIPELINE.map(({ icon: Icon, label }, i) => (
            <div key={label} className="flex items-center gap-2">
              <div className="flex items-center gap-2 rounded-lg bg-muted/40 px-3 py-1.5">
                <Icon className="h-4 w-4 text-primary/70" />
                <span className="text-xs font-medium text-foreground/90">{label}</span>
              </div>
              {i < PIPELINE.length - 1 && (
                <ArrowRight className="h-3.5 w-3.5 text-muted-foreground/40" />
              )}
            </div>
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-border/60 bg-card/50 p-4">
            <div className="mb-1.5 flex items-center gap-2 text-foreground">
              <Bot className="h-4 w-4 text-primary/70" />
              <span className="text-sm font-semibold">A team of specialists</span>
            </div>
            <p className="text-[13px] leading-relaxed text-muted-foreground">
              A deterministic orchestrator coordinates agents that each play a role —
              a theorist proposes hypotheses, an experimentalist writes and runs real
              code, a skeptic pushes back, a writer drafts, and reviewers referee.
              They collaborate and debate, rather than a single model talking to
              itself.
            </p>
          </div>
          <div className="rounded-xl border border-border/60 bg-card/50 p-4">
            <div className="mb-1.5 flex items-center gap-2 text-foreground">
              <ShieldCheck className="h-4 w-4 text-primary/70" />
              <span className="text-sm font-semibold">Grounded &amp; reproducible</span>
            </div>
            <p className="text-[13px] leading-relaxed text-muted-foreground">
              Experiments run as actual code in an isolated sandbox, producing real
              figures and numbers. Every quantitative claim must trace back to an
              experiment or a cited paper — and the final paper only ships if it
              passes peer review.
            </p>
          </div>
        </div>
      </section>

      {/* How to use it */}
      <section className="space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-[0.1em] text-primary/80">
          Using it
        </h2>
        <ol className="space-y-3">
          {STEPS.map(({ icon: Icon, title, body }, i) => (
            <li key={title} className="flex gap-4 rounded-xl border border-border/50 bg-card/40 p-4">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 font-mono text-sm font-semibold text-primary">
                {i + 1}
              </div>
              <div className="min-w-0">
                <div className="mb-0.5 flex items-center gap-2">
                  <Icon className="h-4 w-4 text-primary/70" />
                  <span className="text-sm font-semibold text-foreground">{title}</span>
                </div>
                <p className="text-[13px] leading-relaxed text-muted-foreground">{body}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {/* The name */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-[0.1em] text-primary/80">
          Why &ldquo;Paradigm&rdquo;
        </h2>
        <div className="relative rounded-xl border border-border/60 bg-gradient-to-br from-card/60 to-primary/[0.04] p-5">
          <Quote className="absolute right-4 top-4 h-5 w-5 text-primary/20" />
          <p className="text-[14px] leading-relaxed text-foreground/90">
            The name comes from Thomas Kuhn&apos;s{" "}
            <em>The Structure of Scientific Revolutions</em> (1962). For Kuhn, a{" "}
            <strong className="font-semibold text-foreground">paradigm</strong> is the
            shared framework of theories, methods, and assumptions a scientific
            community works within — and a{" "}
            <strong className="font-semibold text-foreground">paradigm shift</strong>{" "}
            is the rare, upending moment when accumulated anomalies force that
            framework to change.
          </p>
          <p className="mt-3 text-[14px] leading-relaxed text-muted-foreground">
            Those shifts are rare because the work between them — reading, testing,
            arguing — moves at human speed. Paradigm builds on Kuhn&apos;s picture with
            a bolder aim: run that work autonomously and in parallel, and the distance
            from anomaly to insight starts to collapse.{" "}
            <span className="font-medium text-foreground">
              The point isn&apos;t to wait for the next scientific revolution — it&apos;s
              to make them happen faster.
            </span>
          </p>
        </div>
      </section>
    </div>
  );
}
