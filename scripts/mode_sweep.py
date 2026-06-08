#!/usr/bin/env python
"""Operating-mode sweep — run every research mode end-to-end and triage it.

The six `paradigm run --mode` values exercise materially different code paths:
each picks a different team (MODE_TEAM_ROLES), and explore/hypothesis/review inject
mode-specific round-1 prompts, while `review` additionally rewrites the synthesis +
writing prompts and swaps real experiments for auto-generated conceptual figures.
`experimental`/`replication` are experimentalist-led and only mean something with
the sandbox on. This sweep runs one real Flash-Lite cycle per mode with the right
config + a mode-appropriate seed, reusing scripts/selftest.py for triage.

    conda run -n paradigm python scripts/mode_sweep.py
    conda run -n paradigm python scripts/mode_sweep.py --only review,experimental

Cheap by design (Gemini Flash-Lite, 1 round/phase). Real API calls (a few cents
each; sandbox modes also build/run Docker). Exits non-zero if any mode had a real
issue — so it doubles as a mode-coverage smoke gate.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))  # import sibling selftest
from selftest import _run_cycle, triage  # noqa: E402

_PLAIN = "configs/selftest.yaml"  # experiments OFF
_EXP = "configs/selftest-exp.yaml"  # experiments + sandbox ON

# (mode, config, seed, timeout_s). The seed is a --topic for explore, else a
# --prompt (selftest._run_cycle picks the flag from the mode). Seeds are framed
# to suit each mode so the mode-specific prompts have something coherent to chew on.
MODES: list[tuple[str, str, str, int]] = [
    # directed = the well-trodden baseline (control).
    ("directed", _PLAIN, "Explain the period-luminosity relation for Cepheid variable stars.", 480),
    # explore = open-ended survey (takes a --topic, special round-1 prompt).
    ("explore", _PLAIN, "massive star variability across the HR diagram", 480),
    # hypothesis = falsifiable-hypothesis framing (special round-1 prompt).
    (
        "hypothesis",
        _PLAIN,
        "Stellar rotation rate sets the magnetic activity level of low-mass main-sequence stars.",
        480,
    ),
    # review = literature synthesis: NO experiments, mode synthesis/writing overrides,
    # conceptual-figure generation. The most special-cased path → give it more time.
    (
        "review",
        _PLAIN,
        "Survey the observational evidence for and against the existence of Population III stars.",
        720,
    ),
    # experimental = experimentalist-led team, experiments ON (sandbox required).
    (
        "experimental",
        _EXP,
        "Measure how main-sequence stellar lifetime scales with mass using a simple stellar model.",
        1000,
    ),
    # replication = analyst+experimentalist reproduction, experiments ON.
    (
        "replication",
        _EXP,
        "Reproduce the empirical mass-luminosity relation for main-sequence stars.",
        1000,
    ),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", default=None, help="comma-separated mode names")
    args = ap.parse_args()

    modes = MODES
    if args.only:
        wanted = {s.strip() for s in args.only.split(",")}
        modes = [m for m in MODES if m[0] in wanted]

    print(f"▶ mode sweep: {len(modes)} mode(s)\n")
    failures = []
    for i, (mode, config_rel, seed, timeout) in enumerate(modes, 1):
        config = (ROOT / config_rel).resolve()
        if not config.exists():
            print(f"[{i:>2}/{len(modes)}] {mode:<13} SKIP · config not found: {config_rel}\n")
            failures.append(mode)
            continue
        run = _run_cycle(seed, mode, config, timeout)
        issues, info = triage(run)
        verdict = "PASS" if not issues else f"{len(issues)} ISSUE(S)"
        print(
            f"[{i:>2}/{len(modes)}] {mode:<13} {verdict} · {info['elapsed']:.0f}s · "
            f"status={info['status']} · paper={info['paper_chars']}ch · "
            f"cfg={config.name}"
        )
        print(f"        seed: {seed!r}")
        for sev, detail in issues:
            print(f"        ✗ {sev}: {detail}")
        if issues:
            failures.append(mode)
            print(f"        artifacts: {info['data_dir']}")
        for note in info["notes"][:2]:
            print(f"        ~ transient: {note}")
        for swap in info["swaps"]:
            print(f"        · {swap}")
        print(flush=True)

    print(f"== {len(modes)} mode(s), {len(failures)} with issues: {failures or 'none'} ==")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
