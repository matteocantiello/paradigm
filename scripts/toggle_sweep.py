#!/usr/bin/env python
"""Config-toggle sweep — flip each setting on/off and check the cycle still runs.

From the cheap selftest baseline, generate one config per toggle (or coherent
group) with that toggle flipped, run a real Flash-Lite cycle, and triage it
(reusing scripts/selftest.py). Surfaces bugs in code paths that only execute when
a particular feature is enabled/disabled (debates, tournament, pre-registration,
sprints, verification, multimodal review, citation/seed discovery, LaTeX, the
knowledge-off paths, …). Per-toggle PASS / ISSUE report; exits non-zero if any
variant had a real issue.

    conda run -n paradigm python scripts/toggle_sweep.py
    conda run -n paradigm python scripts/toggle_sweep.py --only debates_on,tournament_on
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))  # import sibling selftest
from selftest import _run_cycle, triage  # noqa: E402

PROMPT = "Explain the period-luminosity relation for Cepheid variable stars."
_EXP = {"orchestrator.enable_experimentation": True, "sandbox.enabled": True}

# (name, overrides, timeout_s). Each flips ONE toggle (or the minimal coherent
# group needed for it to actually exercise its code path).
VARIANTS: list[tuple[str, dict, int]] = [
    # --- orchestrator: flip the defaults OFF ---
    ("writing_off", {"orchestrator.enable_writing": False}, 360),
    ("peer_review_off", {"orchestrator.enable_peer_review": False}, 360),
    ("checkpointing_off", {"orchestrator.enable_checkpointing": False}, 480),
    ("preflight_off", {"orchestrator.model_preflight": False}, 480),
    ("convergence_off", {"orchestrator.enable_convergence_detection": False}, 480),
    # --- orchestrator: flip extras ON ---
    ("debates_on", {"orchestrator.enable_debates": True}, 600),
    ("gate_advisory", {"orchestrator.human_gate_mode": "advisory"}, 480),
    # --- knowledge ---
    ("world_model_off", {"knowledge.enable_world_model": False}, 480),
    ("evidence_graph_off", {"knowledge.enable_evidence_graph": False}, 480),
    ("tournament_on", {"knowledge.enable_hypothesis_tournament": True}, 600),
    ("prereg_on", {"knowledge.enable_preregistration": True}, 480),
    # --- citation (Perplexity I/O) ---
    ("citation_grounding_on", {"citation.enable_citation_grounding": True}, 600),
    ("novelty_on", {"citation.enable_novelty_check": True}, 600),
    ("seed_discovery_on", {"citation.enable_seed_discovery": True}, 600),
    # --- journal output ---
    ("latex_on", {"journal.enable_latex_output": True}, 480),
    ("pdf_on", {"journal.enable_latex_output": True, "journal.compile_pdf": True}, 480),
    # --- experiments (Docker) + experiment-dependent toggles ---
    ("experiments_on", {**_EXP}, 900),
    ("sprints_on", {**_EXP, "orchestrator.enable_execution_sprints": True}, 900),
    ("verification_on", {**_EXP, "orchestrator.enable_verification": True}, 900),
    ("multimodal_on", {**_EXP, "orchestrator.enable_multimodal_review": True}, 900),
]


def _set_dotted(d: dict, dotted: str, value) -> None:
    keys = dotted.split(".")
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


def _write_variant_config(base: dict, overrides: dict) -> Path:
    cfg = yaml.safe_load(yaml.safe_dump(base))  # deep copy
    for key, value in overrides.items():
        _set_dotted(cfg, key, value)
    # Keep it under configs/ so the loader's relative-path resolution matches the
    # real configs (data_dir is overridden per-run via PARADIGM_DATA_DIR anyway).
    path = ROOT / "configs" / f"_sweep_{uuid.uuid4().hex[:8]}.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="configs/selftest.yaml", type=Path)
    ap.add_argument("--prompt", default=PROMPT)
    ap.add_argument("--only", default=None, help="comma-separated variant names")
    args = ap.parse_args()

    base_path = (args.base if args.base.is_absolute() else ROOT / args.base).resolve()
    base = yaml.safe_load(base_path.read_text())
    variants = VARIANTS
    if args.only:
        wanted = {s.strip() for s in args.only.split(",")}
        variants = [v for v in VARIANTS if v[0] in wanted]

    print(f"▶ toggle sweep: {len(variants)} variant(s) · base={base_path.name}\n")
    failures = []
    for i, (name, overrides, timeout) in enumerate(variants, 1):
        cfg_path = _write_variant_config(base, overrides)
        try:
            run = _run_cycle(args.prompt, "directed", cfg_path, timeout)
            issues, info = triage(run)
        finally:
            cfg_path.unlink(missing_ok=True)
        verdict = "PASS" if not issues else f"{len(issues)} ISSUE(S)"
        ov = ", ".join(f"{k}={v}" for k, v in overrides.items())
        print(f"[{i:>2}/{len(variants)}] {name:<22} {verdict} · {info['elapsed']:.0f}s · "
              f"status={info['status']} · paper={info['paper_chars']}ch")
        print(f"        ({ov})")
        for sev, detail in issues:
            print(f"        ✗ {sev}: {detail}")
        if issues:
            failures.append(name)
            print(f"        artifacts: {info['data_dir']}")
        for note in info["notes"][:2]:
            print(f"        ~ transient: {note}")
        for swap in info["swaps"]:
            print(f"        · {swap}")
        print(flush=True)

    print(f"== {len(variants)} variant(s), {len(failures)} with issues: {failures or 'none'} ==")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
