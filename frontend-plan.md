# Paradigm Frontend Architecture Plan

## 1. Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Framework** | React 18+ with TypeScript | Industry standard, ecosystem, hooks |
| **Build** | Vite 5+ | Fast HMR, ESBuild, zero-config |
| **State** | Zustand | Lightweight, no boilerplate, great TS support |
| **Data Fetching** | TanStack Query v5 | Caching, deduplication, optimistic updates |
| **UI Components** | shadcn/ui + Tailwind CSS 4 | Copy-paste components, full control, accessible |
| **WebSocket** | Native WebSocket + custom hook | No library overhead, discriminated union types |
| **Type Generation** | openapi-typescript | Auto-gen TS types from FastAPI OpenAPI spec |
| **Routing** | React Router v7 | File-based routing, nested layouts |
| **Charts** | Recharts or d3 (for token usage, timelines) | React-native, lightweight |
| **Markdown** | react-markdown + remark-math + rehype-katex | Paper rendering with LaTeX math |

## 2. Directory Structure

```
frontend/
  src/
    api/
      client.ts              # Typed fetch wrapper (generated from OpenAPI)
      websocket.ts            # WebSocket connection manager
      types.ts                # Auto-generated from openapi.json
    stores/
      sessionStore.ts         # Zustand: active session state (WS-driven)
      cycleStore.ts           # Zustand: research cycles (REST-driven)
      uiStore.ts              # Zustand: UI preferences, theme, sidebar state
    hooks/
      useResearchSession.ts   # Core hook: WS connection + state sync
      useApproval.ts          # Hook for approval dialog flow
      usePapers.ts            # TanStack Query hooks for papers
      useCycles.ts            # TanStack Query hooks for cycles
      useAgents.ts            # TanStack Query hooks for agent config
    components/
      layout/
        AppShell.tsx          # Main layout with sidebar + header
        Sidebar.tsx           # Navigation sidebar
        Header.tsx            # Top bar with session info
      session/
        SessionView.tsx       # Main cockpit view for a running session
        AgentLane.tsx         # Individual agent's output stream
        PhaseTracker.tsx      # Visual phase progression bar
        InteractionBar.tsx    # User input bar for interventions
        ApprovalDialog.tsx    # Modal for phase transition approvals
        TokenCounter.tsx      # Live token usage display
        EventLog.tsx          # Scrolling event log
      research/
        SetupWizard.tsx       # Multi-step research cycle creation
        CycleList.tsx         # List of research cycles
        CycleCard.tsx         # Individual cycle summary card
      papers/
        PaperViewer.tsx       # Markdown paper renderer with LaTeX
        PaperList.tsx         # Browsable paper list
        PaperCard.tsx         # Paper summary card
      agents/
        AgentConfig.tsx       # Agent configuration panel
        AgentCard.tsx         # Individual agent info card
      checkpoint/
        CheckpointList.tsx    # List of checkpoints for a session
        CheckpointControls.tsx # Fork/rewind controls
      shared/
        StatusBadge.tsx       # Colored status indicator
        LoadingSpinner.tsx    # Loading states
        EmptyState.tsx        # Empty state placeholders
    pages/
      Dashboard.tsx           # Home: recent cycles, running sessions
      ResearchPage.tsx        # Create/manage research cycles
      SessionPage.tsx         # Live session cockpit
      PapersPage.tsx          # Paper browser
      AgentsPage.tsx          # Agent configuration
      SettingsPage.tsx        # App settings
    lib/
      utils.ts                # Shared utilities
      constants.ts            # App constants
      theme.ts                # Tailwind theme extensions
  public/
    favicon.svg
  index.html
  vite.config.ts
  tailwind.config.ts
  tsconfig.json
  package.json
```

## 3. Key UI Components

### Session View (Cockpit)
The primary interface when a research cycle is running. Split into lanes:

```
+---------------------------------------------------+
|  Phase Tracker: [SEEDING] [IDEATION] [PLANNING]... |
|  Round: 3/10  |  Tokens: 45.2K  |  Papers: 23    |
+---------------------------------------------------+
|  Agent Lanes                 |  Event Log          |
|  +--------+  +--------+     |  09:23 search...    |
|  |theorist|  |skeptic |     |  09:24 debate...    |
|  |........|  |........|     |  09:25 converged    |
|  |content |  |content |     |                     |
|  +--------+  +--------+     |                     |
|  +--------+  +--------+     |                     |
|  |analyst |  |synth.  |     |                     |
|  +--------+  +--------+     |                     |
+---------------------------------------------------+
|  Interaction Bar: [Type message...] [Send] [Pause] |
+---------------------------------------------------+
```

### Approval Dialog
Modal that appears when the engine requests phase transition approval:

```
+------------------------------------------+
|  Phase Transition Approval               |
|                                          |
|  IDEATION -> PLANNING                    |
|  Thread: thread-abc123                   |
|                                          |
|  [Continue]  [Pause]  [Abort]            |
|                                          |
|  Notes: [optional text field]            |
+------------------------------------------+
```

### Research Setup Wizard
Multi-step form for creating a new research cycle:

1. **Prompt**: Enter seed prompt (textarea, file upload, URL input)
2. **Mode**: Select directed/explore/test
3. **Team**: Choose agent roles (checkboxes with defaults)
4. **Config**: Optional overrides (models, rounds, features)
5. **Review**: Summary before starting

### Output Viewer
Markdown renderer for papers with:
- LaTeX math rendering (KaTeX)
- Figure display (inline images)
- Section navigation (TOC sidebar)
- Citation links
- Export options (copy markdown, download PDF via pandoc)

## 4. State Management

### Zustand Store Architecture

```typescript
// sessionStore.ts — driven by WebSocket messages
interface SessionStore {
  // State (updated by WS messages)
  sessionId: string | null;
  status: SessionStatus;
  currentPhase: string | null;
  roundNum: number;
  maxRounds: number;
  activeAgents: Record<string, string>;
  totalTokens: number;
  totalSearches: number;
  papersFound: number;
  elapsedSeconds: number;
  completedPhases: string[];
  agentOutputs: AgentOutput[];    // Rolling buffer of agent messages
  notifications: Notification[];   // Rolling buffer of events
  pendingApproval: ApprovalRequest | null;

  // Actions
  handleServerMessage(msg: ServerMessage): void;
  sendApprovalResponse(requestId: string, decision: string): void;
  sendIntervention(targetAgent: string, action: string, content: string): void;
  sendSessionControl(action: string): void;
  connect(sessionId: string): void;
  disconnect(): void;
}

// cycleStore.ts — driven by REST + TanStack Query
interface CycleStore {
  selectedCycleId: string | null;
  selectCycle(id: string): void;
}

// uiStore.ts
interface UIStore {
  sidebarOpen: boolean;
  theme: 'light' | 'dark';
  eventLogVisible: boolean;
  toggleSidebar(): void;
  toggleTheme(): void;
}
```

### WebSocket -> Zustand Mapping

| WS Message Type | Store Update |
|-----------------|--------------|
| `session_state` | Full state replace (initial sync) |
| `agent_output_stream` | Append to `agentOutputs`, update `activeAgents` |
| `agent_step_complete` | Append to `agentOutputs`, update `totalTokens` |
| `phase_transition` | Update `currentPhase`, append to `completedPhases` |
| `round_update` | Update `roundNum`, `maxRounds` |
| `approval_request` | Set `pendingApproval` (triggers modal) |
| `notification` | Append to `notifications` |
| `error` | Append to `notifications` with error level |

## 5. Data Flow Diagram

```
User Action (click "Start", type message, approve phase)
    |
    v
React Component (onClick, onSubmit)
    |
    v
Zustand Store Action (sendApprovalResponse, sendIntervention)
    |
    v
WebSocket.send(JSON)  -or-  fetch(/api/v1/...)
    |
    v
FastAPI Backend
    |
    v
SessionManager -> OrchestrationEngine -> Agent (Claude API)
    |
    v
WebSocket broadcast (server -> all connected clients)
    |
    v
useResearchSession hook receives message
    |
    v
Zustand Store (handleServerMessage)
    |
    v
React re-render (components subscribe to store slices)
```

## 6. Type Safety

**Single source of truth: Pydantic models in `backend/api/models/`**

Pipeline:
1. FastAPI auto-generates OpenAPI spec from Pydantic models
2. `openapi-typescript` generates TypeScript types from the spec
3. Frontend imports these types for request/response typing
4. WebSocket messages use the same Pydantic discriminated unions

```bash
# Generate types (add to package.json scripts)
npx openapi-typescript http://localhost:8000/openapi.json -o src/api/types.ts
```

This ensures the frontend and backend never drift out of sync.

## 7. Development Phases

### Phase 1: Scaffold (1-2 days)
- [ ] `npm create vite@latest frontend -- --template react-ts`
- [ ] Install dependencies (shadcn/ui, tailwind, zustand, tanstack-query)
- [ ] Set up directory structure
- [ ] Generate TS types from OpenAPI spec
- [ ] Create AppShell layout with sidebar navigation
- [ ] Implement Dashboard page (placeholder)

### Phase 2: WebSocket Connection (2-3 days)
- [ ] Build `websocket.ts` connection manager (reconnect, heartbeat)
- [ ] Build `useResearchSession` hook
- [ ] Build `sessionStore` with WS message handling
- [ ] Create SessionView with PhaseTracker and basic EventLog
- [ ] Test with real backend: connect, receive events, display them

### Phase 3: Interaction Layer (2-3 days)
- [ ] Build ApprovalDialog for phase transitions
- [ ] Build InteractionBar for user interventions
- [ ] Build AgentLane for individual agent output streams
- [ ] Wire up session control (pause/resume/abort)
- [ ] Test full interaction loop: start cycle, approve phases, see results

### Phase 4: Setup Wizard + Agent Config (1-2 days)
- [ ] Build SetupWizard (multi-step form)
- [ ] Build AgentConfig panel with TanStack Query
- [ ] Wire up `POST /api/v1/research` + `POST .../sessions`
- [ ] Build CycleList and CycleCard components

### Phase 5: Output Viewer (2-3 days)
- [ ] Build PaperViewer with react-markdown + KaTeX
- [ ] Build PaperList and PaperCard
- [ ] Add figure display and section navigation
- [ ] Add export functionality (copy markdown, download)

### Phase 6: Polish (1-2 days)
- [ ] Dark mode toggle
- [ ] Responsive layout for smaller screens
- [ ] Loading states and error boundaries
- [ ] Keyboard shortcuts (Ctrl+Enter to send, Escape to dismiss)
- [ ] Token usage charts (Recharts)
- [ ] Checkpoint controls (list, fork)

## 8. WebSocket Connection Manager

```typescript
// websocket.ts
class ParadigmWebSocket {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectDelay = 1000;

  connect(sessionId: string, onMessage: (msg: ServerMessage) => void) {
    const url = `ws://${window.location.host}/api/v1/sessions/${sessionId}/ws`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      console.log(`Connected to session ${sessionId}`);
    };

    this.ws.onmessage = (event) => {
      const msg = JSON.parse(event.data) as ServerMessage;
      onMessage(msg);
    };

    this.ws.onclose = () => {
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        setTimeout(() => {
          this.reconnectAttempts++;
          this.connect(sessionId, onMessage);
        }, this.reconnectDelay * Math.pow(2, this.reconnectAttempts));
      }
    };
  }

  send(msg: ClientMessage) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  disconnect() {
    this.maxReconnectAttempts = 0; // Prevent reconnection
    this.ws?.close();
  }
}
```

## 9. Environment Configuration

```env
# .env.development
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000

# .env.production
VITE_API_URL=/api
VITE_WS_URL=wss://your-domain.com
```

## 10. Key Design Decisions

1. **No SSR/SSG** — This is a control panel, not a content site. Client-side rendering is fine.
2. **Zustand over Redux** — Less boilerplate, better TS inference, simpler for WS-driven state.
3. **shadcn/ui over Material/Ant** — Full control, accessible, matches the "research tool" aesthetic.
4. **Native WebSocket over Socket.io** — No need for fallbacks; the protocol is simple and typed.
5. **Single session view** — Users monitor one session at a time (multi-session is a future feature).
6. **Rolling buffers** — Agent outputs and notifications use capped arrays to prevent memory bloat.
7. **Optimistic UI** — Session control actions (pause/resume) update the store immediately, reconcile on next WS message.
