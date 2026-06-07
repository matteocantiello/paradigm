"""Pre-flight model health check — verify each agent's model responds before a run.

A dead or over-capacity provider (e.g. a TogetherAI 503), a wrong model id (404),
or an unsupported param (400) would otherwise cripple a role for the whole cycle.
Before starting, we ping each distinct ``(provider, model)`` the team will use with
a tiny 1-token completion (fast + cheap), then reassign any role whose model didn't
answer to a verified-healthy fallback — preferring the config's default model. Each
swap carries the REASON the model failed so it's obvious why (404 / 400 / timeout).

The result feeds ``AgentFactory.create_team(role_overrides=...)``, so the swap is
per-run and never mutates the shared config. Best-effort throughout: any failure
yields "no swaps" so this can never block a cycle from starting.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

_PING_TIMEOUT_S = 10.0


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
    """None if ``model`` answers a 1-token completion; else a short failure reason."""
    try:
        await asyncio.wait_for(
            asyncio.to_thread(
                provider.complete,
                model=model,
                system="",
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
                temperature=0.0,
            ),
            timeout=timeout,
        )
        return None
    except asyncio.CancelledError:
        raise
    except BaseException as e:  # noqa: BLE001 — health check classifies every failure
        return _short_err(e)


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
