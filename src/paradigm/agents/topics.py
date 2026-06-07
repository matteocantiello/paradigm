"""Topic classification — tag research with broad (arXiv-style) fields.

A lightweight LLM classifier maps a research question (at the start of a cycle)
or a finished paper (at the end) onto a small, fixed set of top-level fields. The
end-of-cycle pass intentionally allows MULTIPLE tags so cross-disciplinary work
("economics study using astrophysics techniques") surfaces both badges —
cross-pollination is a feature, not noise.

The taxonomy is a presentation/metadata concern only; the orchestrator stays
domain-agnostic. Keep the keys in sync with the frontend's TOPIC_LABELS/TOPIC_COLORS.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

# key -> "Label — what it covers" (the source of truth for valid topic keys).
# Broad arXiv-style groups, with astrophysics split out from physics and a
# medicine bucket (medRxiv/PubMed) added; "other" is the catch-all.
TOPIC_DESCRIPTIONS: dict[str, str] = {
    "astro": "Astrophysics — stars, galaxies, cosmology, planets, compact objects, astronomical instrumentation",
    "physics": "Physics — condensed matter, quantum, particle/high-energy, nuclear, optics, fluids, statistical mechanics (non-astro)",
    "cs": "Computer Science — algorithms, machine learning/AI, systems, theory, NLP, vision, software",
    "math": "Mathematics — analysis, algebra, geometry, topology, number theory, probability theory, dynamical systems",
    "stat": "Statistics — statistical methodology, inference, Bayesian methods, experimental design, data analysis",
    "bio": "Biology — molecular/cell biology, genomics, neuroscience, ecology, evolution, biophysics",
    "med": "Medicine — clinical research, epidemiology, public health, medical imaging, pharmacology",
    "econ": "Economics & Finance — economics, econometrics, markets, quantitative finance, game theory",
    "eess": "Engineering & Systems — signal/image processing, control, electrical engineering, communications",
    "other": "Other — anything that doesn't fit the categories above (e.g. chemistry, geoscience, social science)",
}

# Ordered list of valid keys + a fast membership set.
TOPICS: list[str] = list(TOPIC_DESCRIPTIONS)
VALID_TOPICS: frozenset[str] = frozenset(TOPICS)

# Tokens the model might emit (keys or natural-language names) -> canonical key.
_SYNONYMS: dict[str, str] = {
    "astro": "astro",
    "astrophysics": "astro",
    "astrophysical": "astro",
    "astronomy": "astro",
    "astronomical": "astro",
    "cosmology": "astro",
    "physics": "physics",
    "phys": "physics",
    "physical": "physics",
    "cs": "cs",
    "computer": "cs",
    "computing": "cs",
    "compsci": "cs",
    "ml": "cs",
    "ai": "cs",
    "math": "math",
    "maths": "math",
    "mathematics": "math",
    "mathematical": "math",
    "stat": "stat",
    "stats": "stat",
    "statistics": "stat",
    "statistical": "stat",
    "bio": "bio",
    "biology": "bio",
    "biological": "bio",
    "biophysics": "bio",
    "med": "med",
    "medicine": "med",
    "medical": "med",
    "clinical": "med",
    "epidemiology": "med",
    "econ": "econ",
    "economics": "econ",
    "economic": "econ",
    "finance": "econ",
    "financial": "econ",
    "fin": "econ",
    "eess": "eess",
    "engineering": "eess",
    "signal": "eess",
    "electrical": "eess",
    "other": "other",
}

_TEXT_LIMIT = 8000  # chars of paper text the classifier sees (enough for a field call)

_CLASSIFY_PROMPT = """You are classifying scientific work into broad fields, using \
these labels (arXiv-style top-level categories):

{taxonomy}

Text to classify:
\"\"\"
{text}
\"\"\"

Respond with ONLY a comma-separated list of the matching label KEYS (lowercase, the \
word before the dash), most relevant FIRST. List the primary field, then ANY additional \
fields whose methods, data, or concepts the work substantially draws on — \
interdisciplinary work should list multiple (e.g. "econ, astro" for an economics study \
that borrows astrophysics techniques). Use at most {max_topics}. If nothing fits, \
respond with "other". Output just the keys, nothing else.
"""


def _taxonomy_block() -> str:
    return "\n".join(f"- {key}: {desc}" for key, desc in TOPIC_DESCRIPTIONS.items())


def _parse_topics(raw: str, max_topics: int) -> list[str]:
    """Extract canonical topic keys from a model response, preserving order."""
    found: list[str] = []
    for tok in re.split(r"[^a-zA-Z]+", (raw or "").lower()):
        key = _SYNONYMS.get(tok)
        if key and key not in found:
            found.append(key)
    # Drop the "other" catch-all when a real field was identified.
    real = [t for t in found if t != "other"]
    result = real or (["other"] if found else [])
    if not result:
        return ["other"]
    return result[:max_topics]


async def classify_topics(
    text: str,
    *,
    provider: Any,
    model: str,
    max_topics: int = 3,
) -> list[str]:
    """Classify ``text`` into 1..max_topics broad field keys (see TOPICS).

    Best-effort and side-effect free: returns ["other"] on empty input. The blocking
    provider call is offloaded so it never stalls the event loop. Never raises for a
    bad model response — it degrades to ["other"].
    """
    if not text or not text.strip():
        return ["other"]
    prompt = _CLASSIFY_PROMPT.format(
        taxonomy=_taxonomy_block(),
        text=text[:_TEXT_LIMIT],
        max_topics=max_topics,
    )
    raw, _in, _out = await asyncio.to_thread(
        provider.complete,
        model=model,
        max_tokens=60,
        temperature=0.0,
        system="",
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_topics(raw, max_topics)


def _has_topics(raw: Any) -> bool:
    """Whether a DB topics column (JSON string or list) already holds tags."""
    if not raw:
        return False
    try:
        val = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return False
    return bool(val)


async def backfill_topics(
    database: Any,
    *,
    provider: Any,
    model: str,
    force: bool = False,
    dry_run: bool = False,
    limit: int = 0,
) -> list[tuple[str, str, str, list[str]]]:
    """Retroactively classify existing papers + cycles in ``database``.

    Papers are tagged from their content (and their owning thread is tagged to
    match, so the cycle badge agrees); remaining cycles are tagged from the seed
    prompt. Idempotent — already-tagged items are skipped unless ``force``; ingested
    literature (``status == "external"``) is left untouched.

    Returns one ``(kind, id, label, topics)`` tuple per processed item, where
    ``kind`` is "paper" or "cycle". With ``dry_run`` nothing is written.
    """
    results: list[tuple[str, str, str, list[str]]] = []
    tagged_threads: set[str] = set()

    # 1) Papers — authoritative tags from the actual paper content.
    for paper in database.list_papers():
        if limit and len(results) >= limit:
            return results
        if paper.get("status") == "external":
            continue
        if _has_topics(paper.get("topics")) and not force:
            continue
        text = "\n\n".join(
            part
            for part in (
                paper.get("title", ""),
                paper.get("abstract", ""),
                (paper.get("body", "") or "")[:6000],
            )
            if part
        )
        topics = await classify_topics(text, provider=provider, model=model, max_topics=3)
        if not dry_run:
            database.update_paper(paper["id"], topics=topics)
            tid = database.get_thread_id_for_paper(paper["id"])
            if tid:
                database.update_thread(tid, topics=topics)
                tagged_threads.add(tid)
        results.append(("paper", paper["id"], paper.get("title", ""), topics))

    # 2) Cycles with no paper (or not reached above) — tag from the seed prompt.
    for thread in database.list_threads():
        if limit and len(results) >= limit:
            return results
        tid = thread["id"]
        if tid in tagged_threads:
            continue
        if _has_topics(thread.get("topics")) and not force:
            continue
        seed = (thread.get("hypothesis") or thread.get("title") or "").strip()
        if not seed:
            continue
        topics = await classify_topics(seed, provider=provider, model=model, max_topics=2)
        if not dry_run:
            database.update_thread(tid, topics=topics)
        results.append(("cycle", tid, seed, topics))

    return results
