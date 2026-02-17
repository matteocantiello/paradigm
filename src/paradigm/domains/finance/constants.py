"""Domain-specific constants for the finance domain.

Team composition, search strategies, literature instructions, and
role reinforcements for financial research.
"""

# ---------------------------------------------------------------------------
# Team composition defaults
# ---------------------------------------------------------------------------

DEFAULT_TEAM_ROLES = [
    "economist",
    "quant",
    "strategist",
    "risk_analyst",
    "writer",
    "editor",
]

MODE_TEAM_ROLES: dict[str, list[str]] = {
    "directed": [
        "economist",
        "quant",
        "strategist",
        "risk_analyst",
        "experimentalist",
        "writer",
        "editor",
        "reviewer",
    ],
    "explore": [
        "economist",
        "quant",
        "strategist",
        "risk_analyst",
    ],
    "empirical": [
        "quant",
        "economist",
        "experimentalist",
        "risk_analyst",
    ],
    "strategy": [
        "quant",
        "strategist",
        "risk_analyst",
        "experimentalist",
    ],
    "policy": [
        "economist",
        "strategist",
        "risk_analyst",
    ],
}

# ---------------------------------------------------------------------------
# Literature search instructions
# ---------------------------------------------------------------------------

LITERATURE_INSTRUCTION = (
    "\n\n## Literature Search & Discovery\n"
    "You have four tools for finding and reading financial research:\n\n"
    "**Keyword search** (best for Round 1, initial exploration):\n"
    "  [SEARCH: your query here]\n\n"
    "**Reference chasing** (follow a paper's bibliography — use the paper ID from search results):\n"
    "  [FOLLOW: 2301.12345]\n\n"
    "**Citation-forward search** (find papers that cite a known paper):\n"
    "  [CITED_BY: 0901.67890]\n\n"
    "**Deep reading** (get extended text from a paper):\n"
    "  [READ: 2301.12345]\n\n"
    "**Data staging** (download a dataset for use in experiments):\n"
    "  [DATA: https://example.com/data.csv]\n\n"
    "**IMPORTANT:** [FOLLOW:], [CITED_BY:], and [READ:] require a paper ID "
    "(e.g., 2301.12345 for arXiv, or an SSRN ID), NOT a URL. "
    "Use the IDs shown in search results.\n\n"
    "### Search Strategy\n"
    "- **Round 1**: Use [SEARCH:] to find initial papers on your financial topic.\n"
    "- **Round 2+**: Shift to graph traversal. Use [FOLLOW:] to explore "
    "references of key papers. Use [CITED_BY:] on foundational papers "
    "to find the current frontier. Use [READ:] when a paper seems critical "
    "to your analysis.\n"
    "- **If keyword search returns no new results**, stop rephrasing and "
    "switch to [FOLLOW:] or [CITED_BY:] on papers you've already found.\n"
    "- After reading a paper, explain how it changes your understanding.\n"
    "- Use `[DATA:]` during PLANNING to request specific datasets you'll "
    "need in EXECUTION (e.g., FRED series, SEC filings, price data).\n"
)

# ---------------------------------------------------------------------------
# Role-specific reinforcements
# ---------------------------------------------------------------------------

ROLE_LATER_ROUND_REINFORCEMENTS: dict[str, str] = {
    "risk_analyst": (
        "\n\n## Your Role: Risk Analyst\n"
        "Your job is NOT to build consensus. You are the risk guardian.\n"
        "- Identify the weakest risk assumption in the discussion so far and challenge it\n"
        "- Name at least one tail risk or scenario the team is ignoring\n"
        "- Propose a concrete stress test that would expose the strategy's vulnerability\n"
        "- If everyone agrees the risk is manageable, that is a red flag — find what they're missing\n"
        "- Do NOT soften your critique with hedging language. Be direct: "
        "'This risk is underestimated because...'\n"
        "- End with an explicit list: 'Unresolved risks: 1. ... 2. ...'"
    ),
    "economist": (
        "\n\n## Your Role: Economist (Later Rounds)\n"
        "Focus on macroeconomic drivers and policy implications. "
        "Do NOT repeat the strategy or portfolio construction — that's "
        "the strategist's job. What specific macro conditions or policy "
        "changes would invalidate the thesis?"
    ),
    "quant": (
        "\n\n## Your Role: Quant (Later Rounds)\n"
        "Focus on quantitative modeling and statistical validation. "
        "Do NOT restate economic theory — instead, specify what models "
        "to estimate, what parameters matter, and what out-of-sample "
        "tests would distinguish the competing hypotheses."
    ),
    "experimentalist": (
        "\n\n## Your Role: Experimentalist (Later Rounds)\n"
        "Focus on practical implementation and data handling. "
        "Do NOT restate theory — instead, specify data sources, "
        "estimation procedures, robustness checks, and failure modes."
    ),
    "strategist": (
        "\n\n## Your Role: Strategist (Later Rounds)\n"
        "Focus on market implications and actionable positioning. "
        "Do NOT restate what others said — instead, translate "
        "findings into concrete portfolio actions and identify "
        "implementation constraints."
    ),
}

# ---------------------------------------------------------------------------
# Role-specific search strategies
# ---------------------------------------------------------------------------

ROLE_SEARCH_STRATEGIES: dict[str, str] = {
    "economist": (
        "\n\n## Your Search Strategy (Economist)\n"
        "Focus your keyword search on macroeconomic research, policy papers, "
        "and seminal economic theory. After finding a key paper, use [FOLLOW:] "
        "to trace its intellectual lineage backward through references. "
        "Search for NBER working papers and central bank research."
    ),
    "quant": (
        "\n\n## Your Search Strategy (Quant)\n"
        "Focus your keyword search on quantitative finance papers — factor "
        "models, derivatives pricing, time series econometrics, and risk "
        "measurement. Use [FOLLOW:] on methodology papers to find the "
        "original technique descriptions and validation studies."
    ),
    "experimentalist": (
        "\n\n## Your Search Strategy (Experimentalist)\n"
        "Focus your keyword search on empirical finance studies, dataset "
        "descriptions, and replication papers. Use [FOLLOW:] on empirical "
        "papers to find the data sources, calibration references, and "
        "robustness check approaches they rely on."
    ),
    "risk_analyst": (
        "\n\n## Your Search Strategy (Risk Analyst)\n"
        "Focus your keyword search on risk management, tail events, "
        "financial crises, and stress testing methodologies. Use [CITED_BY:] "
        "on the team's key papers to find later work that challenges "
        "or qualifies their conclusions."
    ),
    "strategist": (
        "\n\n## Your Search Strategy (Strategist)\n"
        "Focus your keyword search on asset allocation, market strategy, "
        "and cross-asset research. Use [CITED_BY:] on foundational papers "
        "to find the frontier — recent work that extends or recontextualizes "
        "established investment frameworks."
    ),
}
