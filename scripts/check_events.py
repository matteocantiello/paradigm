#!/usr/bin/env python3
"""Validate a per-thread dashboard event stream (events.jsonl).

Usage:
    python scripts/check_events.py data/threads/<thread-id>/events.jsonl
    python scripts/check_events.py <thread-id>          # resolves under data/threads/

Checks: every line parses as JSON, the envelope is complete, seq starts at 1
and increases strictly monotonically, and timestamps parse. Prints an event
type histogram. Exits non-zero on any violation.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ENVELOPE_KEYS = {"seq", "ts", "type", "phase", "round", "agent", "payload"}

KNOWN_TYPES = {
    "run.started",
    "run.completed",
    "phase.started",
    "phase.completed",
    "round.started",
    "round.completed",
    "checkpoint.saved",
    "resource.ingested",
    "search.performed",
    "paper.read",
    "citation.followed",
    "paper.flagged_relevant",
    "hypothesis.created",
    "hypothesis.updated",
    "tournament.round",
    "claim.extracted",
    "evidence.linked",
    "debate.started",
    "debate.turn",
    "debate.resolved",
    "experiment.started",
    "experiment.completed",
    "artifact.created",
    "section.drafted",
    "paper.assembled",
    "review.iteration",
    "review.final",
    "warning.emitted",
}


def resolve_path(arg: str) -> Path:
    p = Path(arg)
    if p.is_file():
        return p
    candidate = Path("data/threads") / arg / "events.jsonl"
    if candidate.is_file():
        return candidate
    print(f"error: no events file at {p} or {candidate}", file=sys.stderr)
    sys.exit(2)


def check(path: Path) -> int:
    errors: list[str] = []
    histogram: Counter[str] = Counter()
    prev_seq = 0
    n_lines = 0

    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            n_lines += 1
            try:
                event = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"line {lineno}: unparseable JSON ({e})")
                continue

            missing = ENVELOPE_KEYS - set(event)
            if missing:
                errors.append(f"line {lineno}: missing envelope keys {sorted(missing)}")

            seq = event.get("seq")
            if not isinstance(seq, int):
                errors.append(f"line {lineno}: seq is not an int: {seq!r}")
            else:
                if prev_seq == 0 and seq != 1:
                    errors.append(f"line {lineno}: seq starts at {seq}, expected 1")
                elif seq <= prev_seq:
                    errors.append(f"line {lineno}: seq {seq} not > previous {prev_seq}")
                prev_seq = max(prev_seq, seq if isinstance(seq, int) else prev_seq)

            ts = event.get("ts")
            if isinstance(ts, str):
                try:
                    datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    errors.append(f"line {lineno}: unparseable ts {ts!r}")
            else:
                errors.append(f"line {lineno}: ts is not a string: {ts!r}")

            etype = event.get("type")
            if not isinstance(etype, str) or not etype:
                errors.append(f"line {lineno}: bad type {etype!r}")
            else:
                histogram[etype] += 1
                if etype not in KNOWN_TYPES:
                    print(f"warning: line {lineno}: unknown event type {etype!r}")

            if not isinstance(event.get("payload"), dict):
                errors.append(f"line {lineno}: payload is not an object")

    print(f"\n{path}: {n_lines} events, seq 1..{prev_seq}")
    for etype, count in histogram.most_common():
        print(f"  {count:>5}  {etype}")

    if errors:
        print(f"\n{len(errors)} violation(s):", file=sys.stderr)
        for e in errors[:50]:
            print(f"  {e}", file=sys.stderr)
        if len(errors) > 50:
            print(f"  ... and {len(errors) - 50} more", file=sys.stderr)
        return 1
    print("\nOK: schema valid, seq strictly monotone, all lines parseable")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    return check(resolve_path(sys.argv[1]))


if __name__ == "__main__":
    sys.exit(main())
