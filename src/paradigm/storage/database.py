"""SQLite database management for Paradigm."""

import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Valid SQL identifier pattern — prevents SQL injection via column names.
_SAFE_FIELD_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def _validate_field_names(fields: dict[str, Any]) -> None:
    """Raise ValueError if any field name is not a safe SQL identifier."""
    for name in fields:
        if not _SAFE_FIELD_RE.match(name):
            raise ValueError(f"Invalid field name: {name!r}")


class Database:
    """SQLite database manager for Paradigm."""

    def __init__(self, db_path: Path) -> None:
        """Initialize database connection and create schema.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # The backend shares one connection across concurrent async sessions.
        # WAL allows concurrent readers alongside a writer, and busy_timeout makes
        # a contended write wait (up to 5s) instead of immediately raising
        # "database is locked". Harmless for the single-threaded CLI path.
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA busy_timeout=5000")
        except sqlite3.Error:  # e.g. :memory: or a filesystem that can't WAL
            pass
        self._create_schema()

    @staticmethod
    def _add_columns_if_missing(cursor: Any, table: str, columns: dict[str, str]) -> None:
        """Add columns to ``table`` if absent (idempotent ALTER; literal identifiers only)."""
        cursor.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in cursor.fetchall()}
        for name, coltype in columns.items():
            if name not in existing:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {name} {coltype}")

    def _create_schema(self) -> None:
        """Create database schema if it doesn't exist."""
        cursor = self.conn.cursor()

        # Papers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                abstract TEXT NOT NULL,
                authors TEXT NOT NULL,
                body TEXT NOT NULL,
                keywords TEXT,
                citations TEXT,
                submitted_at DATETIME,
                published_at DATETIME,
                status TEXT NOT NULL,
                review_scores TEXT,
                citation_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Correctness-kernel artifacts (Phase 1B/1D/1E), added idempotently so
        # existing databases pick them up without a migration framework.
        self._add_columns_if_missing(
            cursor,
            "papers",
            {
                "verification": "TEXT",
                "prereg": "TEXT",
                "provenance": "TEXT",
                "topics": "TEXT",
                # Quality ledger: auto-judge scores (JSON, 1-10 per dimension)
                # recorded for every finished paper so quality is trendable.
                "judge_scores": "TEXT",
            },
        )

        # Agents table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                skill_profile TEXT NOT NULL,
                personality TEXT NOT NULL,
                reputation TEXT NOT NULL,
                active_threads TEXT,
                memory_checkpoints TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Research threads table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS threads (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                mode TEXT,
                participants TEXT NOT NULL,
                hypothesis TEXT,
                key_findings TEXT,
                literature_reviewed TEXT,
                experiments_run TEXT,
                open_questions TEXT,
                next_steps TEXT,
                current_phase TEXT,
                checkpoint_summary TEXT,
                current_draft_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Topic tags (broad arXiv-style fields), added idempotently. Stored as a
        # JSON list; classified by an agent at the start (the seed prompt) and
        # refreshed from the finished paper at the end of the cycle.
        self._add_columns_if_missing(
            cursor, "threads", {"topics": "TEXT", "original_prompt": "TEXT"}
        )

        # Research cycles table — the web/research-tab unit of work. Persisted so
        # the research tab survives a restart and orphaned runs can be marked
        # interrupted + later resumed (a cycle owns a thread + an optional paper).
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cycles (
                cycle_id TEXT PRIMARY KEY,
                seed_prompt TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                team_roles TEXT,
                session_id TEXT,
                thread_id TEXT,
                paper_id TEXT,
                current_phase TEXT,
                resumed_from TEXT,
                status_detail TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Added idempotently so existing databases pick up new columns without a
        # migration framework. status_detail = a short human reason for a terminal
        # (failed/aborted) cycle, surfaced in the research-tab UI. datasets = JSON
        # list of uploaded local dataset paths attached to the cycle. interactive =
        # 0/1 flag: the user approves key decisions during the run.
        self._add_columns_if_missing(
            cursor,
            "cycles",
            {
                "resumed_from": "TEXT",
                "status_detail": "TEXT",
                "datasets": "TEXT",
                "interactive": "INTEGER",
                "model_tier": "TEXT",
            },
        )

        # Graveyard table (failed research)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS graveyard (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                failure_reason TEXT,
                lessons_learned TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # NOTE: a legacy ``events`` table (plus idx_events_* indices) used to be
        # created here but was never written to — events live in the JSONL logs.
        # New databases no longer create it; existing databases keep theirs
        # untouched (no migration/drop).

        # Token usage tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                agent_id TEXT,
                thread_id TEXT,
                model TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                cache_read_tokens INTEGER NOT NULL DEFAULT 0,
                cache_write_tokens INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Prompt-cache accounting for pre-existing token_usage tables.
        self._add_columns_if_missing(
            cursor,
            "token_usage",
            {
                "cache_read_tokens": "INTEGER NOT NULL DEFAULT 0",
                "cache_write_tokens": "INTEGER NOT NULL DEFAULT 0",
            },
        )

        # World model snapshots (knowledge architecture)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS world_model_snapshots (
                thread_id TEXT PRIMARY KEY,
                snapshot TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indices for common queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_papers_status ON papers(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_papers_published_at ON papers(published_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_threads_status ON threads(status)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_token_usage_thread_id ON token_usage(thread_id)"
        )

        self.conn.commit()

    def _serialize_json(self, data: dict[str, Any] | list[Any] | None) -> str | None:
        """Serialize data to JSON string."""
        if data is None:
            return None
        return json.dumps(data)

    def _deserialize_json(self, data: str | None) -> dict[str, Any] | list[Any] | None:
        """Deserialize JSON string to data."""
        if data is None:
            return None
        return json.loads(data)

    # Paper operations

    def create_paper(
        self,
        paper_id: str,
        title: str,
        abstract: str,
        authors: list[str],
        body: str,
        status: str = "draft",
        **kwargs: Any,
    ) -> None:
        """Create a new paper.

        Args:
            paper_id: Unique paper ID
            title: Paper title
            abstract: Paper abstract
            authors: List of author agent IDs
            body: Full paper text (markdown)
            status: Paper status (draft, submitted, etc.)
            **kwargs: Additional fields (keywords, citations, etc.)
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO papers (id, title, abstract, authors, body, status, keywords, citations)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paper_id,
                title,
                abstract,
                self._serialize_json(authors),
                body,
                status,
                self._serialize_json(kwargs.get("keywords")),
                self._serialize_json(kwargs.get("citations")),
            ),
        )
        self.conn.commit()

    def get_paper(self, paper_id: str) -> dict[str, Any] | None:
        """Get paper by ID.

        Args:
            paper_id: Paper ID

        Returns:
            Paper data as dict, or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def update_paper(self, paper_id: str, **fields: Any) -> None:
        """Update paper fields.

        Args:
            paper_id: Paper ID
            **fields: Fields to update
        """
        _validate_field_names(fields)
        # Handle JSON fields
        json_fields = [
            "authors",
            "keywords",
            "citations",
            "review_scores",
            "verification",
            "prereg",
            "provenance",
            "topics",
            "judge_scores",
        ]
        for field in json_fields:
            if field in fields and fields[field] is not None:
                fields[field] = self._serialize_json(fields[field])

        set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
        values = list(fields.values()) + [paper_id]

        cursor = self.conn.cursor()
        cursor.execute(
            f"UPDATE papers SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values,
        )
        self.conn.commit()

    def list_papers(
        self, status: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """List papers with optional filtering.

        Args:
            status: Filter by status
            limit: Maximum number of results

        Returns:
            List of paper dicts
        """
        cursor = self.conn.cursor()
        query = "SELECT * FROM papers"
        params: list[Any] = []

        if status:
            query += " WHERE status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def list_threads(self, limit: int | None = None) -> list[dict[str, Any]]:
        """List all research threads (newest first). Raw rows; JSON columns not decoded."""
        cursor = self.conn.cursor()
        query = "SELECT * FROM threads ORDER BY created_at DESC"
        params: list[Any] = []
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_thread_id_for_paper(self, paper_id: str) -> str | None:
        """Return the thread whose current draft is this paper, if any.

        Used by the evaluation harness to attribute token cost to a paper.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id FROM threads WHERE current_draft_id = ? LIMIT 1",
            (paper_id,),
        )
        row = cursor.fetchone()
        return row["id"] if row else None

    # Agent operations

    def create_agent(
        self,
        agent_id: str,
        skill_profile: str,
        personality: dict[str, Any],
        reputation: dict[str, Any] | None = None,
    ) -> None:
        """Create a new agent.

        Args:
            agent_id: Unique agent ID
            skill_profile: Agent skill type
            personality: Personality traits dict
            reputation: Reputation metrics dict
        """
        if reputation is None:
            reputation = {
                "h_index": 0,
                "total_citations": 0,
                "papers_published": 0,
                "reviews_completed": 0,
                "collaboration_score": 0.0,
            }

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO agents (id, skill_profile, personality, reputation, active_threads, memory_checkpoints)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                skill_profile,
                self._serialize_json(personality),
                self._serialize_json(reputation),
                self._serialize_json([]),
                self._serialize_json({}),
            ),
        )
        self.conn.commit()

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        """Get agent by ID.

        Args:
            agent_id: Agent ID

        Returns:
            Agent data as dict, or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def update_agent(self, agent_id: str, **fields: Any) -> None:
        """Update agent fields.

        Args:
            agent_id: Agent ID
            **fields: Fields to update
        """
        _validate_field_names(fields)
        json_fields = ["personality", "reputation", "active_threads", "memory_checkpoints"]
        for field in json_fields:
            if field in fields and fields[field] is not None:
                fields[field] = self._serialize_json(fields[field])

        set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
        values = list(fields.values()) + [agent_id]

        cursor = self.conn.cursor()
        cursor.execute(
            f"UPDATE agents SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values,
        )
        self.conn.commit()

    # Thread operations

    def create_thread(
        self,
        thread_id: str,
        title: str,
        mode: str,
        participants: list[str],
        status: str = "active",
    ) -> None:
        """Create a new research thread.

        Args:
            thread_id: Unique thread ID
            title: Thread title
            mode: Operating mode (directed, explore, etc.)
            participants: List of participant agent IDs
            status: Thread status
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO threads (id, title, status, mode, participants, current_phase,
                                key_findings, literature_reviewed, experiments_run,
                                open_questions, next_steps)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                title,
                status,
                mode,
                self._serialize_json(participants),
                "seeding",
                self._serialize_json([]),
                self._serialize_json([]),
                self._serialize_json([]),
                self._serialize_json([]),
                self._serialize_json([]),
            ),
        )
        self.conn.commit()

    def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        """Get thread by ID.

        Args:
            thread_id: Thread ID

        Returns:
            Thread data as dict, or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM threads WHERE id = ?", (thread_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def update_thread(self, thread_id: str, **fields: Any) -> None:
        """Update thread fields.

        Args:
            thread_id: Thread ID
            **fields: Fields to update
        """
        _validate_field_names(fields)
        json_fields = [
            "participants",
            "key_findings",
            "literature_reviewed",
            "experiments_run",
            "open_questions",
            "next_steps",
            "topics",
        ]
        for field in json_fields:
            if field in fields and fields[field] is not None:
                fields[field] = self._serialize_json(fields[field])

        set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
        values = list(fields.values()) + [thread_id]

        cursor = self.conn.cursor()
        cursor.execute(
            f"UPDATE threads SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values,
        )
        self.conn.commit()

    # Research cycles (web/research-tab persistence)

    def create_cycle(
        self,
        cycle_id: str,
        seed_prompt: str,
        mode: str,
        status: str,
        team_roles: list[str] | None = None,
        created_at: Any | None = None,
        resumed_from: str | None = None,
        interactive: bool = False,
        model_tier: str | None = None,
    ) -> None:
        """Persist a new research cycle."""
        cursor = self.conn.cursor()
        created = (
            created_at.isoformat()
            if hasattr(created_at, "isoformat")
            else str(created_at)
            if created_at is not None
            else None
        )
        if created is not None:
            cursor.execute(
                """
                INSERT INTO cycles
                    (cycle_id, seed_prompt, mode, status, team_roles, resumed_from,
                     interactive, model_tier, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cycle_id,
                    seed_prompt,
                    mode,
                    status,
                    self._serialize_json(team_roles or []),
                    resumed_from,
                    int(interactive),
                    model_tier,
                    created,
                ),
            )
        else:
            cursor.execute(
                """
                INSERT INTO cycles
                    (cycle_id, seed_prompt, mode, status, team_roles, resumed_from,
                     interactive, model_tier)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cycle_id,
                    seed_prompt,
                    mode,
                    status,
                    self._serialize_json(team_roles or []),
                    resumed_from,
                    int(interactive),
                    model_tier,
                ),
            )
        self.conn.commit()

    def _row_to_cycle(self, row: Any) -> dict[str, Any]:
        d = dict(row)
        for key in ("team_roles", "datasets"):
            raw = d.get(key)
            try:
                d[key] = json.loads(raw) if raw else None
            except (TypeError, ValueError):
                d[key] = None
        return d

    def get_cycle(self, cycle_id: str) -> dict[str, Any] | None:
        """Get a cycle by ID (team_roles deserialized to a list)."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM cycles WHERE cycle_id = ?", (cycle_id,))
        row = cursor.fetchone()
        return self._row_to_cycle(row) if row is not None else None

    def list_cycles(self) -> list[dict[str, Any]]:
        """List all cycles, newest first."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM cycles ORDER BY created_at DESC")
        return [self._row_to_cycle(r) for r in cursor.fetchall()]

    def update_cycle(self, cycle_id: str, **fields: Any) -> None:
        """Update cycle fields (team_roles/datasets auto-serialized)."""
        _validate_field_names(fields)
        for key in ("team_roles", "datasets"):
            if key in fields and fields[key] is not None:
                fields[key] = self._serialize_json(fields[key])
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [cycle_id]
        cursor = self.conn.cursor()
        cursor.execute(
            f"UPDATE cycles SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE cycle_id = ?",
            values,
        )
        self.conn.commit()

    def delete_cycle(self, cycle_id: str) -> None:
        """Delete a cycle row."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM cycles WHERE cycle_id = ?", (cycle_id,))
        self.conn.commit()

    def mark_running_cycles_interrupted(self) -> int:
        """On startup, flag orphaned in-progress cycles as interrupted.

        After a restart no session is alive, so any cycle still ``running`` or
        ``paused`` was cut off mid-run — mark it ``interrupted`` so the research
        tab shows it as resumable instead of perpetually "running".
        Returns the number of rows updated.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE cycles SET status = 'interrupted', updated_at = CURRENT_TIMESTAMP "
            "WHERE status IN ('running', 'paused')"
        )
        self.conn.commit()
        return cursor.rowcount

    # Token tracking

    def record_token_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        agent_id: str | None = None,
        thread_id: str | None = None,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> None:
        """Record token usage for an API call.

        Args:
            model: Model used
            input_tokens: UNcached input token count
            output_tokens: Output token count
            agent_id: Agent ID (if applicable)
            thread_id: Thread ID (if applicable)
            cache_read_tokens: Prompt-cache read tokens (billed ~0.1x)
            cache_write_tokens: Prompt-cache write tokens (billed ~1.25x)
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO token_usage
                (timestamp, agent_id, thread_id, model, input_tokens, output_tokens,
                 cache_read_tokens, cache_write_tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(UTC).isoformat(),
                agent_id,
                thread_id,
                model,
                input_tokens,
                output_tokens,
                cache_read_tokens,
                cache_write_tokens,
            ),
        )
        self.conn.commit()

    def get_token_usage(
        self, thread_id: str | None = None, agent_id: str | None = None
    ) -> dict[str, int]:
        """Get token usage statistics.

        Args:
            thread_id: Filter by thread ID
            agent_id: Filter by agent ID

        Returns:
            Dict with input_tokens, output_tokens, total_tokens
        """
        cursor = self.conn.cursor()
        query = (
            "SELECT SUM(input_tokens) as input, SUM(output_tokens) as output, "
            "SUM(cache_read_tokens) as cread, SUM(cache_write_tokens) as cwrite "
            "FROM token_usage WHERE 1=1"
        )
        params: list[Any] = []

        if thread_id:
            query += " AND thread_id = ?"
            params.append(thread_id)
        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id)

        cursor.execute(query, params)
        row = cursor.fetchone()

        input_tokens = row["input"] or 0
        output_tokens = row["output"] or 0
        cache_read = row["cread"] or 0
        cache_write = row["cwrite"] or 0

        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cache_read_tokens": cache_read,
            "cache_write_tokens": cache_write,
        }

    # Graveyard operations

    def add_to_graveyard(
        self,
        graveyard_id: str,
        entry_type: str,
        content: str,
        failure_reason: str | None = None,
        lessons_learned: str | None = None,
    ) -> None:
        """Add a failed research entry to the graveyard.

        Args:
            graveyard_id: Unique ID
            entry_type: Type of failure (rejected_paper, abandoned_thread)
            content: Compressed summary of the content
            failure_reason: Why it failed
            lessons_learned: What to avoid in the future
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO graveyard (id, type, content, failure_reason, lessons_learned)
            VALUES (?, ?, ?, ?, ?)
            """,
            (graveyard_id, entry_type, content, failure_reason, lessons_learned),
        )
        self.conn.commit()

    def search_graveyard(
        self,
        keyword: str | None = None,
        entry_type: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search the graveyard for past failures and lessons learned.

        Args:
            keyword: Optional keyword to search across content,
                failure_reason, and lessons_learned fields.
            entry_type: Optional filter by entry type (e.g. 'rejected_paper').
            limit: Maximum number of results to return.

        Returns:
            List of graveyard entry dicts, most recent first.
        """
        cursor = self.conn.cursor()
        query = "SELECT * FROM graveyard WHERE 1=1"
        params: list[Any] = []

        if keyword:
            query += " AND (content LIKE ? OR failure_reason LIKE ? OR lessons_learned LIKE ?)"
            like_val = f"%{keyword}%"
            params.extend([like_val, like_val, like_val])

        if entry_type:
            query += " AND type = ?"
            params.append(entry_type)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    # World model snapshot operations

    def save_world_model_snapshot(self, thread_id: str, json_str: str) -> None:
        """Save or update a world model snapshot for a thread.

        Args:
            thread_id: Thread ID.
            json_str: JSON-serialized world model.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO world_model_snapshots (thread_id, snapshot, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            (thread_id, json_str),
        )
        self.conn.commit()

    def load_world_model_snapshot(self, thread_id: str) -> str | None:
        """Load a world model snapshot for a thread.

        Args:
            thread_id: Thread ID.

        Returns:
            JSON string, or None if no snapshot exists.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT snapshot FROM world_model_snapshots WHERE thread_id = ?",
            (thread_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return row["snapshot"]

    def close(self) -> None:
        """Close database connection."""
        self.conn.close()

    def __enter__(self) -> "Database":
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()
