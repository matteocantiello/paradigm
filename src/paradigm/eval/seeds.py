"""Seed prompts and deterministic train/selection/test splits for evaluation (1D).

The split is *hash-fixed*: each seed is assigned to a split by hashing its id, so
the test set never leaks into selection and adding new seeds never reshuffles the
existing ones. ``selection`` is the gate later phases tune against; ``test`` stays
locked until a final report.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel

Split = str  # "train" | "selection" | "test"


class SeedPrompt(BaseModel):
    """A fixed research prompt used to evaluate the system end-to-end."""

    id: str
    prompt: str
    domain: str = "science"


# A small built-in, domain-agnostic starter set. Extend via ``load_seeds(path)``.
DEFAULT_SEEDS: list[SeedPrompt] = [
    SeedPrompt(
        id="cepheid-pl",
        prompt="Characterize the period-luminosity relation for classical Cepheids and "
        "quantify how metallicity affects its slope and zero-point.",
    ),
    SeedPrompt(
        id="rednoise-detection",
        prompt="Assess how red (correlated) noise biases the detection significance of "
        "periodic signals in unevenly sampled time series.",
    ),
    SeedPrompt(
        id="massive-star-variability",
        prompt="Investigate the dominant drivers of photometric variability in massive "
        "main-sequence stars and whether they scale with luminosity.",
    ),
    SeedPrompt(
        id="overshoot-msw",
        prompt="Quantify how convective-core overshooting changes the main-sequence width "
        "for intermediate-mass stars.",
    ),
]


def _bucket(seed_id: str, rng_seed: str) -> float:
    """Stable hash of a seed id to a float in [0, 1)."""
    digest = hashlib.sha1(f"{rng_seed}:{seed_id}".encode()).hexdigest()
    return int(digest[:8], 16) / float(0x100000000)


def split_seeds(
    seeds: list[SeedPrompt],
    ratios: tuple[float, float, float] = (0.5, 0.25, 0.25),
    rng_seed: str = "paradigm-eval",
) -> dict[Split, list[SeedPrompt]]:
    """Deterministically partition seeds into train/selection/test.

    Args:
        seeds: The seed prompts.
        ratios: (train, selection, test) fractions; test is the remainder.
        rng_seed: Salt for the hash (changing it reshuffles all splits).

    Returns:
        Mapping ``{"train": [...], "selection": [...], "test": [...]}``.
    """
    train_r, sel_r, _ = ratios
    out: dict[Split, list[SeedPrompt]] = {"train": [], "selection": [], "test": []}
    for seed in seeds:
        b = _bucket(seed.id, rng_seed)
        if b < train_r:
            out["train"].append(seed)
        elif b < train_r + sel_r:
            out["selection"].append(seed)
        else:
            out["test"].append(seed)
    return out


def load_seeds(path: Path) -> list[SeedPrompt]:
    """Load seeds from a JSON file: a list of ``{id, prompt, domain?}`` objects."""
    data = json.loads(Path(path).read_text())
    return [SeedPrompt(**item) for item in data]
