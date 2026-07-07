"""Experimentation-phase handler — extracted from OrchestrationEngine."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from paradigm.literature.resources import ResourceType
from paradigm.orchestrator.constants import (
    _ADVISORY_PROMPT_TEMPLATE,
    _DATA_ERROR_PATTERNS,
    _EXECUTION_STDERR_LIMIT,
    _FILE_NOT_FOUND_PATTERNS,
    _MAX_RETRIES_PER_EXPERIMENT,
    _MAX_TOTAL_EXPERIMENTS_PER_PHASE,
    _NETWORK_ERROR_PATTERNS,
    _PHASE_INSTRUCTIONS,
    _WRITING_MAX_TOKENS,
    _best_first_order,
    _extract_code_blocks,
    _format_execution_result,
    _is_vacuous_success,
    _list_shared_files,
    _network_caveat,
    _normalize_query_keywords,
    _topological_sort,
)
from paradigm.orchestrator.phases import ResearchPhase
from paradigm.orchestrator.verification import _extract_result_tokens
from paradigm.sandbox.executor import CodeExecutor
from paradigm.sandbox.models import ExecutionRequest, ExecutionResult, ExecutionStatus

if TYPE_CHECKING:
    from paradigm.agents.base import Agent
    from paradigm.knowledge.models import PredictionRule
    from paradigm.orchestrator.engine import OrchestrationEngine


def _format_rule_bound(rule: PredictionRule) -> str:
    """Human-readable description of when a pre-registered prediction holds."""
    key = rule.metric_stdout_key
    direction = str(rule.direction)
    if direction == "inside" and rule.low is not None and rule.high is not None:
        return f"claim holds when {rule.low:g} <= {key} <= {rule.high:g}"
    if direction == "outside" and rule.low is not None and rule.high is not None:
        return f"claim holds when {key} < {rule.low:g} or {key} > {rule.high:g}"
    if direction == "greater" and rule.low is not None:
        return f"claim holds when {key} > {rule.low:g}"
    if direction == "less" and rule.high is not None:
        return f"claim holds when {key} < {rule.high:g}"
    return f"report {key}"


def _truncate_code_for_retry(code: str, error_lineno: int | None, context_lines: int = 10) -> str:
    """Return the failed code for the retry prompt — IN FULL.

    The model's retry response REPLACES the entire script, so it must see the whole
    program to return a complete, runnable fix. Previously this showed only an
    'error region' slice (±context_lines) of any script over 40 lines; the model
    then returned just that slice, dropping every function/variable definition
    elsewhere and turning one bug into a cascade of NameErrors (which made any
    multi-step experiment unrecoverable). The error location is conveyed separately
    via the error feedback, so no truncation is needed here. Args kept for
    backwards-compatible call sites.
    """
    _ = (error_lineno, context_lines)  # intentionally unused — see docstring
    return code


class SprintStopReason(Enum):
    """Reason for stopping execution sprints early."""

    SUFFICIENT = "sufficient"
    PIVOT = "pivot"


def _peek_csv_schema(filepath: Path, max_cols: int = 12) -> str:
    """Return column names from a CSV file header row.

    Args:
        filepath: Path to a CSV file.
        max_cols: Maximum number of columns to show.

    Returns:
        Compact schema string, or empty string on error.
    """
    import csv

    try:
        with open(filepath, newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
        if not header:
            return ""
        row_count = sum(1 for _ in open(filepath)) - 1  # exclude header
        cols = header[:max_cols]
        extra = f" ... +{len(header) - max_cols} more" if len(header) > max_cols else ""
        return f"CSV columns ({row_count} rows): {cols}{extra}"
    except (OSError, UnicodeDecodeError, StopIteration):
        return ""


def _peek_json_schema(filepath: Path, max_keys: int = 8) -> str:
    """Return compact schema description of a JSON file.

    Args:
        filepath: Path to a JSON file.
        max_keys: Maximum number of keys to show.

    Returns:
        Compact schema string, or empty string on error.
    """
    import json

    try:
        text = filepath.read_text()[:10_000]
        data = json.loads(text)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return ""
    if isinstance(data, dict):
        keys = list(data.keys())[:max_keys]
        extra = f" ... +{len(data) - max_keys} more" if len(data) > max_keys else ""
        return f"dict with keys: {keys}{extra}"
    elif isinstance(data, list):
        if not data:
            return "empty list"
        first = data[0]
        if isinstance(first, dict):
            keys = list(first.keys())[:max_keys]
            extra = f" ... +{len(first) - max_keys} more" if len(first) > max_keys else ""
            return f"list[dict] len={len(data)}, entry keys: {keys}{extra}"
        return f"list[{type(first).__name__}] len={len(data)}"
    return f"type: {type(data).__name__}"


def _build_workspace_manifest(workspace_dir: Path) -> str:
    """List files in the workspace directory with sizes.

    Provides experimenters with an exact listing of files available
    from previous experiments, preventing wrong-filename errors.

    Args:
        workspace_dir: Path to the workspace directory.

    Returns:
        Formatted manifest block, or empty string if no files exist.
    """
    if not workspace_dir.exists():
        return ""

    files = sorted(f for f in workspace_dir.rglob("*") if f.is_file())
    if not files:
        return ""

    lines = ["## Available Workspace Files"]
    lines.append("Files saved by previous experiments in /data/workspace/:")
    for f in files[:30]:
        rel = f.relative_to(workspace_dir)
        size = f.stat().st_size
        if size < 1024:
            size_str = f"{size} B"
        elif size < 1024 * 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size / (1024 * 1024):.1f} MB"
        lines.append(f"- `/data/workspace/{rel}` ({size_str})")
        if f.suffix == ".json" and size < 500_000:
            schema = _peek_json_schema(f)
            if schema:
                lines.append(f"  Schema: {schema}")
        elif f.suffix == ".csv" and size < 500_000:
            schema = _peek_csv_schema(f)
            if schema:
                lines.append(f"  Schema: {schema}")
    if len(files) > 30:
        lines.append(f"  ... and {len(files) - 30} more files")
    lines.append("")
    return "\n".join(lines)


def _artifact_kind(filename: str) -> str:
    """Classify an experiment output file for dashboard artifact events."""
    if filename.endswith((".png", ".pdf", ".svg", ".jpg", ".jpeg")):
        return "figure"
    if filename.endswith((".csv", ".tsv")):
        return "table"
    return "data"


def _artifact_rel_path(engine: OrchestrationEngine, path: str | Path) -> str:
    """Path relative to the data dir, so the dashboard server can serve the file."""
    try:
        data_dir = engine._config.storage.data_dir.resolve()
        return str(Path(path).resolve().relative_to(data_dir))
    except (ValueError, OSError):
        return str(path)


def _build_auto_search_query(seed_prompt: str, error_text: str) -> str:
    """Build a focused search query from seed prompt and error context.

    Extracts the top 5 most specific content words from the seed prompt
    (longest words first, as they tend to be more domain-specific) and
    appends error-specific context keywords.

    Args:
        seed_prompt: The research topic / seed prompt.
        error_text: Combined error text from the failed experiment.

    Returns:
        Search query string suitable for literature search.
    """
    keywords = sorted(_normalize_query_keywords(seed_prompt), key=len, reverse=True)[:5]

    # Append error-specific context
    error_lower = error_text.lower()
    if "nan" in error_lower or "overflow" in error_lower or "underflow" in error_lower:
        keywords.append("numerical stability")
    elif "no data" in error_lower or "empty dataframe" in error_lower:
        keywords.append("data availability")
    elif "singular matrix" in error_lower or "convergence failed" in error_lower:
        keywords.append("numerical methods")
    elif "shape mismatch" in error_lower or "missing columns" in error_lower:
        keywords.append("data format")
    else:
        keywords.append("methodology")

    return " ".join(keywords)


def _categorize_failure(result: ExecutionResult) -> str:
    """Categorize an execution failure into a high-level category.

    Args:
        result: Failed execution result.

    Returns:
        Category string.
    """
    if result.status == ExecutionStatus.TIMEOUT:
        return "timeout"

    if result.status == ExecutionStatus.REJECTED:
        return "safety_rejection"

    stderr = result.stderr or ""
    stdout = result.stdout or ""
    combined = stderr + stdout

    # Check network errors
    if any(p in combined for p in _NETWORK_ERROR_PATTERNS):
        return "network_error"

    # Check module not found
    if "ModuleNotFoundError" in combined:
        return "module_not_found"

    # Check file not found
    if any(p in combined for p in _FILE_NOT_FOUND_PATTERNS):
        return "file_not_found"

    # Check for vacuous output
    if result.status == ExecutionStatus.SUCCESS and _is_vacuous_success(result):
        return "vacuous_output"

    return "execution_error"


@dataclass
class ExperimentationResult:
    """Return value of the experimentation phase."""

    execution_context: str = ""
    execution_figures: list[tuple[str, Path]] = field(default_factory=list)
    successful_code: list[tuple[str, str]] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    experiment_metadata: list[dict[str, str | bool]] = field(default_factory=list)


class ExperimentationHandler:
    """Handles the EXECUTION phase: agents propose and run computational experiments."""

    def __init__(self, engine: OrchestrationEngine) -> None:
        self._engine = engine
        # Cross-round failure tracking (Fix 1)
        self._failure_categories: dict[str, int] = {}
        self._consecutive_failures: int = 0
        self._strategy_redirects: int = 0
        # Limit auto literature search to once per retry cycle
        self._auto_searched: bool = False
        # Persistent memory of specific environment facts from prior failures
        self._learned_constraints: list[str] = []
        # Sprint tracking
        self._current_sprint: int = 0
        self._sprint_results: list[str] = []
        # 1C: experiments that have failed at least once this phase (for best-first ordering)
        self._buggy_experiments: set[str] = set()

    async def run_experimentation_phase(self) -> ExperimentationResult:
        """Run the EXECUTION phase: agents propose and run computational experiments.

        Returns:
            ExperimentationResult with execution context and figures.
        """
        engine = self._engine
        explicit = engine._config.orchestrator.max_experiment_rounds
        max_rounds = (
            explicit
            if explicit is not None
            else 2 * engine._config.orchestrator.max_rounds_per_phase
        )

        # Collect sandbox paths for cloned repos (PYTHONPATH injection)
        repo_paths = [
            r.sandbox_path
            for r in engine.state.resolved_resources
            if r.resource_type == ResourceType.CODE_REPO and r.sandbox_path and r.error is None
        ]
        # Also add parent directories of CODE_FILE resources so they are importable
        code_file_dirs = {
            str(Path(r.sandbox_path).parent)
            for r in engine.state.resolved_resources
            if r.resource_type == ResourceType.CODE_FILE and r.sandbox_path and r.error is None
        }
        repo_paths.extend(sorted(code_file_dirs))

        # Per-thread workspace persists across executions so experiments
        # can read files (CSVs, data) produced by earlier experiments.
        workspace_dir = engine._config.storage.data_dir / "workspaces" / engine.state.thread_id
        workspace_dir.mkdir(parents=True, exist_ok=True)

        executor = CodeExecutor(
            config=engine._config.sandbox,
            logger=engine._logger,
            data_dir=engine._config.storage.data_dir,
            workspace_dir=workspace_dir,
        )

        all_results: list[str] = []
        execution_figures: list[tuple[str, Path]] = []
        successful_code: list[tuple[str, str]] = []
        experiment_metadata: list[dict[str, str | bool]] = []

        # Caveat tracking
        _had_network_error = False
        _had_timeout = False
        _vacuous_count = 0
        _circuit_breaker_fired = False
        _total_experiments = 0
        _total_failures = 0

        # Reset cross-round failure tracking for this phase
        self._failure_categories = {}
        self._consecutive_failures = 0
        self._strategy_redirects = 0
        self._buggy_experiments = set()
        _strategy_redirect_message = ""
        _advisory_message = ""
        _skipped_message = ""

        # Sprint configuration
        enable_sprints = engine._config.orchestrator.enable_execution_sprints
        num_sprints = engine._config.orchestrator.num_execution_sprints if enable_sprints else 1
        rounds_per_sprint = max(1, -(-max_rounds // num_sprints))  # ceil division

        global_round = 0

        try:
            for sprint_num in range(1, num_sprints + 1):
                self._current_sprint = sprint_num
                self._sprint_results = []

                if enable_sprints:
                    engine._display.sprint_start(sprint_num, num_sprints)

                # Find experimenter early (needed for design review)
                experimenter = engine._find_agent_by_role("experimentalist")
                if experimenter is None:
                    experimenter = engine._find_agent_by_role("analyst")
                if experimenter is None:
                    engine._display.experiment_no_agent()
                    break

                # Build checkpoint context (shared across sprint sub-phases)
                checkpoint_context = ""
                if engine.state.checkpoint:
                    checkpoint_context = engine.state.checkpoint.to_context_string() + "\n\n"
                file_listing = _list_shared_files(
                    engine._config.storage.data_dir, engine.state.wall_start_time
                )
                checkpoint_context = file_listing + "\n\n" + checkpoint_context
                if engine.state.code_context:
                    checkpoint_context += engine.state.code_context + "\n\n"
                if engine.state.data_context:
                    checkpoint_context += engine.state.data_context + "\n\n"

                previous_results = "\n\n".join(all_results) if all_results else ""

                # --- DESIGN REVIEW (sprint mode only) ---
                design_feedback = ""
                if enable_sprints:
                    design_feedback = await self._run_sprint_design_review(
                        experimenter,
                        sprint_num,
                        num_sprints,
                        checkpoint_context,
                        previous_results,
                    )

                # --- EXECUTE (existing round loop for this sprint's allocation) ---
                sprint_start_round = global_round + 1
                sprint_end_round = min(global_round + rounds_per_sprint, max_rounds)

                for round_num in range(sprint_start_round, sprint_end_round + 1):
                    global_round = round_num
                    # Between-experiment pause gate + steering pickup (typed
                    # guidance becomes OPERATOR DIRECTIVE lines on the plan,
                    # which the prompt below re-reads every round).
                    await engine._execution_checkpoint()
                    engine._display.experiment_round(round_num, max_rounds)
                    engine._literature.search_count_this_round = 0

                    # Re-find experimenter each round (same pattern as before)
                    experimenter = engine._find_agent_by_role("experimentalist")
                    if experimenter is None:
                        experimenter = engine._find_agent_by_role("analyst")
                    if experimenter is None:
                        engine._display.experiment_no_agent()
                        break

                    # Rebuild checkpoint context per round (workspace manifest updates)
                    checkpoint_context = ""
                    if engine.state.checkpoint:
                        checkpoint_context = engine.state.checkpoint.to_context_string() + "\n\n"
                    file_listing = _list_shared_files(
                        engine._config.storage.data_dir, engine.state.wall_start_time
                    )
                    checkpoint_context = file_listing + "\n\n" + checkpoint_context
                    if engine.state.code_context:
                        checkpoint_context += engine.state.code_context + "\n\n"
                    if engine.state.data_context:
                        checkpoint_context += engine.state.data_context + "\n\n"

                    # Inject workspace manifest for round 2+ so agents know
                    # which files were saved by prior experiments
                    if round_num > 1:
                        ws_manifest = _build_workspace_manifest(workspace_dir)
                        if ws_manifest:
                            checkpoint_context = ws_manifest + "\n\n" + checkpoint_context

                    previous_results = "\n\n".join(all_results) if all_results else ""

                    net_caveat = _network_caveat(engine._config.sandbox.network_mode != "none")

                    if round_num == 1:
                        template = _PHASE_INSTRUCTIONS[ResearchPhase.EXECUTION][
                            "propose_experiment"
                        ]
                        prompt = template.format(
                            seed_prompt=engine.state.seed_prompt,
                            checkpoint_context=checkpoint_context,
                            previous_results=previous_results,
                            network_caveat=net_caveat,
                        )
                    else:
                        template = _PHASE_INSTRUCTIONS[ResearchPhase.EXECUTION]["analyze_results"]
                        prompt = template.format(
                            seed_prompt=engine.state.seed_prompt,
                            checkpoint_context=checkpoint_context,
                            previous_results=previous_results,
                            network_caveat=net_caveat,
                        )

                    # Inject design review feedback into first round of each sprint
                    if round_num == sprint_start_round and design_feedback:
                        prompt += design_feedback
                        design_feedback = ""

                    # Inject planning action items (Fix 5)
                    if engine.state.planning_action_items:
                        prompt += (
                            "\n\n## Planned Experiments (from PLANNING phase)\n"
                            "The team agreed on these experiments during planning. "
                            "Execute them in order of priority:\n"
                            + engine.state.planning_action_items
                        )

                    # Inject the console-as-data-bus contract (1B): print key numbers as
                    # machine-readable tokens so results can be re-extracted and verified.
                    if engine._config.orchestrator.enable_verification:
                        prompt += (
                            "\n\n## MACHINE-READABLE RESULTS (required)\n"
                            "Print every key numerical result to stdout on its own line as "
                            "`RESULT[<label>]=<value>` (e.g. `RESULT[rmse]=0.123`). These exact "
                            "tokens are re-extracted and the code is re-run to verify the result "
                            "reproduces — do not omit or rename them."
                        )

                    # Inject pre-registered predictions (1A): the experimentalist MUST
                    # compute and print each metric token so the verdict can be evaluated.
                    if engine.state.registered_rules:
                        rule_lines = [
                            "\n\n## PRE-REGISTERED PREDICTIONS (you MUST report these)",
                            "For each prediction below, compute the metric and print it on its "
                            "own line as `<metric_stdout_key>=<value>` (and `<key>_p=<value>` if a "
                            "p-value is required). These EXACT tokens are parsed to decide whether "
                            "each hypothesis is confirmed or refuted — do not rename them.",
                        ]
                        for r in engine.state.registered_rules:
                            rule_lines.append(
                                f"- `{r.metric_stdout_key}` ({r.metric_name}): "
                                f"{_format_rule_bound(r)}. Refutation: {r.refutation_condition}"
                            )
                        prompt += "\n".join(rule_lines) + "\n"

                    # Inject strategy redirect, advisory, and skipped-experiment messages
                    if _strategy_redirect_message:
                        prompt += _strategy_redirect_message
                        _strategy_redirect_message = ""
                    if _advisory_message:
                        prompt += _advisory_message
                        _advisory_message = ""
                    if _skipped_message:
                        prompt += _skipped_message
                        _skipped_message = ""

                    # Inject learned constraints from prior failures
                    if self._learned_constraints:
                        prompt += (
                            "\n\n## LEARNED CONSTRAINTS (from prior failures — do NOT violate)\n"
                            + "\n".join(f"- {c}" for c in self._learned_constraints)
                            + "\n"
                        )

                    try:
                        response = await experimenter.generate(
                            prompt, max_tokens=_WRITING_MAX_TOKENS
                        )
                    except Exception as e:
                        engine._logger.log_error(
                            e, agent_id=experimenter.agent_id, thread_id=engine.state.thread_id
                        )
                        engine._display.agent_error(experimenter.agent_id, e)
                        break

                    engine._log_agent_response(
                        experimenter.agent_id,
                        response,
                        ResearchPhase.EXECUTION,
                        "experiment_proposal",
                    )

                    await engine._literature.process_search_requests(
                        experimenter.agent_id, response.content, ResearchPhase.EXECUTION
                    )
                    await engine._literature.process_literature_actions(
                        experimenter.agent_id, response.content, ResearchPhase.EXECUTION
                    )

                    # Extract code blocks
                    code_blocks = _extract_code_blocks(response.content)
                    if not code_blocks and round_num > 1:
                        engine._display.experiment_declared_sufficient()
                        break
                    if not code_blocks:
                        engine._display.experiment_no_code()
                        continue

                    # Sort by dependency order and execute
                    code_blocks = _topological_sort(code_blocks)
                    # 1C: prefer non-buggy experiments within the round (default-off).
                    if engine._config.orchestrator.enable_best_first_nodes:
                        code_blocks = _best_first_order(
                            code_blocks,
                            self._buggy_experiments,
                            engine._config.orchestrator.debug_buggy_node_prob,
                            random.Random(f"{engine.state.thread_id}:{round_num}"),
                        )
                    round_total = 0
                    round_failures = 0
                    failed_in_round: set[str] = set()
                    skipped_experiments: list[str] = []

                    for block in code_blocks:
                        # Check dependency failures — skip if upstream failed
                        unmet = [dep for dep in block.depends_on if dep in failed_in_round]
                        if unmet:
                            engine._display.experiment_skipped(block.name, unmet)
                            skipped_experiments.append(block.name)
                            failed_in_round.add(block.name)  # Transitively propagate
                            experiment_metadata.append(
                                {
                                    "name": block.name,
                                    "status": "skipped",
                                    "stdout_preview": "",
                                    "stdout_full": "",
                                    "has_figures": False,
                                    "failure_reason": (
                                        f"Skipped: upstream dependency failed ({', '.join(unmet)})"
                                    ),
                                }
                            )
                            skip_result = (
                                f"## {block.name}\n**Status:** skipped "
                                f"(upstream dependency failed: {', '.join(unmet)})\n"
                            )
                            all_results.append(skip_result)
                            self._sprint_results.append(skip_result)
                            continue

                        # Enforce total experiment cap per phase
                        if _total_experiments >= _MAX_TOTAL_EXPERIMENTS_PER_PHASE:
                            engine._display.experiment_budget_exhausted(_total_experiments)
                            break

                        current_code = block.code

                        # Pre-execution code review (opt-in)
                        if engine._config.orchestrator.enable_pre_execution_review:
                            review_feedback = await self._pre_execution_review(
                                current_code, block.name
                            )
                            if review_feedback is not None:
                                current_code = await self._apply_review_fixes(
                                    experimenter,
                                    current_code,
                                    block.name,
                                    review_feedback,
                                    checkpoint_context,
                                )

                        engine._display.experiment_running(block.name)
                        engine.emit_event(
                            "experiment.started",
                            {"experiment_id": block.name, "title": block.name},
                            agent=experimenter.agent_id if experimenter else None,
                        )
                        # Phase C: stream the experiment to the live panel (code now,
                        # stdout + parsed RESULT[...] once it finishes below).
                        engine._display.experiment_update(
                            experiment_id=block.name,
                            name=block.name,
                            agent_id=experimenter.agent_id if experimenter else "",
                            status="running",
                            code=current_code,
                        )
                        result, final_code = await self._execute_with_retry(
                            executor,
                            experimenter,
                            block.name,
                            current_code,
                            checkpoint_context,
                            repo_paths=repo_paths,
                            workspace_dir=workspace_dir,
                        )
                        formatted = _format_execution_result(block.name, result)
                        all_results.append(formatted)
                        self._sprint_results.append(formatted)

                        _total_experiments += 1
                        round_total += 1
                        if result.status == ExecutionStatus.SUCCESS:
                            successful_code.append((block.name, final_code))
                            self._consecutive_failures = 0
                        else:
                            round_failures += 1
                            _total_failures += 1
                            self._consecutive_failures += 1
                            failed_in_round.add(block.name)
                            self._buggy_experiments.add(block.name)  # 1C best-first signal

                            # Categorize failure for strategy redirect
                            category = _categorize_failure(result)
                            self._failure_categories[category] = (
                                self._failure_categories.get(category, 0) + 1
                            )

                            # Strategy redirect: same-category failures exceed threshold
                            max_strat = engine._config.orchestrator.max_strategy_retries
                            if self._failure_categories[category] >= max_strat:
                                engine._display.experiment_strategy_redirect(
                                    category, self._failure_categories[category]
                                )
                                _strategy_redirect_message = (
                                    f"\n\n## STRATEGY REDIRECT\n"
                                    f"You have failed "
                                    f"{self._failure_categories[category]} times "
                                    f"with '{category}' errors. Your current approach "
                                    f"is NOT working. Try a FUNDAMENTALLY different "
                                    f"approach — different algorithm, different data "
                                    f"source, or different analysis entirely."
                                )
                                self._strategy_redirects += 1

                            # Multi-agent advisory: consecutive failures exceed threshold
                            advisory_threshold = (
                                engine._config.orchestrator.execution_advisory_threshold
                            )
                            if (
                                engine._config.orchestrator.enable_execution_advisory
                                and self._consecutive_failures >= advisory_threshold
                                and experimenter is not None
                            ):
                                _advisory_message = await self._request_advisory(
                                    experimenter.agent_id
                                )
                                self._consecutive_failures = 0  # Reset after advisory

                        # Track caveat triggers
                        if result.status == ExecutionStatus.TIMEOUT:
                            _had_timeout = True
                        stderr_text = result.stderr or ""
                        if any(p in stderr_text for p in _NETWORK_ERROR_PATTERNS):
                            _had_network_error = True

                        # Track output figures + dashboard artifacts
                        exp_artifacts: list[dict[str, str]] = []
                        for output_file in result.output_files:
                            kind = _artifact_kind(output_file.filename)
                            rel = _artifact_rel_path(engine, output_file.path)
                            exp_artifacts.append({"path": rel, "kind": kind})
                            if output_file.filename.endswith((".png", ".pdf")):
                                execution_figures.append((block.name, Path(output_file.path)))
                                engine.emit_event(
                                    "artifact.created",
                                    {"path": rel, "kind": "figure", "experiment_id": block.name},
                                )

                        status_str = result.status.value
                        engine._display.experiment_result(block.name, status_str)
                        engine.emit_event(
                            "experiment.completed",
                            {
                                "experiment_id": block.name,
                                "status": status_str,
                                "artifacts": exp_artifacts,
                            },
                        )

                        # Build metadata entry for the execution fact sheet
                        stdout_preview = (result.stdout or "")[:200]
                        stdout_full = (result.stdout or "")[:2000]
                        has_figures = any(
                            f.filename.endswith((".png", ".pdf")) for f in result.output_files
                        )
                        # Phase C: final experiment state to the live panel.
                        engine._display.experiment_update(
                            experiment_id=block.name,
                            name=block.name,
                            agent_id=experimenter.agent_id if experimenter else "",
                            status=status_str,
                            code=final_code,
                            stdout=stdout_full,
                            results=_extract_result_tokens(result.stdout or ""),
                            has_figures=has_figures,
                            figures=[a["path"] for a in exp_artifacts if a["kind"] == "figure"],
                        )
                        failure_reason = ""
                        if result.status != ExecutionStatus.SUCCESS:
                            if result.error_message:
                                failure_reason = result.error_message[:500]
                            elif result.stderr:
                                failure_reason = result.stderr[:500]
                            else:
                                failure_reason = f"Exited with status: {status_str}"
                        experiment_metadata.append(
                            {
                                "name": block.name,
                                "status": status_str,
                                "stdout_preview": stdout_preview,
                                "stdout_full": stdout_full,
                                "has_figures": has_figures,
                                "failure_reason": failure_reason,
                            }
                        )

                    # Inject skipped-experiment message for next round
                    if skipped_experiments:
                        _skipped_message = (
                            "\n\n## Skipped Experiments\n"
                            "These experiments were skipped because upstream "
                            "dependencies failed:\n"
                            + "\n".join(f"- {name}" for name in skipped_experiments)
                            + "\nRe-propose these (or alternatives) with fixed "
                            "dependencies."
                        )

                    # Total experiment budget exhausted — break outer loop too
                    if _total_experiments >= _MAX_TOTAL_EXPERIMENTS_PER_PHASE:
                        _circuit_breaker_fired = True
                        break

                    # Per-round circuit breaker: if >70% of executions failed, stop
                    if round_total >= 3 and (round_failures / round_total) > 0.7:
                        engine._display.experiment_high_failure_rate(round_failures, round_total)
                        _circuit_breaker_fired = True
                        break

                    # Cross-round circuit breaker: persistent high failure rate
                    cross_threshold = engine._config.orchestrator.cross_round_failure_threshold
                    cross_min = engine._config.orchestrator.cross_round_min_experiments
                    if (
                        _total_experiments >= cross_min
                        and (_total_failures / _total_experiments) > cross_threshold
                    ):
                        engine._display.experiment_cross_round_breaker(
                            _total_failures, _total_experiments
                        )
                        _circuit_breaker_fired = True
                        break

                # --- RESULTS CHECKPOINT (sprint mode only, not last sprint) ---
                if enable_sprints and sprint_num < num_sprints and not _circuit_breaker_fired:
                    sprint_text = "\n\n".join(self._sprint_results)
                    stop_reason = await self._run_sprint_results_checkpoint(
                        sprint_num, num_sprints, checkpoint_context, sprint_text
                    )
                    if stop_reason is not None:
                        if stop_reason == SprintStopReason.PIVOT:
                            engine._display.sprint_pivot_stop(sprint_num)
                        else:
                            engine._display.sprint_early_stop(sprint_num)
                        break

                if _circuit_breaker_fired or _total_experiments >= _MAX_TOTAL_EXPERIMENTS_PER_PHASE:
                    break

            # Build execution context for WRITING phase
            execution_context = "\n\n".join(all_results) if all_results else ""

            # Checkpoint at end of execution
            if engine._config.orchestrator.enable_checkpointing:
                try:
                    engine.state.checkpoint = await engine._checkpoint_mgr.create_checkpoint(
                        thread_id=engine.state.thread_id,
                        phase=str(ResearchPhase.EXECUTION),
                        round_number=max_rounds,
                        messages=engine.state.messages,
                        previous_checkpoint=engine.state.checkpoint,
                    )
                    engine._display.checkpoint_saved("end of execution")
                except Exception as e:
                    engine._logger.log_error(e, thread_id=engine.state.thread_id)
                    engine._display.checkpoint_error(e)

        finally:
            await executor.cleanup()

        # Build caveats list
        caveats: list[str] = []

        # Synthetic data detection: if experiments ran but no /data/shared/ files existed
        shared_dir = engine._config.storage.data_dir / "shared"
        has_shared_data = shared_dir.exists() and any(
            f.is_file() for f in shared_dir.rglob("*") if f.is_file()
        )
        if successful_code and not has_shared_data:
            caveats.append(
                "All experiments used synthetic/simulated data — "
                "no observational data was available in the sandbox."
            )

        if _circuit_breaker_fired:
            caveats.append(
                "The experiment circuit breaker fired (>70% failure rate). "
                "Many experiments failed, limiting the evidence base."
            )

        if _had_network_error:
            caveats.append(
                "One or more experiments encountered network errors. "
                "The sandbox has no internet access, so any results relying "
                "on external data retrieval are absent."
            )

        if _had_timeout:
            caveats.append(
                "One or more experiments timed out before completion. Results may be incomplete."
            )

        # Check for vacuous reclassifications in the results text
        vacuous_marker = "produced no scientific output"
        _vacuous_count = sum(1 for r in all_results if vacuous_marker in r)
        if _vacuous_count > 0:
            caveats.append(
                f"{_vacuous_count} experiment(s) were reclassified from SUCCESS to "
                f"FAILURE for producing no meaningful scientific output."
            )

        return ExperimentationResult(
            execution_context=execution_context,
            execution_figures=execution_figures,
            successful_code=successful_code,
            caveats=caveats,
            experiment_metadata=experiment_metadata,
        )

    async def _request_advisory(self, experimenter_id: str) -> str:
        """Request one-line advice from each non-experimentalist agent.

        Args:
            experimenter_id: ID of the experimentalist to exclude.

        Returns:
            Combined advisory text from team members.
        """
        engine = self._engine
        engine._display.experiment_advisory_requested()
        advisory_parts: list[str] = []

        # Build recent failures summary from sprint results
        failure_lines: list[str] = []
        for result_text in reversed(self._sprint_results):
            lower = result_text.lower()
            if "failure" in lower or "error" in lower or "failed" in lower:
                # Extract first meaningful line as summary
                for line in result_text.split("\n"):
                    stripped = line.strip()
                    if stripped and len(stripped) > 10:
                        failure_lines.append(f"- {stripped[:150]}")
                        break
            if len(failure_lines) >= 3:
                break
        recent_failures = "\n".join(failure_lines) if failure_lines else "- (no details available)"

        net_caveat = _network_caveat(engine._config.sandbox.network_mode != "none")

        for agent_id, agent in engine.state.agents.items():
            if agent_id == experimenter_id:
                continue
            prompt = _ADVISORY_PROMPT_TEMPLATE.format(
                consecutive_failures=self._consecutive_failures,
                seed_prompt=engine.state.seed_prompt,
                recent_failures=recent_failures,
                network_caveat=net_caveat,
                reviewer_role=agent.skill_profile,
            )
            try:
                response = await agent.generate(prompt, max_tokens=256)
                if response.content.strip():
                    advisory_parts.append(
                        f"**{agent.skill_profile}:** {response.content.strip()[:200]}"
                    )
                engine._log_agent_response(agent_id, response, ResearchPhase.EXECUTION, "advisory")
            except Exception:
                continue

        if not advisory_parts:
            return ""
        return (
            "\n\n## Team Advisory\n"
            "Your teammates suggest these alternative approaches:\n"
            + "\n".join(f"- {p}" for p in advisory_parts)
        )

    async def _pre_execution_review(self, code: str, experiment_name: str) -> str | None:
        """Review code before execution. Returns feedback if issues, None if PASS.

        Args:
            code: The experiment code to review.
            experiment_name: Name of the experiment.

        Returns:
            Review feedback string if issues found, None if PASS.
        """
        engine = self._engine
        reviewer_role = engine._config.orchestrator.pre_execution_review_role

        # Find reviewer agent
        reviewer = engine._find_agent_by_role(reviewer_role)
        if reviewer is None:
            return None

        # Skip if reviewer == experimenter (same agent reviewing own code)
        experimenter = engine._find_agent_by_role("experimentalist")
        if experimenter is not None and reviewer.agent_id == experimenter.agent_id:
            return None

        engine._display.experiment_review_requested(experiment_name, reviewer_role)

        template = _PHASE_INSTRUCTIONS[ResearchPhase.EXECUTION]["pre_execution_review"]
        prompt = template.format(experiment_name=experiment_name, code=code)

        try:
            response = await reviewer.generate(prompt, max_tokens=1024)
            engine._log_agent_response(
                reviewer.agent_id, response, ResearchPhase.EXECUTION, "pre_execution_review"
            )
        except Exception:
            return None  # Non-fatal; skip review on error

        content = response.content.strip()
        if content.upper().startswith("PASS"):
            engine._display.experiment_review_passed(experiment_name)
            return None

        engine._display.experiment_review_issues(experiment_name)
        return content

    async def _apply_review_fixes(
        self,
        experimenter: Agent,
        code: str,
        experiment_name: str,
        review_feedback: str,
        checkpoint_context: str,
    ) -> str:
        """Have experimentalist fix issues from review. Returns corrected code.

        Args:
            experimenter: The experimentalist agent.
            code: Original experiment code.
            experiment_name: Name of the experiment.
            review_feedback: Feedback from the reviewer.
            checkpoint_context: Checkpoint context string.

        Returns:
            Corrected code string (falls back to original if extraction fails).
        """
        engine = self._engine
        template = _PHASE_INSTRUCTIONS[ResearchPhase.EXECUTION]["fix_after_review"]
        prompt = template.format(
            seed_prompt=engine.state.seed_prompt,
            checkpoint_context=checkpoint_context,
            code=code,
            review_feedback=review_feedback,
            experiment_name=experiment_name,
        )

        try:
            response = await experimenter.generate(prompt, max_tokens=_WRITING_MAX_TOKENS)
            engine._log_agent_response(
                experimenter.agent_id, response, ResearchPhase.EXECUTION, "fix_after_review"
            )
        except Exception:
            return code  # Fallback to original code

        # Extract corrected code from response
        blocks = _extract_code_blocks(response.content)
        if not blocks:
            return code  # Fallback to original code
        return blocks[0].code

    async def _run_sprint_design_review(
        self,
        experimenter: Agent,
        sprint_num: int,
        num_sprints: int,
        checkpoint_context: str,
        previous_results: str,
    ) -> str:
        """Run design review sub-phase: experimenter proposes plan, team reviews.

        Args:
            experimenter: The experimentalist agent.
            sprint_num: Current sprint number.
            num_sprints: Total number of sprints.
            checkpoint_context: Checkpoint context string.
            previous_results: Formatted results from prior sprints.

        Returns:
            Combined design feedback string to inject into the execution prompt.
        """
        engine = self._engine
        net_caveat = _network_caveat(engine._config.sandbox.network_mode != "none")

        # Build workspace manifest for design review context
        workspace_dir = (
            Path(engine._config.storage.data_dir) / "workspaces" / engine.state.thread_id
        )
        ws_manifest = _build_workspace_manifest(workspace_dir)
        ws_manifest_str = ws_manifest + "\n\n" if ws_manifest else ""

        # 1. Experimenter proposes experiment plan (no code)
        template = _PHASE_INSTRUCTIONS[ResearchPhase.EXECUTION]["sprint_design_proposal"]
        proposal_prompt = template.format(
            sprint_num=sprint_num,
            num_sprints=num_sprints,
            seed_prompt=engine.state.seed_prompt,
            checkpoint_context=checkpoint_context,
            workspace_manifest=ws_manifest_str,
            previous_results=(
                f"## Previous Results\n{previous_results}\n\n" if previous_results else ""
            ),
            network_caveat=net_caveat,
        )

        try:
            proposal_response = await experimenter.generate(proposal_prompt, max_tokens=4096)
            engine._log_agent_response(
                experimenter.agent_id,
                proposal_response,
                ResearchPhase.EXECUTION,
                "sprint_design_proposal",
            )
            engine._display.sprint_design_proposed(sprint_num)
        except Exception as e:
            engine._logger.log_error(
                e, agent_id=experimenter.agent_id, thread_id=engine.state.thread_id
            )
            return ""

        experiment_plan = proposal_response.content

        # 2. Each review role provides feedback
        review_template = _PHASE_INSTRUCTIONS[ResearchPhase.EXECUTION]["sprint_design_review"]
        feedback_parts: list[str] = []

        for role in engine._config.orchestrator.sprint_review_roles:
            reviewer = engine._find_agent_by_role(role)
            if reviewer is None:
                continue

            review_prompt = review_template.format(
                sprint_num=sprint_num,
                num_sprints=num_sprints,
                seed_prompt=engine.state.seed_prompt,
                checkpoint_context=checkpoint_context,
                workspace_manifest=ws_manifest_str,
                previous_results=(
                    f"## Previous Results\n{previous_results}\n\n" if previous_results else ""
                ),
                experiment_plan=experiment_plan,
                reviewer_role=role,
                network_caveat=net_caveat,
            )

            try:
                engine._display.sprint_design_review(sprint_num, role)
                review_response = await reviewer.generate(review_prompt, max_tokens=1024)
                engine._log_agent_response(
                    reviewer.agent_id,
                    review_response,
                    ResearchPhase.EXECUTION,
                    "sprint_design_review",
                )
                if review_response.content.strip():
                    feedback_parts.append(f"**{role}:** {review_response.content.strip()}")
            except Exception:
                continue  # Non-fatal, same pattern as _request_advisory

        if not feedback_parts:
            return ""
        return "\n\n## Design Review Feedback\n" + "\n\n".join(feedback_parts)

    async def _run_sprint_results_checkpoint(
        self,
        sprint_num: int,
        num_sprints: int,
        checkpoint_context: str,
        sprint_results: str,
    ) -> SprintStopReason | None:
        """Run results checkpoint: each reviewer assesses sprint outcomes.

        Args:
            sprint_num: Current sprint number.
            num_sprints: Total number of sprints.
            checkpoint_context: Checkpoint context string.
            sprint_results: Formatted results from this sprint.

        Returns:
            SprintStopReason.SUFFICIENT if majority says sufficient,
            SprintStopReason.PIVOT if majority says stop and pivot,
            None to continue.
        """
        engine = self._engine
        template = _PHASE_INSTRUCTIONS[ResearchPhase.EXECUTION]["sprint_results_checkpoint"]
        sufficient_count = 0
        pivot_count = 0
        total_count = 0

        for role in engine._config.orchestrator.sprint_review_roles:
            reviewer = engine._find_agent_by_role(role)
            if reviewer is None:
                continue

            checkpoint_prompt = template.format(
                sprint_num=sprint_num,
                num_sprints=num_sprints,
                seed_prompt=engine.state.seed_prompt,
                checkpoint_context=checkpoint_context,
                sprint_results=sprint_results,
                reviewer_role=role,
            )

            try:
                engine._display.sprint_checkpoint(sprint_num, role)
                response = await reviewer.generate(checkpoint_prompt, max_tokens=512)
                engine._log_agent_response(
                    reviewer.agent_id,
                    response,
                    ResearchPhase.EXECUTION,
                    "sprint_results_checkpoint",
                )
                total_count += 1
                upper = response.content.upper()
                if "EXPERIMENTS SUFFICIENT" in upper:
                    sufficient_count += 1
                elif "STOP AND PIVOT" in upper:
                    pivot_count += 1
            except Exception:
                continue  # Non-fatal

        if total_count == 0:
            return None
        if sufficient_count > total_count / 2:
            return SprintStopReason.SUFFICIENT
        if pivot_count > total_count / 2:
            return SprintStopReason.PIVOT
        return None

    async def _execute_with_retry(
        self,
        executor: CodeExecutor,
        experimenter: Agent,
        experiment_name: str,
        code: str,
        checkpoint_context: str,
        repo_paths: list[str] | None = None,
        workspace_dir: Path | None = None,
    ) -> tuple[ExecutionResult, str]:
        """Execute code with retry on failure/rejection.

        Args:
            executor: CodeExecutor instance.
            experimenter: Agent that proposed the code.
            experiment_name: Name of the experiment.
            code: Python code to execute.
            checkpoint_context: Checkpoint context string.
            repo_paths: Optional list of repo paths for PYTHONPATH.
            workspace_dir: Optional workspace directory for manifest injection.

        Returns:
            Tuple of (final ExecutionResult, final code version).
        """
        engine = self._engine
        current_code = code
        self._auto_searched = False  # Reset per experiment
        for attempt in range(_MAX_RETRIES_PER_EXPERIMENT + 1):
            request = ExecutionRequest(
                code=current_code,
                agent_id=experimenter.agent_id,
                thread_id=engine.state.thread_id,
            )
            result = await executor.execute(request, repo_paths=repo_paths)

            # Timeout — return immediately
            if result.status == ExecutionStatus.TIMEOUT:
                return result, current_code

            # Success — check for vacuous output before accepting
            if result.status == ExecutionStatus.SUCCESS:
                if not _is_vacuous_success(result):
                    return result, current_code
                # Vacuous: reclassify as failure so retry kicks in
                result = result.model_copy(
                    update={
                        "status": ExecutionStatus.FAILURE,
                        "error_message": (
                            "Script exited successfully but produced no scientific output. "
                            "No figures were saved and stdout contained no quantitative results. "
                            "Ensure your script: (1) prints numerical results to stdout, "
                            "and/or (2) saves figures with plt.savefig('name.png')."
                        ),
                    }
                )
                # Fall through to retry logic below

            # Last attempt — return whatever we got
            if attempt == _MAX_RETRIES_PER_EXPERIMENT:
                return result, current_code

            # Build error feedback for retry
            error_parts = []
            if result.status == ExecutionStatus.REJECTED:
                error_parts.append(f"**Safety rejection:** {result.error_message}")
            else:
                error_parts.append(f"**Execution failed** (status: {result.status.value})")
                if result.stderr:
                    error_parts.append(f"```\n{result.stderr[:_EXECUTION_STDERR_LIMIT]}\n```")
                if result.error_message:
                    error_parts.append(f"Error: {result.error_message}")

            # Detect network errors and prepend clear guidance
            stderr_text = result.stderr or ""
            if any(p in stderr_text for p in _NETWORK_ERROR_PATTERNS):
                error_parts.insert(
                    0,
                    "**\u26a0 NETWORK ERROR:** This failure is because the sandbox has "
                    "NO internet access. Do NOT use requests, urllib, httpx, or any "
                    "HTTP calls. Instead:\n"
                    "- Generate synthetic data that matches the expected statistical "
                    "properties\n"
                    "- Use files already available under /data/shared/ or "
                    "/data/workspace/\n"
                    "- Create mathematical models to simulate the data you need\n",
                )

            # Detect ModuleNotFoundError and provide package guidance
            _module_match = re.search(
                r"ModuleNotFoundError: No module named ['\"](\w+)['\"]", stderr_text
            )
            if _module_match:
                _bad_module = _module_match.group(1)
                # Record learned constraint for future experiments
                constraint = f"Module '{_bad_module}' is NOT available. Do NOT import it."
                if constraint not in self._learned_constraints:
                    self._learned_constraints.append(constraint)

                _replacements: dict[str, str] = {
                    "PyPDF2": "pypdf (use `from pypdf import PdfReader`)",
                    "pdfminer": "pdfminer.six (use `from pdfminer.high_level import extract_text`)",
                    "bs4": "beautifulsoup4 (use `from bs4 import BeautifulSoup`)",
                    "cv2": "not available — use matplotlib for image processing",
                    "pymc": "not available — use scipy.optimize or emcee instead",
                    "tabula": "not available — use pypdf or pdfminer.six instead",
                }
                replacement = _replacements.get(_bad_module, "")
                if replacement:
                    error_parts.insert(
                        0,
                        f"**\u26a0 WRONG PACKAGE NAME:** `{_bad_module}` is not installed. "
                        f"Use {replacement} instead. "
                        f"Do NOT try to pip install — it is blocked.\n",
                    )
                else:
                    error_parts.insert(
                        0,
                        f"**\u26a0 UNAVAILABLE PACKAGE:** `{_bad_module}` is not installed "
                        f"and cannot be installed. Use only the available libraries: "
                        f"numpy, scipy, matplotlib, pandas, scikit-learn, sympy, astropy, "
                        f"seaborn, pypdf, pdfminer.six, beautifulsoup4, h5py, emcee, "
                        f"corner, lmfit, uncertainties, statsmodels, tqdm, numba, "
                        f"xarray, joblib, pyyaml.\n",
                    )

            # Detect file-not-found errors (check both stderr and stdout for
            # scripts that caught the exception and printed to stdout)
            combined_text = stderr_text + (result.stdout or "")
            if any(p in combined_text for p in _FILE_NOT_FOUND_PATTERNS):
                file_listing = _list_shared_files(
                    engine._config.storage.data_dir, engine.state.wall_start_time
                )
                error_parts.insert(
                    0,
                    "**\u26a0 FILE NOT FOUND:** Your script tried to open a file that "
                    "does not exist in the sandbox. Do NOT guess or invent filenames.\n\n"
                    f"{file_listing}\n"
                    "Use ONLY the exact paths listed above. If no suitable data files "
                    "are available, generate realistic synthetic data instead.\n",
                )
                # Record specific missing file as learned constraint
                fnf_match = re.search(
                    r"No such file or directory: ['\"]([^'\"]+)['\"]", combined_text
                )
                if fnf_match:
                    bad_path = fnf_match.group(1)
                    constraint = f"File '{bad_path}' does NOT exist."
                    if constraint not in self._learned_constraints:
                        self._learned_constraints.append(constraint)

            # Record network error constraints (when network IS enabled but URL fails)
            url_match = re.search(
                r"(?:ConnectionError|HTTPError|Timeout).*?(https?://[^\s'\"]+)",
                combined_text,
            )
            if url_match:
                bad_url = url_match.group(1)[:100]
                constraint = f"URL '{bad_url}' failed. Try alternative data sources."
                if constraint not in self._learned_constraints:
                    self._learned_constraints.append(constraint)

            error_feedback = "\n\n".join(error_parts)

            # Auto literature search on data-related errors
            if not self._auto_searched:
                combined_error = stderr_text + (result.stdout or "") + (result.error_message or "")
                if any(p in combined_error for p in _DATA_ERROR_PATTERNS):
                    self._auto_searched = True
                    try:
                        query_text = _build_auto_search_query(
                            engine.state.seed_prompt, combined_error
                        )
                        search_query = f"[SEARCH: {query_text}]"
                        await engine._literature.process_search_requests(
                            experimenter.agent_id,
                            search_query,
                            ResearchPhase.EXECUTION,
                        )
                    except Exception:
                        pass  # Non-fatal

            engine._display.experiment_retry(attempt + 1, _MAX_RETRIES_PER_EXPERIMENT)

            # Try to extract error line number for targeted code display
            error_lineno = None
            if result.stderr:
                line_match = re.search(r"line (\d+)", result.stderr)
                if line_match:
                    error_lineno = int(line_match.group(1))

            truncated_code = _truncate_code_for_retry(current_code, error_lineno)

            net_caveat = _network_caveat(engine._config.sandbox.network_mode != "none")
            # Inject workspace manifest into retry context so agent knows
            # which files are available from prior experiments
            retry_checkpoint = checkpoint_context
            if workspace_dir is not None:
                ws_manifest = _build_workspace_manifest(workspace_dir)
                if ws_manifest:
                    retry_checkpoint = ws_manifest + "\n\n" + retry_checkpoint
                    # 1C: tell the agent to resume from completed steps instead of
                    # recomputing everything (default-off).
                    if engine._config.orchestrator.enable_step_restart:
                        retry_checkpoint += (
                            "\n\n## STEP RESTART\n"
                            "Intermediate artifacts from completed steps are listed above. "
                            "Reload them and resume from the step that failed — do NOT recompute "
                            "steps that already succeeded. Add a `# RESTART_AT: <step>` comment "
                            "at the resume point and print `STEP_COMPLETE: <step>` after each "
                            "step you finish so progress is recoverable."
                        )
            template = _PHASE_INSTRUCTIONS[ResearchPhase.EXECUTION]["retry_after_failure"]
            retry_prompt = template.format(
                seed_prompt=engine.state.seed_prompt,
                checkpoint_context=retry_checkpoint,
                failed_code=truncated_code,
                error_feedback=error_feedback,
                network_caveat=net_caveat,
            )

            # Inject learned constraints into retry prompt
            if self._learned_constraints:
                retry_prompt += (
                    "\n\n## LEARNED CONSTRAINTS (from prior failures — do NOT violate)\n"
                    + "\n".join(f"- {c}" for c in self._learned_constraints)
                    + "\n"
                )

            try:
                response = await experimenter.generate(retry_prompt, max_tokens=_WRITING_MAX_TOKENS)
            except Exception as e:
                engine._logger.log_error(
                    e, agent_id=experimenter.agent_id, thread_id=engine.state.thread_id
                )
                return result, current_code  # Return last failed result

            engine._log_agent_response(
                experimenter.agent_id, response, ResearchPhase.EXECUTION, "retry"
            )

            # Extract corrected code
            blocks = _extract_code_blocks(response.content)
            if not blocks:
                return result, current_code  # Agent didn't provide corrected code
            current_code = blocks[0].code  # Use first block

        return result, current_code  # Should not reach here, but type-safety
