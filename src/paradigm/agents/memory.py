"""Agent episodic memory: cross-cycle learning via semantic retrieval with recency decay."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import chromadb
from pydantic import BaseModel, Field

from paradigm.agents.base import Agent

# Reflection prompt template for generating memories from a research cycle
_REFLECTION_PROMPT = """\
You are reflecting on a completed research cycle to extract lessons for future work.

**Research topic:** {seed_prompt}
**Outcome:** {outcome_summary}
**Your role:** {agent_role}

Below are the messages you contributed during this cycle:

{agent_messages}

---

Extract 3-5 concise memories from this cycle. Each memory should be a single, \
actionable lesson — something that would help you (or a future agent in your role) \
perform better next time.

Categorize each memory as one of:
- **insight**: A factual discovery or key finding
- **mistake**: An approach that failed or was unproductive
- **strategy**: A methodological approach that worked well
- **collaboration**: A lesson about working with other agents

Respond in this exact format (one per line, no extra text):

[type] memory text
[type] memory text
...

Example:
[insight] The period-luminosity relation breaks down for overtone pulsators
[mistake] Fitting a single power law to multi-modal data obscured the bimodal structure
[strategy] Starting with a literature survey before proposing hypotheses saved rework
[collaboration] The skeptic's early pushback on sample selection improved final results

Also provide a 1-2 sentence summary of the cycle on the last line, prefixed with SUMMARY:

SUMMARY: your summary here
"""

VALID_MEMORY_TYPES = {"insight", "mistake", "strategy", "collaboration"}


class Memory(BaseModel):
    """A single episodic memory for an agent."""

    id: str = Field(default_factory=lambda: f"mem-{uuid.uuid4().hex[:12]}")
    agent_id: str
    thread_id: str
    memory_type: str  # "insight" | "mistake" | "strategy" | "collaboration"
    content: str
    topic_keywords: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReflectionResult(BaseModel):
    """Result of a reflection call for one agent."""

    agent_id: str
    memories: list[Memory]
    summary: str


class AgentMemoryStore:
    """ChromaDB-backed store for agent episodic memories."""

    def __init__(
        self,
        vector_db_path: Path | None = None,
        ephemeral: bool = False,
        collection_name: str = "agent_memories",
    ) -> None:
        """Initialize memory store.

        Args:
            vector_db_path: Path for persistent ChromaDB storage.
            ephemeral: If True, use in-memory storage (for tests).
            collection_name: ChromaDB collection name.
        """
        if ephemeral:
            self._client = chromadb.EphemeralClient()
        else:
            if vector_db_path is None:
                raise ValueError("vector_db_path required for persistent storage")
            vector_db_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(vector_db_path))

        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_memory(self, memory: Memory) -> None:
        """Add a single memory to the store."""
        document = f"[{memory.memory_type}] {memory.content}"
        metadata: dict[str, Any] = {
            "agent_id": memory.agent_id,
            "memory_type": memory.memory_type,
            "thread_id": memory.thread_id,
            "created_at": memory.created_at.isoformat(),
            "created_at_epoch": memory.created_at.timestamp(),
        }
        self._collection.upsert(
            ids=[memory.id],
            documents=[document],
            metadatas=[metadata],
        )

    def add_memories(self, memories: list[Memory]) -> None:
        """Add multiple memories in bulk."""
        if not memories:
            return
        ids = []
        documents = []
        metadatas = []
        for m in memories:
            ids.append(m.id)
            documents.append(f"[{m.memory_type}] {m.content}")
            metadatas.append(
                {
                    "agent_id": m.agent_id,
                    "memory_type": m.memory_type,
                    "thread_id": m.thread_id,
                    "created_at": m.created_at.isoformat(),
                    "created_at_epoch": m.created_at.timestamp(),
                }
            )
        self._collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def search(
        self,
        query: str,
        agent_id: str | None = None,
        n_results: int = 20,
        memory_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search for memories.

        Args:
            query: Search query text.
            agent_id: Filter to a specific agent.
            n_results: Maximum results to return.
            memory_type: Filter by memory type.

        Returns:
            List of dicts with keys: id, document, score, metadata.
        """
        where_clauses: list[dict[str, Any]] = []
        if agent_id:
            where_clauses.append({"agent_id": agent_id})
        if memory_type:
            where_clauses.append({"memory_type": memory_type})

        where: dict[str, Any] | None = None
        if len(where_clauses) == 1:
            where = where_clauses[0]
        elif len(where_clauses) > 1:
            where = {"$and": where_clauses}

        count = self._collection.count()
        if count == 0:
            return []

        kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": min(n_results, count),
        }
        if where:
            kwargs["where"] = where

        results = self._collection.query(**kwargs)

        memories = []
        if results["ids"] and results["ids"][0]:
            for i, mem_id in enumerate(results["ids"][0]):
                entry: dict[str, Any] = {"id": mem_id}
                if results["documents"] and results["documents"][0]:
                    entry["document"] = results["documents"][0][i]
                if results["distances"] and results["distances"][0]:
                    entry["score"] = 1.0 - results["distances"][0][i]
                if results["metadatas"] and results["metadatas"][0]:
                    entry["metadata"] = results["metadatas"][0][i]
                memories.append(entry)
        return memories

    def get_memories_for_agent(self, agent_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Get all memories for an agent, sorted by recency (newest first).

        Args:
            agent_id: Agent identifier.
            limit: Maximum memories to return.

        Returns:
            List of memory dicts.
        """
        count = self._collection.count()
        if count == 0:
            return []

        results = self._collection.get(
            where={"agent_id": agent_id},
            limit=limit,
        )

        memories = []
        if results["ids"]:
            for i, mem_id in enumerate(results["ids"]):
                entry: dict[str, Any] = {"id": mem_id}
                if results["documents"]:
                    entry["document"] = results["documents"][i]
                if results["metadatas"]:
                    entry["metadata"] = results["metadatas"][i]
                memories.append(entry)

        # Sort by created_at_epoch descending (newest first)
        memories.sort(
            key=lambda m: m.get("metadata", {}).get("created_at_epoch", 0),
            reverse=True,
        )
        return memories

    def delete_older_than(self, cutoff: datetime) -> int:
        """Delete memories older than a cutoff date.

        Args:
            cutoff: Delete memories created before this time.

        Returns:
            Number of memories deleted.
        """
        cutoff_epoch = cutoff.timestamp()
        results = self._collection.get(
            where={"created_at_epoch": {"$lt": cutoff_epoch}},
        )
        if not results["ids"]:
            return 0
        count = len(results["ids"])
        self._collection.delete(ids=results["ids"])
        return count

    def count(self) -> int:
        """Return the total number of memories."""
        return self._collection.count()


# ---------------------------------------------------------------------------
# Recency decay scoring
# ---------------------------------------------------------------------------


def compute_recency_weight(
    created_at_epoch: float,
    now_epoch: float,
    half_life_days: float = 30.0,
) -> float:
    """Compute exponential recency weight for a memory.

    Args:
        created_at_epoch: Memory creation time (Unix epoch).
        now_epoch: Current time (Unix epoch).
        half_life_days: Half-life in days for decay.

    Returns:
        Weight between 0 and 1 (1 = brand new, 0.5 = one half-life old).
    """
    age_days = max(0.0, now_epoch - created_at_epoch) / 86400.0
    return 0.5 ** (age_days / half_life_days)


def rank_memories_with_recency(
    search_results: list[dict[str, Any]],
    half_life_days: float = 30.0,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Re-rank search results by combined similarity × recency score.

    Args:
        search_results: Raw results from AgentMemoryStore.search().
        half_life_days: Recency half-life in days.
        top_k: Number of top results to return.

    Returns:
        Top-k results sorted by combined score, each with added 'combined_score'
        and 'recency_weight' keys.
    """
    now_epoch = datetime.now(UTC).timestamp()

    for result in search_results:
        similarity = result.get("score", 0.0)
        created_epoch = result.get("metadata", {}).get("created_at_epoch", now_epoch)
        recency = compute_recency_weight(created_epoch, now_epoch, half_life_days)
        result["recency_weight"] = recency
        result["combined_score"] = similarity * recency

    search_results.sort(key=lambda r: r.get("combined_score", 0.0), reverse=True)
    return search_results[:top_k]


# ---------------------------------------------------------------------------
# Context formatting
# ---------------------------------------------------------------------------


def format_memory_context(memories: list[dict[str, Any]], max_chars: int = 2000) -> str:
    """Format ranked memories into a context string for agent prompts.

    Args:
        memories: Ranked memory dicts (from rank_memories_with_recency).
        max_chars: Maximum character length for the output.

    Returns:
        Formatted context string, or "" if no memories.
    """
    if not memories:
        return ""

    lines = [
        "## Agent Memory\n",
        "Relevant lessons from your previous research cycles:\n",
    ]

    for m in memories:
        meta = m.get("metadata", {})
        mem_type = meta.get("memory_type", "unknown")
        created = meta.get("created_at", "")[:10]  # YYYY-MM-DD
        score = m.get("combined_score", m.get("score", 0.0))

        # Extract content from document (strip type prefix)
        doc = m.get("document", "")
        content = doc
        if doc.startswith("[") and "] " in doc:
            content = doc.split("] ", 1)[1]

        line = f"- **[{mem_type}]** ({created}, relevance: {score:.2f}) {content}"
        lines.append(line)

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars].rsplit("\n", 1)[0] + "\n- *(truncated)*"
    return text


# ---------------------------------------------------------------------------
# Reflection generation
# ---------------------------------------------------------------------------


def _parse_reflection_response(
    text: str,
    agent_id: str,
    thread_id: str,
) -> ReflectionResult:
    """Parse Claude's reflection response into structured memories.

    Args:
        text: Raw text response from Claude.
        agent_id: Agent identifier.
        thread_id: Thread identifier.

    Returns:
        ReflectionResult with parsed memories and summary.
    """
    memories: list[Memory] = []
    summary = ""

    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue

        # Parse summary line
        if line.upper().startswith("SUMMARY:"):
            summary = line.split(":", 1)[1].strip()
            continue

        # Parse memory lines: [type] content
        if line.startswith("[") and "] " in line:
            bracket_end = line.index("]")
            mem_type = line[1:bracket_end].strip().lower()
            content = line[bracket_end + 2 :].strip()

            if mem_type in VALID_MEMORY_TYPES and content:
                memories.append(
                    Memory(
                        agent_id=agent_id,
                        thread_id=thread_id,
                        memory_type=mem_type,
                        content=content,
                    )
                )

    return ReflectionResult(agent_id=agent_id, memories=memories, summary=summary)


async def generate_reflections(
    agents: dict[str, Agent],
    messages: list[dict[str, Any]],
    seed_prompt: str,
    thread_id: str,
    outcome_summary: str,
    provider: Any,
    model: str = "claude-sonnet-4-5-20250929",
    database: Any | None = None,
) -> list[ReflectionResult]:
    """Generate episodic memories via reflection for each agent that contributed.

    Args:
        agents: Dict of agent_id -> Agent.
        messages: All messages from the research cycle.
        seed_prompt: The original research prompt.
        thread_id: Thread identifier.
        outcome_summary: Brief description of cycle outcome.
        provider: LLMProvider instance for reflection calls.
        model: Model to use for reflection calls.
        database: Optional Database for token tracking.

    Returns:
        List of ReflectionResult (one per agent that contributed).
    """
    results: list[ReflectionResult] = []

    for agent_id, agent in agents.items():
        # Collect messages from this agent
        agent_msgs = [m for m in messages if m.get("from") == agent_id]
        if not agent_msgs:
            continue

        # Format agent messages for the prompt
        formatted = []
        for m in agent_msgs:
            msg_type = m.get("type", "message")
            content = m.get("content", "")
            if isinstance(content, str):
                formatted.append(f"[{msg_type}] {content[:500]}")
        agent_messages_text = "\n\n".join(formatted)

        prompt = _REFLECTION_PROMPT.format(
            seed_prompt=seed_prompt,
            outcome_summary=outcome_summary,
            agent_role=agent.skill_profile,
            agent_messages=agent_messages_text,
        )

        try:
            text, input_tokens, output_tokens = await asyncio.to_thread(
                provider.complete,
                model=model,
                max_tokens=1024,
                temperature=0.3,
                system="",
                messages=[{"role": "user", "content": prompt}],
            )

            # Track token usage
            if database is not None:
                database.record_token_usage(
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    agent_id=agent_id,
                    thread_id=thread_id,
                )

            result = _parse_reflection_response(text, agent_id, thread_id)
            results.append(result)

        except Exception:
            # Reflection failure is non-fatal — skip this agent
            continue

    return results
