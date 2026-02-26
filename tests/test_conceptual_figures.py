"""Tests for conceptual figure generation (writing.py helpers and guards)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from paradigm.orchestrator.constants import _CONCEPTUAL_FIGURE_PROMPT
from paradigm.orchestrator.writing import WritingHandler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine_mock(
    *,
    execution_figures: list | None = None,
    sandbox_enabled: bool = True,
    enable_conceptual_figures: bool = True,
    max_conceptual_figures: int = 3,
    writer_agent: object | None = "auto",
) -> MagicMock:
    """Build a minimal mock OrchestrationEngine for WritingHandler tests."""
    engine = MagicMock()
    engine._execution_figures = execution_figures or []

    # Use a fully-mocked config (Pydantic models can't be partially constructed)
    config = MagicMock()
    config.sandbox.enabled = sandbox_enabled
    config.orchestrator.enable_conceptual_figures = enable_conceptual_figures
    config.orchestrator.max_conceptual_figures = max_conceptual_figures
    config.storage.data_dir = Path("/tmp/paradigm-test")
    engine._config = config

    engine._thread_id = "test-thread-001"

    # Writer agent
    if writer_agent == "auto":
        agent = MagicMock()
        agent.agent_id = "writer-001"
        engine._find_agent_by_role.return_value = agent
    elif writer_agent is None:
        engine._find_agent_by_role.return_value = None
    else:
        engine._find_agent_by_role.return_value = writer_agent

    # Display (all methods are auto-mocked)
    engine._display = MagicMock()

    # Logger
    engine._logger = MagicMock()

    return engine


# ---------------------------------------------------------------------------
# _extract_figure_references
# ---------------------------------------------------------------------------


class TestExtractFigureReferences:
    def test_basic(self):
        body = (
            "As shown in Figure 1, the relationship is clear. "
            "Further analysis in Figure 2 confirms this trend."
        )
        refs = WritingHandler._extract_figure_references(body)
        assert len(refs) == 2
        assert refs[0][0] == 1
        assert refs[1][0] == 2
        # Context should contain surrounding text
        assert "Figure 1" in refs[0][1]
        assert "Figure 2" in refs[1][1]

    def test_none(self):
        body = "This paper discusses stellar evolution without any figures."
        refs = WritingHandler._extract_figure_references(body)
        assert refs == []

    def test_dedup(self):
        body = "Figure 1 shows the results. As we noted in Figure 1, the trend is consistent."
        refs = WritingHandler._extract_figure_references(body)
        assert len(refs) == 1
        assert refs[0][0] == 1

    def test_fig_dot_variant(self):
        body = "As shown in Fig. 1, the data supports our hypothesis."
        refs = WritingHandler._extract_figure_references(body)
        assert len(refs) == 1
        assert refs[0][0] == 1

    def test_sorted_output(self):
        body = "See Figure 3 first, then Figure 1, and finally Figure 2."
        refs = WritingHandler._extract_figure_references(body)
        assert [r[0] for r in refs] == [1, 2, 3]


# ---------------------------------------------------------------------------
# _strip_orphan_figure_references
# ---------------------------------------------------------------------------


class TestStripOrphanFigureReferences:
    def test_removes_image_tags(self):
        body = "Some text before.\n\n![Figure 1](figures/exp_plot.png)\n\nSome text after."
        result = WritingHandler._strip_orphan_figure_references(body)
        assert "![Figure 1]" not in result
        assert "Some text before." in result
        assert "Some text after." in result

    def test_preserves_text_refs(self):
        body = "As shown in Figure 1, the data confirms the hypothesis."
        result = WritingHandler._strip_orphan_figure_references(body)
        assert "Figure 1" in result

    def test_removes_multiple_tags(self):
        body = "![Figure 1](figures/a.png)\n![Figure 2](figures/b.png)\nText here."
        result = WritingHandler._strip_orphan_figure_references(body)
        assert "![Figure 1]" not in result
        assert "![Figure 2]" not in result
        assert "Text here." in result

    def test_cleans_empty_lines(self):
        body = "Before.\n\n\n\n\nAfter."
        result = WritingHandler._strip_orphan_figure_references(body)
        assert "\n\n\n" not in result

    def test_handles_fig_dot_variant(self):
        body = "Text.\n\n![Fig. 3](figures/plot.png)\n\nMore text."
        result = WritingHandler._strip_orphan_figure_references(body)
        assert "![Fig. 3]" not in result


# ---------------------------------------------------------------------------
# generate_conceptual_figures — guard tests
# ---------------------------------------------------------------------------


class TestGenerateConceptualFiguresGuards:
    @pytest.mark.asyncio
    async def test_guard_existing_figures(self):
        engine = _make_engine_mock(execution_figures=[("exp1", Path("/tmp/fig.png"))])
        handler = WritingHandler(engine)
        body = "See Figure 1 for details."
        result = await handler.generate_conceptual_figures(body)
        assert result == body  # unchanged

    @pytest.mark.asyncio
    async def test_guard_sandbox_disabled(self):
        engine = _make_engine_mock(sandbox_enabled=False)
        handler = WritingHandler(engine)
        body = "See Figure 1 for details."
        result = await handler.generate_conceptual_figures(body)
        assert result == body

    @pytest.mark.asyncio
    async def test_guard_feature_disabled(self):
        engine = _make_engine_mock(enable_conceptual_figures=False)
        handler = WritingHandler(engine)
        body = "See Figure 1 for details."
        result = await handler.generate_conceptual_figures(body)
        assert result == body

    @pytest.mark.asyncio
    async def test_guard_no_writer(self):
        engine = _make_engine_mock(writer_agent=None)
        handler = WritingHandler(engine)
        body = "See Figure 1 for details."
        result = await handler.generate_conceptual_figures(body)
        assert result == body

    @pytest.mark.asyncio
    async def test_guard_no_refs(self):
        engine = _make_engine_mock()
        handler = WritingHandler(engine)
        body = "This paper has no figure references at all."
        result = await handler.generate_conceptual_figures(body)
        assert result == body


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------


class TestConceptualFigurePrompt:
    def test_format(self):
        result = _CONCEPTUAL_FIGURE_PROMPT.format(
            figure_num=1,
            figure_context="As shown in Figure 1, the taxonomy of approaches...",
        )
        assert "Figure 1" in result
        assert "taxonomy" in result
        assert "plt.savefig" in result
        assert "figure_1.png" in result

    def test_format_different_numbers(self):
        for n in [1, 2, 3, 10]:
            result = _CONCEPTUAL_FIGURE_PROMPT.format(
                figure_num=n,
                figure_context=f"Figure {n} shows the relationship.",
            )
            assert f"figure_{n}.png" in result


# ---------------------------------------------------------------------------
# generate_conceptual_figures — code persistence
# ---------------------------------------------------------------------------


class TestConceptualFigureCodePersistence:
    @pytest.mark.asyncio
    async def test_successful_figure_appends_to_successful_code(self):
        """When a conceptual figure succeeds, its code is appended to engine._successful_code."""
        engine = _make_engine_mock()
        engine._successful_code = []

        handler = WritingHandler(engine)
        body = "As shown in Figure 1, the taxonomy is clear."

        # Mock the sandbox executor
        mock_output_file = MagicMock()
        mock_output_file.filename = "figure_1.png"
        mock_output_file.path = "/tmp/figure_1.png"

        mock_result = MagicMock()
        mock_result.output_files = [mock_output_file]

        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value=mock_result)
        mock_executor.cleanup = AsyncMock()

        # Mock writer agent response with code block
        mock_response = MagicMock()
        mock_response.content = (
            '```python\nimport matplotlib.pyplot as plt\nplt.savefig("figure_1.png")\n```'
        )
        engine._find_agent_by_role.return_value.generate = AsyncMock(return_value=mock_response)

        with patch("paradigm.sandbox.executor.CodeExecutor", return_value=mock_executor):
            await handler.generate_conceptual_figures(body)

        # Verify code was appended
        assert len(engine._successful_code) == 1
        name, code = engine._successful_code[0]
        assert name == "conceptual_fig_1"
        assert "plt.savefig" in code
