# Paradigm Research Dashboard

A web dashboard that visualizes the **epistemic state** of a research run — the
hypotheses, evidence, literature graph, experiments, debates, and paper as they
form — as distinct from operational state (tokens, agent chatter), which the
terminal UI already covers.

It is **event-sourced**: the orchestrator writes an append-only, `seq`-ordered
`data/threads/<thread-id>/events.jsonl`, and the entire dashboard is a pure
function of that stream. Replay, scrubbing, and live mode all feed the same
reducer.

## Running

The Python side needs the dashboard extra (FastAPI + uvicorn):

```bash
pip install -e ".[dashboard]"
```

**Replay a finished (or running) thread:**

```bash
paradigm dashboard                 # lists every thread it can find
paradigm dashboard <thread-id>     # deep-links to one
paradigm dashboard --host 0.0.0.0 --port 8060   # expose for a remote box
```

**Watch a run live:**

```bash
paradigm run --mode directed --prompt "..." --dashboard
# opens a server, prints the URL; click the "● live" thread on the landing page
```

A built frontend is committed to `dashboard/dist/`, so `paradigm dashboard`
works without Node. The server serves that directory.

## Developing the frontend

```bash
cd dashboard
npm install
npm run dev        # Vite dev server on :5180, proxies /api to :8060
npm run build      # rebuild dist/ (commit it)
```

Run the Python server separately (`paradigm dashboard`) so the dev server has an
API to proxy to. For frontend work without spending API tokens, generate a
realistic synthetic run:

```bash
python scripts/generate_demo_events.py     # writes data/threads/demo-thread-001
```

## Layout

- `src/types.ts` — the event envelope + dashboard state shapes.
- `src/reducer.ts` — `(state, event) => state`, the cornerstone. Pure.
- `src/replay.ts` — incremental-forward / rebuild-on-backward state + timestamp-paced playback.
- `src/live.ts` — SSE live source (seed from snapshot, then tail; seq-deduped).
- `src/components/` — StatusBar, Ticker, Scrubber, and the five views
  (Hypotheses, Literature, Evidence, Experiments, Paper) + the Debate overlay.

## Event schema

Validate any stream with:

```bash
python scripts/check_events.py <thread-id>
```

Each line is one event: `{seq, ts, type, phase, round, agent, payload}`, ordered
by `seq` (never by timestamp). See `scripts/check_events.py` for the full type
vocabulary.
