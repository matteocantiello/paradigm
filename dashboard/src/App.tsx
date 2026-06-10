import { useEffect, useMemo, useState } from "react";
import { fetchEvents, fetchThreads, type ThreadSummary } from "./api";
import { ExperimentsView } from "./components/ExperimentsView";
import { HypothesesView } from "./components/HypothesesView";
import { Scrubber } from "./components/Scrubber";
import { StatusBar } from "./components/StatusBar";
import { Ticker } from "./components/Ticker";
import { usePlayback, useReplayState } from "./replay";
import type { Ev } from "./types";

type TabKey = "hypotheses" | "experiments";

const TABS: { key: TabKey; label: string }[] = [
  { key: "hypotheses", label: "Hypotheses" },
  { key: "experiments", label: "Experiments" },
];

/** Default tab follows the current phase (user pin overrides). */
function phaseTab(phase: string | null): TabKey {
  switch (phase) {
    case "execution":
    case "verification":
    case "post_execution":
      return "experiments";
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
  const tab = pinnedTab ?? phaseTab(state.run.phase);

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
          {tab === "experiments" && <ExperimentsView state={state} threadId={threadId} />}
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
