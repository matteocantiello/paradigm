# Responsive live progress + real steering

Goal: make it obvious (1) when something is happening, (2) when nothing is, and
(3) when human input is needed/possible — AND make typed steering actually reach
the running cycle (today the backend drops `user_message`/`user_intervention`).

## Part A — Make system state obvious (frontend)
- [ ] A1. Store (`sessionStore.ts`): track `lastActivityAt` (ms), updated for every
      inbound server message; reset on `connect`.
- [ ] A2. `useSystemState` hook: derive a single state with a 1s heartbeat —
      `working | thinking | awaiting | paused | stalled | done | stopped | failed |
      disconnected | starting`. Thresholds: working <12s since activity,
      thinking 12–35s, stalled >35s (only while `running` and no pending approval).
- [ ] A3. `StatusPill` component: prominent, color-coded, icon + label + one-line
      hint (what's happening / what you can do). Mount at top of `SessionView`.
- [ ] A4. `NowPlaying`: make the ping honest (animate only while working).

## Part B — Make steering real (backend + engine + frontend)
- [ ] B1. `EventType.USER_GUIDANCE`.
- [ ] B2. Engine: optional `guidance_provider` (async → list[str]); drain at the
      round boundary (after the pause gate); inject a "Human Guidance" block into
      `_build_agent_prompt`'s `checkpoint_context`; narrate via `self._display.info`;
      clear after the round. Zero behavior change when provider is None (CLI).
- [ ] B3. `session_manager`: per-session guidance inbox + `queue_user_guidance()` +
      `_make_guidance_provider()`; pass provider to the engine.
- [ ] B4. `ws.py`: wire `user_message` + `user_intervention` → inbox; ack with a
      NotificationMsg ("queued — reaches the agents at the next round").
- [ ] B5. `InteractionBar`: hint that guidance applies next round; rely on the ack.

## Verify
- [ ] pytest: engine guidance injection + session_manager inbox; ruff; full suite.
- [ ] frontend: `tsc` typecheck / vite build.
- [ ] Tell the user; restart (with warning) so they can test.

## Review
Done in one pass (both parts).

**Part B — steering is real now.** `user_message`/`user_intervention` no longer
hit a TODO: they queue into a per-session inbox (`SessionManager._guidance`), the
engine drains it at each round boundary (`_drain_guidance`, right after the pause
gate) and injects a top-priority "HUMAN GUIDANCE" block into every agent prompt
that round, then clears it. A `USER_GUIDANCE` event + `display.info` narration
make it visible; the operator gets an immediate "received — applies next round"
ack. Zero behavior change when no provider is supplied (CLI). 4 new tests
(end-to-end injection, no-op CLI path, inbox round-trip, blank-ignored).

**Part A — state is obvious now.** Store tracks `lastActivityAt` (every inbound
message); `useSystemState` derives one of working/thinking/awaiting/paused/
stalled/done/stopped/failed/connecting/disconnected on a 1s heartbeat (stalled =
no activity >35s while running). New `StatusPill` (color + label + hint) replaces
the static StatusBadge in the header; `NowPlaying` pings only while truly live.

Verified: full suite **1478 passed**, ruff clean, frontend `tsc` + vite build
clean. Backend auto-reloaded healthy; frontend HMR live. Not restarted manually.
