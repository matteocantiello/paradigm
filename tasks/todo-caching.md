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

## Increment 2 — CACHING  ✅ DONE + live-verified
- [x] Part A: mark long system block cache_control=ephemeral (universal). Live: 90% saved on a cached call.
- [x] Part B: cache the cycle-stable shared context (data cards+literature+refs+code) as a leading
      system block. Agent.generate(cache_prefix=...) → provider _anthropic_system/_openai_system.
      _build_agent_prompt now returns (cache_prefix, prompt); discussion path passes it.
      LIVE-VERIFIED cross-agent sharing: 31,010-token shared block written once (theorist),
      READ by skeptic + analyst (different roles) → 62,020 tokens reused across 2 calls.
- [x] Instrumentation surfaces it: `paradigm status` shows reads/writes + % input saved.
Suite 2092+ green.

## Tests
- [ ] LLMResult unpacking + attrs; cache-token capture; DB round-trip; report formatting.
