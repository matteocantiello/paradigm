#!/usr/bin/env python
"""Phase-0 spike for parallel-branch research (.planning/PARALLEL-BRANCHES.md).

Standalone A/B test — NO engine changes. The empirical question: does fanning out
B diverse ideation "branches" beat N sequential refinement rounds, at comparable
token cost? We isolate the GENERATION strategy by running BOTH through the same
consolidation (converge) step, then have an INDEPENDENT, BLIND judge score the
result.

  Generator:  Gemini (cheap, temperature works for diversity)   [GEMINI_API_KEY]
  Judge:      Claude Sonnet — different family, blind to method  [ANTHROPIC_API_KEY]

  conda run -n paradigm python scripts/branch_spike.py
  conda run -n paradigm python scripts/branch_spike.py --b 8 --rounds 4 --only branch-6,baseline-3

Makes real API calls (a few cents). Keys load from .env.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

from paradigm.agents.providers import AnthropicProvider, OpenAICompatibleProvider  # noqa: E402

load_dotenv()

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"

# Deliberately diverse "lenses" — the branched strategy commits each branch to a
# DIFFERENT framing so the diversity is substantive, not reworded.
_LENSES: list[tuple[str, str]] = [
    ("first-principles", "Reason from first principles / the underlying physical mechanism."),
    ("empirical", "Start from what the observational data would actually show — be data-driven."),
    ("contrarian", "Challenge the premise; suppose the conventional view is wrong."),
    ("cross-disciplinary", "Import a concept or method from a DIFFERENT field by analogy."),
    ("overlooked-variable", "Center a confounder or variable that others ignore."),
    ("limiting-regime", "Use an extreme / scaling / limiting regime where the effect is cleanest."),
    ("falsification", "Design around what would most decisively FALSIFY the leading idea."),
    ("phenomenology", "Start from the observed pattern and work backward to mechanism."),
]

_BASE = (
    "You are a research scientist in an ideation session.\nTopic: {seed}\n\n"
    "Propose 2-3 CONCRETE, TESTABLE hypotheses. For each: state it precisely and name "
    "the observation or experiment that would test it. Be specific and rigorous — avoid "
    "vague or textbook restatements."
)
_LATER = (
    "You are continuing the ideation session.\nTopic: {seed}\n\n"
    "## Hypotheses so far\n{prior}\n\n"
    "Do NOT repeat the above. Add genuinely NEW hypotheses, OR sharpen/critique an "
    "existing one with a specific decisive test. Be concrete."
)
_BRANCH = (
    "You are a research scientist in an ideation session.\nTopic: {seed}\n\n"
    "Adopt THIS lens and commit to it: {lens}\n\n"
    "Through that lens, propose 2-3 CONCRETE, TESTABLE hypotheses. For each: state it "
    "precisely and name the experiment/observation that would test it."
)
_CONSOLIDATE = (
    "You are the research lead consolidating ideas from several independent thinkers.\n"
    "Topic: {seed}\n\n## Candidate hypotheses\n{candidates}\n\n"
    "Select and synthesize the {k} STRONGEST and most genuinely DIVERSE hypotheses "
    "(drop weak or redundant ones). For each survivor: state it crisply and give its "
    "decisive test. Output ONLY the consolidated shortlist."
)
# Diversity-PRESERVING merge: coverage-first, not quality-first. The Phase-0 finding
# was that the naive merge above flattens the branches' diversity; this one is
# structurally biased to keep maximally-different mechanisms.
_CONSOLIDATE_DIV = (
    "You are the research lead choosing which directions to pursue from several "
    "independent explorations.\nTopic: {seed}\n\n## Candidate hypotheses\n{candidates}\n\n"
    "Choose {k} hypotheses that MAXIMIZE COVERAGE of the solution space — they must "
    "rest on genuinely DIFFERENT underlying mechanisms or approaches. Rules:\n"
    "- Treat two hypotheses with the same core mechanism as ONE; keep the stronger and "
    "spend the freed slot on a genuinely different angle.\n"
    "- Prefer a bold, distinct, testable hypothesis over a safe but redundant one.\n"
    "- Your goal is a PORTFOLIO that covers the most ground, NOT the {k} individually "
    "'best' ideas.\n"
    "For each survivor: state it crisply and give its decisive test. Output ONLY the "
    "shortlist."
)
_MERGE_PROMPTS = {"quality": _CONSOLIDATE, "diversity": _CONSOLIDATE_DIV}
_JUDGE = (
    "You are a strict, fair research-methodology referee. You are given a topic and a "
    "set of proposed hypotheses produced by SOME method (you do NOT know which). Score "
    "the SET 1-10 on each axis:\n"
    "- novelty: non-obvious, beyond textbook\n"
    "- testability: clear falsifiable predictions / feasible experiments\n"
    "- specificity: concrete vs vague\n"
    "- breadth: covers genuinely different angles (not variations of one idea)\n"
    "- rigor: sound reasoning, aware of confounders/limitations\n\n"
    "## Topic\n{seed}\n\n## Hypotheses\n{output}\n\n"
    'Respond with ONLY JSON: {{"novelty":N,"testability":N,"specificity":N,'
    '"breadth":N,"rigor":N,"rationale":"one sentence"}}'
)

_DEFAULT_SEEDS = [
    # astro
    "What sets the upper mass limit of stars, and could it depend on metallicity?",
    "Why do some pulsating stars show slow amplitude modulation over years to decades?",
    "What drives the scatter in exoplanet atmospheric metallicity at fixed planet mass?",
    "How does rotation alter the chemical yields a massive star returns to its galaxy?",
    # cross-domain (tests generality — the platform is domain-agnostic)
    "Why do some bacterial populations develop antibiotic tolerance without genetic resistance?",
    "What governs whether a deep neural network generalizes versus memorizes its training data?",
    "What controls the brittle-to-ductile transition in metallic glasses?",
    "Why do some mRNA sequences translate far more efficiently than others encoding the same protein?",
]
_DIMS = ["novelty", "testability", "specificity", "breadth", "rigor"]


@dataclass
class Usage:
    in_tok: int = 0
    out_tok: int = 0

    @property
    def total(self) -> int:
        return self.in_tok + self.out_tok


async def _complete(provider, model, prompt, usage, *, max_tokens=1000, temperature=0.9, system=""):
    sys_prompt = system or "You are a careful, creative research scientist."
    try:
        content, i, o = await asyncio.to_thread(
            provider.complete,
            model=model,
            system=sys_prompt,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception as e:  # noqa: BLE001 — a failed call shouldn't crash the sweep
        print(f"      ! generation error: {str(e)[:120]}", file=sys.stderr)
        return ""
    usage.in_tok += i
    usage.out_tok += o
    return content


async def _candidates_baseline(provider, model, seed, rounds, usage) -> str:
    outs = [await _complete(provider, model, _BASE.format(seed=seed), usage)]
    for _ in range(rounds - 1):
        prior = "\n\n".join(outs)[:6000]
        outs.append(await _complete(provider, model, _LATER.format(seed=seed, prior=prior), usage))
    return "\n\n".join(f"### Round {i + 1}\n{o}" for i, o in enumerate(outs))


async def _candidates_branched(provider, model, seed, b, usage) -> str:
    lenses = _LENSES[:b]
    outs = await asyncio.gather(
        *(
            _complete(provider, model, _BRANCH.format(seed=seed, lens=desc), usage, temperature=1.0)
            for _name, desc in lenses
        )
    )
    return "\n\n".join(f"### {lenses[i][0]}\n{o}" for i, o in enumerate(outs))


async def _consolidate(provider, model, seed, candidates, k, usage, mode="quality") -> str:
    return await _complete(
        provider,
        model,
        _MERGE_PROMPTS[mode].format(seed=seed, candidates=candidates[:12000], k=k),
        usage,
        max_tokens=1500,
        temperature=0.4,
    )


def _parse_scores(raw: str) -> dict | None:
    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        vals = {dim: float(d[dim]) for dim in _DIMS}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
    vals["overall"] = sum(vals[dim] for dim in _DIMS) / len(_DIMS)
    return vals


async def _judge(provider, model, seed, output) -> dict | None:
    raw = await _complete(
        provider,
        model,
        _JUDGE.format(seed=seed, output=(output or "")[:8000]),
        Usage(),  # judge tokens are eval overhead — not counted in strategy cost
        max_tokens=500,
        temperature=0.0,
        system="You are a strict, fair referee. Output only the JSON object.",
    )
    return _parse_scores(raw)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gen-model", default="gemini-2.5-flash-lite")
    ap.add_argument("--judge-model", default="claude-sonnet-4-6")
    ap.add_argument("--b", type=int, default=6, help="branching factor")
    ap.add_argument("--k", type=int, default=3, help="survivors kept after consolidation")
    ap.add_argument("--rounds", type=int, default=3, help="rounds for baseline-N")
    ap.add_argument("--seed", action="append", default=None, help="(repeatable) override seeds")
    ap.add_argument("--only", default=None, help="comma-separated variant names")
    args = ap.parse_args()

    if not os.getenv("GEMINI_API_KEY") or not os.getenv("ANTHROPIC_API_KEY"):
        print(
            "need GEMINI_API_KEY (generator) + ANTHROPIC_API_KEY (judge) in .env", file=sys.stderr
        )
        return 2

    gen = OpenAICompatibleProvider(
        api_key=os.environ["GEMINI_API_KEY"], base_url=_GEMINI_BASE, default_model=args.gen_model
    )
    judge = AnthropicProvider(api_key=os.environ["ANTHROPIC_API_KEY"])
    seeds = args.seed or _DEFAULT_SEEDS

    # (name, kind, param, merge). Branch variants share generated candidates and
    # differ ONLY in the merge — that isolates "is the merge the bottleneck?".
    variants = [
        ("baseline-1", "baseline", 1, "quality"),
        (f"baseline-{args.rounds}", "baseline", args.rounds, "quality"),
        (f"branch-{args.b}", "branched", args.b, "quality"),
        (f"branch-{args.b}-div", "branched", args.b, "diversity"),
    ]
    if args.only:
        wanted = {s.strip() for s in args.only.split(",")}
        variants = [v for v in variants if v[0] in wanted]

    print(
        f"▶ branch spike · gen={args.gen_model} · judge={args.judge_model} · "
        f"{len(seeds)} seed(s) · B={args.b} K={args.k}\n"
    )
    names = [v[0] for v in variants]
    results: dict[str, list[tuple[dict, int]]] = {n: [] for n in names}

    async def run() -> None:
        for si, seed in enumerate(seeds, 1):
            print(f"[{si}/{len(seeds)}] {seed!r}")
            # branched candidates generated ONCE per (seed, B), reused across merges.
            branch_cache: dict[int, tuple[str, int]] = {}
            for name, kind, param, merge in variants:
                cons = Usage()
                t0 = time.monotonic()
                if kind == "baseline":
                    gu = Usage()
                    cands = await _candidates_baseline(gen, args.gen_model, seed, param, gu)
                    gen_tok = gu.total
                else:
                    if param not in branch_cache:
                        gu = Usage()
                        txt = await _candidates_branched(gen, args.gen_model, seed, param, gu)
                        branch_cache[param] = (txt, gu.total)
                    cands, gen_tok = branch_cache[param]
                output = await _consolidate(
                    gen, args.gen_model, seed, cands, args.k, cons, mode=merge
                )
                scores = await _judge(judge, args.judge_model, seed, output)
                total_tok = gen_tok + cons.total
                dt = time.monotonic() - t0
                if scores is None:
                    print(f"    {name:<14} JUDGE PARSE FAIL ({total_tok} tok)")
                    continue
                results[name].append((scores, total_tok))
                print(
                    f"    {name:<14} overall={scores['overall']:.1f}  "
                    f"(nov {scores['novelty']:.0f} test {scores['testability']:.0f} "
                    f"spec {scores['specificity']:.0f} brea {scores['breadth']:.0f} "
                    f"rig {scores['rigor']:.0f})  {total_tok} tok · {dt:.0f}s"
                )
            print()

    asyncio.run(run())

    # --- aggregate ---
    print("== AGGREGATE (mean over seeds) ==")
    header = f"{'variant':<14} {'overall':>7}  " + "  ".join(f"{d[:4]:>4}" for d in _DIMS)
    print(header + f"  {'tokens':>7}  {'q/1k':>5}")
    for name in names:
        rows = results[name]
        if not rows:
            print(f"{name:<14}  (no data)")
            continue
        n = len(rows)
        mean = {d: sum(r[0][d] for r in rows) / n for d in _DIMS}
        overall = sum(r[0]["overall"] for r in rows) / n
        tok = sum(r[1] for r in rows) / n
        q_per_k = overall / (tok / 1000) if tok else 0.0
        dims = "  ".join(f"{mean[d]:>4.1f}" for d in _DIMS)
        print(f"{name:<14} {overall:>7.2f}  {dims}  {tok:>7.0f}  {q_per_k:>5.2f}")

    # verdict
    scored = [(name, results[name]) for name in names if results[name]]
    if scored:
        best_q = max(scored, key=lambda x: sum(r[0]["overall"] for r in x[1]) / len(x[1]))
        best_eff = max(
            scored,
            key=lambda x: (
                (sum(r[0]["overall"] for r in x[1]) / len(x[1]))
                / max(1, sum(r[1] for r in x[1]) / len(x[1]))
            ),
        )
        print(f"\nbest quality: {best_q[0]}   ·   best quality/token: {best_eff[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
