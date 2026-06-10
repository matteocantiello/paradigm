import { getSessionEventStream, sessionArtifactUrl } from "@/api/client";
import { LiteratureConstellation } from "@/components/session/LiteratureGraph";
import { KnowledgeGraph } from "@/components/session/KnowledgeGraph";
import { buildKnowledgeGraph } from "@/lib/knowledgeGraph";
import {
  ReplayExperiments,
  ReplayHypotheses,
  ReplayPaper,
  ReplayStatusBar,
  ReplayTicker,
} from "@/components/replay/ReplayPanels";
import { ReplayScrubber } from "@/components/replay/ReplayScrubber";
import { buildLitGraph } from "@/lib/litGraph";
import { usePlayback, useReplayState } from "@/lib/replay/engine";
import type { Ev } from "@/lib/replay/types";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

type Tab = "literature" | "knowledge" | "hypotheses" | "experiments" | "paper" | "events";

export default function ReplayPage() {
  const { id: sessionId } = useParams<{ id: string }>();
  const [events, setEvents] = useState<Ev[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("literature");

  useEffect(() => {
    if (!sessionId) return;
    setEvents(null);
    setError(null);
    getSessionEventStream(sessionId)
      .then((r) => {
        const evs = (r.events as unknown as Ev[]).slice().sort((a, b) => a.seq - b.seq);
        setEvents(evs);
      })
      .catch((e) => setError(String(e)));
  }, [sessionId]);

  const loaded = events ?? [];
  const playback = usePlayback(loaded);
  const state = useReplayState(loaded, playback.cursor);
  const litGraph = useMemo(
    () => buildLitGraph(loaded.slice(0, playback.cursor) as never),
    [loaded, playback.cursor],
  );
  const knowGraph = useMemo(
    () => buildKnowledgeGraph(loaded.slice(0, playback.cursor) as never),
    [loaded, playback.cursor],
  );

  const counts: Record<Tab, number> = {
    literature: litGraph.nodes.length,
    knowledge: knowGraph.counts.hypotheses + knowGraph.counts.entities,
    hypotheses: state.hypotheses.size,
    experiments: state.experiments.size,
    paper: state.paper.sections.length + state.review.iterations.length,
    events: state.ticker.length,
  };
  const TABS: { key: Tab; label: string }[] = [
    { key: "literature", label: "Literature" },
    { key: "knowledge", label: "World model" },
    { key: "hypotheses", label: "Hypotheses" },
    { key: "experiments", label: "Experiments" },
    { key: "paper", label: "Paper" },
    { key: "events", label: "Events" },
  ];

  if (error) {
    return <div className="p-10 text-center text-sm text-muted-foreground">{error}</div>;
  }
  if (events === null) {
    return <div className="p-10 text-center text-sm text-muted-foreground">loading replay…</div>;
  }
  if (events.length === 0) {
    return (
      <div className="p-10 text-center text-sm text-muted-foreground">
        No recorded events for this run yet.
        <div className="mt-3">
          <Link to="/research" className="text-primary hover:underline">
            ← Back to research
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-5rem)] flex-col overflow-hidden">
      <div className="flex items-center gap-3 border-b border-border px-4 py-2">
        <Link
          to="/research"
          className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:border-primary hover:text-primary"
        >
          ‹ Research
        </Link>
        <span className="font-serif text-lg">Replay</span>
        <span className="truncate text-xs text-muted-foreground" title={state.run.prompt}>
          {state.run.prompt?.split("\n")[0]?.slice(0, 100)}
        </span>
      </div>

      <ReplayStatusBar state={state} />

      <div className="flex gap-1 border-b border-border px-4 pt-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex items-center gap-1.5 border-b-2 px-3.5 pb-2.5 pt-1.5 text-xs transition-colors ${
              tab === t.key
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {t.label}
            <span
              className={`rounded-full px-1.5 text-[10px] tabular-nums ${
                tab === t.key ? "bg-primary/15 text-primary" : "bg-card text-muted-foreground"
              } ${counts[t.key] === 0 ? "opacity-40" : ""}`}
            >
              {counts[t.key]}
            </span>
          </button>
        ))}
      </div>

      <div className="relative flex-1 overflow-hidden">
        {tab === "literature" && <LiteratureConstellation graph={litGraph} />}
        {tab === "knowledge" && <KnowledgeGraph graph={knowGraph} />}
        {tab === "hypotheses" && <ReplayHypotheses state={state} />}
        {tab === "experiments" && (
          <ReplayExperiments
            state={state}
            artifactUrl={(p) => (sessionId ? sessionArtifactUrl(sessionId, p) : null)}
          />
        )}
        {tab === "paper" && <ReplayPaper state={state} />}
        {tab === "events" && <ReplayTicker events={state.ticker} />}
      </div>

      <ReplayScrubber events={loaded} playback={playback} />
    </div>
  );
}
