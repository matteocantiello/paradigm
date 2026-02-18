"""Constants, prompt templates, and pure helper functions for the orchestrator."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from paradigm.orchestrator.phases import ResearchPhase
from paradigm.sandbox.models import ExecutionResult

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

# Intervention hook type: called with (thread_id, from_phase, to_phase) → "continue"|"pause"|"abort"
InterventionHook = Callable[[str, str, str], str]

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


def _network_caveat(network_enabled: bool) -> str:
    """Return the appropriate network access caveat for experiment prompts.

    Args:
        network_enabled: Whether the sandbox has network access.

    Returns:
        Caveat string to embed in experiment prompts.
    """
    if network_enabled:
        return (
            "**Network access is available.** You may use `requests`, `httpx`, "
            "`urllib.request`, etc. to fetch data from the internet if needed."
        )
    return (
        "**\u26a0 CRITICAL: The sandbox has NO network access.** Do NOT use `requests`, "
        "`urllib.request`, `httpx`, `http.client`, `aiohttp`, or any HTTP/socket calls "
        "— they will always fail. All data must come from: (1) files under "
        "/data/shared/, (2) /data/workspace/, or (3) synthetic/simulated data you "
        "generate in code."
    )


_PHASE_INSTRUCTIONS: dict[ResearchPhase, dict[str, str]] = {
    ResearchPhase.IDEATION: {
        "round_1": (
            "You are participating in a collaborative research ideation session.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "{recent_messages}"
            "Propose 1-2 concrete, testable hypotheses "
            "related to this topic. Be specific about what you'd predict and why.\n\n"
            "**CRITICAL DIFFERENTIATION RULE:** If prior proposals appear above, "
            "you MUST NOT repeat hypotheses already proposed. Instead:\n"
            "- Propose genuinely DIFFERENT hypotheses or alternative mechanisms\n"
            "- Challenge or refine prior proposals with new evidence\n"
            "- Identify blind spots, overlooked variables, or unstated assumptions\n"
            "- If you agree with existing proposals, say so in ONE sentence and "
            "spend your response on what's MISSING\n\n"
            "Redundant proposals waste the team's entire token budget."
        ),
        "later_rounds": (
            "You are participating in a collaborative research ideation session.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "## Recent Discussion\n{recent_messages}\n\n"
            "**CRITICAL: Do NOT repeat ideas already established above.** "
            "If a hypothesis or research direction has been proposed, do not re-propose it. "
            "Instead:\n"
            "- Challenge, refine, or combine existing proposals\n"
            "- Identify gaps or contradictions between proposals\n"
            "- Add NEW evidence, NEW references, or NEW perspectives not yet raised\n"
            "- If you agree with everything, say so briefly and focus on what is still unresolved\n\n"
            "Your response should contain zero redundant information."
        ),
    },
    ResearchPhase.PLANNING: {
        "round_1": (
            "You are developing a concrete research plan.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "{recent_messages}"
            "**IMPORTANT:** The Phase Syntheses section above contains the agreed "
            "hypotheses and scope boundaries from IDEATION. Your plan MUST address "
            "these specific hypotheses — do NOT propose new research directions.\n\n"
            "**CRITICAL DIFFERENTIATION RULE:** If prior plans appear above, "
            "do NOT restate experiments already proposed. Instead:\n"
            "- Add NEW experiments or analyses not yet covered\n"
            "- Critique specific weaknesses in proposed experiments\n"
            "- Suggest improvements to methodology or success criteria\n"
            "- Identify missing controls, data sources, or feasibility risks\n\n"
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
            "**Do NOT restate the plan from scratch.** The plan above already exists. "
            "Your job is to:\n"
            "- Identify specific weaknesses, missing controls, or unrealistic assumptions\n"
            "- Suggest concrete improvements to specific steps\n"
            "- Raise feasibility concerns or resource constraints\n"
            "- If the plan is solid, say so briefly and flag remaining risks\n\n"
            "Do NOT repeat experiments or analyses already listed."
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
            "{network_caveat}\n\n"
            "**Available libraries:** numpy, scipy, matplotlib, pandas, scikit-learn, "
            "sympy, astropy, seaborn, pypdf (NOT PyPDF2), pdfminer.six, "
            "beautifulsoup4, h5py, emcee, corner, lmfit, "
            "uncertainties, statsmodels, tqdm, numba, xarray, joblib, pyyaml, "
            "and standard library modules. Note: numpy (np), pandas (pd), "
            "matplotlib.pyplot (plt), and scipy are auto-imported, but you should "
            "still import any other libraries you use.\n"
            "**IMPORTANT:** Use `import pypdf` (NOT `import PyPDF2`). "
            "Use `from pdfminer.high_level import extract_text` for PDF text extraction. "
            "Do NOT try to pip install packages — it is blocked.\n"
            "**Installing extra packages:** If you need a package not already installed, run "
            "`import os; os.system('pip install --user --no-index --find-links /data/packages/ "
            "<package_name>')` at the top of your script. Packages available in the offline "
            "cache include: photutils, specutils, dust_extinction, galpy, healpy, "
            "plotly, bokeh, tables, netCDF4, pyarrow, and more.\n"
            "**Environment:** Code runs inside a Docker container. "
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
            "matplotlib (plt.savefig('figure_name.png', dpi=150, bbox_inches='tight')). "
            "All .png/.pdf files in the working directory will be collected.\n"
            "**FIGURES ARE REQUIRED:** At least one experiment MUST produce publication-quality "
            "figures (e.g., correlation plots, parameter distributions, model comparisons). "
            "A paper without figures will be rejected during review. Plan your experiments "
            "so that figure-generating scripts run AFTER data analysis scripts.\n"
            "**Important:** When using LaTeX in matplotlib labels or titles, always use "
            "raw strings (r'...') to avoid invalid escape sequences. For example: "
            r"r'$M_\odot$' not '$M_\odot$'."
            "\n\n"
            "**Code length limit:** Each code block must be under 100,000 characters. "
            "If your analysis is complex, break it into multiple smaller "
            "`# EXPERIMENT:` blocks that each do one focused task (e.g., data extraction, "
            "analysis, plotting). Save intermediate results to /data/workspace/ so "
            "subsequent experiments can load them.\n"
            "**Experiment dependencies:** If an experiment depends on output from another "
            "experiment in the same batch (e.g., B reads a file that A creates), declare "
            "the dependency: `# DEPENDS: <name>` on the line after `# EXPERIMENT: <name>`. "
            "Multiple: `# DEPENDS: exp_a, exp_b`. Experiments execute in dependency order; "
            "if an upstream dependency fails, downstream experiments are skipped.\n"
            "**Data strategy:** If the research topic references specific datasets or "
            "observations, generate realistic synthetic data that captures the key "
            "statistical properties (distributions, correlations, noise characteristics). "
            "Document your synthetic data assumptions with comments. "
            "Focus on producing clear, reproducible computational results.\n"
            "**CRITICAL — Synthetic vs. real data:** When generating synthetic data, "
            "print a clear banner: `print('NOTE: Using SYNTHETIC data — not real observations')`. "
            "Your code comments and stdout MUST distinguish synthetic results from real data. "
            "Never present synthetic data as if it were real observations. The paper writing "
            "phase relies on your output to determine what is real vs. simulated."
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
            "**Experiment dependencies:** If an experiment depends on output from another "
            "experiment in the same batch (e.g., B reads a file that A creates), declare "
            "the dependency: `# DEPENDS: <name>` on the line after `# EXPERIMENT: <name>`. "
            "Multiple: `# DEPENDS: exp_a, exp_b`. Experiments execute in dependency order; "
            "if an upstream dependency fails, downstream experiments are skipped.\n\n"
            "{network_caveat}"
        ),
        "retry_after_failure": (
            "Your previous experiment failed or was rejected.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "## Your Previous Code\n```python\n{failed_code}\n```\n\n"
            "## Error Feedback\n{error_feedback}\n\n"
            "Fix the code above. Patch the existing code rather than rewriting from scratch — "
            "preserve working parts and only fix the broken lines.\n\n"
            "**If the error is about code length:** Do NOT try to shorten the same script. "
            "Instead, break it into multiple smaller `# EXPERIMENT:` blocks that each do "
            "one focused task. Save intermediate results to /data/workspace/ and load them "
            "in subsequent experiments.\n"
            "{network_caveat}"
        ),
        "pre_execution_review": (
            "You are reviewing a teammate's experiment code BEFORE it runs.\n"
            "Experiment: {experiment_name}\n\n"
            "```python\n{code}\n```\n\n"
            "Check for bugs that would cause the experiment to fail:\n"
            "- Wrong module names or imports (e.g., PyPDF2 instead of pypdf)\n"
            "- Hardcoded file paths that don't exist\n"
            "- Logic errors (wrong variable names, off-by-one, missing return)\n"
            "- Missing data generation (assumes files exist that weren't created)\n\n"
            "Respond with EXACTLY one of:\n"
            "- `PASS` — if the code looks correct and should run\n"
            "- `ISSUES:` followed by a numbered list of specific bugs to fix\n\n"
            "Do NOT rewrite the code. Only flag concrete bugs."
        ),
        "fix_after_review": (
            "A teammate reviewed your experiment code and found issues.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "## Your Original Code\n```python\n{code}\n```\n\n"
            "## Review Feedback\n{review_feedback}\n\n"
            "Fix the issues listed above. Provide the corrected code in a "
            "```python block with the same `# EXPERIMENT: {experiment_name}` header."
        ),
    },
    ResearchPhase.POST_EXECUTION: {
        "round_1": (
            "You are reviewing the computational experiment results from the EXECUTION phase.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "{recent_messages}"
            "**CRITICAL DIFFERENTIATION RULE:** If prior evaluations appear above, "
            "do NOT repeat the same assessment. Each team member must evaluate a "
            "DIFFERENT dimension:\n"
            "- If you are the FIRST to evaluate: provide the factual summary of "
            "what experiments achieved and what they did not.\n"
            "- If prior evaluations exist: focus ONLY on what they missed — "
            "methodological flaws, alternative interpretations, unstated caveats, "
            "or overlooked evidence. Do NOT restate correlation tables or results "
            "already reported.\n\n"
            "Critically evaluate these results:\n"
            "1. What do the results actually show? Distinguish strong evidence from suggestive trends.\n"
            "2. What are the limitations? (synthetic data, missing observations, failed experiments)\n"
            "3. Which hypotheses from PLANNING are supported, weakened, or untested?\n"
            "4. What caveats MUST appear in the paper?\n\n"
            "Be honest about what the experiments achieved and what they did not."
        ),
        "later_rounds": (
            "You are discussing the experimental results with your team.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "## Recent Discussion\n{recent_messages}\n\n"
            "**STRICT RULE: Do NOT repeat or re-summarize points already made above.** "
            "If a colleague already stated a finding, do NOT restate it — say "
            "'I agree with [colleague]'s point about X' and move on. Your contribution "
            "must be NOVEL — something not yet said in the discussion.\n\n"
            "Focus ONLY on:\n"
            "- Points of DISAGREEMENT about what the evidence shows\n"
            "- Limitations or caveats NOT YET mentioned by any colleague\n"
            "- Concrete FORBIDDEN claims for the writing phase (prefix with '- FORBIDDEN:')\n\n"
            "If you have nothing new to add, say 'I concur with the assessment above' "
            "and stop. A short, novel response is better than a long, repetitive one."
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
            "by evidence from the research. Use active voice where possible.\n\n"
            "**Every quantitative claim MUST trace to the Execution Fact Sheet. "
            "Do NOT invent numbers, statistics, or results not present in experiment output.**\n\n"
            "**Figure references:** If experiments produced figures, reference them in "
            "the text (e.g., 'as shown in Figure 1'). A figure that is never discussed "
            "in the text adds no value. Every figure should be introduced, described, "
            "and interpreted in the relevant section.\n\n"
            "**Anti-repetition:** Do NOT repeat the same finding in multiple paragraphs. "
            "State each result ONCE with its evidence, then move on. Readers should "
            "learn something new in every paragraph. If a point was covered in a "
            "previous section, reference it rather than restating it."
        ),
        "assembly": (
            "You are assembling a research paper from section drafts.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "## Section Drafts\n{section_drafts}\n\n"
            "Combine all section drafts into a single coherent paper. "
            "Harmonize writing style, ensure smooth transitions between sections, "
            "add a title, and make sure the paper tells a complete story. "
            "Output the full paper in markdown with ## section headers.\n\n"
            "**Verify that all numerical claims are consistent with the Execution Fact Sheet. "
            "If a number appears in the abstract, it must match the number in results.**\n\n"
            "**Figure integration:** Every figure listed in the 'Figures from Computational "
            "Experiments' section MUST be referenced in the paper text using the exact "
            "markdown syntax provided (e.g., `![Figure 1](figures/...)`). Figures should "
            "appear near their first discussion. A paper that generates figures but never "
            "discusses them is incomplete.\n\n"
            "**Eliminate redundancy:** When harmonizing sections, remove duplicate "
            "statements of the same finding. Each result should appear once in the "
            "appropriate section. The abstract summarizes; the body expands — "
            "do not copy-paste between them."
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
            "IMPORTANT: You MUST include the ## Recommendation section. "
            "Keep your review concise to ensure all sections are included. "
            "Use exactly ## headers (not ###).\n\n"
            "**Mandatory verification checklist** (check each before recommending accept):\n"
            "1. **Internal consistency:** Do claims in the abstract match claims in the "
            "body? Are numerical values consistent across sections? Flag ANY contradiction.\n"
            "2. **Data integrity:** Check tables for duplicate rows, missing values, or "
            "suspiciously uniform distributions. Flag if data looks fabricated.\n"
            "3. **Figure references:** Are all referenced figures actually present? "
            "Do not accept a paper that references figures that do not exist.\n"
            "4. **Claim-evidence alignment:** Does each major claim have supporting "
            "evidence (numbers, statistics, references)?\n"
            "5. **Anti-confabulation:** Cross-reference every quantitative claim against "
            "the Execution Fact Sheet. Flag any number not traceable to experiment output.\n"
            "6. **Forbidden claims:** Cross-reference every major claim against the "
            "Forbidden Claims list. If the paper describes a failed experiment as "
            "successful or claims results from analyses that were never completed, "
            "that is a MANDATORY REJECT regardless of other qualities.\n\n"
            "Provide a structured review with these sections (use ## headers):\n"
            "## Strengths\n- What works well\n\n"
            "## Weaknesses\n- What needs improvement\n\n"
            "## Required Changes\n- Specific changes needed before submission\n\n"
            "## Recommendation\n- Either 'accept' (ready for submission), "
            "'revise' (needs another round of revisions), or "
            "'reject' (fundamentally flawed — would not pass peer review even with revisions)\n\n"
            "**If ALL mandatory checks fail, the paper should be rejected, not merely revised.**"
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
            "{execution_metadata}"
            "**MANDATORY: Claim Verification Checklist**\n"
            "Before scoring, you MUST complete each check:\n"
            "1. For every quantitative claim in the paper (numbers, percentages, "
            "p-values, correlation coefficients, sample sizes), verify it appears "
            "in the experiment output above. Flag any claim that cannot be traced "
            "to a specific experiment result.\n"
            "2. Check whether the data is real (observational) or synthetic/simulated. "
            "If synthetic, does the paper clearly state this? Score Rigor accordingly.\n"
            "3. Look for internal contradictions: do different sections report "
            "inconsistent statistics (e.g., a chi-squared test rejecting a model "
            "that another section claims is well-fit)?\n"
            "4. Check sample sizes: are they stated? Are they large enough to "
            "support the claimed statistical significance?\n"
            "5. Check for overclaiming: does the paper claim more than the "
            "evidence supports? Are limitations adequately discussed?\n\n"
            "Provide your review in this exact format using ## headers:\n\n"
            "## Summary\nBrief summary of the paper.\n\n"
            "## Claim Verification\n"
            "For each major quantitative claim, state whether you found supporting "
            "evidence in the experiment output. Flag unverifiable or contradictory claims.\n\n"
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

_SEARCH_ENABLED_PHASES: set[ResearchPhase] = {
    ResearchPhase.IDEATION,
    ResearchPhase.PLANNING,
    ResearchPhase.EXECUTION,
    ResearchPhase.POST_EXECUTION,
}

_DEBATE_ENABLED_PHASES: set[ResearchPhase] = {
    ResearchPhase.IDEATION,
    ResearchPhase.PLANNING,
    ResearchPhase.POST_EXECUTION,
}

_CONVERGENCE_CHECK_PHASES: set[ResearchPhase] = {
    ResearchPhase.IDEATION,
    ResearchPhase.PLANNING,
    ResearchPhase.POST_EXECUTION,
}

_CONVERGENCE_CHECK_PROMPT = (
    "You are evaluating whether a group of AI research agents have converged "
    "on their core proposals during a collaborative discussion.\n\n"
    "## Phase: {phase}\n\n"
    "## Agent Messages from Recent Rounds\n{messages}\n\n"
    "Assess whether the agents have reached substantial agreement (70%+ overlap) "
    "on their core proposals, hypotheses, or plans. Minor differences in wording "
    "or emphasis do NOT count as divergence — focus on whether the substantive "
    "ideas, conclusions, or recommendations are materially the same.\n\n"
    "Be decisive: if agents are largely saying the same things with minor "
    "variations, that IS convergence. Only report non-convergence when agents "
    "have genuinely different conclusions or recommendations.\n\n"
    "Respond with ONLY a JSON object (no markdown fences, no extra text):\n"
    '{{"converged": true/false, "confidence": 0.0-1.0, "rationale": "one sentence"}}'
)

_GENERAL_LATER_ROUND_REINFORCEMENT = (
    "\n\n## Anti-Repetition Rule\n"
    "Before writing your response, review the Recent Discussion above. "
    "If a point has already been made by any colleague, do NOT restate it. "
    "Instead, either (a) extend it with new specifics, (b) challenge it, "
    "or (c) skip it entirely. Responses that repeat established points "
    "waste the team's time and token budget."
)

_CHALLENGE_INSTRUCTION = (
    "\n\n## Focused Debate\n"
    "If you strongly disagree with another agent's position and believe a "
    "focused exchange would advance the research, you may challenge them:\n"
    "  [CHALLENGE: agent-id: brief reason for disagreement]\n\n"
    "This triggers a structured debate between you and the challenged agent. "
    "Use this sparingly — only when genuine intellectual disagreement exists "
    "and a back-and-forth would produce better ideas than the normal round.\n\n"
    "**Do NOT re-challenge an agent on a topic that was already debated and "
    "resolved in an earlier round or phase.**\n"
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
# Synthesis closing templates (structured phase conclusions)
# ---------------------------------------------------------------------------

_SYNTHESIS_CLOSING_TEMPLATES: dict[ResearchPhase, str] = {
    ResearchPhase.IDEATION: (
        "You are the synthesizer closing the IDEATION phase.\n"
        "Topic: {seed_prompt}\n\n"
        "## Recent Discussion\n{recent_messages}\n\n"
        "Write a structured synthesis with EXACTLY these sections:\n\n"
        "### Agreed Hypotheses\n"
        "List each hypothesis the team converged on, with one sentence of supporting rationale.\n\n"
        "### Unresolved Questions\n"
        "List open questions or disagreements that need resolution in PLANNING.\n\n"
        "### Scope Boundaries\n"
        "What is explicitly IN scope and OUT of scope for this research.\n\n"
        "Be concise — this synthesis will be carried forward to all subsequent phases."
    ),
    ResearchPhase.PLANNING: (
        "You are the synthesizer closing the PLANNING phase.\n"
        "Topic: {seed_prompt}\n\n"
        "## Recent Discussion\n{recent_messages}\n\n"
        "Write a structured synthesis with EXACTLY these sections:\n\n"
        "### Prioritized Experiment List\n"
        "Numbered list of experiments to run, in priority order. "
        "Each must include: objective, method, success criterion.\n\n"
        "### Agreed Methodology\n"
        "Key methodological decisions the team agreed on.\n\n"
        "### Open Risks\n"
        "Known risks, data limitations, or potential failure modes.\n\n"
        "Be concise — this synthesis will guide the EXECUTION phase."
    ),
    ResearchPhase.POST_EXECUTION: (
        "You are the synthesizer closing the POST_EXECUTION phase.\n"
        "Topic: {seed_prompt}\n\n"
        "## Recent Discussion\n{recent_messages}\n\n"
        "Write a structured synthesis with EXACTLY these sections:\n\n"
        "### Validated Findings\n"
        "What the experiments conclusively demonstrated, with specific numbers.\n\n"
        "### Failed or Inconclusive Analyses\n"
        "Experiments that failed, produced ambiguous results, or were not attempted.\n\n"
        "### Paper Scope Agreement\n"
        "What the paper SHOULD claim and what it MUST NOT claim, "
        "based on the actual evidence.\n\n"
        "### FORBIDDEN CLAIMS\n"
        "List specific claims the paper MUST NOT make, using this exact format:\n"
        "- FORBIDDEN: [specific claim that must not appear]\n"
        "- FORBIDDEN: [another specific claim]\n"
        "For each failed experiment, there must be at least one FORBIDDEN entry "
        "preventing the paper from describing that experiment as successful.\n\n"
        "Be concise — this synthesis will guide the WRITING phase."
    ),
}

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
    ResearchPhase.POST_EXECUTION: {
        "theorist",
        "analyst",
        "synthesizer",
        "skeptic",
        "experimentalist",
    },
}

_PHASE_CONTEXT_NEEDS: dict[ResearchPhase, set[str]] = {
    ResearchPhase.IDEATION: {"literature", "references", "memory"},
    ResearchPhase.PLANNING: {"literature", "code_data", "memory"},
    ResearchPhase.POST_EXECUTION: {"literature", "execution", "memory"},
}

# ---------------------------------------------------------------------------
# Numeric limits
# ---------------------------------------------------------------------------

_WRITING_MAX_TOKENS = 32768
_REVIEW_MAX_TOKENS = 8192
_PAPER_CONTEXT_LIMIT = 50000
_LITERATURE_CONTEXT_LIMIT = 15000
_MIN_PAPER_LENGTH = 10000
_EXECUTION_OUTPUT_LIMIT = 4000
_EXECUTION_STDERR_LIMIT = 2000
_PEER_REVIEW_METADATA_LIMIT = 8000
_MAX_RETRIES_PER_EXPERIMENT = 2
_MAX_TOTAL_EXPERIMENTS_PER_PHASE = 50
# (Also exposed as _RECENT_MESSAGES_LIMIT above)

# Literature handler magic numbers
_TITLE_TRUNCATION_INDEX = 80
_TITLE_TRUNCATION_SHORT = 60
_STALE_SEARCH_THRESHOLD = 5
_CONSECUTIVE_STALE_LIMIT = 2
_FOLLOW_EXAMPLES_COUNT = 3
_PER_AGENT_CAP_MIN = 1
_PER_AGENT_CAP_NUMERATOR = 2
_PER_AGENT_CAP_DENOMINATOR = 5
_DATA_REQUESTS_PER_ROUND = 3

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
# Data-related error patterns (trigger auto literature search)
# ---------------------------------------------------------------------------

_DATA_ERROR_PATTERNS: list[str] = [
    "negative values",
    "NaN",
    "nan",
    "missing columns",
    "invalid value encountered",
    "could not convert",
    "empty DataFrame",
    "no data",
    "shape mismatch",
    "singular matrix",
    "convergence failed",
    "overflow",
    "underflow",
]

# ---------------------------------------------------------------------------
# Code block regexes
# ---------------------------------------------------------------------------

_CODE_BLOCK_RE = re.compile(r"```python\s*\n(.*?)```", re.DOTALL)
_EXPERIMENT_NAME_RE = re.compile(r"^#\s*EXPERIMENT:\s*(.+)", re.MULTILINE)
_EXPERIMENT_DEPENDS_RE = re.compile(r"^#\s*DEPENDS:\s*(.+)", re.MULTILINE)


@dataclass(frozen=True)
class CodeBlock:
    """A parsed experiment code block with optional dependencies."""

    name: str
    code: str
    depends_on: tuple[str, ...]  # empty if no dependencies


# ---------------------------------------------------------------------------
# Stop words for fuzzy query normalization
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset(
    {
        # Standard English stop words
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
        # Scientific filler — common in queries but carry no discriminative meaning
        "analysis",
        "based",
        "between",
        "can",
        "during",
        "effect",
        "evidence",
        "evolution",
        "model",
        "new",
        "observation",
        "observed",
        "properties",
        "recent",
        "relation",
        "role",
        "study",
        "using",
        "through",
        "which",
    }
)

# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def _extract_code_blocks(text: str) -> list[CodeBlock]:
    """Extract Python code blocks from agent response text.

    Looks for fenced ```python blocks. Extracts experiment name from
    a ``# EXPERIMENT: name`` comment on the first line, and optional
    dependencies from a ``# DEPENDS: dep1, dep2`` comment.

    Args:
        text: Agent response text.

    Returns:
        List of CodeBlock instances.
    """
    blocks: list[CodeBlock] = []
    for match in _CODE_BLOCK_RE.finditer(text):
        code = match.group(1).strip()
        if not code:
            continue
        name_match = _EXPERIMENT_NAME_RE.match(code)
        name = name_match.group(1).strip() if name_match else "unnamed_experiment"
        # Parse dependencies
        deps_match = _EXPERIMENT_DEPENDS_RE.search(code)
        if deps_match:
            deps = tuple(d.strip() for d in deps_match.group(1).split(",") if d.strip())
        else:
            deps = ()
        blocks.append(CodeBlock(name=name, code=code, depends_on=deps))
    return blocks


def _topological_sort(blocks: list[CodeBlock]) -> list[CodeBlock]:
    """Sort code blocks by dependency order. Cycles fall back to original order.

    Dependencies referencing names not in the current batch are ignored
    (they were likely executed in a prior round).

    Args:
        blocks: List of CodeBlock instances to sort.

    Returns:
        Topologically sorted list of CodeBlock instances.
    """
    if len(blocks) <= 1:
        return list(blocks)

    name_to_block = {b.name: b for b in blocks}
    batch_names = set(name_to_block.keys())

    # Build adjacency: dep → list of dependents
    # Filter to only in-batch dependencies
    adj: dict[str, list[str]] = {b.name: [] for b in blocks}
    in_degree: dict[str, int] = {b.name: 0 for b in blocks}

    for block in blocks:
        for dep in block.depends_on:
            if dep in batch_names:
                adj[dep].append(block.name)
                in_degree[block.name] += 1

    # Kahn's algorithm
    queue = [name for name in in_degree if in_degree[name] == 0]
    # Stable sort: process in original order among same-level nodes
    original_order = {b.name: i for i, b in enumerate(blocks)}
    queue.sort(key=lambda n: original_order[n])

    sorted_names: list[str] = []
    while queue:
        current = queue.pop(0)
        sorted_names.append(current)
        for dependent in adj[current]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)
                queue.sort(key=lambda n: original_order[n])

    # Cycle detected — fall back to original order
    if len(sorted_names) != len(blocks):
        return list(blocks)

    return [name_to_block[n] for n in sorted_names]


def _get_downstream_dependents(failed_name: str, blocks: list[CodeBlock]) -> set[str]:
    """Find all experiments transitively depending on a failed experiment.

    Args:
        failed_name: Name of the failed experiment.
        blocks: All code blocks in the current batch.

    Returns:
        Set of experiment names that transitively depend on failed_name.
    """
    batch_names = {b.name for b in blocks}
    # Build adjacency: dep → set of direct dependents
    adj: dict[str, set[str]] = {b.name: set() for b in blocks if b.name in batch_names}
    for block in blocks:
        for dep in block.depends_on:
            if dep in adj:
                adj[dep].add(block.name)

    # BFS from failed_name
    visited: set[str] = set()
    frontier = list(adj.get(failed_name, set()))
    while frontier:
        current = frontier.pop()
        if current in visited:
            continue
        visited.add(current)
        frontier.extend(adj.get(current, set()) - visited)

    return visited


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
    threshold: float = 0.4,
) -> bool:
    """Check if a query is a near-duplicate of any previously executed query.

    Uses two checks:
    1. Jaccard similarity: |A ∩ B| / |A ∪ B| >= threshold
    2. Subset/superset: if new query's keywords are a subset (or superset)
       of an existing query, it's a duplicate regardless of Jaccard score.

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
        # Subset/superset check: if one query fully contains the other,
        # the narrower query won't find anything new
        if new_keywords <= existing or existing <= new_keywords:
            return True
        intersection = len(new_keywords & existing)
        union = len(new_keywords | existing)
        if union > 0 and intersection / union >= threshold:
            return True
    return False


def _filter_relevant_papers(
    query: str,
    papers: list,
    threshold: float = 0.15,
) -> list:
    """Filter search results by keyword relevance to the query.

    Uses query coverage (fraction of query keywords present in paper
    title/summary). This avoids the Jaccard penalty where papers with
    long abstracts dilute the score despite being relevant.

    Args:
        query: The search query string.
        papers: List of paper objects (must have .title and optionally .summary).
        threshold: Minimum query coverage to keep a paper.

    Returns:
        Filtered list of papers above the threshold.
    """
    if threshold <= 0 or not papers:
        return papers

    query_kw = _normalize_query_keywords(query)
    if not query_kw:
        return papers

    filtered = []
    for paper in papers:
        # Combine title and summary (if available) for matching
        text = paper.title
        if hasattr(paper, "summary") and paper.summary:
            text += " " + paper.summary
        paper_kw = _normalize_query_keywords(text)
        if not paper_kw:
            continue
        coverage = len(query_kw & paper_kw) / len(query_kw)
        if coverage >= threshold:
            filtered.append(paper)
    return filtered


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
