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
    "### Detailed Mass-Dependent Results\n\n"
    "Table 1 summarizes the main-sequence lifetime extension as a function of stellar "
    "mass and overshooting parameter. At 1.5 solar masses, the zero-overshooting model "
    "yields a main-sequence lifetime of 2.81 Gyr, which increases to 3.23 Gyr for "
    "f_ov = 0.020 (a 15% extension). At 2.0 solar masses, the corresponding values are "
    "1.14 Gyr and 1.35 Gyr (18% extension). For 3.0 solar masses, the lifetime grows "
    "from 284 Myr to 347 Myr (22% extension), while at 5.0 solar masses the increase "
    "is from 78.4 Myr to 97.0 Myr (24% extension). The most massive models at 8.0 "
    "solar masses show a lifetime increase from 26.1 Myr to 32.6 Myr (25% extension).\n\n"
    "The convective core mass fraction at the terminal-age main sequence exhibits a "
    "monotonic increase with f_ov across all masses. For the 3.0 solar mass model, "
    "the core mass fraction grows from 0.24 (no overshooting) to 0.28 (f_ov = 0.020), "
    "representing an 18% increase in the mass of processed material. This larger core "
    "translates to a higher luminosity at the TAMS and a wider main-sequence band in "
    "the HR diagram, consistent with observations of open clusters.\n\n"
    "### Surface Abundance Signatures\n\n"
    "Convective overshooting also affects surface abundances through enhanced mixing. "
    "Our models predict that the surface nitrogen enrichment during the main sequence "
    "increases by a factor of 1.3 to 1.8 when overshooting is included, depending on "
    "stellar mass. For stars above 4 solar masses, the carbon-to-nitrogen ratio at the "
    "TAMS decreases by approximately 30% compared to the non-overshooting case, "
    "providing an independent observational diagnostic for calibrating f_ov.\n\n"
    "The boron depletion pattern is particularly sensitive to overshooting: models with "
    "f_ov = 0.020 deplete boron 40% more efficiently than standard models by the "
    "mid-main-sequence point. This effect is most pronounced in the 1.5-3.0 solar mass "
    "range where the convective envelope base temperature is marginally sufficient for "
    "boron destruction via proton capture reactions.\n\n"
    "## Discussion\n\n"
    "Our results have significant implications for several areas of stellar astrophysics. "
    "First, the calibrated overshooting parameters provide improved age estimates for "
    "stellar clusters. Using our mass-dependent f_ov prescription, we re-derive the age "
    "of the Hyades cluster as 680 +/- 40 Myr, compared to the classical estimate of "
    "625 +/- 50 Myr obtained with no overshooting. This 9% age increase is consistent "
    "with recent lithium depletion boundary measurements.\n\n"
    "Second, the increased core mass at the TAMS has implications for post-main-sequence "
    "evolution. Stars with more massive helium cores at the end of core hydrogen burning "
    "will ignite helium at lower luminosities along the red giant branch, potentially "
    "explaining the observed luminosity function of red clump stars in the Kepler field. "
    "Our models predict that the red clump luminosity should be 0.05-0.10 dex brighter "
    "when overshooting is included, in good agreement with asteroseismic observations.\n\n"
    "Third, the mass dependence of f_ov suggests a physical origin related to the "
    "Peclet number at the convective boundary. In more massive stars, the convective "
    "velocities are higher and the thermal diffusion timescale is longer, leading to "
    "more vigorous penetration into the stable layers. This is qualitatively consistent "
    "with 3D hydrodynamic simulations by Meakin & Arnett (2007) and more recent work "
    "by Andrassy et al. (2022), though quantitative agreement remains elusive due to "
    "the limited duration and resolution of current 3D models.\n\n"
    "### Comparison with Previous Calibrations\n\n"
    "Our best-fit value of f_ov = 0.016 +/- 0.004 for intermediate-mass stars is "
    "consistent with the calibration by Claret & Torres (2017) who found f_ov = 0.017 "
    "using a sample of detached eclipsing binaries. It also agrees with the asteroseismic "
    "constraints from Deheuvels et al. (2016) who derived f_ov = 0.015 +/- 0.005 for "
    "subgiant stars observed by Kepler. However, our value is somewhat lower than the "
    "f_ov = 0.022 reported by Stancliffe et al. (2015) from fitting the width of the "
    "main sequence in the Large Magellanic Cloud, which may reflect metallicity effects "
    "not captured in our solar-metallicity grid.\n\n"
    "### Limitations and Caveats\n\n"
    "Several limitations should be noted. First, our models assume the exponential "
    "diffusive overshooting scheme of Herwig (2000), and the calibrated f_ov values "
    "are not directly transferable to step-function overshooting parameterizations. "
    "Second, we have not included the effects of rotation, which can mimic or enhance "
    "overshooting through rotationally-induced mixing. Third, our grid is limited to "
    "solar metallicity; extension to sub-solar and super-solar compositions is needed "
    "to assess the metallicity dependence of overshooting.\n\n"
    "## Conclusions\n\nWe conclude that convective overshooting is a critical ingredient "
    "in stellar evolution models for intermediate-mass stars. Our systematic grid of "
    "models provides calibrated overshooting parameters that can be applied to stellar "
    "population synthesis and cluster age determinations. The mass dependence of f_ov "
    "suggests that a single overshooting parameter is insufficient to describe the "
    "physics across the full mass range studied here.\n\n"
    "Finally, our results provide specific predictions that can be tested with future "
    "observations. The mass-dependent overshooting prescription predicts distinct "
    "morphological features in cluster color-magnitude diagrams: a wider main-sequence "
    "band for higher masses, a brighter turnoff point, and a more extended hook feature "
    "at the TAMS. High-precision photometry from missions such as Gaia and the Vera "
    "Rubin Observatory's Legacy Survey of Space and Time (LSST) will enable stringent "
    "tests of these predictions for a large sample of open clusters spanning a range of "
    "ages and metallicities.\n\n"
    "The surface abundance predictions — particularly the enhanced nitrogen enrichment "
    "and accelerated boron depletion — can be verified with high-resolution spectroscopy "
    "of main-sequence stars in young clusters. The upcoming WEAVE and 4MOST spectroscopic "
    "surveys will provide large homogeneous samples ideal for this purpose. Additionally, "
    "asteroseismic detection of mixed modes in subgiants observed by TESS and the future "
    "PLATO mission will directly constrain the size of the convective core and hence the "
    "overshooting parameter for individual stars.\n\n"
    "## Acknowledgements\n\n"
    "We thank the MESA development team for making their stellar evolution code publicly "
    "available. This research was supported by the National Science Foundation under "
    "grant AST-2205990. Computational resources were provided by the NASA High-End "
    "Computing Program through the NASA Advanced Supercomputing Division at Ames "
    "Research Center. We also acknowledge useful discussions with A. Claret regarding "
    "the calibration of overshooting parameters from eclipsing binary data, and thank "
    "the anonymous referee for constructive comments that substantially improved the "
    "clarity and presentation of this manuscript."
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
        # Long enough to count as a substantive contribution (>200 chars after
        # tag-stripping) — otherwise the engine's thin-output retry fires and
        # every mocked turn is generated twice, breaking call-count assertions.
        response_content = (
            f"Response from {agent_id}: I have ideas about this topic. "
            "The observed variability suggests a convective origin operating near "
            "the iron opacity bump, which we can test by correlating the amplitude "
            "with effective temperature and surface gravity across the sample and "
            "checking the predicted scaling against the tabulated measurements."
        )

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
        MagicMock(return_value=(mock_provider, "claude-sonnet-4-5-20250929", None)),
    )
    return mock_provider
