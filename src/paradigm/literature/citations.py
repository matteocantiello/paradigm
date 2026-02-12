"""Citation tracking and graph queries."""

from __future__ import annotations

from typing import Any

from paradigm.storage.database import Database


class CitationTracker:
    """Tracks citation relationships between papers."""

    def __init__(self, database: Database) -> None:
        """Initialize citation tracker.

        Args:
            database: Database instance for storing citations.
        """
        self._db = database
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create the citations table if it doesn't exist."""
        cursor = self._db.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS citations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                citing_paper_id TEXT NOT NULL,
                cited_paper_id TEXT NOT NULL,
                context TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(citing_paper_id, cited_paper_id)
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_citations_citing ON citations(citing_paper_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_citations_cited ON citations(cited_paper_id)"
        )
        self._db.conn.commit()

    def add_citation(
        self,
        citing_id: str,
        cited_id: str,
        context: str | None = None,
    ) -> None:
        """Record a citation from one paper to another.

        Args:
            citing_id: ID of the paper that contains the citation.
            cited_id: ID of the paper being cited.
            context: Optional text context where the citation appears.
        """
        cursor = self._db.conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO citations (citing_paper_id, cited_paper_id, context) VALUES (?, ?, ?)",
            (citing_id, cited_id, context),
        )
        self._db.conn.commit()

    def add_citations_bulk(self, citations: list[tuple[str, str, str | None]]) -> None:
        """Add multiple citations at once.

        Args:
            citations: List of (citing_id, cited_id, context) tuples.
        """
        cursor = self._db.conn.cursor()
        cursor.executemany(
            "INSERT OR IGNORE INTO citations (citing_paper_id, cited_paper_id, context) VALUES (?, ?, ?)",
            citations,
        )
        self._db.conn.commit()

    def get_references(self, paper_id: str) -> list[dict[str, Any]]:
        """Get papers cited by the given paper.

        Args:
            paper_id: ID of the citing paper.

        Returns:
            List of dicts with cited_paper_id and context.
        """
        cursor = self._db.conn.cursor()
        cursor.execute(
            "SELECT cited_paper_id, context FROM citations WHERE citing_paper_id = ?",
            (paper_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_cited_by(self, paper_id: str) -> list[dict[str, Any]]:
        """Get papers that cite the given paper.

        Args:
            paper_id: ID of the cited paper.

        Returns:
            List of dicts with citing_paper_id and context.
        """
        cursor = self._db.conn.cursor()
        cursor.execute(
            "SELECT citing_paper_id, context FROM citations WHERE cited_paper_id = ?",
            (paper_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_citation_count(self, paper_id: str) -> int:
        """Get number of papers that cite the given paper.

        Args:
            paper_id: ID of the cited paper.

        Returns:
            Citation count.
        """
        cursor = self._db.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM citations WHERE cited_paper_id = ?",
            (paper_id,),
        )
        row = cursor.fetchone()
        return row[0]

    def get_most_cited(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get the most cited papers.

        Args:
            limit: Maximum number of results.

        Returns:
            List of dicts with cited_paper_id and citation_count, ordered by count descending.
        """
        cursor = self._db.conn.cursor()
        cursor.execute(
            """
            SELECT cited_paper_id, COUNT(*) as citation_count
            FROM citations
            GROUP BY cited_paper_id
            ORDER BY citation_count DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]
