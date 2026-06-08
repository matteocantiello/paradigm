"""Pre-flight model health check — verify each agent's model responds before a run.

A dead or over-capacity provider (e.g. a TogetherAI 503), a wrong model id (404),
or an unsupported param (400) would otherwise cripple a role for the whole cycle.
Before starting, we ping each distinct ``(provider, model)`` the team will use with
a tiny completion (fast + cheap), then reassign any role whose model didn't answer
to a verified-healthy fallback — preferring the config's default model. Each swap
carries the REASON the model failed so it's obvious why (404 / 400 / timeout).

Two false-negatives this guards against:
  * **Reasoning models** (gpt-5.x, o-series) spend tokens on hidden reasoning
    before any visible output, so a tiny-budget ping can 400 with "max_tokens /
    model output limit was reached". That error PROVES the model is reachable —
    it accepted the request and began generating — so we count it healthy, not a
    failure. (The real cycle uses a large max_tokens, so it never hits this.)
  * **Cold connections** (first TLS/auth handshake to a provider endpoint) can be
    slow, so a single short timeout would wrongly swap a healthy model. We allow a
    generous timeout and one retry before giving up on a model.

The result feeds ``AgentFactory.create_team(role_overrides=...)``, so the swap is
per-run and never mutates the shared config. Best-effort throughout: any failure
yields "no swaps" so this can never block a cycle from starting.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

_PING_TIMEOUT_S = 15.0  # generous: first call pays the TLS/auth cold-start
_PING_ATTEMPTS = 2  # retry once — a cold endpoint often answers on the 2nd try
_PING_MAX_TOKENS = 16  # small but non-trivial; reasoning models fail fast into the healthy path

# Error fragments meaning "the model accepted the request and began generating,
# only hitting the tiny ping's output budget" — i.e. it is reachable, not broken.
_OUTPUT_LIMIT_HINTS = (
    "could not finish the message",
    "max_tokens or model output limit",
    "output limit was reached",
    "max output limit",
)


def _is_output_limit_error(e: BaseException) -> bool:
    """True if the failure is just the ping exhausting its (tiny) output budget."""
    msg = (str(e) or "").lower()
    return any(h in msg for h in _OUTPUT_LIMIT_HINTS)


# Transient failures worth a retry: a 429/rate-limit is COMMON here because preflight
# pings every model AT ONCE, so two OpenAI roles fire concurrently and can trip a
# per-minute limit that clears in seconds (and never recurs once the cycle spaces its
# calls out). Retrying avoids needlessly swapping a perfectly usable model. (A genuine
# quota/billing exhaustion keeps failing and still swaps after the retries.)
_RETRYABLE_PING_HINTS = (
    "429",
    "rate limit",
    "rate-limit",
    "too many requests",
    "503",
    "502",
    "504",
    "overloaded",
    "temporarily",
)
_PING_RETRY_BACKOFF_S = 3.0


def _is_retryable_ping_error(e: BaseException) -> bool:
    msg = (str(e) or "").lower()
    return any(h in msg for h in _RETRYABLE_PING_HINTS)


@dataclass
class PreflightResult:
    # role -> (provider_obj, model) to use instead of the configured one
    overrides: dict[str, tuple[Any, str]] = field(default_factory=dict)
    checked: int = 0  # distinct (provider, model) pairs pinged
    # (role, old_model, new_model, reason); new_model "" => nothing healthy to use
    swaps: list[tuple[str, str, str, str]] = field(default_factory=list)


def _provider_name_for(config: Any, role: str) -> str:
    override = config.agent.overrides.get(role)
    if override is not None and getattr(override, "provider", None):
        return override.provider
    return config.agent.default_provider


def _short_err(e: BaseException) -> str:
    if isinstance(e, (TimeoutError, asyncio.TimeoutError)):
        return "timed out"
    s = (str(e) or type(e).__name__).strip().replace("\n", " ")
    return s[:240]


async def _ping(provider: Any, model: str, *, timeout: float) -> str | None:
    """None if ``model`` is reachable; else a short failure reason.

    Retries once on timeout (cold-start tolerance). An output/token-limit error is
    treated as reachable — see the module docstring.
    """
    last = "unreachable"
    for _attempt in range(_PING_ATTEMPTS):
        try:
            await asyncio.wait_for(
                asyncio.to_thread(
                    provider.complete,
                    model=model,
                    system="",
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=_PING_MAX_TOKENS,
                    temperature=0.0,
                ),
                timeout=timeout,
            )
            return None
        except asyncio.CancelledError:
            raise
        except TimeoutError as e:  # asyncio.TimeoutError is an alias on 3.11+
            last = _short_err(e)  # retry: a cold connection often answers next time
            continue
        except BaseException as e:  # noqa: BLE001 — health check classifies every failure
            # A tiny-budget output-limit 400 means the model is up and generating.
            if _is_output_limit_error(e):
                return None
            # A 429/rate-limit (often from the concurrent ping burst) usually clears —
            # back off and retry before giving up on the model.
            if _is_retryable_ping_error(e) and _attempt < _PING_ATTEMPTS - 1:
                last = _short_err(e)
                await asyncio.sleep(_PING_RETRY_BACKOFF_S * (_attempt + 1))
                continue
            return _short_err(e)
    return last


async def preflight_team_models(
    config: Any,
    roles: list[str],
    *,
    timeout: float = _PING_TIMEOUT_S,
    logger: Any = None,
) -> PreflightResult:
    """Ping the team's models; return per-role swaps (with reasons) for any that fail."""
    try:
        # 1) Resolve each role's (provider_name, provider_obj, model).
        role_target: dict[str, tuple[str, Any, str]] = {}
        for role in dict.fromkeys(roles):
            provider, model, _extra = config.get_provider_and_model_for_role(role)
            role_target[role] = (_provider_name_for(config, role), provider, model)

        # 2) The config default is a candidate fallback (meant to be responsive).
        default_pname = config.agent.default_provider
        default_model = config.agent.default_model
        try:
            default_provider = config.get_provider(default_pname)
        except Exception:
            default_provider = None

        # 3) Distinct (provider_name, model) pairs to ping = team's + the default.
        pairs: dict[tuple[str, str], Any] = {}
        for pname, provider, model in role_target.values():
            pairs.setdefault((pname, model), provider)
        if default_provider is not None:
            pairs.setdefault((default_pname, default_model), default_provider)

        # 4) Ping all distinct pairs concurrently; capture each failure reason.
        keys = list(pairs)
        pings = await asyncio.gather(*(_ping(pairs[k], k[1], timeout=timeout) for k in keys))
        reasons = dict(zip(keys, pings, strict=True))  # key -> reason|None
        healthy = {k for k, err in reasons.items() if err is None}

        # 5) Pick a fallback: the healthy default first, else any healthy team model.
        fallback_key: tuple[str, str] | None = None
        if (default_pname, default_model) in healthy:
            fallback_key = (default_pname, default_model)
        else:
            for pname, _provider, model in role_target.values():
                if (pname, model) in healthy:
                    fallback_key = (pname, model)
                    break

        # 6) Build per-role swaps for unhealthy roles, recording why.
        result = PreflightResult(checked=len(keys))
        for role, (pname, _provider, model) in role_target.items():
            key = (pname, model)
            if key in healthy:
                continue
            reason = reasons.get(key) or "unreachable"
            if logger is not None:
                logger.log_error(
                    RuntimeError(f"preflight: {pname}/{model} for {role!r}: {reason}"),
                    metadata_key="model_preflight",
                )
            if fallback_key is None:
                result.swaps.append((role, model, "", reason))
                continue
            fb_model = fallback_key[1]
            result.overrides[role] = (pairs[fallback_key], fb_model)
            result.swaps.append((role, model, fb_model, reason))
        return result
    except Exception:
        # Never let a health check block a cycle from starting.
        return PreflightResult()
