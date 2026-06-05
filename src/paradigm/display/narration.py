"""Plain-language narration of research events (Phase B).

Turns a structured event (category + context) into one short, pedagogical
sentence explaining *what is happening and why* — so a viewer learns from
watching the research unfold. Pure, deterministic, dependency-free, and safe
(never raises): importable by both the Rich/CLI display and the WebSocket
adapter.

``narrate()`` is the templated default (zero tokens, zero latency).
``narrate_llm()`` is the seam for an optional LLM mode (wired later).
"""

from __future__ import annotations

from typing import Any

# Why each phase exists — the "so that" behind a transition.
PHASE_PURPOSE: dict[str, str] = {
    "seeding": "gathering background literature to ground the work",
    "ideation": "brainstorming candidate hypotheses to investigate",
    "planning": "turning the most promising idea into a concrete experiment plan",
    "pre_registration": "freezing falsifiable predictions before running anything, so results cannot be reinterpreted after the fact",
    "execution": "running experiments in an isolated sandbox to test the predictions",
    "verification": "re-running the committed code to confirm the reported results reproduce",
    "post_execution": "interpreting what the experiments actually showed",
    "writing": "drafting the paper from the verified findings",
    "internal_review": "self-critiquing the draft before peer review",
    "peer_review": "submitting the paper to independent reviewers",
    "revision": "revising the paper in response to reviewer feedback",
    "published": "finalizing and publishing the paper",
    "complete": "wrapping up the research cycle",
}


def _phase_label(phase: str) -> str:
    return (phase or "").replace("_", " ").strip().lower()


def narrate(
    category: str,
    *,
    phase: str = "",
    agent_id: str = "",
    title: str = "",
    **ctx: Any,
) -> str:
    """Return one pedagogical sentence for an event, or ``""`` if none applies.

    Always safe: unknown categories fall back to ``title`` (or empty), and
    missing context never raises.
    """
    try:
        return _narrate(category, phase=phase, agent_id=agent_id, title=title, **ctx)
    except Exception:  # noqa: BLE001 - narration must never break a caller
        return title or ""


def _narrate(category: str, *, phase: str, agent_id: str, title: str, **ctx: Any) -> str:
    cat = (category or "").lower()
    role = _role_of(agent_id)

    if cat in ("phase", "phase_transition"):
        to_phase = _phase_label(ctx.get("to_phase") or phase)
        purpose = PHASE_PURPOSE.get(to_phase.replace(" ", "_"))
        if purpose:
            return f"Entering {to_phase}: the team is now {purpose}."
        return f"Entering {to_phase}." if to_phase else ""

    if cat in ("round", "round_start"):
        rnd = ctx.get("round_num")
        mx = ctx.get("max_rounds")
        where = _phase_label(phase)
        if rnd and mx:
            return f"Round {rnd} of up to {mx}{f' in {where}' if where else ''} — agents build on each other across rounds."
        return "A new round of agent discussion begins."

    if cat in ("search", "literature", "search_result"):
        n = ctx.get("count")
        q = ctx.get("query")
        if q:
            return f"Searching the literature for “{q}” to see what is already known."
        if n is not None:
            return f"Found {n} related paper(s) — checking prior work avoids reinventing it."
        return "Scanning the literature for relevant prior work."

    if cat in ("debate", "debate_start"):
        challenger = _role_of(ctx.get("challenger_id", ""))
        defender = _role_of(ctx.get("defender_id", ""))
        if challenger and defender:
            return f"The {challenger} is challenging the {defender}'s claim — debate stress-tests which hypothesis survives scrutiny."
        return "A debate begins to stress-test a claim."

    if cat == "debate_complete":
        return "Debate resolved — the stronger argument carries forward."

    if cat in ("experiment_running", "experiment"):
        name = ctx.get("exp_name") or ctx.get("name") or "an experiment"
        return f"Running {name} in an isolated sandbox to test a prediction empirically."

    if cat == "experiment_result":
        name = ctx.get("exp_name") or ctx.get("name") or "the experiment"
        status = (ctx.get("status") or "").lower()
        if status in ("success", "passed", "ok"):
            return f"{name} completed successfully — its output becomes evidence."
        if status:
            return f"{name} finished with status “{status}”."
        return f"{name} finished."

    if cat in ("convergence", "convergence_detected"):
        return "The team converged early, so remaining rounds are skipped to save effort."

    if cat in ("peer_review", "peer_review_decision", "review"):
        decision = (ctx.get("decision") or ctx.get("status") or "").lower()
        if decision:
            return f"Peer review decision: {decision}."
        return "Independent reviewers are evaluating the paper."

    if cat in ("paper", "paper_saved", "paper_published"):
        return "The paper has been written and saved."

    if cat in ("citation", "citation_grounding"):
        n = ctx.get("num_citations")
        if n is not None:
            return f"Grounded {n} citation(s) against real sources to keep claims verifiable."
        return "Grounding citations against real sources."

    if cat in ("novelty", "novelty_check"):
        return "Checking the idea's novelty against existing literature."

    if cat in ("seed", "seed_discovery"):
        n = ctx.get("count")
        if n is not None:
            return f"Seeded the corpus with {n} foundational paper(s) to start from."
        return "Discovering seed papers to ground the investigation."

    if cat in ("agent_step", "agent"):
        if role:
            return f"The {role} finished its turn."
        return ""

    # Unknown category — fall back to the human-provided title.
    return title or ""


def _role_of(agent_id: str) -> str:
    """Best-effort role from an agent id like 'theorist-1' -> 'theorist'."""
    if not agent_id:
        return ""
    return agent_id.split("-")[0]


def narrate_llm(
    provider: Any,
    model: str,
    category: str,
    *,
    phase: str = "",
    agent_id: str = "",
    title: str = "",
    max_tokens: int = 60,
    **ctx: Any,
) -> str:
    """LLM-backed narration (optional, opt-in).

    Seam for a future cheap-model narrator. Until wired, it falls back to the
    deterministic templated narration so enabling ``mode="llm"`` is always safe.
    """
    # TODO(phase-B+): call provider.complete with a tiny prompt for a natural
    # one-liner. For now, defer to the templated narrator (zero cost).
    return narrate(category, phase=phase, agent_id=agent_id, title=title, **ctx)
