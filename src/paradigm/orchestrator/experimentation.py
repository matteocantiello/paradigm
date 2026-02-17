"""Experimentation-phase handler — extracted from OrchestrationEngine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from paradigm.literature.resources import ResourceType
from paradigm.orchestrator.constants import (
    _EXECUTION_STDERR_LIMIT,
    _FILE_NOT_FOUND_PATTERNS,
    _MAX_RETRIES_PER_EXPERIMENT,
    _NETWORK_ERROR_PATTERNS,
    _PHASE_INSTRUCTIONS,
    _WRITING_MAX_TOKENS,
    _extract_code_blocks,
    _format_execution_result,
    _is_vacuous_success,
    _list_shared_files,
)
from paradigm.orchestrator.phases import ResearchPhase
from paradigm.sandbox.executor import CodeExecutor
from paradigm.sandbox.models import ExecutionRequest, ExecutionResult, ExecutionStatus

if TYPE_CHECKING:
    from paradigm.agents.base import Agent
    from paradigm.orchestrator.engine import OrchestrationEngine


@dataclass
class ExperimentationResult:
    """Return value of the experimentation phase."""

    execution_context: str = ""
    execution_figures: list[tuple[str, Path]] = field(default_factory=list)


class ExperimentationHandler:
    """Handles the EXECUTION phase: agents propose and run computational experiments."""

    def __init__(self, engine: OrchestrationEngine) -> None:
        self._engine = engine

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
            for r in engine._resolved_resources
            if r.resource_type == ResourceType.CODE_REPO and r.sandbox_path and r.error is None
        ]
        # Also add parent directories of CODE_FILE resources so they are importable
        code_file_dirs = {
            str(Path(r.sandbox_path).parent)
            for r in engine._resolved_resources
            if r.resource_type == ResourceType.CODE_FILE and r.sandbox_path and r.error is None
        }
        repo_paths.extend(sorted(code_file_dirs))

        # Per-thread workspace persists across executions so experiments
        # can read files (CSVs, data) produced by earlier experiments.
        workspace_dir = engine._config.storage.data_dir / "workspaces" / engine._thread_id
        workspace_dir.mkdir(parents=True, exist_ok=True)

        executor = CodeExecutor(
            config=engine._config.sandbox,
            logger=engine._logger,
            data_dir=engine._config.storage.data_dir,
            workspace_dir=workspace_dir,
        )

        all_results: list[str] = []
        execution_figures: list[tuple[str, Path]] = []

        try:
            for round_num in range(1, max_rounds + 1):
                engine._display.experiment_round(round_num, max_rounds)
                engine._literature.search_count_this_round = 0

                # Find experimenter (prefer experimentalist, fallback to analyst)
                experimenter = engine._find_agent_by_role("experimentalist")
                if experimenter is None:
                    experimenter = engine._find_agent_by_role("analyst")
                if experimenter is None:
                    engine._display.experiment_no_agent()
                    break

                # Build prompt
                checkpoint_context = ""
                if engine._checkpoint:
                    checkpoint_context = engine._checkpoint.to_context_string() + "\n\n"

                # Inject actual file listing so agents know what exists
                file_listing = _list_shared_files(engine._config.storage.data_dir)
                checkpoint_context = file_listing + "\n\n" + checkpoint_context

                # Inject code/data context from resolved resources
                if engine._code_context:
                    checkpoint_context += engine._code_context + "\n\n"
                if engine._data_context:
                    checkpoint_context += engine._data_context + "\n\n"

                previous_results = "\n\n".join(all_results) if all_results else ""

                if round_num == 1:
                    template = _PHASE_INSTRUCTIONS[ResearchPhase.EXECUTION]["propose_experiment"]
                    prompt = template.format(
                        seed_prompt=engine._seed_prompt,
                        checkpoint_context=checkpoint_context,
                        previous_results=previous_results,
                    )
                else:
                    template = _PHASE_INSTRUCTIONS[ResearchPhase.EXECUTION]["analyze_results"]
                    prompt = template.format(
                        seed_prompt=engine._seed_prompt,
                        checkpoint_context=checkpoint_context,
                        previous_results=previous_results,
                    )

                try:
                    response = await experimenter.generate(prompt, max_tokens=_WRITING_MAX_TOKENS)
                except Exception as e:
                    engine._logger.log_error(
                        e, agent_id=experimenter.agent_id, thread_id=engine._thread_id
                    )
                    engine._display.agent_error(experimenter.agent_id, e)
                    break

                engine._log_agent_response(
                    experimenter.agent_id, response, ResearchPhase.EXECUTION, "experiment_proposal"
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

                # Execute each code block
                round_total = 0
                round_failures = 0
                for exp_name, code in code_blocks:
                    engine._display.experiment_running(exp_name)
                    result = await self._execute_with_retry(
                        executor,
                        experimenter,
                        exp_name,
                        code,
                        checkpoint_context,
                        repo_paths=repo_paths,
                    )
                    formatted = _format_execution_result(exp_name, result)
                    all_results.append(formatted)

                    round_total += 1
                    if result.status != ExecutionStatus.SUCCESS:
                        round_failures += 1

                    # Track output figures
                    for output_file in result.output_files:
                        if output_file.filename.endswith((".png", ".pdf")):
                            execution_figures.append((exp_name, Path(output_file.path)))

                    status_str = result.status.value
                    engine._display.experiment_result(exp_name, status_str)

                # Circuit breaker: if >70% of executions failed, stop experimenting
                if round_total >= 3 and (round_failures / round_total) > 0.7:
                    engine._display.experiment_high_failure_rate(round_failures, round_total)
                    break

            # Build execution context for WRITING phase
            execution_context = "\n\n".join(all_results) if all_results else ""

            # Checkpoint at end of execution
            if engine._config.orchestrator.enable_checkpointing:
                try:
                    engine._checkpoint = await engine._checkpoint_mgr.create_checkpoint(
                        thread_id=engine._thread_id,
                        phase=str(ResearchPhase.EXECUTION),
                        round_number=max_rounds,
                        messages=engine._messages,
                        previous_checkpoint=engine._checkpoint,
                    )
                    engine._display.checkpoint_saved("end of execution")
                except Exception as e:
                    engine._logger.log_error(e, thread_id=engine._thread_id)
                    engine._display.checkpoint_error(e)

        finally:
            await executor.cleanup()

        return ExperimentationResult(
            execution_context=execution_context,
            execution_figures=execution_figures,
        )

    async def _execute_with_retry(
        self,
        executor: CodeExecutor,
        experimenter: Agent,
        experiment_name: str,
        code: str,
        checkpoint_context: str,
        repo_paths: list[str] | None = None,
    ) -> ExecutionResult:
        """Execute code with retry on failure/rejection.

        Args:
            executor: CodeExecutor instance.
            experimenter: Agent that proposed the code.
            experiment_name: Name of the experiment.
            code: Python code to execute.
            checkpoint_context: Checkpoint context string.
            repo_paths: Optional list of repo paths for PYTHONPATH.

        Returns:
            Final ExecutionResult.
        """
        engine = self._engine
        current_code = code
        for attempt in range(_MAX_RETRIES_PER_EXPERIMENT + 1):
            request = ExecutionRequest(
                code=current_code,
                agent_id=experimenter.agent_id,
                thread_id=engine._thread_id,
            )
            result = await executor.execute(request, repo_paths=repo_paths)

            # Timeout — return immediately
            if result.status == ExecutionStatus.TIMEOUT:
                return result

            # Success — check for vacuous output before accepting
            if result.status == ExecutionStatus.SUCCESS:
                if not _is_vacuous_success(result):
                    return result
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
                return result

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

            # Detect file-not-found errors (check both stderr and stdout for
            # scripts that caught the exception and printed to stdout)
            combined_text = stderr_text + (result.stdout or "")
            if any(p in combined_text for p in _FILE_NOT_FOUND_PATTERNS):
                file_listing = _list_shared_files(engine._config.storage.data_dir)
                error_parts.insert(
                    0,
                    "**\u26a0 FILE NOT FOUND:** Your script tried to open a file that "
                    "does not exist in the sandbox. Do NOT guess or invent filenames.\n\n"
                    f"{file_listing}\n"
                    "Use ONLY the exact paths listed above. If no suitable data files "
                    "are available, generate realistic synthetic data instead.\n",
                )

            error_feedback = "\n\n".join(error_parts)
            engine._display.experiment_retry(attempt + 1, _MAX_RETRIES_PER_EXPERIMENT)

            template = _PHASE_INSTRUCTIONS[ResearchPhase.EXECUTION]["retry_after_failure"]
            retry_prompt = template.format(
                seed_prompt=engine._seed_prompt,
                checkpoint_context=checkpoint_context,
                error_feedback=error_feedback,
            )

            try:
                response = await experimenter.generate(retry_prompt, max_tokens=_WRITING_MAX_TOKENS)
            except Exception as e:
                engine._logger.log_error(
                    e, agent_id=experimenter.agent_id, thread_id=engine._thread_id
                )
                return result  # Return last failed result

            engine._log_agent_response(
                experimenter.agent_id, response, ResearchPhase.EXECUTION, "retry"
            )

            # Extract corrected code
            blocks = _extract_code_blocks(response.content)
            if not blocks:
                return result  # Agent didn't provide corrected code
            current_code = blocks[0][1]  # Use first block

        return result  # Should not reach here, but type-safety
