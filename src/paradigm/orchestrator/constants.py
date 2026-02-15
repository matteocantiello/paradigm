"""Constants, prompt templates, and pure helper functions for the orchestrator."""

import re
from collections.abc import Callable
from pathlib import Path

from paradigm.orchestrator.phases import ResearchPhase
from paradigm.sandbox.models import ExecutionResult

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

# Intervention hook type: called with (thread_id, from_phase, to_phase) → "continue"|"pause"|"abort"
InterventionHook = Callable[[str, str, str], str]

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
# Mode-specific prompt overrides (round_1 only)
# ---------------------------------------------------------------------------

_MODE_PROMPT_OVERRIDES: dict[str, dict[str, str]] = {
    "explore": {
        "round_1": (
            "You are participating in an open-ended exploratory research session.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "This is an exploration session — there is no single hypothesis to test. "
            "Instead, survey the landscape of this topic broadly. Identify interesting "
            "open questions, unexplored connections between subfields, and surprising "
            "gaps in the literature. Propose 2-3 diverse research directions worth pursuing."
        ),
    },
    "hypothesis": {
        "round_1": (
            "You are participating in a rigorous hypothesis-testing session.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "Focus on formulating precise, falsifiable hypotheses. For each hypothesis:\n"
            "1. State it clearly and unambiguously\n"
            "2. Describe what evidence would confirm or refute it\n"
            "3. Identify potential confounding factors\n"
            "4. Propose the simplest experiment that could test it\n\n"
            "Rigor over creativity — every hypothesis must be testable."
        ),
    },
}

# ---------------------------------------------------------------------------
# Phase-specific prompt templates
# ---------------------------------------------------------------------------

_PHASE_INSTRUCTIONS: dict[ResearchPhase, dict[str, str]] = {
    ResearchPhase.IDEATION: {
        "round_1": (
            "You are participating in a collaborative research ideation session.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "This is the opening round. Propose 1-2 concrete, testable hypotheses "
            "related to this topic. Be specific about what you'd predict and why."
        ),
        "later_rounds": (
            "You are participating in a collaborative research ideation session.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "## Recent Discussion\n{recent_messages}\n\n"
            "Respond to your colleagues: critique ideas, build on promising hypotheses, "
            "draw connections between proposals, and help prioritize. "
            "Be constructive but rigorous."
        ),
    },
    ResearchPhase.PLANNING: {
        "round_1": (
            "You are developing a concrete research plan.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "Based on the ideation phase, propose specific:\n"
            "- Experiments or analyses to run\n"
            "- Data requirements and sources\n"
            "- Success criteria and expected outcomes\n"
            "- Potential pitfalls and how to address them"
        ),
        "later_rounds": (
            "You are refining a research plan.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "## Recent Discussion\n{recent_messages}\n\n"
            "Refine the plan: challenge assumptions, identify dependencies between "
            "experiments, suggest controls, and ensure the plan is feasible. "
            "Focus on making the plan actionable."
        ),
    },
    ResearchPhase.EXECUTION: {
        "propose_experiment": (
            "You are designing and running computational experiments.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "{previous_results}"
            "Write Python code to test the hypotheses and plans from prior discussion. "
            "Wrap each experiment in a fenced ```python block with a "
            "`# EXPERIMENT: <name>` comment on the first line.\n\n"
            "**\u26a0 CRITICAL: The sandbox has NO network access.** Do NOT use `requests`, "
            "`urllib.request`, `httpx`, `http.client`, `aiohttp`, or any HTTP/socket calls "
            "— they will always fail. All data must come from: (1) files under "
            "/data/shared/, (2) /data/workspace/, or (3) synthetic/simulated data you "
            "generate in code.\n\n"
            "**Available libraries:** numpy, scipy, matplotlib, pandas, scikit-learn, "
            "sympy, astropy, seaborn, pypdf, h5py, emcee, corner, lmfit, "
            "uncertainties, statsmodels, tqdm, numba, xarray, joblib, pyyaml, "
            "and standard library modules. Note: numpy (np), pandas (pd), "
            "matplotlib.pyplot (plt), and scipy are auto-imported, but you should "
            "still import any other libraries you use.\n"
            "**Installing extra packages:** If you need a package not already installed, run "
            "`import os; os.system('pip install --user --no-index --find-links /data/packages/ "
            "<package_name>')` at the top of your script. Packages available in the offline "
            "cache include: photutils, specutils, dust_extinction, galpy, healpy, "
            "plotly, bokeh, tables, netCDF4, pyarrow, and more.\n"
            "**Environment:** Code runs inside a Docker container with no network access. "
            "You can use os, pathlib, open(), io, glob, shutil, etc. for file operations. "
            "Do NOT use subprocess, ctypes, multiprocessing, exec(), or eval().\n"
            "**Shared resources:** Code repositories and data files from the research prompt "
            "are listed in the 'Available Files' section above. Do NOT assume files exist — "
            "only use paths explicitly listed above. If no files are listed, generate all data "
            "synthetically.\n"
            "**PDF files:** PDF files from the research prompt are available under "
            "/data/shared/papers/. Use pypdf (not PyPDF2) to parse them.\n"
            "**Code files:** Code files from the research prompt are importable directly "
            "(their directories are on PYTHONPATH). See 'Available Files' above for paths.\n"
            "**Workspace:** IMPORTANT: Save ALL intermediate data files to /data/workspace/ "
            "so later experiments can reuse them. This is a persistent read-write directory "
            "shared across all experiments. Read previous outputs from there.\n"
            "**Output:** Print results to stdout. Save figures as .png files using "
            "matplotlib (plt.savefig('figure_name.png')). All .png/.pdf files in the "
            "working directory will be collected.\n"
            "**Important:** When using LaTeX in matplotlib labels or titles, always use "
            "raw strings (r'...') to avoid invalid escape sequences. For example: "
            r"r'$M_\odot$' not '$M_\odot$'."
            "\n\n"
            "**Data strategy:** If the research topic references specific datasets or "
            "observations, generate realistic synthetic data that captures the key "
            "statistical properties (distributions, correlations, noise characteristics). "
            "Document your synthetic data assumptions with comments. "
            "Focus on producing clear, reproducible computational results."
        ),
        "analyze_results": (
            "You are reviewing computational experiment results.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "## Previous Experiment Results\n{previous_results}\n\n"
            "Analyze the results above. You may either:\n"
            "1. Propose a follow-up experiment by writing a ```python block "
            "(with `# EXPERIMENT: <name>` header)\n"
            "2. Declare experiments sufficient by NOT including any code block "
            "(just provide your analysis)\n\n"
            "If proposing follow-up experiments, explain what additional question "
            "they address.\n\n"
            "**Remember:** The sandbox has NO network access. All experiments must use "
            "synthetic/simulated data or files from /data/shared/ and /data/workspace/. "
            "Do NOT use requests, urllib, or any HTTP calls."
        ),
        "retry_after_failure": (
            "Your previous experiment failed or was rejected.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "## Error Feedback\n{error_feedback}\n\n"
            "Fix the code and resubmit in a ```python block with "
            "`# EXPERIMENT: <name>` header. Address the specific error above.\n\n"
            "**Remember:** The sandbox has NO network access. Do NOT use requests, "
            "urllib, or any HTTP calls. Generate synthetic data or use files from "
            "/data/shared/."
        ),
    },
    ResearchPhase.WRITING: {
        "section_drafting": (
            "You are writing sections of a research paper.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "Draft the following sections in markdown, using ## headers for each:\n"
            "{assigned_sections}\n\n"
            "**Length guidance:** Each section should be substantive — 200-500 words "
            "per section. A one-paragraph section is not acceptable.\n"
            "**Quantitative results:** Include quantitative results (numbers, statistical "
            "measures, comparisons) wherever applicable. Do not write vague summaries — "
            "cite specific values, uncertainties, and trends from the experiments.\n\n"
            "Write clear, precise scientific prose. Every claim should be supported "
            "by evidence from the research. Use active voice where possible."
        ),
        "assembly": (
            "You are assembling a research paper from section drafts.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "## Section Drafts\n{section_drafts}\n\n"
            "Combine all section drafts into a single coherent paper. "
            "Harmonize writing style, ensure smooth transitions between sections, "
            "add a title, and make sure the paper tells a complete story. "
            "Output the full paper in markdown with ## section headers."
        ),
        "refinement": (
            "You are refining a research paper.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "## Current Draft\n{current_draft}\n\n"
            "## Recent Discussion\n{recent_messages}\n\n"
            "Provide specific suggestions to improve the paper. "
            "Focus on clarity, accuracy, and completeness."
        ),
    },
    ResearchPhase.INTERNAL_REVIEW: {
        "editor_review": (
            "You are reviewing a research paper for internal quality control.\n"
            "Topic: {seed_prompt}\n\n"
            "## Paper Draft\n{current_draft}\n\n"
            "Provide a structured review with these sections (use ## headers):\n"
            "## Strengths\n- What works well\n\n"
            "## Weaknesses\n- What needs improvement\n\n"
            "## Required Changes\n- Specific changes needed before submission\n\n"
            "## Recommendation\n- Either 'accept' (ready for submission) or "
            "'revise' (needs another round of revisions)"
        ),
        "revision": (
            "You are revising a research paper based on internal review feedback.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "## Current Draft\n{current_draft}\n\n"
            "## Review Feedback\n{review_feedback}\n\n"
            "Revise the paper to address the required changes. "
            "Output the complete revised paper in markdown."
        ),
    },
    ResearchPhase.SUBMITTED: {
        "desk_review": (
            "You are the editor-in-chief performing a desk review of a submitted paper.\n"
            "Topic: {seed_prompt}\n\n"
            "## Submitted Paper\n{current_draft}\n\n"
            "Perform a quick quality check:\n"
            "- Is the paper coherent and on-topic?\n"
            "- Does it have the basic structure of a research paper?\n"
            "- Is it written in intelligible prose?\n\n"
            "Respond with:\n"
            "## Decision\nEither 'send_to_review' (paper is suitable for peer review) "
            "or 'desk_reject' (paper has fundamental issues)\n\n"
            "## Reason\nBrief explanation of your decision."
        ),
    },
    ResearchPhase.PEER_REVIEW: {
        "review": (
            "You are an independent peer reviewer evaluating a submitted manuscript.\n"
            "Topic: {seed_prompt}\n\n"
            "## Manuscript\n{current_draft}\n\n"
            "Provide your review in this exact format using ## headers:\n\n"
            "## Summary\nBrief summary of the paper.\n\n"
            "## Strengths\n- Key strengths as bullet points\n\n"
            "## Weaknesses\n- Key weaknesses as bullet points\n\n"
            "## Questions\n- Questions for the authors\n\n"
            "## Suggestions\n- Specific suggestions for improvement\n\n"
            "## Scores\nNovelty: X/10\nRigor: X/10\nClarity: X/10\nSignificance: X/10\n\n"
            "## Recommendation\nOne of: accept, minor_revision, major_revision, reject"
        ),
    },
    ResearchPhase.REVISION: {
        "revise": (
            "You are revising a research paper based on peer review feedback.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "## Current Draft\n{current_draft}\n\n"
            "## Peer Review Feedback\n{review_feedback}\n\n"
            "Revise the paper to address the reviewer concerns and suggestions. "
            "Output the complete revised paper in markdown."
        ),
    },
}

# ---------------------------------------------------------------------------
# Literature search & debate instructions
# ---------------------------------------------------------------------------

_RECENT_MESSAGES_LIMIT = 10

_LITERATURE_INSTRUCTION = (
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
)

_SEARCH_ENABLED_PHASES: set[ResearchPhase] = {
    ResearchPhase.IDEATION,
    ResearchPhase.PLANNING,
    ResearchPhase.EXECUTION,
}

_DEBATE_ENABLED_PHASES: set[ResearchPhase] = {
    ResearchPhase.IDEATION,
    ResearchPhase.PLANNING,
}

_CHALLENGE_INSTRUCTION = (
    "\n\n## Focused Debate\n"
    "If you strongly disagree with another agent's position and believe a "
    "focused exchange would advance the research, you may challenge them:\n"
    "  [CHALLENGE: agent-id: brief reason for disagreement]\n\n"
    "This triggers a structured debate between you and the challenged agent. "
    "Use this sparingly — only when genuine intellectual disagreement exists "
    "and a back-and-forth would produce better ideas than the normal round.\n"
)

_DEBATE_PROMPT_DEFENDER = (
    "You are {defender_id} in a focused debate with {challenger_id}.\n\n"
    "## Challenge\n{challenger_id} challenges your position:\n"
    "{challenger_argument}\n\n"
    "## Topic: {debate_topic}\n\n"
    "Respond to this challenge. Defend your position with evidence and reasoning, "
    "or concede specific points where the criticism is valid.\n\n"
    "If you believe the disagreement is resolved, end your response with:\n"
    "  [RESOLVED: brief summary of agreement]\n"
    "If you concede the challenger's main point, end with:\n"
    "  [CONCEDE: what you now accept]\n"
)

_DEBATE_PROMPT_CHALLENGER = (
    "You are {challenger_id} continuing a focused debate with {defender_id}.\n\n"
    "## Debate Topic: {debate_topic}\n\n"
    "## Defender's Response\n{defender_argument}\n\n"
    "Respond to the defender's argument. Refine your critique, acknowledge "
    "valid points, or press where you see weaknesses.\n\n"
    "If you believe the disagreement is resolved, end your response with:\n"
    "  [RESOLVED: brief summary of agreement]\n"
    "If you concede the defender's main point, end with:\n"
    "  [CONCEDE: what you now accept]\n"
)

_DEBATE_SYNTHESIS_PROMPT = (
    "Summarize the following debate between {challenger_id} and {defender_id} "
    "on the topic: {debate_topic}\n\n"
    "## Debate Transcript\n{transcript}\n\n"
    "## Resolution: {resolution_type}\n{resolution_statement}\n\n"
    "Write a concise summary (2-4 paragraphs) capturing:\n"
    "1. The core disagreement\n"
    "2. Key arguments from each side\n"
    "3. What was resolved and what remains open\n"
    "4. How this debate should inform the research going forward\n"
)

# ---------------------------------------------------------------------------
# Resolution detection regexes
# ---------------------------------------------------------------------------

_RESOLVED_RE = re.compile(r"\[RESOLVED:\s*([^\]]+?)\]", re.IGNORECASE)
_CONCEDE_RE = re.compile(r"\[CONCEDE:\s*([^\]]+?)\]", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Phase-based role filtering and context injection
# ---------------------------------------------------------------------------

_PHASE_ACTIVE_ROLES: dict[ResearchPhase, set[str]] = {
    ResearchPhase.IDEATION: {"theorist", "analyst", "synthesizer", "skeptic", "experimentalist"},
    ResearchPhase.PLANNING: {"theorist", "analyst", "synthesizer", "skeptic", "experimentalist"},
}

_PHASE_CONTEXT_NEEDS: dict[ResearchPhase, set[str]] = {
    ResearchPhase.IDEATION: {"literature", "references", "memory"},
    ResearchPhase.PLANNING: {"literature", "code_data", "memory"},
}

# ---------------------------------------------------------------------------
# Numeric limits
# ---------------------------------------------------------------------------

_WRITING_MAX_TOKENS = 32768
_PAPER_CONTEXT_LIMIT = 50000
_LITERATURE_CONTEXT_LIMIT = 10000
_MIN_PAPER_LENGTH = 3000
_EXECUTION_OUTPUT_LIMIT = 4000
_EXECUTION_STDERR_LIMIT = 2000
_MAX_RETRIES_PER_EXPERIMENT = 2
# (Also exposed as _RECENT_MESSAGES_LIMIT above)

# ---------------------------------------------------------------------------
# Vacuous success detection
# ---------------------------------------------------------------------------

_VACUOUS_STDOUT_PATTERNS: list[str] = [
    "file not found",
    "no such file or directory",
    "please check the file path",
    "no data available",
    "error loading",
    "could not find",
    "does not exist",
    "failed to load",
    "cannot open",
]


def _is_vacuous_success(result: ExecutionResult) -> bool:
    """Check if a SUCCESS result produced no scientific output.

    A result is vacuous if it has no output files AND either:
    - stdout is empty/trivially short (< 20 chars), or
    - stdout is dominated by error-like messages.

    Args:
        result: Execution result with SUCCESS status.

    Returns:
        True if the result appears vacuous.
    """
    # Output files (figures, data) → not vacuous
    if result.output_files:
        return False
    stdout = (result.stdout or "").strip()
    # Empty or trivially short stdout with no files → vacuous
    if len(stdout) < 20:
        return True
    # Stdout dominated by error-like messages → vacuous
    stdout_lower = stdout.lower()
    return any(p in stdout_lower for p in _VACUOUS_STDOUT_PATTERNS)


# ---------------------------------------------------------------------------
# File-not-found error patterns
# ---------------------------------------------------------------------------

_FILE_NOT_FOUND_PATTERNS: list[str] = [
    "FileNotFoundError",
    "No such file or directory",
]

# ---------------------------------------------------------------------------
# Network error patterns
# ---------------------------------------------------------------------------

_NETWORK_ERROR_PATTERNS: list[str] = [
    "Temporary failure in name resolution",
    "Name or service not known",
    "ConnectionRefusedError",
    "ConnectionError",
    "No route to host",
    "Network is unreachable",
    "urlopen error",
    "MaxRetryError",
    "NewConnectionError",
    "socket.gaierror",
    "requests.exceptions",
]

# ---------------------------------------------------------------------------
# Code block regexes
# ---------------------------------------------------------------------------

_CODE_BLOCK_RE = re.compile(r"```python\s*\n(.*?)```", re.DOTALL)
_EXPERIMENT_NAME_RE = re.compile(r"^#\s*EXPERIMENT:\s*(.+)", re.MULTILINE)

# ---------------------------------------------------------------------------
# Stop words for fuzzy query normalization
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "to",
        "was",
        "were",
        "will",
        "with",
    }
)

# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def _extract_code_blocks(text: str) -> list[tuple[str, str]]:
    """Extract Python code blocks from agent response text.

    Looks for fenced ```python blocks. Extracts experiment name from
    a ``# EXPERIMENT: name`` comment on the first line.

    Args:
        text: Agent response text.

    Returns:
        List of (experiment_name, code) tuples.
    """
    blocks: list[tuple[str, str]] = []
    for match in _CODE_BLOCK_RE.finditer(text):
        code = match.group(1).strip()
        if not code:
            continue
        name_match = _EXPERIMENT_NAME_RE.match(code)
        name = name_match.group(1).strip() if name_match else "unnamed_experiment"
        blocks.append((name, code))
    return blocks


def _list_shared_files(data_dir: Path) -> str:
    """Scan /data/shared/ and return a concrete listing of available files.

    Args:
        data_dir: The base data directory (contains shared/ subdirectory).

    Returns:
        Formatted string listing available files, or a "No files" message.
    """
    shared_dir = data_dir / "shared"
    if not shared_dir.exists():
        return "## Available Files\nNo files are available under /data/shared/.\n"

    lines = ["## Available Files"]
    found_any = False

    for category_dir in sorted(shared_dir.iterdir()):
        if not category_dir.is_dir():
            continue
        files = sorted(f for f in category_dir.rglob("*") if f.is_file())
        if not files:
            continue
        found_any = True
        lines.append(f"\n### /data/shared/{category_dir.name}/")
        for f in files[:50]:
            rel = f.relative_to(shared_dir)
            size = f.stat().st_size
            if size < 1024:
                size_str = f"{size} B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size / (1024 * 1024):.1f} MB"
            lines.append(f"- `/data/shared/{rel}` ({size_str})")
        if len(files) > 50:
            lines.append(f"  ... and {len(files) - 50} more files")

    top_files = sorted(f for f in shared_dir.iterdir() if f.is_file())
    if top_files:
        found_any = True
        lines.append("\n### /data/shared/")
        for f in top_files[:20]:
            size = f.stat().st_size
            if size < 1024:
                size_str = f"{size} B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size / (1024 * 1024):.1f} MB"
            lines.append(f"- `/data/shared/{f.name}` ({size_str})")

    if not found_any:
        return "## Available Files\nNo files are available under /data/shared/.\n"

    lines.append("")
    return "\n".join(lines)


def _normalize_query_keywords(query: str) -> frozenset[str]:
    """Normalize a search query to a set of lowercase keywords, minus stop words.

    Args:
        query: Raw search query string.

    Returns:
        Frozen set of meaningful keywords.
    """
    words = set(re.sub(r"[^a-z0-9\s]", " ", query.lower()).split())
    return frozenset(words - _STOP_WORDS)


def _is_duplicate_query(
    new_keywords: frozenset[str],
    existing_keyword_sets: list[frozenset[str]],
    threshold: float = 0.7,
) -> bool:
    """Check if a query is a near-duplicate of any previously executed query.

    Uses Jaccard similarity: |A ∩ B| / |A ∪ B| >= threshold.

    Args:
        new_keywords: Keyword set of the new query.
        existing_keyword_sets: List of keyword sets from previously executed queries.
        threshold: Minimum Jaccard similarity to consider a duplicate.

    Returns:
        True if the query is a near-duplicate.
    """
    if not new_keywords:
        return False
    for existing in existing_keyword_sets:
        if not existing:
            continue
        intersection = len(new_keywords & existing)
        union = len(new_keywords | existing)
        if union > 0 and intersection / union >= threshold:
            return True
    return False


def _format_execution_result(experiment_name: str, result: ExecutionResult) -> str:
    """Format an execution result as markdown for agent context.

    Args:
        experiment_name: Name of the experiment.
        result: Execution result.

    Returns:
        Markdown-formatted result string.
    """
    parts = [f"### Experiment: {experiment_name}"]
    parts.append(f"**Status:** {result.status.value}")
    if result.duration_seconds is not None:
        parts.append(f"**Duration:** {result.duration_seconds:.1f}s")
    if result.stdout:
        stdout = result.stdout[:_EXECUTION_OUTPUT_LIMIT]
        if len(result.stdout) > _EXECUTION_OUTPUT_LIMIT:
            stdout += "\n... (output truncated)"
        parts.append(f"**Output:**\n```\n{stdout}\n```")
    if result.stderr:
        stderr = result.stderr[:_EXECUTION_STDERR_LIMIT]
        if len(result.stderr) > _EXECUTION_STDERR_LIMIT:
            stderr += "\n... (stderr truncated)"
        parts.append(f"**Errors:**\n```\n{stderr}\n```")
    if result.error_message:
        parts.append(f"**Error:** {result.error_message}")
    if result.output_files:
        file_list = ", ".join(f"`{f.filename}`" for f in result.output_files)
        parts.append(f"**Output files:** {file_list}")
    return "\n\n".join(parts)
