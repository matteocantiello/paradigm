"""Shared helper functions for orchestrator-related tests.

These are importable by test files: ``from helpers import make_mock_agent, ...``
Fixtures live in ``conftest.py`` (auto-discovered by pytest).
"""

import json
from unittest.mock import AsyncMock, MagicMock

from paradigm.agents.base import Agent, AgentResponse, TokenUsage

# Long response content that exceeds _MIN_PAPER_LENGTH for writing tests
LONG_RESPONSE = (
    "# Test Paper Title\n\n"
    "## Abstract\n\nThis is a comprehensive study of stellar convection. "
    "We present new theoretical models and observational constraints on "
    "convective overshooting in intermediate-mass stars using 1D stellar "
    "evolution models. Our analysis reveals that overshooting extends the "
    "main-sequence lifetime by 15-25% for stars in the 1.5-8 solar mass range, "
    "with significant implications for age determinations of stellar clusters.\n\n"
    "## Introduction\n\nStellar convection is a fundamental process in stellar physics "
    "that governs energy transport, chemical mixing, and angular momentum redistribution "
    "in stellar interiors. Understanding convective processes is essential for modeling "
    "stellar evolution accurately. In this paper, we present a detailed analysis of "
    "convective overshooting in intermediate-mass stars.\n\n"
    "The treatment of convective boundaries remains one of the largest uncertainties "
    "in stellar evolution theory. Classical mixing-length theory (MLT) provides a "
    "local description of convection but does not predict the extent of mixing beyond "
    "formally stable boundaries. Overshooting — the penetration of convective motions "
    "into radiatively stable layers — has profound effects on stellar structure, "
    "nucleosynthesis, and observable properties.\n\n"
    "Previous studies have parameterized overshooting as a fraction of the pressure "
    "scale height (f_ov), with values ranging from 0.01 to 0.03 depending on stellar "
    "mass, evolutionary state, and calibration method. However, systematic uncertainties "
    "persist, particularly regarding the mass dependence of f_ov and its effect on "
    "the main-sequence width in the Hertzsprung-Russell diagram.\n\n"
    "## Methods\n\nWe use one-dimensional stellar evolution models computed with the "
    "MESA code (version r23.05.1) to investigate the effects of convective overshooting "
    "on the main-sequence width. Our models span a mass range of 1.5 to 8 solar masses "
    "with initial metallicity Z = 0.014 and helium fraction Y = 0.266.\n\n"
    "For each mass, we compute evolutionary tracks with overshooting parameters "
    "f_ov = 0.000, 0.005, 0.010, 0.015, 0.020, 0.025, and 0.030 using the exponential "
    "diffusive scheme of Herwig (2000). We define the main-sequence width as the "
    "temperature difference between the zero-age main sequence and the terminal-age "
    "main sequence at constant luminosity.\n\n"
    "## Results\n\nOur results show that convective overshooting significantly affects "
    "the main-sequence lifetime and core hydrogen burning efficiency. For a 3 solar mass "
    "star, increasing f_ov from 0.000 to 0.020 extends the main-sequence lifetime from "
    "284 Myr to 347 Myr (a 22% increase). The convective core mass at the TAMS "
    "increases by approximately 18%, leading to a more luminous and cooler turnoff point.\n\n"
    "The mass dependence of overshooting shows a clear trend: the relative effect on "
    "main-sequence lifetime increases from 15% at 1.5 solar masses to 25% at 8 solar "
    "masses for f_ov = 0.020. Statistical comparison with observed eclipsing binaries "
    "yields a best-fit overshooting parameter of f_ov = 0.016 +/- 0.004, consistent "
    "with previous calibrations.\n\n"
    "## Conclusions\n\nWe conclude that convective overshooting is a critical ingredient "
    "in stellar evolution models for intermediate-mass stars. Our systematic grid of "
    "models provides calibrated overshooting parameters that can be applied to stellar "
    "population synthesis and cluster age determinations. The mass dependence of f_ov "
    "suggests that a single overshooting parameter is insufficient to describe the "
    "physics across the full mass range studied here."
)


def build_checkpoint_response(
    summary: str = "Agents discussed the topic.",
    hypothesis: str = "Test hypothesis",
) -> tuple[str, int, int]:
    """Build a mock provider.complete() response for checkpoint compression.

    Returns:
        Tuple of (json_string, input_tokens, output_tokens).
    """
    return (
        json.dumps(
            {
                "hypothesis": hypothesis,
                "key_findings": ["Finding 1"],
                "open_questions": ["Question 1"],
                "next_steps": ["Next step 1"],
                "conversation_summary": summary,
            }
        ),
        200,
        100,
    )


def make_mock_agent(
    agent_id: str,
    role: str,
    content: str | None = None,
    long_response: bool = False,
) -> Agent:
    """Create a mock agent that returns canned responses.

    Args:
        agent_id: Agent identifier.
        role: Skill profile / role name.
        content: Custom response content (overrides long_response).
        long_response: If True and content is None, use LONG_RESPONSE.

    Returns:
        Mock Agent with generate() and format_message() stubbed.
    """
    agent = MagicMock(spec=Agent)
    agent.agent_id = agent_id
    agent.skill_profile = role

    if content is not None:
        response_content = content
    elif long_response:
        response_content = LONG_RESPONSE
    else:
        response_content = f"Response from {agent_id}: I have ideas about this topic."

    response = AgentResponse(
        content=response_content,
        usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
        model="claude-sonnet-4-5-20250929",
    )
    agent.generate = AsyncMock(return_value=response)

    def _format_message(to, thread_id, phase, message_type, content, **kwargs):
        msg = MagicMock()
        msg.model_dump.return_value = {
            "from": agent_id,
            "to": to,
            "thread_id": thread_id,
            "phase": phase,
            "type": message_type,
            "content": content,
            "references": [],
            "metadata": {},
        }
        return msg

    agent.format_message = MagicMock(side_effect=_format_message)
    return agent


def patch_config_provider(config, checkpoint_response=None):
    """Patch a Config object's provider methods with a mock provider.

    Args:
        config: Config instance to patch.
        checkpoint_response: Optional custom checkpoint response tuple.
            Defaults to build_checkpoint_response().

    Returns:
        The mock provider (for further customization).
    """
    if checkpoint_response is None:
        checkpoint_response = build_checkpoint_response()

    mock_provider = MagicMock()
    mock_provider.complete.return_value = checkpoint_response
    mock_provider.default_model = "claude-sonnet-4-5-20250929"
    object.__setattr__(config, "get_provider", MagicMock(return_value=mock_provider))
    object.__setattr__(
        config,
        "get_provider_and_model_for_role",
        MagicMock(return_value=(mock_provider, "claude-sonnet-4-5-20250929")),
    )
    return mock_provider
