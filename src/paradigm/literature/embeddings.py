"""ChromaDB wrapper for paper embeddings and semantic search."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb

from paradigm.literature.arxiv import ArxivPaper


class EmbeddingStore:
    """Vector store for paper embeddings using ChromaDB."""

    COLLECTION_NAME = "paradigm_papers"

    def __init__(
        self,
        vector_db_path: Path | None = None,
        ephemeral: bool = False,
        collection_name: str | None = None,
    ) -> None:
        """Initialize embedding store.

        Args:
            vector_db_path: Path for persistent ChromaDB storage.
            ephemeral: If True, use in-memory storage (for tests).
            collection_name: Optional custom collection name (useful for test isolation).
        """
        if ephemeral:
            self._client = chromadb.EphemeralClient()
        else:
            if vector_db_path is None:
                raise ValueError("vector_db_path required for persistent storage")
            vector_db_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(vector_db_path))

        self._collection = self._client.get_or_create_collection(
            name=collection_name or self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def add_paper(
        self,
        arxiv_id: str,
        title: str,
        abstract: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add or update a single paper in the embedding store.

        Args:
            arxiv_id: Paper identifier (used as document ID).
            title: Paper title.
            abstract: Paper abstract.
            metadata: Optional metadata dict (values must be str, int, float, or bool).
        """
        document = f"{title}\n\n{abstract}"
        self._collection.upsert(
            ids=[arxiv_id],
            documents=[document],
            metadatas=[metadata] if metadata else None,
        )

    def add_papers(self, papers: list[ArxivPaper]) -> None:
        """Add multiple papers in bulk.

        Args:
            papers: List of ArxivPaper objects to embed.
        """
        if not papers:
            return

        ids = []
        documents = []
        metadatas = []

        for paper in papers:
            ids.append(paper.arxiv_id)
            documents.append(f"{paper.title}\n\n{paper.abstract}")
            metadatas.append(
                {
                    "title": paper.title,
                    "authors": ", ".join(paper.authors),
                    "primary_category": paper.primary_category,
                    "published": paper.published.isoformat(),
                }
            )

        self._collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

    def search(
        self,
        query: str,
        n_results: int = 10,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search for papers by semantic similarity.

        Args:
            query: Search query text.
            n_results: Maximum number of results to return.
            where: Optional ChromaDB filter dict (e.g., {"primary_category": "astro-ph.SR"}).

        Returns:
            List of dicts with keys: arxiv_id, document, score, metadata.
        """
        kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": min(n_results, self._collection.count()) or 1,
        }
        if where:
            kwargs["where"] = where

        results = self._collection.query(**kwargs)

        papers = []
        if results["ids"] and results["ids"][0]:
            for i, arxiv_id in enumerate(results["ids"][0]):
                paper: dict[str, Any] = {"arxiv_id": arxiv_id}
                if results["documents"] and results["documents"][0]:
                    paper["document"] = results["documents"][0][i]
                if results["distances"] and results["distances"][0]:
                    # ChromaDB returns distances; for cosine, lower = more similar
                    paper["score"] = 1.0 - results["distances"][0][i]
                if results["metadatas"] and results["metadatas"][0]:
                    paper["metadata"] = results["metadatas"][0][i]
                papers.append(paper)

        return papers

    def get_paper(self, arxiv_id: str) -> dict[str, Any] | None:
        """Get a specific paper by its ID.

        Args:
            arxiv_id: Paper identifier.

        Returns:
            Dict with paper data, or None if not found.
        """
        result = self._collection.get(ids=[arxiv_id])
        if not result["ids"]:
            return None

        paper: dict[str, Any] = {"arxiv_id": result["ids"][0]}
        if result["documents"]:
            paper["document"] = result["documents"][0]
        if result["metadatas"]:
            paper["metadata"] = result["metadatas"][0]
        return paper

    def delete_paper(self, arxiv_id: str) -> None:
        """Delete a paper from the embedding store.

        Args:
            arxiv_id: Paper identifier to remove.
        """
        self._collection.delete(ids=[arxiv_id])

    def count(self) -> int:
        """Return the number of papers in the store."""
        return self._collection.count()
