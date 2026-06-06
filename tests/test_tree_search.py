"""Tests for Phase 1C — tree-search / step-restart helpers."""

from __future__ import annotations

import random

from paradigm.orchestrator.constants import (
    CodeBlock,
    _best_first_order,
    _extract_code_blocks,
)

# ---------------------------------------------------------------------------
# CodeBlock.restart_at_step parsing
# ---------------------------------------------------------------------------


class TestRestartAtParsing:
    def test_parses_restart_at(self):
        text = "```python\n# EXPERIMENT: resume_fit\n# RESTART_AT: 2\nprint('resuming')\n```"
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0].restart_at_step == 2
        assert blocks[0].name == "resume_fit"

    def test_default_is_zero(self):
        text = "```python\n# EXPERIMENT: fresh\nprint('x')\n```"
        blocks = _extract_code_blocks(text)
        assert blocks[0].restart_at_step == 0


# ---------------------------------------------------------------------------
# _best_first_order
# ---------------------------------------------------------------------------


def _blocks(*specs: tuple[str, tuple[str, ...]]) -> list[CodeBlock]:
    return [CodeBlock(name=n, code=f"# EXPERIMENT: {n}", depends_on=d) for n, d in specs]


class TestBestFirstOrder:
    def test_single_block_unchanged(self):
        blocks = _blocks(("a", ()))
        out = _best_first_order(blocks, set(), 0.3, random.Random(0))
        assert [b.name for b in out] == ["a"]

    def test_respects_dependencies(self):
        blocks = _blocks(("a", ()), ("b", ("a",)), ("c", ()))
        out = _best_first_order(blocks, {"c"}, 0.0, random.Random(1))
        names = [b.name for b in out]
        # b must come after a; all present exactly once
        assert names.index("a") < names.index("b")
        assert sorted(names) == ["a", "b", "c"]

    def test_non_buggy_preferred_when_debug_prob_zero(self):
        # a (clean) and c (buggy) both ready at start; debug_prob=0 → a first.
        blocks = _blocks(("a", ()), ("c", ()))
        out = _best_first_order(blocks, {"c"}, 0.0, random.Random(1))
        assert [b.name for b in out] == ["a", "c"]

    def test_buggy_promoted_when_debug_prob_one(self):
        blocks = _blocks(("a", ()), ("c", ()))
        out = _best_first_order(blocks, {"c"}, 1.0, random.Random(1))
        assert [b.name for b in out] == ["c", "a"]

    def test_buggy_dependency_still_runs_first(self):
        # c is buggy AND a dependency of b → must still run before b even when promoted.
        blocks = _blocks(("c", ()), ("b", ("c",)))
        out = _best_first_order(blocks, {"c"}, 1.0, random.Random(1))
        names = [b.name for b in out]
        assert names.index("c") < names.index("b")

    def test_deterministic_for_same_seed(self):
        blocks = _blocks(("a", ()), ("b", ()), ("c", ()), ("d", ()))
        buggy = {"a", "c"}
        out1 = [b.name for b in _best_first_order(blocks, buggy, 0.5, random.Random(7))]
        out2 = [b.name for b in _best_first_order(blocks, buggy, 0.5, random.Random(7))]
        assert out1 == out2

    def test_cycle_falls_back_to_original(self):
        blocks = _blocks(("a", ("b",)), ("b", ("a",)))
        out = _best_first_order(blocks, set(), 0.3, random.Random(1))
        assert [b.name for b in out] == ["a", "b"]

    def test_no_blocks_dropped(self):
        blocks = _blocks(("a", ()), ("b", ("a",)), ("c", ("a",)), ("d", ("b", "c")))
        out = _best_first_order(blocks, {"b"}, 0.3, random.Random(3))
        assert sorted(b.name for b in out) == ["a", "b", "c", "d"]
        names = [b.name for b in out]
        assert names.index("a") < names.index("d")
        assert names.index("b") < names.index("d")
        assert names.index("c") < names.index("d")
