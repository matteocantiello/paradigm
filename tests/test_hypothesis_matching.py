"""Tests for pluggable hypothesis de-duplication (C2 step 3)."""

from __future__ import annotations

from paradigm.knowledge.hypothesis_matching import NormalizedMatcher, normalize_statement
from paradigm.knowledge.models import Hypothesis


class TestNormalizeStatement:
    def test_lowercase_and_whitespace_collapse(self):
        assert normalize_statement("  X   Drives   Y  ") == "x drives y"

    def test_blank_normalizes_to_empty(self):
        assert normalize_statement("   ") == ""


class TestNormalizedMatcher:
    def test_matches_case_and_whitespace_variant(self):
        existing = [Hypothesis(id="h1", statement="X drives Y")]
        assert NormalizedMatcher().find_duplicate("  x   DRIVES y ", existing) == "h1"

    def test_no_match_for_distinct(self):
        existing = [Hypothesis(id="h1", statement="X drives Y")]
        assert NormalizedMatcher().find_duplicate("Z blocks W", existing) is None

    def test_blank_candidate_returns_none(self):
        existing = [Hypothesis(id="h1", statement="X drives Y")]
        assert NormalizedMatcher().find_duplicate("   ", existing) is None

    def test_empty_existing_returns_none(self):
        assert NormalizedMatcher().find_duplicate("anything", []) is None

    def test_first_match_wins(self):
        existing = [Hypothesis(id="h1", statement="A"), Hypothesis(id="h2", statement="a")]
        assert NormalizedMatcher().find_duplicate("A", existing) == "h1"


def _fake_embed(texts):
    """Keyword-based fake embedder: paraphrases share a basis vector."""
    out = []
    for t in texts:
        tl = t.lower()
        if "copper" in tl and any(w in tl for w in ("toxic", "harm", "detriment")):
            out.append([1.0, 0.0, 0.0])
        elif "copper" in tl and any(w in tl for w in ("benefi", "protect")):
            out.append([0.0, 1.0, 0.0])
        else:
            out.append([0.0, 0.0, 1.0])
    return out


class TestCosine:
    def test_identical(self):
        from paradigm.knowledge.hypothesis_matching import _cosine

        assert _cosine([1.0, 0.0], [1.0, 0.0]) == 1.0

    def test_orthogonal(self):
        from paradigm.knowledge.hypothesis_matching import _cosine

        assert _cosine([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_zero_vector(self):
        from paradigm.knowledge.hypothesis_matching import _cosine

        assert _cosine([0.0, 0.0], [1.0, 0.0]) == 0.0


class TestEmbeddingMatcher:
    def test_folds_paraphrase(self):
        from paradigm.knowledge.hypothesis_matching import EmbeddingMatcher

        existing = [Hypothesis(id="h1", statement="Copper accumulation is toxic in the brain")]
        m = EmbeddingMatcher(_fake_embed, threshold=0.85)
        # a paraphrase NormalizedMatcher would miss (different words, same meaning vector)
        assert m.find_duplicate("Excess copper is harmful to neurons", existing) == "h1"

    def test_distinct_not_folded(self):
        from paradigm.knowledge.hypothesis_matching import EmbeddingMatcher

        existing = [Hypothesis(id="h1", statement="Copper accumulation is toxic")]
        m = EmbeddingMatcher(_fake_embed, threshold=0.85)
        assert m.find_duplicate("Copper is beneficial and protective", existing) is None

    def test_threshold_respected(self):
        from paradigm.knowledge.hypothesis_matching import EmbeddingMatcher

        def embed(texts):
            return [
                {"cand": [1.0, 0.0], "exist": [0.6, 0.8]}.get(t, [0.0, 0.0, 1.0]) for t in texts
            ]

        existing = [Hypothesis(id="h1", statement="exist")]  # cosine(cand,exist)=0.6
        assert EmbeddingMatcher(embed, threshold=0.85).find_duplicate("cand", existing) is None
        assert EmbeddingMatcher(embed, threshold=0.50).find_duplicate("cand", existing) == "h1"

    def test_blank_and_empty(self):
        from paradigm.knowledge.hypothesis_matching import EmbeddingMatcher

        m = EmbeddingMatcher(_fake_embed)
        assert m.find_duplicate("   ", [Hypothesis(id="h1", statement="x")]) is None
        assert m.find_duplicate("anything", []) is None

    def test_caches_embeddings(self):
        from paradigm.knowledge.hypothesis_matching import EmbeddingMatcher

        calls = []

        def counting_embed(texts):
            calls.append(list(texts))
            return [[1.0, 0.0, 0.0] for _ in texts]

        existing = [Hypothesis(id="h1", statement="A")]
        m = EmbeddingMatcher(counting_embed)
        m.find_duplicate("B", existing)  # embeds B + A
        m.find_duplicate("B", existing)  # both cached -> no new embed
        flat = [t for c in calls for t in c]
        assert flat.count("A") == 1 and flat.count("B") == 1
