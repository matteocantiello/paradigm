"""Tests for tolerant LLM-JSON parsing (C2 step 6)."""

from __future__ import annotations

from paradigm.knowledge.json_utils import first_json_array, first_json_object, strip_fences


class TestStripFences:
    def test_plain_unchanged(self):
        assert strip_fences('{"a": 1}') == '{"a": 1}'

    def test_json_fence(self):
        assert strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_bare_fence(self):
        assert strip_fences("```\n[1, 2]\n```") == "[1, 2]"


class TestFirstJsonObject:
    def test_clean(self):
        assert first_json_object('{"winner": "A"}') == {"winner": "A"}

    def test_chatty_preamble(self):
        assert first_json_object('Verdict: {"winner": "B"} done')["winner"] == "B"

    def test_array_is_not_an_object(self):
        assert first_json_object("[1, 2, 3]") is None

    def test_garbage(self):
        assert first_json_object("no json here") is None


class TestFirstJsonArray:
    def test_clean(self):
        assert first_json_array('[{"s": 1}, {"s": 2}]') == [{"s": 1}, {"s": 2}]

    def test_fenced(self):
        assert first_json_array('```json\n[{"s": 1}]\n```') == [{"s": 1}]

    def test_truncated_salvages_complete_leading_objects(self):
        # Cut off mid-3rd object (no closing ]) — recover the first two.
        raw = '[{"statement": "a", "rationale": "x"}, {"statement": "b"}, {"statement": "c'
        assert first_json_array(raw) == [
            {"statement": "a", "rationale": "x"},
            {"statement": "b"},
        ]

    def test_truncated_mid_string(self):
        raw = '[{"statement": "first"}, {"statement": "second is very long and gets cut'
        assert first_json_array(raw) == [{"statement": "first"}]

    def test_no_array_returns_none(self):
        assert first_json_array("just prose, no array") is None

    def test_unsalvageable_returns_none(self):
        assert first_json_array("[ {incomplete") is None
