"""Hybrid human-gate logic (Phase 1E).

Autonomous by default. When enabled, named gate points (problem selection,
pre-registration, final verification) consult the human via the existing
``InterventionHook``. Three modes:

- ``off``      — always continue (no behavior change).
- ``advisory`` — surface the decision payload but never block (cannot deadlock
  an autonomous run).
- ``blocking`` — defer to the intervention hook; if NO hook is registered (fully
  autonomous, no human present), fall back to continue with a logged reason
  rather than hanging (explicit deadlock guard).

Pure functions so the gate + provenance logic is unit-testable without the engine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from paradigm.knowledge.models import ProvenanceRecord

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from paradigm.knowledge.models import PredictionRule, VerificationRecord

_VALID = ("continue", "pause", "abort")


def decide_human_gate(
    mode: str,
    points: Sequence[str],
    point: str,
    hook: Callable[[str, str, str], str] | None,
    thread_id: str,
) -> tuple[str, str]:
    """Decide whether to continue/pause/abort at a named human gate point.

    Args:
        mode: ``off`` | ``advisory`` | ``blocking``.
        points: Enabled gate-point names.
        point: The current gate point.
        hook: Optional intervention hook ``(thread_id, from, to) -> decision``.
        thread_id: Current thread id (passed to the hook).

    Returns:
        ``(decision, reason)`` where decision is one of continue/pause/abort.
    """
    if mode == "off" or point not in points:
        return "continue", "gate disabled"
    if mode == "advisory":
        return "continue", "advisory (not blocking)"
    # blocking
    if hook is None:
        return "continue", "blocking but no intervention hook registered (deadlock guard)"
    result = hook(thread_id, point, point)
    if result not in _VALID:
        result = "continue"
    return result, "human decision"


def build_provenance(
    *,
    paper_id: str,
    thread_id: str,
    mode: str,
    gate_decisions: dict[str, str],
    registered_rules: Sequence[PredictionRule],
    verification_records: Sequence[VerificationRecord],
) -> ProvenanceRecord:
    """Assemble the human-vs-agent provenance record for a paper.

    All fields are derived from engine-tracked state, never from agent output.
    """
    human_involved = mode == "blocking"
    framed_by = "human" if (human_involved and "problem_selection" in gate_decisions) else "agents"
    registered_by = "agents" if registered_rules else "none"

    verified: list[str] = []
    if verification_records:
        verified.append("kernel")
    if human_involved and "final_verification" in gate_decisions:
        verified.append("human")
    verified_by = "+".join(verified) if verified else "none"

    accepted = sum(1 for r in verification_records if r.status == "accepted")
    return ProvenanceRecord(
        paper_id=paper_id,
        thread_id=thread_id,
        framed_by=framed_by,
        registered_by=registered_by,
        verified_by=verified_by,
        human_gate_mode=mode,
        gate_decisions=dict(gate_decisions),
        prereg_rule_ids=[r.id for r in registered_rules],
        verification_summary={"accepted": str(accepted), "total": str(len(verification_records))},
    )
