# Caching fix + replication-gate fix (measured on the exoplanet run)

## Fix 1 — make caching actually save (measured: 50k writes / 4k reads = net loss)
- [ ] 1A: drop LITERATURE from cache_prefix (it grows each round → thrashes). Keep it in the user prompt.
      Cache only stable blocks: data_context + code_context + reference_context.
- [ ] 1B: wire the EXPERIMENTATION phase for cache_prefix (the 38k data cards live there;
      it builds its own prompts and wasn't wired). Pass data_context as cache_prefix; drop it from the prompt body.
- [ ] Test: cache_prefix excludes literature; experimentation passes cache_prefix.

## Fix 2 — replication gate silent failure (0 events, 2nd time)
- [ ] Bump replicator max_tokens 8192 -> 16384 (reasoning-model empty-output).
- [ ] Emit replication.completed even on ERROR/skip paths + surface to display (never vanish silently).
- [ ] Test: error path still emits an event / verdict is visible.

Gate: full suite green each step. Then merge + redeploy + re-run to measure the real cache saving.
