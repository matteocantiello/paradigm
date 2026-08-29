"""Adversarial replication gate (Layer 1): an independent re-derivation + spec-curve
verdict on the paper's headline claim.

The verification kernel checks REPRODUCIBILITY (same code + data -> same number). That
cannot catch a headline that is deterministic but FRAGILE — one that flips sign or
loses significance under an equally-defensible sample cut or estimator. This gate has
an INDEPENDENT agent re-derive the headline from the data and stress-test it across
alternative specifications; the engine assesses sign-stability deterministically and
feeds a FRAGILE / NOT-REPRODUCED verdict to review as a blocking, reframe-forcing note.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from paradigm.orchestrator.constants import (
    _REPLICATOR_PROMPT,
    _REPLICATOR_SYSTEM,
    _extract_code_blocks,
)
from paradigm.orchestrator.verification import _extract_result_tokens
from paradigm.sandbox.executor import CodeExecutor
from paradigm.sandbox.models import ExecutionRequest, ExecutionStatus

if TYPE_CHECKING:
    from paradigm.journal.paper import PaperDraft
    from paradigm.orchestrator.engine import OrchestrationEngine

REPRODUCED = "reproduced"
FRAGILE = "fragile"
NOT_REPRODUCED = "not_reproduced"
ERROR = "error"
SKIPPED = "skipped"


@dataclass
class ReplicationReport:
    """Verdict of the independent replication of a paper's headline claim."""

    ran: bool = False
    verdict: str = SKIPPED
    headline_recomputed: float | None = None
    reproduced: bool = False
    n_specs: int = 0
    n_same_sign: int = 0
    sign_stability: float = 0.0
    detail: str = ""

    @property
    def is_blocking(self) -> bool:
        """A fragile / not-reproduced headline must be reframed before acceptance."""
        return self.verdict in (FRAGILE, NOT_REPRODUCED)

    def as_review_block(self) -> str:
        """Markdown block injected into the editor prompt (empty when uninformative)."""
        if not self.ran or self.verdict in (SKIPPED, ERROR):
            return ""
        head = {
            REPRODUCED: "REPRODUCED — the headline re-derived and kept its sign across specifications.",
            FRAGILE: "FRAGILE — the headline re-derived but its sign/size did NOT survive alternative specifications.",
            NOT_REPRODUCED: "NOT REPRODUCED — an independent re-derivation did not recover the headline.",
        }.get(self.verdict, self.verdict)
        lines = [
            "## Independent Replication Report",
            head,
            f"- Independent re-derivation of the headline value: {self.headline_recomputed}",
            f"- Sign stable in {self.n_same_sign}/{self.n_specs} alternative specifications "
            f"({self.sign_stability:.0%}).",
        ]
        if self.detail:
            lines.append(f"- {self.detail}")
        return "\n".join(lines)


class ReplicationHandler:
    """Runs the independent, adversarial replication of the paper's headline claim."""

    def __init__(self, engine: OrchestrationEngine) -> None:
        self._engine = engine

    async def run_replication(self, paper_draft: PaperDraft | None) -> ReplicationReport:
        engine = self._engine
        cfg = engine._config.orchestrator
        if not getattr(cfg, "enable_replication_gate", False) or paper_draft is None:
            return ReplicationReport(ran=False, verdict=SKIPPED)
        headline = self._paper_headline(paper_draft)
        if not headline.strip():
            return ReplicationReport(ran=False, verdict=SKIPPED)

        data_ctx = (engine.state.data_context or "")[:6000]
        prompt = _REPLICATOR_PROMPT.format(
            paper_headline=headline[:6000],
            data_context=data_ctx or "(no staged data cards)",
            max_specs=cfg.replication_max_specs,
        )
        try:
            provider, model, extra_body = engine._config.get_provider_and_model_for_role(
                "replicator"
            )
            text, itok, otok = await asyncio.to_thread(
                provider.complete,
                model=model,
                system=_REPLICATOR_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                # 16384, not 8192: a reasoning-model replicator spends hidden
                # thinking tokens from this budget and a tight cap left no room for
                # the visible script → empty output → the gate silently produced
                # nothing (observed twice in production). Match the judge's headroom.
                max_tokens=16384,
                extra_body=extra_body,
            )
            engine._db.record_token_usage(
                model=model,
                input_tokens=itok,
                output_tokens=otok,
                thread_id=engine.state.thread_id,
            )
        except Exception as e:  # noqa: BLE001 — replication must never crash the cycle
            engine._logger.log_error(e, thread_id=engine.state.thread_id)
            return self._finalize(ReplicationReport(ran=False, verdict=ERROR, detail=str(e)[:200]))

        blocks = _extract_code_blocks(text)
        if not blocks:
            return self._finalize(
                ReplicationReport(ran=True, verdict=ERROR, detail="replicator produced no code")
            )
        stdout = await self._execute("\n\n".join(b.code for b in blocks if b.code))
        if stdout is None:
            return self._finalize(
                ReplicationReport(ran=True, verdict=ERROR, detail="replication code failed to run")
            )

        return self._finalize(self._assess(stdout))

    def _finalize(self, report: ReplicationReport) -> ReplicationReport:
        """Emit the replication verdict + surface it — even on error, so a failed
        gate is never silently invisible (the failure mode we hit twice)."""
        engine = self._engine
        if report.verdict == SKIPPED:
            return report  # gate off / no draft — nothing to report
        engine.emit_event(
            "replication.completed",
            {
                "verdict": report.verdict,
                "reproduced": report.reproduced,
                "sign_stability": round(report.sign_stability, 2),
                "n_specs": report.n_specs,
                "detail": report.detail,
            },
        )
        if report.n_specs:
            engine._display.info(
                f"[replication] {report.verdict} — headline sign stable "
                f"{report.n_same_sign}/{report.n_specs}"
            )
        else:
            engine._display.warning(
                f"[replication] {report.verdict}" + (f" — {report.detail}" if report.detail else "")
            )
        return report

    def _assess(self, stdout: str) -> ReplicationReport:
        """Deterministic verdict from the replicator's RESULT[...] tokens."""
        cfg = self._engine._config.orchestrator
        tok = _extract_result_tokens(stdout)
        recomputed = tok.get("headline_recomputed")
        reproduced = tok.get("headline_reproduced", 0.0) >= 1.0
        n_specs = int(tok.get("n_specs", 0) or 0)
        n_same = int(tok.get("n_same_sign", 0) or 0)
        # Fall back to the per-spec sign tokens when the summary counts are absent.
        if n_specs == 0 and recomputed is not None:
            signs = [v for k, v in tok.items() if k.startswith("spec_") and k.endswith("_sign")]
            if signs:
                head_pos = recomputed >= 0
                n_specs = len(signs)
                n_same = sum(1 for s in signs if (s >= 0) == head_pos)
        stability = (n_same / n_specs) if n_specs else 0.0

        if not reproduced:
            verdict, detail = (
                NOT_REPRODUCED,
                "Independent re-derivation did not recover the headline.",
            )
        elif n_specs > 0 and stability >= cfg.replication_sign_stability:
            verdict, detail = REPRODUCED, ""
        else:
            verdict, detail = (
                FRAGILE,
                "Headline sign not stable across the alternative specifications.",
            )
        return ReplicationReport(
            ran=True,
            verdict=verdict,
            headline_recomputed=recomputed,
            reproduced=reproduced,
            n_specs=n_specs,
            n_same_sign=n_same,
            sign_stability=stability,
            detail=detail,
        )

    async def _execute(self, code: str) -> str | None:
        """Run the replicator's code in the thread sandbox workspace; return stdout."""
        engine = self._engine
        from paradigm.literature.resources import ResourceType

        thread = engine.state.thread_id or "thread"
        workspace = engine._config.storage.data_dir / "workspaces" / thread
        workspace.mkdir(parents=True, exist_ok=True)
        resources = getattr(engine.state, "resolved_resources", None) or []
        repo_paths = [
            r.sandbox_path
            for r in resources
            if r.resource_type == ResourceType.CODE_REPO and r.sandbox_path and r.error is None
        ]
        repo_paths += sorted(
            {
                str(Path(r.sandbox_path).parent)
                for r in resources
                if r.resource_type == ResourceType.CODE_FILE and r.sandbox_path and r.error is None
            }
        )
        executor = CodeExecutor(
            config=engine._config.sandbox,
            logger=engine._logger,
            data_dir=engine._config.storage.data_dir,
            workspace_dir=workspace,
        )
        try:
            result = await executor.execute(
                ExecutionRequest(
                    code=code, agent_id="replicator", thread_id=engine.state.thread_id
                ),
                repo_paths=repo_paths,
            )
        except Exception as e:  # noqa: BLE001 — never crash the cycle on a sandbox hiccup
            engine._logger.log_error(e, thread_id=engine.state.thread_id)
            return None
        finally:
            await executor.cleanup()
        if result.status != ExecutionStatus.SUCCESS:
            return None
        return result.stdout or ""

    @staticmethod
    def _paper_headline(paper_draft: PaperDraft) -> str:
        """Abstract + first slice of the body — where the headline claim lives."""
        body = getattr(paper_draft, "assembled_body", None) or ""
        if not body and hasattr(paper_draft, "to_markdown"):
            body = paper_draft.to_markdown()
        return body or ""
