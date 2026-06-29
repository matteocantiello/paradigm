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
