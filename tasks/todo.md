# Responsiveness & Live Progress (A→B→C)

Plan: `~/.claude/plans/squishy-crafting-dahl.md`. Branch: `responsive-live-progress`.
Every new behavior behind a default-safe flag; Rich `DisplayManager` gets no-op mirrors of any new engine-called method.

> Prior completed todos (Prompt 67 reliability/eval, Phase 1 Correctness Kernel, Phase 2 output quality) are preserved in git history + HISTORY.md.

## Phase A — Liveness (token streaming + unblock the loop)  ✅ DONE (live-verified: 28 chunks + final)
- [x] A1+A2 agent infra: non-blocking `generate` via `asyncio.to_thread`, `AgentResponse.stream_id`, per-agent stream sink (`set_stream_sink`) + tests
- [x] `DisplayConfig` (`stream_tokens`, `stream_chunk_min_chars`) in config.py + register on Config; `configs/fast.yaml` enables it
- [x] Engine attaches the stream sink to agents when `display.stream_tokens` (routes to `display.agent_stream_start/chunk`); sink is phase-safe + non-fatal
- [x] ws_display: thread-safe `_schedule` (run_coroutine_threadsafe) + `agent_stream_start/chunk`; Rich `DisplayManager` no-op mirrors
- [x] ws_display `agent_response`: drop 500-char truncation; final carries `stream_id` + full content
- [x] session_manager `_broadcast`: don't buffer non-final stream chunks in replay deque
- [x] `agent_step_complete` emitted from `_log_agent_response` choke point (Rich no-op + WS); frontend double-count fixed
- [x] frontend: accumulate `agent_output_stream` by `stream_id`; live bubble + cursor + thinking/elapsed
- [ ] (optional) vitest + sessionStore reducer test — deferred
- [x] LOOP FIX: offloaded non-generate `provider.complete()` (convergence, checkpoint, tournament x2, memory, prereg, figure review) via `to_thread`; Docker already wrapped. Residual: ChromaDB/embeddings (CPU-bound, deferred).

## Phase B — Education (timeline + narration + progress/ETA)  ✅ DONE (live-verified: 3 activity events w/ narration + pacing)
- [x] `display/narration.py` (templated) + `NarrationConfig` (LLM stub)
- [x] `ActivityEventMsg` + `_activity` helper + duration timers; promoted high-value events
- [x] frontend phase-grouped activity timeline (EventLog upgrade: title + why-narration + duration + severity)
- [x] rolling-avg ETA + now-playing header (avg_step_ms + phase_elapsed_seconds)

## Phase C — Depth (live artifacts + GUI intervention)
- [x] hypothesis board + tournament bracket — `TournamentBoard.tsx`: Elo standings (rank, ▲▼ movement via store `previousElo`, W–L from matchups), readable matchup feed with real hypothesis labels (was the uninformative "A vs B"); detailed Hypotheses cards collapse while the tournament ranks them. (tsc/eslint/build green; standings logic unit-checked)
- [ ] `ExperimentUpdateMsg` + experiment panel (code + stdout + RESULT parsing)
- [ ] `DraftUpdateMsg` + live PaperViewer (section-by-section)
- [ ] human-gate payload threading + GUI-aware ApprovalDialog
- [ ] interactive profile enables `stream_tokens` + `human_gate_mode`

## Review
(to be filled in as phases land)
