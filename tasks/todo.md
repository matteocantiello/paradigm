# Responsiveness & Live Progress (A→B→C)

Plan: `~/.claude/plans/squishy-crafting-dahl.md`. Branch: `responsive-live-progress`.
Every new behavior behind a default-safe flag; Rich `DisplayManager` gets no-op mirrors of any new engine-called method.

> Prior completed todos (Prompt 67 reliability/eval, Phase 1 Correctness Kernel, Phase 2 output quality) are preserved in git history + HISTORY.md.

## Phase A — Liveness (token streaming + unblock the loop)
- [x] A1+A2 agent infra: non-blocking `generate` via `asyncio.to_thread`, `AgentResponse.stream_id`, per-agent stream sink (`set_stream_sink`) + tests
- [ ] `DisplayConfig` (`stream_tokens`, `stream_chunk_min_chars`) in config.py + register on Config; `configs/fast.yaml` enables it
- [ ] Engine attaches the stream sink to agents when `display.stream_tokens` (routes to `display.agent_stream_start/chunk`)
- [ ] ws_display: thread-safe `_schedule` (run_coroutine_threadsafe) + `agent_stream_start/chunk`; Rich `DisplayManager` no-op mirrors
- [ ] ws_display `agent_response`: drop 500-char truncation; final carries `stream_id` + full content
- [ ] session_manager `_broadcast`: don't buffer non-final stream chunks in replay deque
- [ ] `agent_step_complete` emitted from `_log_agent_response` choke point (Rich no-op + WS); fix frontend double-count
- [ ] frontend: accumulate `agent_output_stream` by `stream_id`; live bubble + cursor + thinking/elapsed
- [ ] (optional) vitest + sessionStore reducer test

## Phase B — Education (timeline + narration + progress/ETA)
- [ ] `display/narration.py` (templated) + `NarrationConfig` (LLM stub)
- [ ] `ActivityEventMsg` + `_activity` helper + duration timers; promote high-value events
- [ ] frontend phase-grouped activity timeline (EventLog upgrade)
- [ ] per-phase progress + rolling-avg ETA + now-playing header

## Phase C — Depth (live artifacts + GUI intervention)
- [ ] hypothesis board + tournament bracket (frontend on existing KnowledgeUpdateMsg)
- [ ] `ExperimentUpdateMsg` + experiment panel (code + stdout + RESULT parsing)
- [ ] `DraftUpdateMsg` + live PaperViewer (section-by-section)
- [ ] human-gate payload threading + GUI-aware ApprovalDialog
- [ ] interactive profile enables `stream_tokens` + `human_gate_mode`

## Review
(to be filled in as phases land)
