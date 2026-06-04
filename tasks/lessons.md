# Lessons

Patterns to avoid repeating. Updated as mistakes/corrections surface.

## Subagents inherit CLAUDE.md and will auto-log to HISTORY.md
- **What happened (2026-06-03, Prompt 68):** A research subagent spawned via the Agent tool inherited the project's CLAUDE.md "MANDATORY: append every prompt to HISTORY.md" rule and the Edit tool, so it appended a spurious "Prompt 69" entry derived from my *internal* research-dispatch instruction (not a human prompt). Had to remove it.
- **Why it matters:** HISTORY.md must only record real human prompts. Subagent dispatches are part of executing the current human prompt, not new prompts.
- **How to apply:** When dispatching subagents in this repo, either (a) explicitly instruct them "do NOT modify HISTORY.md or any repo files; return your findings as text only," or (b) audit HISTORY.md after a multi-subagent run and remove any entries they added. Read-only research subagents (Explore) avoid the problem entirely since they lack Edit/Write.
