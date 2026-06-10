import { useEffect, useMemo, useState } from "react";
import { fetchEvents, fetchThreads, type ThreadSummary } from "./api";
import { DebateOverlay } from "./components/DebateOverlay";
import { EvidenceView } from "./components/EvidenceView";
import { ExperimentsView } from "./components/ExperimentsView";
import { HypothesesView } from "./components/HypothesesView";
import { LiteratureView } from "./components/LiteratureView";
import { PaperView } from "./components/PaperView";
import { Scrubber } from "./components/Scrubber";
import { StatusBar } from "./components/StatusBar";
import { Ticker } from "./components/Ticker";
import { usePlayback, useReplayState } from "./replay";
import type { DashboardState, Ev } from "./types";

type TabKey = "hypotheses" | "literature" | "evidence" | "experiments" | "paper";

const TABS: { key: TabKey; label: string }[] = [
  { key: "hypotheses", label: "Hypotheses" },
  { key: "literature", label: "Literature" },
  { key: "evidence", label: "Evidence" },
  { key: "experiments", label: "Experiments" },
  { key: "paper", label: "Paper" },
];

const LIT_EVENTS = new Set(["search.performed", "paper.read", "citation.followed"]);

/** Default tab follows the current phase; heavy searching pulls Literature forward. */
function phaseTab(state: DashboardState): TabKey {
  const recent = state.ticker.slice(-10);
  if (recent.length >= 4 && recent.filter((e) => LIT_EVENTS.has(e.type)).length > 5) {
    return "literature";
  }
  switch (state.run.phase) {
    case "execution":
    case "verification":
    case "post_execution":
      return "experiments";
    case "writing":
    case "internal":
    case "submitted":
    case "peer_review":
    case "revision":
    case "published":
    case "rejected":
      return "paper";
    default:
      return "hypotheses";
  }
}

function Landing({ onPick }: { onPick: (id: string) => void }) {
  const [threads, setThreads] = useState<ThreadSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    fetchThreads().then(setThreads).catch((e) => setError(String(e)));
  }, []);
  return (
    <div className="landing">
      <h1>
        <span>Paradigm</span> — research run dashboard
      </h1>
      {error && <div className="empty-note">{error}</div>}
      {threads && threads.length === 0 && (
        <div className="empty-note">
          No event streams found. Run a research cycle (the orchestrator writes
          data/threads/&lt;id&gt;/events.jsonl) or generate a demo:
          <code> python scripts/generate_demo_events.py</code>
        </div>
      )}
      {threads?.map((t) => (
        <a className="thread-row" key={t.id} onClick={() => onPick(t.id)}>
          <span className="title">{t.title}</span>
          <span className={`status-chip ${t.status === "published" ? "published" : t.status === "running" ? "running" : "other"}`}>
            {t.status}
          </span>
          <span className="meta">
            {t.id} · {t.n_events} events · {t.date?.slice(0, 10) ?? ""}
          </span>
        </a>
      ))}
    </div>
  );
}

function Session({ threadId }: { threadId: string }) {
  const [events, setEvents] = useState<Ev[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pinnedTab, setPinnedTab] = useState<TabKey | null>(null);

  useEffect(() => {
    setEvents(null);
    fetchEvents(threadId).then(setEvents).catch((e) => setError(String(e)));
  }, [threadId]);

  const loaded = events ?? [];
  const playback = usePlayback(loaded);
  const state = useReplayState(loaded, playback.cursor);
  const tab = pinnedTab ?? phaseTab(state);
  const fastMode = playback.playing && playback.speed > 5;

  const visibleTicker = useMemo(() => state.ticker.slice(-50), [state]);

  if (error) return <div className="empty-note">{error}</div>;
  if (events === null) return <div className="empty-note">loading {threadId}…</div>;

  return (
    <div className="app">
      <StatusBar state={state} live={false} />
      <main className="canvas">
        <div className="tabbar">
          {TABS.map((t) => (
            <button
              key={t.key}
              className={`tab ${tab === t.key ? "active" : ""}`}
              onClick={() => setPinnedTab(pinnedTab === t.key ? null : t.key)}
            >
              {t.label}
              {pinnedTab === t.key && <span className="pin">●</span>}
            </button>
          ))}
        </div>
        <div className="view">
          {tab === "hypotheses" && <HypothesesView state={state} />}
          {tab === "literature" && <LiteratureView state={state} fastMode={fastMode} />}
          {tab === "evidence" && <EvidenceView state={state} />}
          {tab === "experiments" && <ExperimentsView state={state} threadId={threadId} />}
          {tab === "paper" && <PaperView state={state} />}
          <DebateOverlay state={state} />
        </div>
      </main>
      <Ticker events={visibleTicker} />
      <Scrubber events={loaded} playback={playback} />
    </div>
  );
}

export default function App() {
  const [threadId, setThreadId] = useState<string | null>(
    () => new URLSearchParams(window.location.search).get("thread"),
  );

  const pick = (id: string) => {
    const url = new URL(window.location.href);
    url.searchParams.set("thread", id);
    window.history.pushState({}, "", url);
    setThreadId(id);
  };

  useEffect(() => {
    const onPop = () =>
      setThreadId(new URLSearchParams(window.location.search).get("thread"));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  if (!threadId) return <Landing onPick={pick} />;
  return <Session threadId={threadId} key={threadId} />;
}
