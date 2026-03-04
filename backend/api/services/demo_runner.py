"""Demo runner that simulates a research cycle for frontend testing.

Used when the Paradigm core is not available (e.g. Python version mismatch).
Sends realistic WebSocket messages through the session manager to exercise
the full frontend UI: phase transitions, agent outputs, notifications,
approval requests, and session completion.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import datetime, timezone

from backend.api.models.messages import (
    AgentOutputStreamMsg,
    AgentStepCompleteMsg,
    KnowledgeUpdateMsg,
    NotificationMsg,
    PhaseTransitionMsg,
    RoundUpdateMsg,
    SessionStateMsg,
)

logger = logging.getLogger(__name__)

# Simulated agent IDs and their roles
DEMO_AGENTS = [
    ("agent-theorist-1", "theorist"),
    ("agent-analyst-1", "analyst"),
    ("agent-experimentalist-1", "experimentalist"),
    ("agent-synthesizer-1", "synthesizer"),
    ("agent-skeptic-1", "skeptic"),
    ("agent-writer-1", "writer"),
    ("agent-editor-1", "editor"),
]

# Demo phase progression with simulated content
DEMO_PHASES = [
    {
        "phase": "seeding",
        "rounds": 1,
        "agents": ["agent-theorist-1", "agent-analyst-1"],
        "messages": [
            (
                "agent-theorist-1",
                "Analyzing the research prompt. The topic involves stellar variability patterns in massive stars, which connects to several active areas of astrophysical research.",
            ),
            (
                "agent-analyst-1",
                "Identified key parameters for analysis: luminosity variations, pulsation periods, mass-loss rates, and evolutionary stage indicators.",
            ),
        ],
        "notifications": [
            ("info", "search", "Initialized research thread with seed prompt"),
        ],
    },
    {
        "phase": "ideation",
        "rounds": 2,
        "agents": ["agent-theorist-1", "agent-analyst-1", "agent-skeptic-1"],
        "messages": [
            (
                "agent-theorist-1",
                "Hypothesis 1: Stochastic low-frequency variability in massive stars is driven by subsurface convection zones interacting with the stellar envelope, producing characteristic red noise power spectra.",
            ),
            (
                "agent-analyst-1",
                "The power spectral density analysis suggests a broken power law with break frequencies correlating with the convective turnover timescale.",
            ),
            (
                "agent-skeptic-1",
                "We need to distinguish this mechanism from other sources of variability: wind clumping, binary interactions, and instrumental artifacts. What specific predictions does this hypothesis make that alternatives don't?",
            ),
            (
                "agent-theorist-1",
                "The subsurface convection hypothesis predicts a specific relationship between $T_{\\mathrm{eff}}$ and the characteristic frequency $\\nu_0$, namely $\\nu_0 \\propto T_{\\mathrm{eff}}^{4.2}$. This is testable with TESS data.",
            ),
        ],
        "notifications": [
            ("info", "debate", "Ideation round 1: 3 hypotheses proposed"),
            ("info", "debate", "Ideation round 2: Hypothesis ranking complete"),
        ],
    },
    {
        "phase": "planning",
        "rounds": 1,
        "agents": ["agent-theorist-1", "agent-analyst-1", "agent-experimentalist-1"],
        "messages": [
            (
                "agent-analyst-1",
                "Research plan:\n1. Retrieve TESS light curves for a sample of OB stars\n2. Compute power spectra using Lomb-Scargle periodograms\n3. Fit broken power law models to extract characteristic frequencies\n4. Test correlation with stellar parameters from Gaia DR3",
            ),
            (
                "agent-experimentalist-1",
                "I'll set up the analysis pipeline. We'll need: `lightkurve` for TESS data, `astropy` for coordinate matching, and a custom periodogram fitting routine.",
            ),
        ],
        "notifications": [
            ("info", "phase", "Research plan finalized with 4 execution steps"),
        ],
    },
    {
        "phase": "execution",
        "rounds": 3,
        "agents": ["agent-experimentalist-1", "agent-analyst-1"],
        "messages": [
            (
                "agent-experimentalist-1",
                "Running TESS light curve retrieval for 47 OB stars in the sample. Using 2-minute cadence data from sectors 1-55.",
            ),
            (
                "agent-analyst-1",
                "Power spectrum computation complete for 42/47 targets (5 excluded due to contamination). Median noise floor: $2.3 \\times 10^{-6}$ ppm$^2$/Hz.",
            ),
            (
                "agent-experimentalist-1",
                "Broken power law fits converged for 38 targets. Best-fit parameters: $\\alpha_0 = 3.1 \\pm 0.4$, $\\nu_{\\mathrm{char}} = 0.8 \\pm 0.3$ d$^{-1}$.",
            ),
            (
                "agent-analyst-1",
                "Correlation analysis: Spearman rank coefficient between $\\log T_{\\mathrm{eff}}$ and $\\log \\nu_{\\mathrm{char}}$ is $r_s = 0.72$ ($p < 0.001$). This strongly supports the theoretical prediction.",
            ),
        ],
        "notifications": [
            ("success", "experiment", "Retrieved 42 TESS light curves"),
            ("info", "search", "Cross-matched with Gaia DR3 catalog"),
            ("success", "experiment", "Power spectrum analysis complete"),
        ],
    },
    {
        "phase": "post_execution",
        "rounds": 1,
        "agents": ["agent-synthesizer-1", "agent-skeptic-1", "agent-theorist-1"],
        "messages": [
            (
                "agent-synthesizer-1",
                "Key findings: (1) Red noise is ubiquitous in massive stars, (2) characteristic frequency correlates with $T_{\\mathrm{eff}}$, (3) power law slope $\\alpha_0 \\approx 3$ consistent with convective driving.",
            ),
            (
                "agent-skeptic-1",
                "The correlation is significant, but we should address: selection bias (TESS observability), the effect of stellar winds at high $T_{\\mathrm{eff}}$, and the limited sample of cool supergiants.",
            ),
            (
                "agent-theorist-1",
                "Agreed. We should include a section on caveats and propose follow-up observations with PLATO for longer baselines.",
            ),
        ],
        "notifications": [
            ("info", "debate", "Post-execution discussion complete"),
        ],
    },
    {
        "phase": "writing",
        "rounds": 2,
        "agents": ["agent-writer-1", "agent-editor-1"],
        "messages": [
            (
                "agent-writer-1",
                "Draft complete: 'Subsurface Convection as the Driver of Stochastic Variability in Massive Stars: Evidence from TESS Photometry'. 12 pages, 8 figures, 2 tables.",
            ),
            (
                "agent-editor-1",
                "Revision notes: strengthen the abstract conclusion, add comparison table with Bowman et al. (2019) results, fix LaTeX formatting in equations 3-5.",
            ),
            (
                "agent-writer-1",
                "Revisions applied. Final word count: 6,842. All figures updated with consistent color scheme.",
            ),
        ],
        "notifications": [
            ("info", "writing", "First draft complete"),
            ("info", "writing", "Editorial revisions applied"),
        ],
    },
    {
        "phase": "internal",
        "rounds": 1,
        "agents": ["agent-skeptic-1", "agent-theorist-1"],
        "messages": [
            (
                "agent-skeptic-1",
                "Internal review score: 7.8/10. Strengths: clear methodology, strong statistical analysis. Weaknesses: could better discuss alternative interpretations of the $T_{\\mathrm{eff}}$ correlation.",
            ),
            (
                "agent-theorist-1",
                "Concur with review. Paper is suitable for submission after minor revisions to Section 5.2.",
            ),
        ],
        "notifications": [
            ("success", "review", "Internal review passed (7.8/10)"),
        ],
    },
    {
        "phase": "submitted",
        "rounds": 1,
        "agents": ["agent-writer-1"],
        "messages": [
            (
                "agent-writer-1",
                "Paper submitted to the Paradigm Journal: 'Subsurface Convection as the Driver of Stochastic Variability in Massive Stars: Evidence from TESS Photometry'. Awaiting peer review assignment.",
            ),
        ],
        "notifications": [
            ("success", "writing", "Paper submitted to journal"),
        ],
    },
    {
        "phase": "peer_review",
        "rounds": 1,
        "agents": ["agent-skeptic-1", "agent-editor-1"],
        "messages": [
            (
                "agent-skeptic-1",
                "Peer review report: The paper presents a compelling analysis of SLF variability. The $T_{\\mathrm{eff}}$–$\\nu_0$ correlation is statistically robust (r=0.72). Minor revision requested: expand discussion of selection effects and TESS window function impact.",
            ),
            (
                "agent-editor-1",
                "Editorial decision: Accept with minor revisions. The methodology is sound and the conclusions are well-supported by the data. Revisions to Section 5.2 addressing selection effects are satisfactory.",
            ),
        ],
        "notifications": [
            ("info", "review", "Peer review received (1 referee)"),
            ("success", "review", "Editorial decision: Accept with minor revisions"),
        ],
    },
    {
        "phase": "published",
        "rounds": 1,
        "agents": ["agent-editor-1"],
        "messages": [
            (
                "agent-editor-1",
                "Paper accepted and published in the Paradigm Journal. Final version includes all referee-requested revisions. DOI assigned.",
            ),
        ],
        "notifications": [
            ("success", "lifecycle", "Paper published successfully"),
        ],
    },
]

# Sample content for the demo paper
DEMO_PAPER_BODY = """## Abstract

We present an analysis of stochastic low-frequency variability in 42 massive OB stars
observed by TESS. Using broken power-law fits to the power spectral density, we find a
significant correlation between the characteristic frequency and effective temperature.

## 1. Introduction

Massive stars ($M > 8 M_\\odot$) exhibit rich variability across multiple timescales.
Recent space photometry missions have revealed ubiquitous stochastic low-frequency
variability (SLF) characterized by red noise power spectra.

## 2. Methods

### 2.1 Sample Selection

We selected 47 OB-type stars from the TESS Input Catalog with $T_{\\mathrm{eff}} > 15,000$ K
and $V < 10$ mag.

### 2.2 Power Spectrum Analysis

Power spectra were computed using the Lomb-Scargle periodogram:

$$P(\\nu) = \\frac{\\alpha_0 \\nu_0^2}{\\nu^2 + \\nu_0^2} + C_w$$

## 3. Results

The characteristic frequency $\\nu_0$ shows a strong correlation with $T_{\\mathrm{eff}}$:

$$\\log \\nu_0 = (4.2 \\pm 0.6) \\log T_{\\mathrm{eff}} + \\mathrm{const}$$

| Parameter | Value | Unit |
|-----------|-------|------|
| $\\alpha_0$ | $3.1 \\pm 0.4$ | - |
| $\\nu_0$ | $0.8 \\pm 0.3$ | d$^{-1}$ |
| $r_s$ | 0.72 | - |

## 4. Discussion

These results support the subsurface convection hypothesis proposed by Cantiello et al. (2009).

## 5. Conclusions

Stochastic variability in massive stars is driven by subsurface convection zones.
"""


def _create_demo_paper(state) -> None:
    """Create a demo paper in the in-memory store and link it to the cycle."""
    from backend.api.routes.papers import _demo_papers
    from backend.api.routes.research import _cycles

    paper_id = f"paper-demo-{state.session_id[-8:]}"
    now = datetime.now(timezone.utc).isoformat()

    _demo_papers[paper_id] = {
        "id": paper_id,
        "title": (
            "Subsurface Convection as the Driver of Stochastic Variability "
            "in Massive Stars: Evidence from TESS Photometry"
        ),
        "abstract": (
            "We present an analysis of stochastic low-frequency variability in 42 massive "
            "OB stars observed by TESS. Using broken power-law fits to the power spectral "
            "density, we find a significant correlation between the characteristic frequency "
            "and effective temperature."
        ),
        "authors": ["Agent Theorist", "Agent Analyst", "Agent Writer"],
        "body": DEMO_PAPER_BODY,
        "status": "submitted",
        "keywords": [
            "massive stars",
            "stellar variability",
            "convection",
            "TESS",
            "red noise",
        ],
        "citation_count": 0,
        "created_at": now,
        "published_at": None,
    }

    # Link paper to the research cycle
    for cycle in _cycles.values():
        if cycle.session_id == state.session_id:
            cycle.paper_id = paper_id
            break

    logger.info("Demo paper %s created for session %s", paper_id, state.session_id)


def _publish_demo_paper(state) -> None:
    """Update the demo paper status to published."""
    from backend.api.routes.papers import _demo_papers
    from backend.api.routes.research import _cycles

    for cycle in _cycles.values():
        if cycle.session_id == state.session_id and cycle.paper_id:
            paper = _demo_papers.get(cycle.paper_id)
            if paper:
                paper["status"] = "published"
                paper["published_at"] = datetime.now(timezone.utc).isoformat()
                logger.info("Demo paper %s published", cycle.paper_id)
            break


async def run_demo_cycle(session_id: str, manager) -> None:
    """Simulate a research cycle by sending WS messages through the manager.

    This runs as a background task, sending messages at realistic intervals
    to exercise the full frontend UI.
    """
    from backend.api.models.session import SessionStatus

    state = manager._sessions.get(session_id)
    if state is None:
        return

    state.status = SessionStatus.RUNNING
    state.updated_at = datetime.now(timezone.utc)

    total_tokens = 0
    total_searches = 0
    papers_found = 0

    try:
        for phase_info in DEMO_PHASES:
            phase = phase_info["phase"]
            rounds = phase_info["rounds"]
            prev_phase = state.current_phase

            # Phase transition
            state.current_phase = phase
            state.max_rounds = rounds
            state.round_num = 0
            state.updated_at = datetime.now(timezone.utc)

            await manager.broadcast_message(
                session_id,
                PhaseTransitionMsg(
                    from_phase=prev_phase,
                    to_phase=phase,
                    max_rounds=rounds,
                ),
            )
            await asyncio.sleep(1.0)

            # Rounds
            for rnd in range(1, rounds + 1):
                state.round_num = rnd
                await manager.broadcast_message(
                    session_id,
                    RoundUpdateMsg(round_num=rnd, max_rounds=rounds, phase=phase),
                )

                # Update active agents
                active = {}
                for agent_id in phase_info["agents"]:
                    role = agent_id.split("-")[1]
                    active[agent_id] = role
                state.active_agents = active

                await asyncio.sleep(0.5)

            # Agent messages
            for agent_id, content in phase_info["messages"]:
                role = agent_id.split("-")[1]
                tokens = random.randint(800, 3000)
                total_tokens += tokens

                # Stream the message
                await manager.broadcast_message(
                    session_id,
                    AgentOutputStreamMsg(
                        agent_id=agent_id,
                        role=role,
                        content=content,
                        phase=phase,
                        stream_id=f"stream-{agent_id}-{phase}",
                        is_final=True,
                        tokens=tokens,
                        model="claude-sonnet-4-5-20250929",
                    ),
                )
                await asyncio.sleep(1.5)

                # Step complete
                await manager.broadcast_message(
                    session_id,
                    AgentStepCompleteMsg(
                        agent_id=agent_id,
                        role=role,
                        summary=content[:100] + "..." if len(content) > 100 else content,
                        phase=phase,
                        tokens=tokens,
                    ),
                )

                state.total_tokens = total_tokens
                state.updated_at = datetime.now(timezone.utc)

                # Broadcast updated session state (stats, elapsed time)
                await manager.broadcast_message(
                    session_id,
                    SessionStateMsg(
                        session_id=session_id,
                        status=state.status.value,
                        current_phase=state.current_phase,
                        round_num=state.round_num,
                        max_rounds=state.max_rounds,
                        thread_id=state.thread_id,
                        active_agents=state.active_agents,
                        total_tokens=state.total_tokens,
                        total_searches=state.total_searches,
                        papers_found=state.papers_found,
                        elapsed_seconds=round(
                            time.monotonic()
                            - manager._session_start_times.get(session_id, time.monotonic()),
                            1,
                        ),
                        completed_phases=state.completed_phases or [],
                    ),
                )
                await asyncio.sleep(0.5)

            # Notifications
            for level, category, message in phase_info["notifications"]:
                if category == "search":
                    total_searches += 1
                    state.total_searches = total_searches
                if "paper" in message.lower() or "retrieved" in message.lower():
                    papers_found += random.randint(1, 5)
                    state.papers_found = papers_found

                await manager.broadcast_message(
                    session_id,
                    NotificationMsg(level=level, category=category, message=message),
                )
                await asyncio.sleep(0.3)

            # Mark phase complete
            if phase not in (state.completed_phases or []):
                if not hasattr(state, "completed_phases") or state.completed_phases is None:
                    state.completed_phases = []
                state.completed_phases.append(phase)

            # Send demo knowledge updates at key phase transitions
            if phase == "ideation":
                knowledge_msg = _build_demo_knowledge_ideation()
                manager.store_knowledge_snapshot(session_id, knowledge_msg)
                await manager.broadcast_message(session_id, knowledge_msg)
            elif phase == "execution":
                knowledge_msg = _build_demo_knowledge_execution()
                manager.store_knowledge_snapshot(session_id, knowledge_msg)
                await manager.broadcast_message(session_id, knowledge_msg)

            # Create demo paper after writing phase
            if phase == "writing":
                _create_demo_paper(state)
            elif phase == "published":
                _publish_demo_paper(state)

            await asyncio.sleep(1.0)

        # Complete
        state.status = SessionStatus.COMPLETED
        state.thread_id = "thread-demo-001"
        state.updated_at = datetime.now(timezone.utc)

        await manager.broadcast_message(
            session_id,
            NotificationMsg(
                level="success",
                category="lifecycle",
                message="Research cycle completed successfully! Paper ready for submission.",
            ),
        )

    except asyncio.CancelledError:
        state.status = SessionStatus.ABORTED
        state.updated_at = datetime.now(timezone.utc)
        logger.info("Demo session %s cancelled", session_id)

    except Exception as e:
        from backend.api.models.messages import ErrorMsg
        from backend.api.models.session import SessionStatus

        state.status = SessionStatus.FAILED
        state.updated_at = datetime.now(timezone.utc)
        logger.exception("Demo session %s failed", session_id)
        await manager.broadcast_message(
            session_id,
            ErrorMsg(code="demo_failed", message=str(e), recoverable=False),
        )


def _build_demo_knowledge_ideation() -> KnowledgeUpdateMsg:
    """Build a demo knowledge snapshot after IDEATION phase."""
    return KnowledgeUpdateMsg(
        entities=[
            {
                "id": "e1",
                "name": "OB Stars",
                "entity_type": "object",
                "description": "Massive OB-type stars with Teff > 15,000 K",
            },
            {
                "id": "e2",
                "name": "TESS",
                "entity_type": "instrument",
                "description": "Transiting Exoplanet Survey Satellite",
            },
            {
                "id": "e3",
                "name": "Subsurface Convection Zones",
                "entity_type": "mechanism",
                "description": "Convective regions beneath the stellar surface",
            },
            {
                "id": "e4",
                "name": "Red Noise",
                "entity_type": "observable",
                "description": "Stochastic low-frequency variability in power spectra",
            },
        ],
        relationships=[
            {
                "id": "r1",
                "source": "e3",
                "target": "e4",
                "relationship_type": "causes",
                "description": "Subsurface convection drives red noise variability",
            },
        ],
        hypotheses=[
            {
                "id": "h1",
                "statement": "Stochastic low-frequency variability in massive stars is driven by subsurface convection zones",
                "status": "supported",
                "elo_rating": 1580,
                "rationale": "Predicts Teff-frequency correlation",
                "supporting_evidence": ["ev1", "ev2"],
                "contradicting_evidence": [],
            },
            {
                "id": "h2",
                "statement": "Wind clumping dominates the observed variability in hot stars",
                "status": "under_investigation",
                "elo_rating": 1420,
                "rationale": "Alternative mechanism for OB star variability",
                "supporting_evidence": [],
                "contradicting_evidence": ["ev1"],
            },
            {
                "id": "h3",
                "statement": "Binary interactions produce the observed red noise signatures",
                "status": "under_investigation",
                "elo_rating": 1400,
                "rationale": "Binary effects could mimic stochastic variability",
                "supporting_evidence": [],
                "contradicting_evidence": [],
            },
        ],
        evidence=[
            {
                "id": "ev1",
                "content": "Power law slope alpha_0 ~ 3 consistent with convective driving predictions",
                "source": "analysis",
                "supports": ["h1"],
                "contradicts": ["h2"],
            },
            {
                "id": "ev2",
                "content": "Characteristic frequency correlates with Teff (Spearman r=0.72)",
                "source": "observation",
                "supports": ["h1"],
                "contradicts": [],
            },
        ],
        research_goals=[
            {
                "id": "g1",
                "description": "Determine the physical mechanism driving stochastic variability in massive stars",
                "status": "active",
            },
            {
                "id": "g2",
                "description": "Test the Teff-frequency correlation prediction",
                "status": "active",
            },
        ],
        open_questions=[
            {
                "id": "q1",
                "question": "How does wind clumping affect the power spectrum at high Teff?",
                "priority": "high",
            },
            {
                "id": "q2",
                "question": "Is the sample biased by TESS observability constraints?",
                "priority": "medium",
            },
        ],
        conflicts=[
            {
                "id": "c1",
                "conflict_type": "unresolved",
                "description": "Convection vs wind clumping as primary variability driver",
                "hypothesis_ids": ["h1", "h2"],
            },
        ],
        assumptions=[
            {
                "id": "a1",
                "statement": "TESS 2-minute cadence is sufficient to resolve the characteristic frequencies",
                "status": "active",
            },
            {
                "id": "a2",
                "statement": "Gaia DR3 Teff values are accurate for hot stars",
                "status": "active",
            },
        ],
        tournament_rankings=[
            {
                "hypothesis_id": "h1",
                "statement": "Subsurface convection drives SLF variability",
                "elo_rating": 1580,
                "status": "supported",
            },
            {
                "hypothesis_id": "h2",
                "statement": "Wind clumping dominates variability",
                "elo_rating": 1420,
                "status": "under_investigation",
            },
            {
                "hypothesis_id": "h3",
                "statement": "Binary interactions produce red noise",
                "elo_rating": 1400,
                "status": "under_investigation",
            },
        ],
        matchup_results=[
            {
                "hypothesis_a_id": "h1",
                "hypothesis_b_id": "h2",
                "winner_id": "h1",
                "judge_reasoning": "Convection hypothesis makes specific testable prediction about Teff-frequency relation",
                "margin": 0.7,
            },
            {
                "hypothesis_a_id": "h1",
                "hypothesis_b_id": "h3",
                "winner_id": "h1",
                "judge_reasoning": "Binary hypothesis lacks mechanism for power law slope",
                "margin": 0.8,
            },
        ],
        tournament_status="completed",
        world_model_summary="3 hypotheses under investigation, 2 pieces of evidence, 4 entities identified. Leading hypothesis: subsurface convection (Elo 1580).",
        evidence_landscape_summary="1 unresolved conflict (convection vs wind), 2 active assumptions.",
        tournament_summary="Tournament complete: subsurface convection hypothesis ranked #1 (Elo 1580).",
    )


def _build_demo_knowledge_execution() -> KnowledgeUpdateMsg:
    """Build an updated demo knowledge snapshot after EXECUTION phase."""
    return KnowledgeUpdateMsg(
        entities=[
            {
                "id": "e1",
                "name": "OB Stars",
                "entity_type": "object",
                "description": "Massive OB-type stars with Teff > 15,000 K",
            },
            {
                "id": "e2",
                "name": "TESS",
                "entity_type": "instrument",
                "description": "Transiting Exoplanet Survey Satellite",
            },
            {
                "id": "e3",
                "name": "Subsurface Convection Zones",
                "entity_type": "mechanism",
                "description": "Convective regions beneath the stellar surface",
            },
            {
                "id": "e4",
                "name": "Red Noise",
                "entity_type": "observable",
                "description": "Stochastic low-frequency variability in power spectra",
            },
            {
                "id": "e5",
                "name": "Broken Power Law",
                "entity_type": "model",
                "description": "P(v) = a0 * v0^2 / (v^2 + v0^2) + Cw",
            },
        ],
        relationships=[
            {
                "id": "r1",
                "source": "e3",
                "target": "e4",
                "relationship_type": "causes",
                "description": "Subsurface convection drives red noise variability",
            },
            {
                "id": "r2",
                "source": "e5",
                "target": "e4",
                "relationship_type": "models",
                "description": "Broken power law fits the observed PSD",
            },
        ],
        hypotheses=[
            {
                "id": "h1",
                "statement": "Stochastic low-frequency variability in massive stars is driven by subsurface convection zones",
                "status": "supported",
                "elo_rating": 1620,
                "rationale": "Confirmed by Teff-frequency correlation (r=0.72, p<0.001)",
                "supporting_evidence": ["ev1", "ev2", "ev3", "ev4"],
                "contradicting_evidence": [],
            },
            {
                "id": "h2",
                "statement": "Wind clumping dominates the observed variability in hot stars",
                "status": "weakened",
                "elo_rating": 1380,
                "rationale": "Power law slope inconsistent with wind predictions",
                "supporting_evidence": [],
                "contradicting_evidence": ["ev1", "ev3"],
            },
            {
                "id": "h3",
                "statement": "Binary interactions produce the observed red noise signatures",
                "status": "weakened",
                "elo_rating": 1350,
                "rationale": "No correlation with known binary fraction",
                "supporting_evidence": [],
                "contradicting_evidence": ["ev4"],
            },
        ],
        evidence=[
            {
                "id": "ev1",
                "content": "Power law slope alpha_0 = 3.1 +/- 0.4 consistent with convective driving",
                "source": "experiment",
                "supports": ["h1"],
                "contradicts": ["h2"],
            },
            {
                "id": "ev2",
                "content": "Characteristic frequency correlates with Teff (Spearman r=0.72, p<0.001)",
                "source": "experiment",
                "supports": ["h1"],
                "contradicts": [],
            },
            {
                "id": "ev3",
                "content": "42/47 targets show red noise; 38 well-fit by broken power law",
                "source": "experiment",
                "supports": ["h1"],
                "contradicts": ["h2"],
            },
            {
                "id": "ev4",
                "content": "No significant correlation between variability amplitude and known binary status",
                "source": "experiment",
                "supports": ["h1"],
                "contradicts": ["h3"],
            },
        ],
        research_goals=[
            {
                "id": "g1",
                "description": "Determine the physical mechanism driving stochastic variability in massive stars",
                "status": "achieved",
            },
            {
                "id": "g2",
                "description": "Test the Teff-frequency correlation prediction",
                "status": "achieved",
            },
        ],
        open_questions=[
            {
                "id": "q1",
                "question": "How does wind clumping affect the power spectrum at high Teff?",
                "priority": "high",
            },
            {
                "id": "q2",
                "question": "Is the sample biased by TESS observability constraints?",
                "priority": "medium",
            },
            {
                "id": "q3",
                "question": "Can PLATO observations extend the baseline to lower frequencies?",
                "priority": "low",
            },
        ],
        conflicts=[
            {
                "id": "c1",
                "conflict_type": "resolved",
                "description": "Convection vs wind clumping — resolved in favor of convection based on power law slope and Teff correlation",
                "hypothesis_ids": ["h1", "h2"],
            },
        ],
        assumptions=[
            {
                "id": "a1",
                "statement": "TESS 2-minute cadence is sufficient to resolve the characteristic frequencies",
                "status": "validated",
            },
            {
                "id": "a2",
                "statement": "Gaia DR3 Teff values are accurate for hot stars",
                "status": "active",
            },
            {
                "id": "a3",
                "statement": "5 excluded targets do not bias the Teff correlation",
                "status": "active",
            },
        ],
        tournament_rankings=[
            {
                "hypothesis_id": "h1",
                "statement": "Subsurface convection drives SLF variability",
                "elo_rating": 1620,
                "status": "supported",
            },
            {
                "hypothesis_id": "h2",
                "statement": "Wind clumping dominates variability",
                "elo_rating": 1380,
                "status": "weakened",
            },
            {
                "hypothesis_id": "h3",
                "statement": "Binary interactions produce red noise",
                "elo_rating": 1350,
                "status": "weakened",
            },
        ],
        matchup_results=[
            {
                "hypothesis_a_id": "h1",
                "hypothesis_b_id": "h2",
                "winner_id": "h1",
                "judge_reasoning": "Experimental evidence strongly supports convection hypothesis",
                "margin": 0.85,
            },
            {
                "hypothesis_a_id": "h1",
                "hypothesis_b_id": "h3",
                "winner_id": "h1",
                "judge_reasoning": "No binary correlation found in data",
                "margin": 0.9,
            },
        ],
        tournament_status="completed",
        world_model_summary="3 hypotheses (1 supported, 2 weakened), 4 pieces of experimental evidence, 5 entities. Convection hypothesis confirmed (Elo 1620).",
        evidence_landscape_summary="1 resolved conflict, 2 active assumptions, 1 validated assumption.",
        tournament_summary="Post-execution tournament: convection hypothesis strengthened to Elo 1620 with experimental confirmation.",
    )
