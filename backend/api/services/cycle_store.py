"""Persistence for research cycles.

DB-backed when a ``Database`` is available — cycles then survive a restart and
orphaned in-progress runs are flagged ``interrupted`` on startup, so the research
tab is durable and unfinished runs are visible/resumable. Falls back to an
in-memory dict when there's no database (demo / core-unavailable mode), which
preserves the previous behavior.
"""

from __future__ import annotations

from typing import Any

from backend.api.models.research import ResearchCycleResponse


class CycleStore:
    """Thin persistence wrapper over the cycles table (or an in-memory dict)."""

    def __init__(self, database: Any | None) -> None:
        self._db = database
        if database is None:
            # Demo / core-unavailable mode: share the module-level dict the demo
            # paths (papers.py, demo_runner.py) already read/write, so the store
            # and those paths stay consistent without migrating them.
            from backend.api.routes.research import _cycles

            self._mem: dict[str, ResearchCycleResponse] = _cycles
        else:
            self._mem = {}

    @property
    def persistent(self) -> bool:
        return self._db is not None

    @staticmethod
    def _from_row(row: dict[str, Any]) -> ResearchCycleResponse:
        return ResearchCycleResponse(
            cycle_id=row["cycle_id"],
            seed_prompt=row["seed_prompt"],
            mode=row["mode"],
            status=row["status"],
            team_roles=row.get("team_roles"),
            session_id=row.get("session_id"),
            thread_id=row.get("thread_id"),
            paper_id=row.get("paper_id"),
            current_phase=row.get("current_phase"),
            resumed_from=row.get("resumed_from"),
            status_detail=row.get("status_detail"),
            datasets=row.get("datasets"),
            interactive=bool(row.get("interactive") or 0),
            model_tier=row.get("model_tier"),
            created_at=row["created_at"],
            updated_at=row.get("updated_at"),
        )

    def create(self, cycle: ResearchCycleResponse) -> ResearchCycleResponse:
        if self._db is not None:
            self._db.create_cycle(
                cycle.cycle_id,
                cycle.seed_prompt,
                cycle.mode,
                cycle.status.value,
                cycle.team_roles,
                cycle.created_at,
                cycle.resumed_from,
                cycle.interactive,
                cycle.model_tier,
            )
        else:
            self._mem[cycle.cycle_id] = cycle
        return cycle

    def get(self, cycle_id: str) -> ResearchCycleResponse | None:
        if self._db is not None:
            row = self._db.get_cycle(cycle_id)
            return self._from_row(row) if row else None
        return self._mem.get(cycle_id)

    def list(self) -> list[ResearchCycleResponse]:
        if self._db is not None:
            return [self._from_row(r) for r in self._db.list_cycles()]
        return sorted(self._mem.values(), key=lambda c: c.created_at, reverse=True)

    def update(self, cycle_id: str, **fields: Any) -> None:
        # Normalize enum values for the DB / model.
        if "status" in fields and hasattr(fields["status"], "value"):
            fields["status"] = fields["status"].value
        if self._db is not None:
            self._db.update_cycle(cycle_id, **fields)
        else:
            cur = self._mem.get(cycle_id)
            if cur is not None:
                self._mem[cycle_id] = cur.model_copy(update=fields)

    def delete(self, cycle_id: str) -> None:
        if self._db is not None:
            self._db.delete_cycle(cycle_id)
        else:
            self._mem.pop(cycle_id, None)

    def mark_interrupted_on_startup(self) -> int:
        """Flag orphaned running/paused cycles as interrupted. Returns the count."""
        if self._db is not None:
            return self._db.mark_running_cycles_interrupted()
        return 0
