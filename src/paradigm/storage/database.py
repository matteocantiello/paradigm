"""SQLite database management for Paradigm."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


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
        self._create_schema()

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

        # Events table (for structured querying, complements JSONL logs)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                event_type TEXT NOT NULL,
                agent_id TEXT,
                thread_id TEXT,
                phase TEXT,
                content TEXT,
                metadata TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indices for common queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_papers_status ON papers(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_papers_published_at ON papers(published_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_threads_status ON threads(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_thread_id ON events(thread_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type)")
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
        # Handle JSON fields
        json_fields = ["authors", "keywords", "citations", "review_scores"]
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
        json_fields = [
            "participants",
            "key_findings",
            "literature_reviewed",
            "experiments_run",
            "open_questions",
            "next_steps",
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

    # Token tracking

    def record_token_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        agent_id: str | None = None,
        thread_id: str | None = None,
    ) -> None:
        """Record token usage for an API call.

        Args:
            model: Model used
            input_tokens: Input token count
            output_tokens: Output token count
            agent_id: Agent ID (if applicable)
            thread_id: Thread ID (if applicable)
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO token_usage (timestamp, agent_id, thread_id, model, input_tokens, output_tokens)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(UTC).isoformat(),
                agent_id,
                thread_id,
                model,
                input_tokens,
                output_tokens,
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
        query = "SELECT SUM(input_tokens) as input, SUM(output_tokens) as output FROM token_usage WHERE 1=1"
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

        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
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

    def close(self) -> None:
        """Close database connection."""
        self.conn.close()

    def __enter__(self) -> "Database":
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()
