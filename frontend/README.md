# Paradigm Web UI

React frontend for the Paradigm agentic research platform. Provides real-time monitoring, session control, and paper browsing via WebSocket and REST integration with the FastAPI backend.

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

## Directory Structure

```
frontend/src/
  App.tsx                         Main app with routing
  main.tsx                        Entry point
  index.css                       Global styles (Tailwind)

  api/
    client.ts                     REST API client (typed fetch wrapper)
    websocket.ts                  WebSocket connection manager (reconnect, backoff)
    ws-types.ts                   Server/client WebSocket message types

  stores/
    sessionStore.ts               Research session state (WS-driven)
    uiStore.ts                    UI preferences (sidebar, theme, panel tab)

  hooks/
    useResearchSession.ts         WS connection + session state lifecycle
    useConfigMode.ts              Config mode (normal/testing) query + mutation
    useCycles.ts                  Research cycle CRUD (TanStack Query)
    usePapers.ts                  Paper list/detail queries
    useAgents.ts                  Agent list/config queries + update mutation

  components/
    layout/
      AppShell.tsx                Main layout (header + sidebar + outlet)
      Header.tsx                  Top navigation bar
      Sidebar.tsx                 Left navigation menu
    research/
      SetupWizard.tsx             New research cycle creation dialog
      CycleList.tsx               Research cycle list view
      CycleCard.tsx               Individual cycle summary card
    session/
      SessionView.tsx             Main session monitoring container
      PhaseTracker.tsx            Phase progression bar
      StatsBar.tsx                Token/search/paper/time counters
      MessagesPanel.tsx           Agent output messages (rolling buffer)
      AgentPanel.tsx              Active agent info panel
      RightPanel.tsx              Tabbed panel (events + knowledge)
      EventLog.tsx                Notification/event stream
      KnowledgePanel.tsx          Knowledge architecture viewer
      InteractionBar.tsx          User input controls (messages, pause, abort)
      ApprovalDialog.tsx          Phase transition approval modal
      ConnectionIndicator.tsx     WebSocket connection status badge
    papers/
      PaperList.tsx               Browsable paper list
      PaperCard.tsx               Paper summary card
      PaperViewer.tsx             Full paper renderer (Markdown + LaTeX)
      PaperTOC.tsx                Table of contents sidebar
      PaperExport.tsx             Export controls (copy markdown)
    agents/
      AgentGrid.tsx               Agent grid display
      AgentCard.tsx               Agent info card
      AgentConfig.tsx             Agent configuration form
    shared/
      StatusBadge.tsx             Colored status indicator
      LoadingSpinner.tsx          Loading state
      EmptyState.tsx              Empty state placeholder
      ErrorState.tsx              Error display
      ErrorBoundary.tsx           React error boundary

  pages/
    Dashboard.tsx                 Home: recent cycles, running sessions, stats
    ResearchPage.tsx              Create/manage research cycles
    SessionPage.tsx               Live session monitoring cockpit
    PapersPage.tsx                Paper browser
    AgentsPage.tsx                Agent configuration

  lib/
    utils.ts                      Shared utilities (cn, formatters)
    constants.ts                  App constants
```

## Pages

| Route | Page | Description |
|-------|------|-------------|
| `/` | Dashboard | Overview of recent cycles, running sessions, and quick stats |
| `/research` | ResearchPage | Research cycle list with create-new wizard |
| `/session/:id` | SessionPage | Real-time session monitoring and control |
| `/papers` | PapersPage | Published papers library with status filter |
| `/agents` | AgentsPage | Agent configuration and model assignment |

## State Management

The frontend uses three complementary state strategies:

### Zustand --- `sessionStore`
WebSocket-driven store holding live session state: phase, round, active agents, token counts, agent outputs (rolling buffer of 200), notifications (rolling buffer of 100), knowledge architecture, and pending approval requests. Updated in real time by server messages.

### Zustand --- `uiStore`
Local UI preferences: sidebar visibility, dark/light theme, right panel tab selection. Persisted across page navigations but not across sessions.

### TanStack Query
REST-driven server state with automatic caching and deduplication: research cycles, papers, agent configs, config mode. Queries use a 30-second stale time and single retry.

## WebSocket Integration

The `useResearchSession(sessionId)` hook manages the full WebSocket lifecycle:

1. Connects to `ws://localhost:8000/api/v1/sessions/{sessionId}/ws` on mount
2. Dispatches incoming messages to `sessionStore.handleServerMessage()`
3. Supports auto-reconnect with exponential backoff (max 10 attempts, 30s cap)
4. Exposes connection status via `connectionStatus` field
5. Disconnects on unmount or session change

### Server -> Client messages
`session_state`, `agent_output_stream`, `agent_step_complete`, `phase_transition`, `round_update`, `approval_request`, `notification`, `error`, `knowledge_update`

### Client -> Server messages
`approval_response`, `session_control` (pause/resume/checkpoint/rewind/abort), `user_intervention`, `user_message`

## Build for Production

```bash
npm run build
```

Output goes to `frontend/dist/`. Serve with any static file server, configured to proxy `/api` requests to the backend.
