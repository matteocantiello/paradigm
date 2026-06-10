#!/usr/bin/env python3
"""Generate a realistic synthetic event stream for dashboard development.

Produces a compressed ~1-hour research run (a few hundred events) without
spending API tokens:

    python scripts/generate_demo_events.py [out_dir]   # default: data/threads/demo-thread-001
"""

from __future__ import annotations

import json
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

rng = random.Random(42)

AGENTS = [
    "theorist-0",
    "analyst-1",
    "experimentalist-2",
    "synthesizer-3",
    "skeptic-4",
    "writer-5",
    "editor-6",
]

PROMPT = (
    "Why do Cepheid variable stars obey a period-luminosity relation? "
    "Derive the basic physics and test one observational consequence."
)

HYPOTHESES = [
    "The PL relation follows from the pulsation equation: period scales with 1/sqrt(mean density), and density correlates with luminosity along the instability strip.",
    "Metallicity shifts the PL zero-point by changing envelope opacity, producing a measurable offset between Galactic and LMC Cepheids.",
    "The finite width of the instability strip is the dominant intrinsic scatter term in the PL relation at fixed period.",
    "Overtone pulsators contaminate PL samples and steepen the apparent slope at short periods.",
    "Circumstellar dust around long-period Cepheids biases infrared PL calibrations brighter.",
]

CLAIMS = [
    ("Period scales as rho^-1/2 for adiabatic radial pulsation", "agent_reasoning"),
    ("OGLE LMC sample shows PL scatter of 0.15 mag in V", "literature"),
    ("Fundamental and first-overtone sequences separate cleanly in P-L space", "literature"),
    ("Synthetic strip-width model reproduces 0.12 of the 0.15 mag scatter", "experiment"),
    ("Metallicity term estimated at -0.2 mag/dex from two-galaxy comparison", "experiment"),
]

PAPERS = [
    ("2208.10561", "The Cepheid Period-Luminosity Relation: A Review"),
    ("1908.00993", "Calibrating the Distance Ladder with Gaia Parallaxes"),
    ("2103.04539", "Metallicity Effects on Cepheid PL Relations"),
    ("0707.3144", "Theoretical Instability Strip Models for Classical Cepheids"),
    ("1604.01424", "OGLE-IV Catalog of Classical Cepheids in the LMC"),
    ("2012.08534", "Overtone Pulsators in Large Photometric Surveys"),
    ("1011.4909", "Nonlinear Pulsation Models of Cepheids"),
    ("1502.01589", "Dust Around Long-Period Cepheids: Infrared Excesses"),
]

EXPERIMENTS = [
    ("exp_strip_width_scatter", "success"),
    ("exp_pl_slope_fit", "success"),
    ("exp_overtone_contamination", "failure"),
    ("exp_overtone_contamination_v2", "success"),
    ("exp_metallicity_offset", "success"),
]

SECTIONS = [
    ("abstract", "writer-5", 180),
    ("introduction", "writer-5", 640),
    ("methods", "theorist-0", 820),
    ("results", "analyst-1", 910),
    ("discussion", "synthesizer-3", 730),
    ("conclusion", "writer-5", 240),
]


class Stream:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.f = path.open("w", encoding="utf-8")
        self.seq = 0
        self.t = datetime(2026, 6, 9, 14, 0, 0, tzinfo=UTC)
        self.phase: str | None = None
        self.round: int | None = None

    def tick(self, lo: float = 2, hi: float = 30) -> None:
        self.t += timedelta(seconds=rng.uniform(lo, hi))

    def emit(self, etype: str, payload: dict, agent: str | None = None) -> None:
        self.seq += 1
        self.tick()
        self.f.write(
            json.dumps(
                {
                    "seq": self.seq,
                    "ts": self.t.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                    "type": etype,
                    "phase": self.phase,
                    "round": self.round,
                    "agent": agent,
                    "payload": payload,
                }
            )
            + "\n"
        )

    def close(self) -> None:
        self.f.close()


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/threads/demo-thread-001")
    s = Stream(out_dir / "events.jsonl")
    thread_id = out_dir.name

    hyp_ids = [f"h{i:02d}" for i in range(len(HYPOTHESES))]
    claim_ids = [f"c{i:02d}" for i in range(len(CLAIMS))]

    # --- seeding ---
    s.phase = "seeding"
    s.emit(
        "run.started",
        {"thread_id": thread_id, "prompt": PROMPT, "config": {"rounds": 4, "mode": "directed", "agents": AGENTS}},
    )
    s.emit("search.performed", {"query": "[seed discovery]", "n_results": 6, "n_new": 4})

    # --- ideation ---
    s.emit("phase.completed", {"phase": "seeding"})
    s.phase = "ideation"
    s.emit("phase.started", {"phase": "ideation", "rounds_planned": 4})
    paper_pool = list(PAPERS)
    for rnd in range(1, 4):
        s.round = rnd
        s.emit("round.started", {"round": rnd, "active_agents": AGENTS[:5]})
        for agent in AGENTS[:5]:
            if rng.random() < 0.7 and paper_pool:
                n = rng.randint(3, 12)
                s.emit(
                    "search.performed",
                    {"query": f"cepheid {rng.choice(['instability strip', 'metallicity', 'pulsation models', 'PL slope', 'overtone'])}",
                     "n_results": n, "n_new": max(0, n - rng.randint(0, 4))},
                    agent=agent,
                )
            if rng.random() < 0.45 and paper_pool:
                pid, title = paper_pool.pop(0)
                s.emit("paper.read", {"paper_id": pid, "title": title, "chars_read": rng.randint(8000, 30000)}, agent=agent)
                if rng.random() < 0.5:
                    refs = [p[0] for p in rng.sample(PAPERS, k=3)]
                    s.emit(
                        "citation.followed",
                        {"source_paper_id": pid, "direction": rng.choice(["refs", "cited_by"]), "n_found": len(refs), "paper_ids": refs},
                        agent=agent,
                    )
        # hypotheses surface across rounds 1-2
        if rnd <= 2:
            for i in range(rnd * 2 - 2, min(rnd * 2 + 1, len(HYPOTHESES))):
                s.emit(
                    "hypothesis.created",
                    {"hypothesis_id": hyp_ids[i], "statement": HYPOTHESES[i]},
                    agent=rng.choice(AGENTS[:4]),
                )
        if rnd == 2:
            # a debate flares up
            s.emit("debate.started", {"debate_id": "debate-01", "challenger": "skeptic-4", "defender": "theorist-0",
                                      "topic": "Is the strip-width scatter claim falsifiable with the proposed dataset?"})
            for turn, agent in enumerate(["theorist-0", "skeptic-4", "theorist-0"]):
                s.emit("debate.turn", {"debate_id": "debate-01", "summary": f"Turn {turn + 1}: argument about scatter decomposition and sample selection effects..."}, agent=agent)
            s.emit("debate.resolved", {"debate_id": "debate-01", "outcome": "concede_challenger", "winner": "theorist-0", "n_turns": 3})
        s.emit("round.completed", {"round": rnd})
        s.emit("checkpoint.saved", {"phase": "ideation", "label": f"round {rnd}"})
    s.round = None

    # tournament
    matchups = []
    for i in range(len(hyp_ids)):
        for j in range(i + 1, len(hyp_ids)):
            winner = hyp_ids[i] if rng.random() < 0.6 else hyp_ids[j]
            matchups.append([hyp_ids[i], hyp_ids[j], winner])
    s.emit("tournament.round", {"matchups": matchups, "rationales": ["judged on falsifiability and evidence" for _ in matchups]})
    for h in hyp_ids:
        s.emit("hypothesis.updated", {"hypothesis_id": h, "status": "under_investigation", "elo": round(rng.uniform(1430, 1570), 1)})
    for h in hyp_ids[:2]:
        s.emit("hypothesis.updated", {"hypothesis_id": h, "status": "supported", "selected": True})

    # --- planning ---
    s.emit("phase.completed", {"phase": "ideation"})
    s.phase = "planning"
    s.emit("phase.started", {"phase": "planning", "rounds_planned": 4})
    for rnd in range(1, 3):
        s.round = rnd
        s.emit("round.started", {"round": rnd, "active_agents": AGENTS[:5]})
        for i, (text, src) in enumerate(CLAIMS[:3]):
            if rng.random() < 0.5:
                s.emit("claim.extracted", {"claim_id": claim_ids[i], "statement": text, "source": src}, agent=rng.choice(AGENTS[:5]))
        s.emit("round.completed", {"round": rnd})
    s.round = None

    # --- execution ---
    s.emit("phase.completed", {"phase": "planning"})
    s.phase = "execution"
    s.emit("phase.started", {"phase": "execution", "rounds_planned": None})
    for i, (name, status) in enumerate(EXPERIMENTS):
        s.emit("experiment.started", {"experiment_id": name, "title": name.replace("_", " ")}, agent="experimentalist-2")
        s.tick(30, 120)
        artifacts = []
        if status == "success":
            for k in range(rng.randint(1, 2)):
                path = f"executions/demo/{name}_fig{k + 1}.png"
                artifacts.append({"path": path, "kind": "figure"})
                s.emit("artifact.created", {"path": path, "kind": "figure", "experiment_id": name})
        s.emit("experiment.completed", {"experiment_id": name, "status": status, "artifacts": artifacts})
        if status == "success" and i < len(CLAIMS):
            s.emit("claim.extracted", {"claim_id": claim_ids[min(i + 3, len(claim_ids) - 1)], "statement": CLAIMS[min(i + 3, len(CLAIMS) - 1)][0], "source": "experiment"}, agent="experimentalist-2")
    s.emit("hypothesis.updated", {"hypothesis_id": hyp_ids[0], "status": "supported"})
    s.emit("hypothesis.updated", {"hypothesis_id": hyp_ids[3], "status": "contradicted"})
    s.emit("warning.emitted", {"kind": "api_error", "message": "experimentalist-2: transient 503 from provider (retried)"})

    # --- writing ---
    s.emit("phase.completed", {"phase": "execution"})
    s.phase = "writing"
    s.emit("phase.started", {"phase": "writing", "rounds_planned": None})
    for section, author, words in SECTIONS:
        s.tick(20, 90)
        s.emit("section.drafted", {"section": section, "word_count": words}, agent=author)
    s.emit("paper.assembled", {"paper_id": "paper-demo123", "title": "The Physics of the Cepheid Period-Luminosity Relation", "word_count": sum(w for _, _, w in SECTIONS), "n_figures": 5, "n_sections": len(SECTIONS)})

    # --- internal review ---
    s.emit("phase.completed", {"phase": "writing"})
    s.phase = "internal"
    s.emit("phase.started", {"phase": "internal", "rounds_planned": None})
    for it, (rec, changes) in enumerate([("revise", 7), ("revise", 2), ("accept", 0)], start=1):
        s.tick(40, 120)
        s.emit("review.iteration", {"iteration": it, "recommendation": rec, "n_required_changes": changes, "stage": "internal"})

    # --- peer review ---
    s.phase = "peer_review"
    s.emit("phase.started", {"phase": "peer_review", "rounds_planned": None})
    s.emit("review.iteration", {"recommendation": "minor_revision", "n_required_changes": None, "stage": "peer", "n_reviewers": 3})
    s.emit("review.iteration", {"recommendation": "accept", "n_required_changes": None, "stage": "peer", "n_reviewers": 3})
    s.emit("review.final", {"outcome": "accepted", "stage": "peer"})

    s.phase = "published"
    s.emit(
        "run.completed",
        {"status": "published", "paper_id": "paper-demo123", "duration_s": 3420.0,
         "totals": {"searches": 21, "papers_read": 8, "experiments": 5, "debates": 1, "tokens": 1_840_000}},
    )
    s.close()
    print(f"wrote {s.seq} events to {out_dir / 'events.jsonl'}")


if __name__ == "__main__":
    main()
