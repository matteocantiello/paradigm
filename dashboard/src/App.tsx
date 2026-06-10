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
import { useLiveEvents } from "./live";
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

/** Per-tab item counts — shown on the tab and used to avoid defaulting to an empty view. */
function tabCounts(state: DashboardState): Record<TabKey, number> {
  return {
    hypotheses: state.hypotheses.size,
    literature: state.papers.size,
    evidence: state.hypotheses.size + state.claims.size,
    experiments: state.experiments.size,
    paper: state.paper.sections.length + state.review.iterations.length + (state.paper.id ? 1 : 0),
  };
}

/**
 * Default tab follows the current phase, but never lands on an empty view — if
 * the phase-appropriate tab has nothing yet, fall through to the richest one
 * that does. This is why a thread always opens on something worth seeing.
 */
function phaseTab(state: DashboardState): TabKey {
  const counts = tabCounts(state);
  const recent = state.ticker.slice(-10);
  const preferred: TabKey[] = [];
  if (recent.length >= 4 && recent.filter((e) => LIT_EVENTS.has(e.type)).length > 5) {
    preferred.push("literature");
  }
  switch (state.run.phase) {
    case "execution":
    case "verification":
    case "post_execution":
      preferred.push("experiments", "evidence", "hypotheses");
      break;
    case "writing":
    case "internal":
    case "submitted":
    case "peer_review":
    case "revision":
    case "published":
    case "rejected":
      preferred.push("paper", "experiments", "evidence", "hypotheses");
      break;
    default:
      preferred.push("hypotheses", "literature");
  }
  for (const t of preferred) if (counts[t] > 0) return t;
  // Fall back to whichever tab has the most content.
  const richest = (Object.keys(counts) as TabKey[]).sort((a, b) => counts[b] - counts[a])[0];
  return counts[richest] > 0 ? richest : "hypotheses";
}

function Landing({ onPick }: { onPick: (id: string, live: boolean) => void }) {
  const [threads, setThreads] = useState<ThreadSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    fetchThreads().then(setThreads).catch((e) => setError(String(e)));
  }, []);
  return (
    <div className="landing">
      <div className="landing-head">
        <h1>
          <span className="accent">Paradigm</span> Observatory
        </h1>
        <div className="tag">the evolution of a research run, as it happens</div>
      </div>
      {error && <div className="empty-note">{error}</div>}
      {threads && threads.length === 0 && (
        <div className="empty-note">
          <span className="big">No runs yet</span>
          The orchestrator writes <code>data/threads/&lt;id&gt;/events.jsonl</code> for every
          run. Generate a demo to explore: <code>python scripts/generate_demo_events.py</code>
        </div>
      )}
      {threads?.map((t, i) => (
        <a
          className="thread-row"
          key={t.id}
          style={{ animationDelay: `${Math.min(i, 12) * 40}ms` }}
          onClick={() => onPick(t.id, t.status === "running")}
        >
          <span className="title">{t.title}</span>
          <span className={`status-chip ${t.status === "published" ? "published" : t.status === "running" ? "live" : "other"}`}>
            {t.status === "running" ? "● live" : t.status}
          </span>
          <span className="meta">
            {t.id} · {t.n_events} events · {t.date?.slice(0, 10) ?? ""}
          </span>
        </a>
      ))}
    </div>
  );
}

function SessionShell({
  threadId,
  events,
  live,
  cursor,
  fastMode,
  onBack,
  onToggleTheme,
}: {
  threadId: string;
  events: Ev[];
  live: boolean;
  cursor: number;
  fastMode: boolean;
  onBack: () => void;
  onToggleTheme: () => void;
}) {
  const [pinnedTab, setPinnedTab] = useState<TabKey | null>(null);
  const state = useReplayState(events, cursor);
  const tab = pinnedTab ?? phaseTab(state);
  const counts = tabCounts(state);
  const visibleTicker = useMemo(() => state.ticker.slice(-50), [state]);

  return (
    <>
      <StatusBar state={state} live={live} onBack={onBack} onToggleTheme={onToggleTheme} />
      <main className="canvas">
        <div className="tabbar">
          {TABS.map((t) => (
            <button
              key={t.key}
              className={`tab ${tab === t.key ? "active" : ""}`}
              onClick={() => setPinnedTab(pinnedTab === t.key ? null : t.key)}
              title={pinnedTab === t.key ? "Unpin (auto-follow phase)" : "Pin this tab"}
            >
              {t.label}
              <span className={`count ${counts[t.key] === 0 ? "zero" : ""}`}>{counts[t.key]}</span>
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
      <Ticker events={visibleTicker} live={live} />
    </>
  );
}

function ReplaySession({
  threadId,
  onBack,
  onToggleTheme,
}: {
  threadId: string;
  onBack: () => void;
  onToggleTheme: () => void;
}) {
  const [events, setEvents] = useState<Ev[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setEvents(null);
    fetchEvents(threadId).then(setEvents).catch((e) => setError(String(e)));
  }, [threadId]);

  const loaded = events ?? [];
  const initialCursor = useMemo(() => {
    const t = new URLSearchParams(window.location.search).get("t");
    if (t === null) return undefined;
    const targetSeq = Number(t);
    const idx = loaded.findIndex((e) => e.seq > targetSeq);
    return idx < 0 ? loaded.length : idx;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events]);
  const playback = usePlayback(loaded, initialCursor);
  const fastMode = playback.playing && playback.speed > 5;

  if (error) return <div className="empty-note">{error}</div>;
  if (events === null) return <div className="empty-note">loading {threadId}…</div>;

  return (
    <div className="app">
      <SessionShell
        threadId={threadId}
        events={loaded}
        live={false}
        cursor={playback.cursor}
        fastMode={fastMode}
        onBack={onBack}
        onToggleTheme={onToggleTheme}
      />
      <Scrubber events={loaded} playback={playback} shareable />
    </div>
  );
}

function LiveSession({
  threadId,
  onBack,
  onToggleTheme,
}: {
  threadId: string;
  onBack: () => void;
  onToggleTheme: () => void;
}) {
  const { events, conn } = useLiveEvents(threadId);
  const [following, setFollowing] = useState(true);
  const [cursor, setCursor] = useState(0);

  // Follow the head as events arrive, unless the user scrubbed back.
  useEffect(() => {
    if (following) setCursor(events.length);
  }, [events.length, following]);

  // A finished live run is just a replay from here on.
  const fakePlayback = {
    cursor,
    playing: false,
    speed: 1,
    atEnd: cursor >= events.length,
    play: () => setFollowing(true),
    pause: () => {},
    setSpeed: () => {},
    seek: (c: number) => {
      setCursor(Math.max(0, Math.min(c, events.length)));
      setFollowing(c >= events.length);
    },
  };

  if (events.length === 0) {
    return (
      <div className="empty-note">
        {conn === "error" ? "connection error" : `waiting for events from ${threadId}…`}
      </div>
    );
  }

  return (
    <div className="app">
      <SessionShell
        threadId={threadId}
        events={events}
        live={conn === "live" && following}
        cursor={cursor}
        fastMode={false}
        onBack={onBack}
        onToggleTheme={onToggleTheme}
      />
      <div style={{ position: "relative" }}>
        {!following && (
          <button
            className="jump-live"
            onClick={() => {
              setFollowing(true);
              setCursor(events.length);
            }}
          >
            ● Jump to live
          </button>
        )}
        <Scrubber events={events} playback={fakePlayback} />
      </div>
    </div>
  );
}

function applyTheme(light: boolean) {
  document.body.classList.toggle("light", light);
}

export default function App() {
  const [search, setSearch] = useState(() => window.location.search);
  const params = new URLSearchParams(search);
  const threadId = params.get("thread");
  const live = params.get("live") === "1";

  useEffect(() => {
    applyTheme(localStorage.getItem("pd-theme") === "light");
  }, []);

  const toggleTheme = () => {
    const next = !document.body.classList.contains("light");
    applyTheme(next);
    localStorage.setItem("pd-theme", next ? "light" : "dark");
  };

  const pick = (id: string, isLive: boolean) => {
    const url = new URL(window.location.href);
    url.searchParams.set("thread", id);
    if (isLive) url.searchParams.set("live", "1");
    else url.searchParams.delete("live");
    window.history.pushState({}, "", url);
    setSearch(url.search);
  };

  const goHome = () => {
    const url = new URL(window.location.href);
    url.searchParams.delete("thread");
    url.searchParams.delete("live");
    url.searchParams.delete("t");
    window.history.pushState({}, "", url);
    setSearch(url.search);
  };

  useEffect(() => {
    const onPop = () => setSearch(window.location.search);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  if (!threadId) return <Landing onPick={pick} />;
  return live ? (
    <LiveSession threadId={threadId} key={threadId} onBack={goHome} onToggleTheme={toggleTheme} />
  ) : (
    <ReplaySession threadId={threadId} key={threadId} onBack={goHome} onToggleTheme={toggleTheme} />
  );
}
