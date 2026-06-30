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

import math
from collections.abc import Callable, Iterable
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


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class EmbeddingMatcher:
    """Semantic de-dup via cosine similarity over sentence embeddings.

    Catches paraphrases the ``NormalizedMatcher`` misses (real data: 53 created →
    only 2 literal-restatement merges). The embedder is INJECTED (``embed_fn``) so
    the matcher is testable without loading a model and so the encoder can be
    swapped. Vectors are cached by statement (hypotheses are immutable once
    created), keeping a cycle's dedup ~O(n) embeds total rather than O(n²).
    """

    def __init__(
        self,
        embed_fn: Callable[[list[str]], list[list[float]]],
        *,
        threshold: float = 0.85,
    ) -> None:
        self._embed = embed_fn
        self._threshold = threshold
        self._cache: dict[str, list[float]] = {}

    def _ensure(self, texts: list[str]) -> None:
        missing = [t for t in dict.fromkeys(texts) if t and t not in self._cache]
        if missing:
            for t, v in zip(missing, self._embed(missing), strict=True):
                self._cache[t] = list(v)

    def find_duplicate(self, statement: str, existing: Iterable[Hypothesis]) -> str | None:
        s = statement.strip()
        if not s:
            return None
        candidates = [h for h in existing if h.statement.strip()]
        self._ensure([s] + [h.statement for h in candidates])
        cand_vec = self._cache.get(s)
        if not cand_vec:
            return None
        best_id: str | None = None
        best_sim = self._threshold
        for h in candidates:
            vec = self._cache.get(h.statement)
            if not vec:
                continue
            sim = _cosine(cand_vec, vec)
            if sim >= best_sim:
                best_sim = sim
                best_id = h.id
        return best_id


def default_embed_fn() -> Callable[[list[str]], list[list[float]]]:
    """Build the embedder ChromaDB uses (all-MiniLM-L6-v2) as a plain callable.

    Imported + constructed lazily by the caller so importing this module never
    loads a model. Reuses Chroma's default so hypothesis embeddings match the
    paper-embedding space already in the system.
    """
    from chromadb.utils import embedding_functions

    ef = embedding_functions.DefaultEmbeddingFunction()

    def embed(texts: list[str]) -> list[list[float]]:
        return [list(v) for v in ef(texts)]

    return embed
