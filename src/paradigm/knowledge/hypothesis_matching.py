"""Pluggable hypothesis de-duplication.

The world model otherwise accretes ~100 near-duplicate hypotheses per cycle (the
agents restate the same idea many ways). De-duplication at creation collapses
that, but it is irreversible mid-cycle — so the matcher is a pluggable seam: the
conservative ``NormalizedMatcher`` (literal restatements only) ships first, and a
paraphrase-aware embedding matcher can drop in later WITHOUT touching callers.

Real-data note (Prompt 207 A/B over data_vm threads): normalized matching catches
only the minority of duplicates that are literal restatements (e.g. 106 → 83);
most are paraphrases, which is exactly why the semantic tier needs this seam.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from paradigm.knowledge.models import Hypothesis


def normalize_statement(statement: str) -> str:
    """Normalize a hypothesis statement for light de-duplication.

    Lowercase + whitespace-collapse — catches case/whitespace restatements.
    """
    return " ".join(statement.lower().split())


class HypothesisMatcher(Protocol):
    """Finds an existing hypothesis that duplicates a candidate statement."""

    def find_duplicate(self, statement: str, existing: Iterable[Hypothesis]) -> str | None:
        """Return the id of an existing hypothesis that duplicates ``statement``.

        Returns None if there is no duplicate (so the caller creates a new one).
        """
        ...


class NormalizedMatcher:
    """Default matcher: exact match on the normalized statement.

    Cheap, deterministic, and conservative — it will not merge paraphrases, which
    is the safe default for an irreversible merge.
    """

    def find_duplicate(self, statement: str, existing: Iterable[Hypothesis]) -> str | None:
        key = normalize_statement(statement)
        if not key:
            return None
        for h in existing:
            if normalize_statement(h.statement) == key:
                return h.id
        return None
