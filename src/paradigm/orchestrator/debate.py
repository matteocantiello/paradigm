"""Debate handler for focused agent-vs-agent debates."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from paradigm.literature.prompt_utils import parse_challenge_requests
from paradigm.logging.events import EventType
from paradigm.orchestrator.constants import (
    _CONCEDE_RE,
    _DEBATE_ENABLED_PHASES,
    _DEBATE_PROMPT_CHALLENGER,
    _DEBATE_PROMPT_DEFENDER,
    _DEBATE_SYNTHESIS_PROMPT,
    _RESOLVED_RE,
    _normalize_query_keywords,
)
from paradigm.orchestrator.phases import ResearchPhase

if TYPE_CHECKING:
    from paradigm.orchestrator.engine import OrchestrationEngine


class DebateHandler:
    """Handles focused debates between agents when challenges are issued."""

    def __init__(self, engine: OrchestrationEngine) -> None:
        self._engine = engine
        self.debate_counts: dict[str, int] = {}
        self.resolved_topics: list[dict[str, str]] = []

    def reset_cycle(self) -> None:
        """Reset debate state for a new research cycle."""
        self.debate_counts = {}
        self.resolved_topics = []

    def _is_duplicate_challenge(
        self,
        defender_id: str,
        reason: str,
    ) -> bool:
        """Check if a challenge duplicates an already-resolved debate topic.

        Uses Jaccard similarity on normalized keywords. Only checks debates
        targeting the same defender (any challenger).

        Args:
            defender_id: ID of the agent being challenged.
            reason: Reason / topic for the proposed challenge.

        Returns:
            True if this challenge is a near-duplicate of a resolved topic.
        """
        new_keywords = _normalize_query_keywords(reason)
        if not new_keywords:
            return False

        for resolved in self.resolved_topics:
            if resolved["defender_id"] != defender_id:
                continue
            existing_keywords = _normalize_query_keywords(resolved["topic"])
            if not existing_keywords:
                continue
            # Jaccard similarity check (same threshold as search dedup)
            intersection = len(new_keywords & existing_keywords)
            union = len(new_keywords | existing_keywords)
            if union > 0 and intersection / union >= 0.4:
                return True
        return False

    async def process_challenge_requests(
        self,
        challenger_id: str,
        response_text: str,
        phase: ResearchPhase,
        round_num: int,
    ) -> None:
        """Parse [CHALLENGE: agent-id: reason] markers and trigger debates.

        Only the first valid challenge per response is processed.

        Args:
            challenger_id: ID of the agent whose response contains the challenge.
            response_text: The agent's response text.
            phase: Current research phase.
            round_num: Current round number.
        """
        if not self._engine._config.orchestrator.enable_debates:
            return
        if phase not in _DEBATE_ENABLED_PHASES:
            return

        phase_key = str(phase)
        current_count = self.debate_counts.get(phase_key, 0)
        max_debates = self._engine._config.orchestrator.max_debates_per_phase

        if current_count >= max_debates:
            return

        challenges = parse_challenge_requests(response_text)
        if not challenges:
            return

        # Only process the first valid challenge
        active_roles = self._engine._get_phase_active_roles(phase)
        for challenge in challenges:
            target_id = challenge.challenged_agent_id

            # Skip self-challenge
            if target_id == challenger_id:
                continue

            # Target must exist
            if target_id not in self._engine.state.agents:
                self._engine._display.debate_skipped(target_id, f"target '{target_id}' not found")
                continue

            # Target must be active in this phase
            if active_roles is not None:
                target_role = self._engine.state.agents[target_id].skill_profile
                if target_role not in active_roles:
                    self._engine._display.debate_skipped(
                        target_id, f"'{target_id}' not active in {phase_key}"
                    )
                    continue

            # Duplicate check: skip if this topic was already debated and resolved
            if self._is_duplicate_challenge(target_id, challenge.reason):
                self._engine._display.debate_skipped(
                    target_id, "duplicate of already-resolved debate topic"
                )
                continue

            # Budget check (re-check inside loop in case of prior skip)
            if self.debate_counts.get(phase_key, 0) >= max_debates:
                self._engine._display.debate_budget_exhausted(max_debates, phase_key)
                break

            # Trigger the debate
            await self.run_debate(
                challenger_id=challenger_id,
                defender_id=target_id,
                debate_topic=challenge.reason,
                challenger_position=response_text,
                phase=phase,
                round_num=round_num,
            )
            # Only one debate per response
            break

    async def run_debate(
        self,
        challenger_id: str,
        defender_id: str,
        debate_topic: str,
        challenger_position: str,
        phase: ResearchPhase,
        round_num: int,
    ) -> None:
        """Execute a focused debate between two agents.

        Defender speaks first (challenger already stated position).
        On the final exchange, only the defender speaks.

        Args:
            challenger_id: Agent who issued the challenge.
            defender_id: Agent being challenged.
            debate_topic: Reason/topic for the debate.
            challenger_position: Challenger's original response (opening position).
            phase: Current research phase.
            round_num: Current round number.
        """
        phase_key = str(phase)
        max_exchanges = self._engine._config.orchestrator.max_debate_exchanges
        debate_id = f"debate-{uuid.uuid4().hex[:8]}"

        self._engine._display.debate_start(challenger_id, defender_id, debate_topic)
        self._engine.emit_event(
            "debate.started",
            {
                "debate_id": debate_id,
                "challenger": challenger_id,
                "defender": defender_id,
                "topic": debate_topic[:2000],
            },
        )

        self._engine._logger.log(
            EventType.DEBATE_TRIGGERED,
            content={
                "challenger": challenger_id,
                "defender": defender_id,
                "topic": debate_topic,
                "status": "started",
            },
            thread_id=self._engine.state.thread_id,
            phase=phase_key,
        )

        transcript: list[dict[str, str]] = []
        challenger_agent = self._engine.state.agents[challenger_id]
        defender_agent = self._engine.state.agents[defender_id]

        # The challenger's original response is the opening argument
        last_challenger_arg = challenger_position
        resolution_type = "max_turns"
        resolution_statement = ""

        for exchange_num in range(1, max_exchanges + 1):
            is_final_exchange = exchange_num == max_exchanges

            # --- Defender turn ---
            defender_prompt = _DEBATE_PROMPT_DEFENDER.format(
                defender_id=defender_id,
                challenger_id=challenger_id,
                challenger_argument=last_challenger_arg[:2000],
                debate_topic=debate_topic,
            )
            try:
                defender_response = await defender_agent.generate(defender_prompt)
            except Exception as e:
                self._engine._logger.log_error(
                    e, agent_id=defender_id, thread_id=self._engine.state.thread_id
                )
                self._engine._display.debate_error(defender_id, e)
                resolution_type = "error"
                resolution_statement = f"Debate ended due to error: {e}"
                break

            self._engine._log_agent_response(
                defender_id, defender_response, phase, "debate_defense"
            )
            transcript.append({"agent": defender_id, "content": defender_response.content})
            self._engine.emit_event(
                "debate.turn",
                {"debate_id": debate_id, "summary": defender_response.content[:200]},
                agent=defender_id,
            )

            # Check for resolution tags
            resolved_match = _RESOLVED_RE.search(defender_response.content)
            concede_match = _CONCEDE_RE.search(defender_response.content)
            if resolved_match:
                resolution_type = "resolved"
                resolution_statement = resolved_match.group(1).strip()
                self._engine._display.debate_resolved(defender_id)
                break
            if concede_match:
                resolution_type = "concede_defender"
                resolution_statement = concede_match.group(1).strip()
                self._engine._display.debate_concede(defender_id)
                break

            # On the final exchange, only the defender speaks
            if is_final_exchange:
                break

            # --- Challenger turn ---
            challenger_prompt = _DEBATE_PROMPT_CHALLENGER.format(
                challenger_id=challenger_id,
                defender_id=defender_id,
                defender_argument=defender_response.content[:2000],
                debate_topic=debate_topic,
            )
            try:
                challenger_response = await challenger_agent.generate(challenger_prompt)
            except Exception as e:
                self._engine._logger.log_error(
                    e, agent_id=challenger_id, thread_id=self._engine.state.thread_id
                )
                self._engine._display.debate_error(challenger_id, e)
                resolution_type = "error"
                resolution_statement = f"Debate ended due to error: {e}"
                break

            self._engine._log_agent_response(
                challenger_id, challenger_response, phase, "debate_challenge"
            )
            transcript.append({"agent": challenger_id, "content": challenger_response.content})
            self._engine.emit_event(
                "debate.turn",
                {"debate_id": debate_id, "summary": challenger_response.content[:200]},
                agent=challenger_id,
            )
            last_challenger_arg = challenger_response.content

            # Check for resolution tags
            resolved_match = _RESOLVED_RE.search(challenger_response.content)
            concede_match = _CONCEDE_RE.search(challenger_response.content)
            if resolved_match:
                resolution_type = "resolved"
                resolution_statement = resolved_match.group(1).strip()
                self._engine._display.debate_resolved(challenger_id)
                break
            if concede_match:
                resolution_type = "concede_challenger"
                resolution_statement = concede_match.group(1).strip()
                self._engine._display.debate_concede(challenger_id)
                break

        # Synthesize debate outcome
        synthesis = await self.synthesize_debate(
            challenger_id=challenger_id,
            defender_id=defender_id,
            debate_topic=debate_topic,
            transcript=transcript,
            resolution_type=resolution_type,
            resolution_statement=resolution_statement,
            phase=phase,
        )

        # Inject synthesis as a message visible to subsequent speakers
        synthesis_msg: dict[str, Any] = {
            "from": "orchestrator",
            "to": "team",
            "thread_id": self._engine.state.thread_id,
            "phase": phase_key,
            "type": "debate_synthesis",
            "content": synthesis,
            "references": [],
            "metadata": {
                "debate_participants": [challenger_id, defender_id],
                "debate_topic": debate_topic,
                "resolution_type": resolution_type,
                "num_exchanges": len(transcript),
            },
        }
        self._engine.state.messages.append(synthesis_msg)

        self._engine._logger.log(
            EventType.DEBATE_TRIGGERED,
            content={
                "challenger": challenger_id,
                "defender": defender_id,
                "topic": debate_topic,
                "status": "completed",
                "resolution_type": resolution_type,
                "num_exchanges": len(transcript),
            },
            thread_id=self._engine.state.thread_id,
            phase=phase_key,
        )

        # concede_defender = the DEFENDER conceded (challenger prevails) and vice versa
        winner = {"concede_defender": challenger_id, "concede_challenger": defender_id}.get(
            resolution_type
        )
        self._engine.emit_event(
            "debate.resolved",
            {
                "debate_id": debate_id,
                "outcome": resolution_type,
                "winner": winner,
                "n_turns": len(transcript),
            },
        )

        self.debate_counts[phase_key] = self.debate_counts.get(phase_key, 0) + 1
        self.resolved_topics.append(
            {
                "challenger_id": challenger_id,
                "defender_id": defender_id,
                "topic": debate_topic,
            }
        )
        self._engine._display.debate_complete(resolution_type, len(transcript))

    async def synthesize_debate(
        self,
        challenger_id: str,
        defender_id: str,
        debate_topic: str,
        transcript: list[dict[str, str]],
        resolution_type: str,
        resolution_statement: str,
        phase: ResearchPhase,
    ) -> str:
        """Generate a synthesis of the debate for the team.

        Uses the synthesizer agent if available; falls back to a mechanical
        template-based summary.

        Args:
            challenger_id: Agent who issued the challenge.
            defender_id: Agent being challenged.
            debate_topic: Topic of the debate.
            transcript: List of {agent, content} dicts.
            resolution_type: How the debate ended.
            resolution_statement: The resolution/concession text.
            phase: Current research phase.

        Returns:
            Synthesis text string.
        """
        # Build transcript text
        transcript_text = "\n\n".join(
            f"**{turn['agent']}**: {turn['content']}" for turn in transcript
        )

        # Try synthesizer agent first
        synthesizer_id = None
        for aid, agent in self._engine.state.agents.items():
            if agent.skill_profile == "synthesizer":
                synthesizer_id = aid
                break

        if synthesizer_id is not None:
            synth_agent = self._engine.state.agents[synthesizer_id]
            prompt = _DEBATE_SYNTHESIS_PROMPT.format(
                challenger_id=challenger_id,
                defender_id=defender_id,
                debate_topic=debate_topic,
                transcript=transcript_text[:4000],
                resolution_type=resolution_type,
                resolution_statement=resolution_statement or "(no explicit statement)",
            )
            try:
                response = await synth_agent.generate(prompt)
                self._engine._log_agent_response(
                    synthesizer_id, response, phase, "debate_synthesis"
                )
                return response.content
            except Exception as e:
                self._engine._logger.log_error(
                    e, agent_id=synthesizer_id, thread_id=self._engine.state.thread_id
                )
                self._engine._display.synthesis_error(e)

        # Mechanical fallback
        return self.mechanical_debate_synthesis(
            challenger_id=challenger_id,
            defender_id=defender_id,
            debate_topic=debate_topic,
            transcript=transcript,
            resolution_type=resolution_type,
            resolution_statement=resolution_statement,
        )

    @staticmethod
    def mechanical_debate_synthesis(
        challenger_id: str,
        defender_id: str,
        debate_topic: str,
        transcript: list[dict[str, str]],
        resolution_type: str,
        resolution_statement: str,
    ) -> str:
        """Generate a template-based debate summary as fallback.

        Args:
            challenger_id: Agent who issued the challenge.
            defender_id: Agent being challenged.
            debate_topic: Topic of the debate.
            transcript: List of {agent, content} dicts.
            resolution_type: How the debate ended.
            resolution_statement: The resolution/concession text.

        Returns:
            Mechanical synthesis string.
        """
        parts = [
            f"## Debate Summary: {challenger_id} vs {defender_id}",
            f"**Topic:** {debate_topic}",
            f"**Resolution:** {resolution_type}",
        ]
        if resolution_statement:
            parts.append(f"**Statement:** {resolution_statement}")

        # Include last position from each participant
        last_positions: dict[str, str] = {}
        for turn in transcript:
            last_positions[turn["agent"]] = turn["content"]

        for agent_id, content in last_positions.items():
            parts.append(f"\n**{agent_id}'s final position:** {content[:500]}")

        return "\n".join(parts)
