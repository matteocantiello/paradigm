"""Tolerant parsing of LLM JSON output.

LLM responses get truncated at ``max_tokens`` (cut off mid-element, no closing
bracket), wrapped in markdown fences, or surrounded by prose — so a naive
``json.loads`` fails (the ~75 ``JSONDecodeError``s seen in production). These
helpers recover what they can; callers layer domain-specific regex fallbacks on
top (e.g. the tournament judge salvages winner+reasoning from a truncated object).
"""

from __future__ import annotations

import json
import re

_FIRST_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)
_FIRST_ARR_RE = re.compile(r"\[.*\]", re.DOTALL)


def strip_fences(text: str) -> str:
    """Strip a leading/trailing markdown code fence from an LLM response."""
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1] if "\n" in s else ""
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s.strip()


def first_json_object(text: str) -> dict | None:
    """Return the first complete, parseable JSON object in ``text``, or None.

    Robust to code fences, chatty preamble ("Here is my verdict: {...}"),
    reasoning-model prose that itself contains braces, and truncation: after the
    greedy region fails, salvage the first complete top-level ``{...}`` via a
    brace-balanced, string-aware scan (the same recovery ``first_json_array`` uses).
    This is what a thinking judge needs — it may wrap the JSON in ``<thinking>``
    prose whose stray braces defeat the greedy match.
    """
    s = strip_fences(text)
    m = _FIRST_OBJ_RE.search(s)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    start = s.find("{")
    if start == -1:
        return None
    salvaged = _salvage_objects(s[start:])
    return salvaged[0] if salvaged else None


def first_json_array(text: str) -> list | None:
    """Return the first JSON array in ``text``, with truncation recovery.

    Tries a clean parse of the bracketed region first; if that fails (e.g. the
    array was cut off mid-element at ``max_tokens``, so there's no closing ``]``),
    salvages the complete leading top-level objects after the first ``[``. Returns
    None only when nothing parses.
    """
    s = strip_fences(text)
    m = _FIRST_ARR_RE.search(s)
    if m:
        try:
            arr = json.loads(m.group(0))
            if isinstance(arr, list):
                return arr
        except json.JSONDecodeError:
            pass
    start = s.find("[")
    if start == -1:
        return None
    salvaged = _salvage_objects(s[start + 1 :])
    return salvaged or None


def _salvage_objects(text: str) -> list[dict]:
    """Parse the complete top-level ``{...}`` objects in ``text``.

    A trailing incomplete object (the truncation point) is ignored. So
    ``{...}, {...}, {...`` yields the first two.
    """
    objs: list[dict] = []
    depth = 0
    start: int | None = None
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    parsed = json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict):
                    objs.append(parsed)
                start = None
    return objs
