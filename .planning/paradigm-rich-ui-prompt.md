# Paradigm: Rich Terminal UI Implementation

## Context

Paradigm is a Python CLI tool that orchestrates multi-agent AI research cycles. Multiple LLM agents (theorist, experimentalist, analyst, synthesizer, skeptic, writer, editor) collaborate through phases (IDEATION → PLANNING → EXECUTION → WRITING → INTERNAL_REVIEW) to conduct scientific research, search literature, run computational experiments, and produce papers.

Currently, the tool dumps all output as flat, unformatted text to the terminal. I want to create a rich, colorful, live-updating terminal interface using the Python `rich` library while preserving the full detailed log to a file inside the paper output folder.

## Architecture Goal

Split output into two streams:

1. **Log file** (inside `paper-<id>/` folder): Full verbose output, same as current behavior. Plain text, every detail preserved.
2. **Terminal display**: A styled, live-updating `rich` interface that renders the same underlying events in a visually engaging way.

The cleanest approach is an **event-based architecture**: the research engine emits structured events (phase change, agent start, agent done, search performed, paper read, debate started, debate resolved, experiment running, experiment result, review score, etc.), and two listeners consume them — one writes to the log file, one updates the rich display. If refactoring to a full event system is too invasive, an alternative is a `DisplayManager` class that wraps `rich` and gets called at key points in the existing code, acting as a drop-in replacement for print statements.

## Design Specification

### 1. Agent Colors

Each agent role gets a persistent color used everywhere that agent appears:

```
Role                Color         Icon
theorist-0          blue          🔭
analyst-1           orange3       📊
experimentalist-2   green         🧪
synthesizer-3       magenta       🔗
skeptic-4           red           🔍
writer-5            cyan          ✍️
editor-6            yellow        📝
```

Agent names should always appear in their assigned color. The icon prefix is optional but nice.

### 2. Overall Layout (using `rich.live.Live`)

The terminal should show a persistent, updating layout (not scrolling logs):

```
┌─ PARADIGM ──────────────────────────────────────────────────────────┐
│  Phase: ✓ IDEATION  ● PLANNING  ○ EXECUTION  ○ WRITING  ○ REVIEW  │
│  Round: 2/2  │  Papers: 4  │  Searches: 186  │  Tokens: 245k      │
├─────────────────────────────────────────────────────────────────────┤
│  Active Agents                                                      │
│  🔭 theorist-0    searching: "Bowman 2019 red noise..."            │
│  🧪 experimentalist-2  reading: 2006.03012                         │
│  🔍 skeptic-4     thinking... (23,960 tokens)                      │
├─────────────────────────────────────────────────────────────────────┤
│  Recent Events                                                      │
│  14:23:01 🔭 theorist-0 read 2504.15861                            │
│  14:23:03 🧪 experimentalist-2 searched → 50 (16 new)              │
│  14:22:58 🔍 skeptic-4 followed refs of 2408.11082                 │
│  14:22:55 ⚠️  experimentalist-2: per-agent cap reached              │
└─────────────────────────────────────────────────────────────────────┘
```

Key elements:
- **Phase bar** at top: horizontal list of all phases, current one highlighted/bold, completed ones dimmed with checkmark
- **Stats bar**: running counters for round, papers ingested, total searches, cumulative tokens
- **Active agents panel**: shows which agents are currently running and what they're doing
- **Event log panel**: scrolling list of recent events (keep last ~15-20), timestamped, color-coded by agent

### 3. Phase Transitions

When moving between phases, briefly display a prominent banner before the live layout resumes:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ▶  PHASE: EXECUTION
  3 experiment rounds planned
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 4. Debates (Special Event)

When a debate triggers, render a distinctive panel with double-line border or gold border color:

```
╔══════════════════════════════════════════════════╗
║  ⚔️  DEBATE                                      ║
║  🔭 theorist-0  vs  📊 analyst-1                 ║
║  Topic: "The proposal to extract relevant..."    ║
║                                                   ║
║  Result: analyst-1 concedes (1 turn)             ║
╚══════════════════════════════════════════════════╝
```

### 5. Resource Ingestion (Startup)

Render as a compact `rich.table.Table`:

```
📚 Resources Loaded
┌──────────────────────────────────┬───────────┬────────┐
│ Source                           │ Type      │ Status │
├──────────────────────────────────┼───────────┼────────┤
│ waps.cfa.harvard.edu/MIST/...   │ reference │ ✓      │
│ read_mist_models.py             │ code_file │ ✓      │
│ A&A, 692, A49 (2024)            │ paper     │ ✓ PDF  │
│ A&A 668, A134 (2022)            │ paper     │ ✓ PDF  │
└──────────────────────────────────┴───────────┴────────┘
```

### 6. Execution Phase: Progress Bars

Show a progress bar for experiment rounds with nested task tracking:

```
Experiment Round [2/3] ━━━━━━━━━━━━━━━━━━━━ 67%

  ✓ Extract red noise parameters from PDF papers
  ✓ Deep extraction of Bowman2019 data tables
  ⟳ Parse Bowman 2019 Table A.1 data (retry 1/2)
  ◻ Build comprehensive red noise database
  ► Currently running task name here
```

Color-code: ✓ green (success), ✗ red (failure), ⟳ yellow (retry), ◻ dim (pending), ► bright (running)

### 7. Internal Review Scorecard

```
📝 Internal Review
┌──────────┬───────────────┬──────────┐
│ Iteration│ Recommendation│ Changes  │
├──────────┼───────────────┼──────────┤
│ 1        │ revise        │ 73       │
│ 2        │ revise        │ 0  ↓     │
│ 3        │ revise        │ 0  →     │
└──────────┴───────────────┴──────────┘
Status: ⚠️ Max iterations reached
```

### 8. Final Summary

```
┌─ RESEARCH CYCLE COMPLETE ────────────────────────┐
│  Thread: thread-f77c4ffcc059                     │
│  Paper: paper-fe88e5bd8253                       │
│  Status: ⚠️ Review not accepted                   │
│                                                   │
│  Stats:                                           │
│   Phases completed: 5                            │
│   Total searches: 186 (110 unique papers)        │
│   Papers read: 12                                │
│   Debates: 1 (theorist won)                      │
│   Experiments: 45 run, 43 succeeded, 2 failed    │
│   Total tokens: ~1.2M                            │
│   Duration: 14m 32s                              │
│                                                   │
│  Log: paper-fe88e5bd8253/paradigm.log            │
└──────────────────────────────────────────────────┘
```

### 9. Error/Warning Styling

- `[!]` warnings: yellow with ⚠️ prefix
- `[skip]` messages: dim/grey (routine)
- `[~]` similar query skips: dim/grey
- Retry messages: yellow
- Failures: red with ✗
- `529 Overloaded` errors: red

### 10. Token Counts

Don't show raw token counts in the main event flow. Instead: show per-agent tokens dimmed at the right margin if space permits, accumulate into the stats bar total, full details go to the log file only.

## Implementation Notes

- Use `rich >= 13.0` as a dependency
- The `DisplayManager` should accept a `verbose: bool` flag — when verbose or when stdout is not a TTY, fall back to current plain-text behavior (for CI/piping/debugging)
- The log file should use the existing plain-text format, not rich markup
- All `rich.live.Live` updates should use `refresh_per_second=4` or similar to avoid flicker
- Keep the display manager decoupled from the research engine logic — it should be easy to swap or disable
- The goal is minimal invasion of the core logic: ideally just replacing print calls with display manager method calls

## Files to Read First

Before implementing, read through the existing codebase to understand:
1. Where print/logging statements currently live
2. How phases, rounds, and agents are orchestrated
3. What data is available at each point (agent names, token counts, search queries, etc.)
4. The existing logging setup

## Dependencies

```
pip install rich
```

No other new dependencies should be needed.
