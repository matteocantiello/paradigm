"""Per-thread, seq-ordered JSONL event stream for the research dashboard.

Each research cycle writes an append-only ``events.jsonl`` under
``data/threads/<thread_id>/``. Every line is one event with a common envelope:

    {"seq": 142, "ts": "...", "type": "hypothesis.created",
     "phase": "ideation", "round": 2, "agent": "theorist-0", "payload": {...}}

- ``seq`` is a monotonically increasing integer, unique within a run; consumers
  order by ``seq``, never by timestamp.
- ``agent`` is None for engine-level events (phase changes, checkpoints).
- Events are facts about the research, not UI instructions. The file doubles as
  a provenance record, so payload text is not pre-truncated below ~2000 chars.
- Emission must never interrupt a run: any write problem is noted once on
  stderr and the cycle continues.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

_UNSET: Any = object()


class ResearchEventStream:
    """Append-only JSONL writer with a per-run sequence counter.

    The stream carries the current phase/round as context so emit calls at the
    call sites stay one-liners. Writes are flushed immediately (the file is
    read incrementally in live mode).
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._seq = 0
        self._phase: str | None = None
        self._round: int | None = None
        self._handle: TextIO | None = None
        self._warned = False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                self._seq = self._last_seq(self.path)
            self._handle = self.path.open("a", encoding="utf-8")
        except Exception as e:  # never let the stream break a run
            self._note_failure(e)

    @staticmethod
    def _last_seq(path: Path) -> int:
        """Continue the counter when re-opening an existing stream (resume)."""
        last = 0
        try:
            with path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    last += 1
                    try:
                        last = max(last, int(json.loads(line).get("seq", 0)))
                    except (ValueError, TypeError):
                        pass
        except Exception:
            return last
        return last

    def set_context(self, *, phase: str | None = _UNSET, round_num: int | None = _UNSET) -> None:
        """Update the phase/round stamped on subsequent events."""
        if phase is not _UNSET:
            self._phase = phase
        if round_num is not _UNSET:
            self._round = round_num

    def emit(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        agent: str | None = None,
    ) -> None:
        """Append one event. Never raises."""
        if self._handle is None:
            return
        self._seq += 1
        event = {
            "seq": self._seq,
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "type": event_type,
            "phase": self._phase,
            "round": self._round,
            "agent": agent,
            "payload": payload or {},
        }
        try:
            self._handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
            self._handle.flush()
        except Exception as e:
            self._note_failure(e)

    def close(self) -> None:
        """Close the underlying file handle (best-effort)."""
        if self._handle is not None:
            try:
                self._handle.close()
            except Exception:
                pass
            self._handle = None

    def _note_failure(self, error: Exception) -> None:
        self._handle = None
        if not self._warned:
            self._warned = True
            print(f"[paradigm] event stream disabled ({self.path}): {error}", file=sys.stderr)
