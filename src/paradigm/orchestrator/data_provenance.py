"""Deterministic data-provenance classification for experiment code (D1).

The real-data mandate needs a mechanical answer to "where did this
experiment's inputs come from?" — agents fabricate stand-in datasets exactly
when acquisition fails (the "MIST-like tracks" incident), and an LLM reviewer
only catches that when it happens to notice. This classifier is regex-level on
purpose: cheap, auditable, and biased toward high precision on the verdict
that has consequences (``synthetic`` → excluded from the evidence base under
``data_policy: real_only``).

Verdicts:
- ``real``      — loads data files, no random generation.
- ``resampled`` — loads data files AND uses randomness (bootstrap/permutation/
                  Monte-Carlo over real data — legitimate statistics).
- ``derived``   — neither loads files nor generates randomness (pure
                  computation / theory / plotting of literature values).
- ``synthetic`` — generates random arrays WITHOUT loading any data, or
                  self-describes its data as synthetic/mock while generating.
"""

from __future__ import annotations

import re

REAL = "real"
DERIVED = "derived"
RESAMPLED = "resampled"
SYNTHETIC = "synthetic"

# Reading data into the experiment (staged files, workspace CSVs, FITS, HDF5…).
_INPUT_RE = re.compile(
    r"""
    pd\.read_\w+ | read_csv | read_fwf | read_table | read_parquet |
    np\.load | np\.loadtxt | np\.genfromtxt | loadtxt\( | genfromtxt\( |
    fits\.open | Table\.read | h5py\.File | np\.fromfile |
    open\(\s*['"][^'"]*(?:/data/|workspace|shared)[^'"]*['"] |
    json\.load\( | pickle\.load\(
    """,
    re.VERBOSE,
)

# Random generation / sampling of any kind.
_RANDOM_RE = re.compile(
    r"""
    np\.random\. | numpy\.random\. | default_rng | RandomState |
    \brandom\.(?:random|randint|gauss|uniform|normal|choice|sample|shuffle)\b |
    \.rvs\( | torch\.rand | make_classification | make_blobs | make_regression
    """,
    re.VERBOSE,
)

# The experiment says its own data is synthetic (word-boundary, case-insensitive).
_MARKER_RE = re.compile(
    r"\b(?:synthetic|mock|fake|toy|placeholder|simulated)[\s_-]*"
    r"(?:data|dataset|catalog|catalogue|observations|sample|tracks|grid|light[\s_-]?curves?)\b",
    re.IGNORECASE,
)


def classify_data_provenance(code: str, stdout: str = "") -> tuple[str, list[str]]:
    """Classify an experiment's data provenance from its code (+ stdout).

    Returns ``(verdict, reasons)`` where reasons are short human-readable
    justifications for the fact sheet / editor alerts.
    """
    reasons: list[str] = []
    has_input = bool(_INPUT_RE.search(code))
    has_random = bool(_RANDOM_RE.search(code))
    marker = _MARKER_RE.search(code) or _MARKER_RE.search(stdout or "")

    if has_random and not has_input:
        reasons.append("generates random arrays without loading any data file")
        if marker:
            reasons.append(f"self-describes its data as '{marker.group(0)}'")
        return SYNTHETIC, reasons

    if has_random and has_input and marker:
        # Loads real data but ALSO fabricates a labeled synthetic component —
        # conservative: the fabricated part poisons the experiment's evidence.
        reasons.append(f"loads data but also generates a component it calls '{marker.group(0)}'")
        return SYNTHETIC, reasons

    if has_input and has_random:
        reasons.append("randomness over loaded data (bootstrap/permutation/Monte-Carlo)")
        return RESAMPLED, reasons

    if has_input:
        reasons.append("loads data files, no random generation")
        return REAL, reasons

    reasons.append("no data files and no random generation (pure computation)")
    return DERIVED, reasons


def excluded_by_policy(verdict: str, policy: str) -> bool:
    """True when this experiment must be dropped from the evidence base."""
    return policy == "real_only" and verdict == SYNTHETIC
