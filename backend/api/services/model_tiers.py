"""Per-cycle model tiers: "premium" (top closed models) vs "open" (open weights).

The backend process loads ONE config file at startup, but a cycle may ask for
either model mapping (the SetupWizard's Models toggle). The chosen tier's
`agent:` section — parsed from its canonical yaml — is grafted onto a deep copy
of the active config for that session only, so concurrent cycles on different
tiers never share mutated state and no restart is needed.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Canonical yaml per tier — the agent: section is the tier's model mapping.
TIER_CONFIG_FILES: dict[str, Path] = {
    "premium": Path("configs/production.yaml"),
    "open": Path("configs/open.yaml"),
}

_TIER_INFO: list[dict[str, str]] = [
    {
        "id": "premium",
        "label": "Top models",
        "description": (
            "Frontier closed models (GPT-5.5, Claude Opus/Sonnet 5, Gemini) — "
            "best quality, roughly $15–25 per cycle."
        ),
        "key_env": "ANTHROPIC_API_KEY",
    },
    {
        "id": "open",
        "label": "Open models",
        "description": (
            "Open weights on Together serverless (GLM-5.2, Kimi K2.6, MiniMax M3) — "
            "roughly $2–3 per cycle."
        ),
        "key_env": "TOGETHER_API_KEY",
    },
]


@lru_cache(maxsize=4)
def agent_config_for_tier(tier: str):
    """The tier's AgentConfig, parsed from its canonical yaml (None if unavailable)."""
    path = TIER_CONFIG_FILES.get(tier)
    if path is None or not path.exists():
        return None
    try:
        import yaml

        from paradigm.config import AgentConfig

        raw = yaml.safe_load(path.read_text()) or {}
        return AgentConfig(**(raw.get("agent") or {}))
    except Exception:  # noqa: BLE001 — a broken tier yaml must not break sessions
        logger.exception("Could not load agent config for tier %r from %s", tier, path)
        return None


def apply_tier(config: Any, tier: str | None) -> Any:
    """Return the config with the tier's agent mapping applied (deep copy).

    ``tier=None`` (or an unavailable tier) returns the active config unchanged,
    so existing callers and cycles created before this feature are unaffected.
    """
    if not tier:
        return config
    agent = agent_config_for_tier(tier)
    if agent is None:
        logger.warning("Model tier %r unavailable — running on the active config", tier)
        return config
    tier_config = config.model_copy(deep=True)
    tier_config.agent = agent.model_copy(deep=True)
    return tier_config


def tier_availability() -> list[dict[str, Any]]:
    """Tier descriptors for the GUI (available = yaml parses + its key is set)."""
    out: list[dict[str, Any]] = []
    for info in _TIER_INFO:
        available = agent_config_for_tier(info["id"]) is not None and bool(
            os.getenv(info["key_env"], "")
        )
        out.append(
            {
                "id": info["id"],
                "label": info["label"],
                "description": info["description"],
                "available": available,
            }
        )
    return out


def default_tier(config: Any) -> str:
    """Which tier the ACTIVE config resembles — the wizard's preselection."""
    try:
        return "open" if config.agent.default_provider == "together" else "premium"
    except Exception:  # noqa: BLE001
        return "premium"
