"""Domain-specific constants for the science domain.

These are extracted from orchestrator/constants.py. The originals remain
in place until Commit 8 removes them.
"""

# ---------------------------------------------------------------------------
# Team composition defaults
# ---------------------------------------------------------------------------

DEFAULT_TEAM_ROLES = ["theorist", "analyst", "synthesizer", "skeptic", "writer", "editor"]

MODE_TEAM_ROLES: dict[str, list[str]] = {
    "directed": [
        "theorist",
        "analyst",
        "experimentalist",
        "synthesizer",
        "skeptic",
        "writer",
        "editor",
    ],
    "explore": [
        "theorist",
        "analyst",
        "experimentalist",
        "synthesizer",
        "skeptic",
        "writer",
        "editor",
    ],
    "hypothesis": ["theorist", "skeptic", "experimentalist", "analyst", "writer", "editor"],
    "experimental": ["experimentalist", "analyst", "theorist", "writer", "editor"],
    "replication": ["analyst", "experimentalist", "skeptic", "writer", "editor"],
}

# ---------------------------------------------------------------------------
# Literature search instructions
# ---------------------------------------------------------------------------

LITERATURE_INSTRUCTION = (
    "\n\n## Literature Search & Discovery\n"
    "You have four tools for finding and reading scientific literature:\n\n"
    "**Keyword search** (best for Round 1, initial exploration):\n"
    "  [SEARCH: your query here]\n\n"
    "**Reference chasing** (follow a paper's bibliography — use the arXiv ID from search results):\n"
    "  [FOLLOW: 2301.12345]\n\n"
    "**Citation-forward search** (find papers that cite a known paper):\n"
    "  [CITED_BY: 0901.67890]\n\n"
    "**Deep reading** (get extended text from a paper):\n"
    "  [READ: 2301.12345]\n\n"
    "**Data staging** (download a dataset for use in experiments):\n"
    "  [DATA: https://example.com/catalog.csv]\n\n"
    "**IMPORTANT:** [FOLLOW:], [CITED_BY:], and [READ:] require an arXiv ID "
    "(e.g., 2301.12345), NOT a URL. Use the IDs shown in search results.\n\n"
    "### Search Strategy\n"
    "- **Round 1**: Use [SEARCH:] to find initial papers on your topic.\n"
    "- **Round 2+**: Shift to graph traversal. Use [FOLLOW:] to explore "
    "references of promising papers. Use [CITED_BY:] on foundational papers "
    "to find the current frontier. Use [READ:] when a paper seems critical "
    "to your argument.\n"
    "- **If keyword search returns no new results**, stop rephrasing and "
    "switch to [FOLLOW:] or [CITED_BY:] on papers you've already found.\n"
    "- After reading a paper, explain how it changes your understanding.\n"
    "- Use `[DATA:]` during PLANNING to request specific datasets you'll "
    "need in EXECUTION (e.g., catalogs, survey data, spectra).\n"
)

# ---------------------------------------------------------------------------
# Role-specific reinforcements
# ---------------------------------------------------------------------------

ROLE_LATER_ROUND_REINFORCEMENTS: dict[str, str] = {
    "skeptic": (
        "\n\n## Your Role: Skeptic\n"
        "Your job is NOT to build consensus. You are the intellectual adversary.\n"
        "- Identify the weakest claim in the discussion so far and attack it directly\n"
        "- Name at least one assumption the team is making without evidence\n"
        "- Propose a concrete alternative explanation that would invalidate the "
        "leading hypothesis\n"
        "- If everyone agrees, that is a red flag — find what they're missing\n"
        "- Do NOT soften your critique with hedging language ('perhaps', "
        "'it might be worth considering'). Be direct: 'This is wrong because...'\n"
        "- End with an explicit list: 'Unresolved problems: 1. ... 2. ...'"
    ),
    "theorist": (
        "\n\n## Your Role: Theorist (Later Rounds)\n"
        "Focus on theoretical predictions and mathematical derivations. "
        "Do NOT repeat the research plan or experimental design — that's "
        "the experimentalist's job. What specific quantitative predictions "
        "distinguish the competing hypotheses?"
    ),
    "analyst": (
        "\n\n## Your Role: Analyst (Later Rounds)\n"
        "Focus on statistical methodology and potential confounders. "
        "Do NOT restate hypotheses — instead, specify what statistical tests "
        "would distinguish them, what sample sizes are needed, and what "
        "systematic biases could produce spurious results."
    ),
    "experimentalist": (
        "\n\n## Your Role: Experimentalist (Later Rounds)\n"
        "Focus on practical experimental design and data handling. "
        "Do NOT restate theory — instead, specify code architecture, "
        "data formats, validation checks, and failure modes."
    ),
    "synthesizer": (
        "\n\n## Your Role: Synthesizer (Later Rounds)\n"
        "Focus on integration and gaps. Do NOT restate what others said — "
        "instead, identify where proposals conflict, what's missing, and "
        "what the team should prioritize. Keep it brief."
    ),
}

# ---------------------------------------------------------------------------
# Role-specific search strategies
# ---------------------------------------------------------------------------

ROLE_SEARCH_STRATEGIES: dict[str, str] = {
    "theorist": (
        "\n\n## Your Search Strategy (Theorist)\n"
        "Focus your keyword search on foundational and seminal papers — the "
        "theoretical frameworks that underpin this topic. After finding a key "
        "paper, use [FOLLOW:] to trace its intellectual lineage backward through "
        "references. Build a genealogy of ideas rather than searching for "
        "variations of the same query."
    ),
    "analyst": (
        "\n\n## Your Search Strategy (Analyst)\n"
        "Focus your keyword search on methodological papers — statistical "
        "techniques, analysis frameworks, and data-processing pipelines relevant "
        "to this topic. Use [FOLLOW:] on methods papers to find the original "
        "technique descriptions and validation studies they reference."
    ),
    "experimentalist": (
        "\n\n## Your Search Strategy (Experimentalist)\n"
        "Focus your keyword search on observational techniques, instrument "
        "papers, and datasets. Use [FOLLOW:] on observational papers to find "
        "the calibration references, data sources, and instrument descriptions "
        "they rely on."
    ),
    "skeptic": (
        "\n\n## Your Search Strategy (Skeptic)\n"
        "Focus your keyword search on contradicting evidence, alternative "
        "explanations, and null results. Use [CITED_BY:] on the team's key "
        "papers to find later work that challenges or qualifies their "
        "conclusions."
    ),
    "synthesizer": (
        "\n\n## Your Search Strategy (Synthesizer)\n"
        "Focus your keyword search on cross-disciplinary connections and review "
        "papers that bridge subfields. Use [CITED_BY:] on foundational papers "
        "to find the frontier — recent work that extends or recontextualizes "
        "established results."
    ),
}
