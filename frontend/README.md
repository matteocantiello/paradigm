# Paradigm Web UI

React frontend for the Paradigm agentic research platform — the "Observatory" interface. Launch research from a prompt-first console, watch and steer live sessions, replay finished runs, and read published papers with their digests, reviews, code, and figures. Talks to the FastAPI backend via REST and WebSocket.

## Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Framework | React (TypeScript) | 19 |
| Build | Vite | 7 |
| State | Zustand | 5 |
| Data Fetching | TanStack Query | 5 |
| Styling | Tailwind CSS | 4 |
| Routing | React Router | 7 |
| Markdown | react-markdown + remark-math + rehype-katex | --- |
| Icons | Lucide React | --- |

## Quick Start

```bash
# Install dependencies
npm install

# Start the dev server (port 3000)
npm run dev

# Build for production
npm run build

# Lint
npm run lint
```

> **Prerequisite:** The backend must be running on port 8000 (`uvicorn backend.api.main:app --reload --port 8000`). The Vite dev server proxies `/api` and `/health` requests to `localhost:8000`.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE_URL` | `` (uses Vite proxy) | REST API base URL |
| `VITE_WS_BASE_URL` | `ws://localhost:8000` | WebSocket server URL |

Set these in `.env.development` or `.env.production`.

## Pages

| Route | Page | Description |
|-------|------|-------------|
| `/` | Dashboard | Prompt-first hero console (type a question, attach datasets, Launch or Configure) + recent cycles and stats |
| `/research` | ResearchPage | Research cycle list with the setup wizard |
| `/session/:id` | SessionPage | Live session cockpit: mission digest, steering, decisions |
| `/replay/:id` | ReplayPage | Replay a finished run from its durable event stream |
| `/papers` | PapersPage | Paper library with judge-score badges, topic filters, artifact tabs |
| `/agents` | AgentsPage | Agent team + per-role model assignment |
| `/settings` | SettingsPage | Runtime settings (curated config sections) |
| `/about` | AboutPage | Platform overview |

## Directory Structure

```
frontend/src/
  App.tsx                         Main app with routing
  main.tsx                        Entry point
  index.css                       Global styles (Tailwind, Observatory theme)

  api/
    client.ts                     REST API client (typed fetch wrapper)
    websocket.ts                  WebSocket connection manager (reconnect, backoff)
    ws-types.ts                   Server/client WebSocket message types

  stores/
    sessionStore.ts               Research session state (WS-driven)
    uiStore.ts                    UI preferences (sidebar, theme, panel tab)

  hooks/
    useResearchSession.ts         WS connection + session state lifecycle
    useLaunchCycle.ts             Create cycle -> upload datasets -> start session
    useSystemState.ts             Derived system status (StatusPill state machine)
    useConfigMode.ts              Config mode (production/testing) query + mutation
    useCycles.ts                  Research cycle CRUD (TanStack Query)
    usePapers.ts                  Paper list/detail/artifact queries
    useAgents.ts                  Agent list/config queries + update mutation
    useSettings.ts                Runtime settings queries + mutations

  components/
    layout/
      AppShell.tsx                Main layout (header + sidebar + outlet)
      Header.tsx                  Top navigation bar
      Sidebar.tsx                 Left navigation menu
    research/
      SetupWizard.tsx             Cycle wizard: prompt+datasets -> supervision,
                                  model tier, mode -> team -> review & launch
      DatasetPicker.tsx           Attach local data files with schema previews
      CycleList.tsx               Research cycle list view
      CycleCard.tsx               Individual cycle summary card
    session/
      SessionView.tsx             Main session monitoring container
      DigestPanel.tsx             Mission Digest (Now / So far / Ahead)
      InteractionBar.tsx          Steering bar: typed guidance (lands at the
                                  next agent turn), pause/resume, abort
      ApprovalDialog.tsx          Decision dialogs (phase gates, hypothesis
                                  selection, experiment plan, PI reflection)
      TerminalScreen.tsx          Finished/aborted/rejected end-of-run screen
                                  (reason, prompt, retry)
      PhaseTracker.tsx            Phase progression bar
      StatsBar.tsx                Token/search/paper/time counters
      StatusPill.tsx              Session status indicator
      NowPlaying.tsx              Active agent + current activity
      MessagesPanel.tsx           Agent output messages (rolling buffer)
      AgentPanel.tsx              Active agent info panel
      DraftPanel.tsx              Live paper draft status
      ExperimentPanel.tsx         Experiment lifecycle panel
      TournamentBoard.tsx         Hypothesis tournament standings
      KnowledgePanel.tsx          Knowledge architecture viewer
      KnowledgeGraph.tsx          Evidence/hypothesis graph
      LiteratureGraph.tsx         Literature constellation
      RightPanel.tsx              Tabbed panel (events + knowledge)
      EventLog.tsx                Notification/event stream
      SessionControls.tsx         Pause/resume/abort controls
      ConnectionIndicator.tsx     WebSocket connection status badge
    replay/
      ReplayScrubber.tsx          Timeline scrubber over the event stream
      ReplayPanels.tsx            Reconstructed session panels at a point in time
    papers/
      PaperList.tsx               Browsable paper list
      PaperCard.tsx               Paper summary card (judge scores, topics)
      PaperViewer.tsx             Full paper renderer (Markdown + LaTeX)
      ArtifactTabs.tsx            Paper / Digest / Literature / Reviews /
                                  Transcript / Code / Figures tabs
      DigestTab.tsx               Plain-language digest
      LiteratureTab.tsx           Cycle's literature corpus
      ReviewsTab.tsx              Internal + peer reviews
      TranscriptTab.tsx           Research transcript
      CodeTab.tsx                 Experiment code
      FiguresTab.tsx              Figures gallery
      PaperTOC.tsx                Table of contents sidebar
      PaperExport.tsx             Export controls (markdown copy, PDF)
    agents/
      AgentGrid.tsx               Agent grid display
      AgentCard.tsx               Agent info card
      AgentConfig.tsx             Per-role provider/model picker
    settings/
      SettingsSection.tsx         Settings section card
      SettingsField.tsx           Typed settings field
    shared/
      Markdown.tsx                Markdown + LaTeX renderer
      TopicBadges.tsx             Field/topic pills
      StatusBadge.tsx             Colored status indicator
      LoadingSpinner.tsx          Loading state
      EmptyState.tsx              Empty state placeholder
      ErrorState.tsx              Error display
      ErrorBoundary.tsx           React error boundary

  pages/
    Dashboard.tsx                 Hero console + recent cycles, stats
    ResearchPage.tsx              Create/manage research cycles
    SessionPage.tsx               Live session monitoring cockpit
    ReplayPage.tsx                Post-hoc replay of a finished run
    PapersPage.tsx                Paper browser
    AgentsPage.tsx                Agent configuration
    SettingsPage.tsx              Runtime settings
    AboutPage.tsx                 About/overview

  lib/
    utils.ts                      Shared utilities (cn, formatters)
    constants.ts                  App constants (topic taxonomy, phase labels)
```

## State Management

The frontend uses three complementary state strategies:

### Zustand --- `sessionStore`
WebSocket-driven store holding live session state: phase, round, active agents, token counts, agent outputs (rolling buffer), notifications, draft/experiment/literature/knowledge state, and pending approval requests. Updated in real time by server messages.

### Zustand --- `uiStore`
Local UI preferences: sidebar visibility, dark/light theme, right panel tab selection. Persisted across page navigations but not across sessions.

### TanStack Query
REST-driven server state with automatic caching and deduplication: research cycles, papers and artifacts, agent configs, model catalog, tiers, settings. Queries use a 30-second stale time and single retry.

## WebSocket Integration

The `useResearchSession(sessionId)` hook manages the full WebSocket lifecycle:

1. Connects to `ws://localhost:8000/api/v1/sessions/{sessionId}/ws` on mount
2. Dispatches incoming messages to `sessionStore.handleServerMessage()`
3. Supports auto-reconnect with exponential backoff (max 10 attempts, 30s cap)
4. Exposes connection status via `connectionStatus` field
5. Disconnects on unmount or session change

### Server -> Client messages
`session_state`, `agent_output_stream`, `agent_step_complete`, `phase_transition`, `round_update`, `approval_request`, `notification`, `activity_event`, `draft_update`, `experiment_update`, `literature_update`, `knowledge_update`, `topics_update`, `error`

### Client -> Server messages
`approval_response`, `session_control` (pause/resume/checkpoint/rewind/abort), `user_intervention`, `user_message`

The Replay page does not use the WebSocket: it fetches the durable per-thread event stream (`GET /api/v1/sessions/{id}/event-stream`, backed by `data/threads/<id>/events.jsonl`) and reconstructs the session at any point in time.

## Build for Production

```bash
npm run build
```

Output goes to `frontend/dist/`. Serve with any static file server, configured to proxy `/api` requests to the backend.
