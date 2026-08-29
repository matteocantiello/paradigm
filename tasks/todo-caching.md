# Token instrumentation + prompt caching (Levers: measure, then cache)

Branch: responsive-live-progress. Commit per increment; suite green each step.

## Increment 1 — INSTRUMENTATION (behavior-preserving; ship first)
- [ ] LLMResult: 3-tuple subclass carrying cache_read_tokens/cache_write_tokens (back-compat unpacking).
- [ ] Anthropic complete + complete_streaming: capture usage.cache_read_input_tokens + cache_creation_input_tokens.
- [ ] OpenAI-compat: capture prompt_tokens_details.cached_tokens (read only) if present.
- [ ] Agent.generate: thread cache stats into TokenUsage + AgentResponse.
- [ ] DB: token_usage gains cache_read_tokens/cache_write_tokens (migration) + record_token_usage params + get_token_usage sums.
- [ ] Engine + direct callers: pass cache stats to record_token_usage.
- [ ] Cycle-end report: show cache read/write + effective-vs-billed savings.

## Increment 2 — CACHING (one phase prototype)
- [ ] Anthropic complete/complete_streaming: mark system block cache_control=ephemeral (universal, safe).
- [ ] Agent.generate: optional cached_prefix → user message as [cached block][tail].
- [ ] Engine: for EXECUTION phase, split built prompt into (shared_prefix, tail); pass cached_prefix.
- [ ] Measure cache_read climb via Increment 1.

## Tests
- [ ] LLMResult unpacking + attrs; cache-token capture; DB round-trip; report formatting.
