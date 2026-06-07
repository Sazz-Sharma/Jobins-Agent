"""
Orchestrator — The ReAct Engine with Reflection Pipeline.

Coordinates the agent's execution loop following the 4-phase tick:
  1. Budget Check → query Sentinel
  2. ReAct Tick → LLM call via Sentinel → parse Thought → Action
  3. Execution Gate → dispatch tool via Registry within timeout wrapper
  4. Progress Evaluator → detect stalls → inject Replanning prompt

Handles BudgetExceededException gracefully: serializes Ledger, prints
partial results, and exits cleanly.
"""

from __future__ import annotations

import sys

from agent.ledger import EntryType, Ledger
from agent.llm_client import LLMClient
from agent.parser import parse_react_response
from agent.prompts import build_react_prompt, build_replan_prompt
from agent.sentinel import BudgetExceededException, Sentinel
from tools.registry import ToolRegistry


# Maximum consecutive stalls before forcing a replan
MAX_STALLS = 2


class Orchestrator:
    """
    The ReAct engine with reflection and replanning.

    Manages the full agent lifecycle:
      - Builds conversation history for multi-turn ReAct
      - Detects duplicate actions and stalled progress
      - Injects replanning prompts when stuck
      - Enforces budget through the Sentinel proxy
      - Produces graceful exit reports on budget exhaustion
    """

    def __init__(
        self,
        llm_client: LLMClient,
        ledger: Ledger,
        sentinel: Sentinel,
        tool_registry: ToolRegistry,
        max_calls: int = 10,
        max_budget: float = 0.20,
        verbose: bool = True,
    ) -> None:
        self._llm = llm_client
        self._ledger = ledger
        self._sentinel = sentinel
        self._tools = tool_registry
        self._max_calls = max_calls
        self._max_budget = max_budget
        self._verbose = verbose

        # Conversation history for multi-turn context
        self._messages: list[dict] = []
        # Track stall count for replanning
        self._stall_count = 0
        self._last_observation: str | None = None

    # ── Public API ───────────────────────────────────────────────────────

    def run(self, task: str) -> str:
        """
        Execute the full agent loop for a given task.

        Returns the agent's final answer, or a partial completion report
        if the budget is exhausted.
        """
        self._log(f"\n{'='*60}")
        self._log(f"  TASK: {task}")
        self._log(f"  Budget: {self._max_calls} calls / ${self._max_budget:.2f}")
        self._log(f"  Model: {self._llm.model_name}")
        self._log(f"{'='*60}\n")

        # Record task start in ledger
        self._ledger.append(EntryType.SYSTEM, f"Task started: {task}")

        try:
            return self._execute_loop(task)
        except BudgetExceededException as e:
            return self._handle_budget_exceeded(e)

    # ── Core Loop ────────────────────────────────────────────────────────

    def _execute_loop(self, task: str) -> str:
        """Main ReAct loop with reflection pipeline."""

        tick = 0
        while True:
            tick += 1

            # ── Phase 1: Budget Check ────────────────────────────────
            self._log(f"\n{'─'*60}")
            self._log(f"  📍 TICK {tick} | {self._sentinel.budget_status}")
            self._log(f"{'─'*60}")

            # ── Phase 2: ReAct Tick (LLM call via Sentinel) ──────────
            system_prompt = build_react_prompt(
                max_calls=self._max_calls,
                used_calls=self._ledger.total_calls,
                max_budget=self._max_budget,
                used_budget=self._ledger.total_cost_usd,
                tool_descriptions=self._tools.get_tool_descriptions(),
            )

            # Build messages for this turn
            messages = [{"role": "system", "content": system_prompt}]

            # Add the task as the first user message if conversation is fresh
            if not self._messages:
                self._messages.append({"role": "user", "content": f"Task: {task}"})

            messages.extend(self._messages)

            # Call LLM through Sentinel (enforces budget)
            response = self._sentinel.chat(messages)
            llm_text = response["content"]

            # ── Parse the response ───────────────────────────────────
            parsed = parse_react_response(llm_text)

            # ── Display Thought ──────────────────────────────────────
            if parsed.thought:
                self._log(f"\n  💭 THOUGHT: {parsed.thought}")
                self._ledger.append(EntryType.THOUGHT, parsed.thought)

            # ── Handle parse errors ──────────────────────────────────
            if parsed.parse_error:
                self._log(f"\n  ⚠️  PARSE ERROR: {parsed.parse_error}")
                self._ledger.append(EntryType.ERROR, parsed.parse_error)
                # Feed the error back as an observation
                self._messages.append({"role": "assistant", "content": llm_text})
                self._messages.append({
                    "role": "user",
                    "content": f"Observation: {parsed.parse_error}\n\n"
                    "Please respond in the correct format:\n"
                    "Thought: ...\nAction: <tool_name>\nAction Input: <input>\n\n"
                    "OR:\nThought: ...\nFinal Answer: <answer>",
                })
                continue

            # ── If Action present, execute tool FIRST ────────────────
            # (even if Final Answer is also present — tool must run first)
            if parsed.action and parsed.action_input is not None:
                action = parsed.action
                action_input = parsed.action_input
                action_key = f"{action}:{action_input}"

                # ── Deduplication check ──────────────────────────────
                if self._ledger.has_duplicate_action(action_key):
                    self._log(f"\n  🔁 DUPLICATE ACTION BLOCKED: {action}")
                    self._log(f"     Input: {action_input[:100]}")
                    self._ledger.append(
                        EntryType.ERROR,
                        f"Duplicate action blocked: {action_key}",
                    )
                    self._messages.append({"role": "assistant", "content": llm_text})
                    self._messages.append({
                        "role": "user",
                        "content": (
                            "Observation: ERROR — You already tried this exact action. "
                            "You MUST try a DIFFERENT approach. Do NOT repeat the same action."
                        ),
                    })
                    self._stall_count += 1

                    # Check if we need to force replan
                    if self._stall_count >= MAX_STALLS:
                        self._inject_replan(task)
                    continue

                # Record the action
                self._ledger.append(EntryType.ACTION, action_key)

                # ── Phase 3: Tool Execution ──────────────────────────
                self._log(f"\n  🔧 TOOL CALL: {action}")
                self._log(f"     Input: {action_input[:200]}")
                observation = self._tools.execute(action, action_input)
                self._log(f"\n  📋 TOOL OUTPUT:")
                for line in observation.split("\n"):
                    self._log(f"     {line}")

                # Record observation
                self._ledger.append(EntryType.OBSERVATION, observation)

                # ── Phase 4: Reflection — Progress Evaluation ────────
                self._log(f"\n  🔍 REFLECTION:")
                if self._is_stalled(observation):
                    self._stall_count += 1
                    self._log(f"     ⚠️  Progress STALLED ({self._stall_count}/{MAX_STALLS})")
                    self._log(f"     Reason: {'Same observation as last tick' if observation.strip() == (self._last_observation or '').strip() else 'Consecutive errors detected'}")

                    if self._stall_count >= MAX_STALLS:
                        self._inject_replan(task)
                    else:
                        self._log(f"     → Will allow one more attempt before replanning")
                else:
                    self._stall_count = 0  # Reset on progress
                    self._log(f"     ✅ Making progress — stall counter reset")

                self._last_observation = observation

                # Append to conversation
                self._messages.append({"role": "assistant", "content": llm_text})
                self._messages.append({"role": "user", "content": f"Observation: {observation}"})
                continue

            # ── Check for Final Answer (only if no action) ───────────
            if parsed.is_final:
                self._ledger.append(EntryType.FINAL_ANSWER, parsed.final_answer or "")
                self._log(f"\n  🏁 FINAL ANSWER: {parsed.final_answer}")
                self._log(f"\n{self._ledger.print_summary()}")
                return parsed.final_answer or ""

            # ── Fallback: no action and no final answer ──────────────
            self._log(f"\n  ⚠️  Could not extract Action or Final Answer from response:")
            self._log(f"     Raw: {llm_text[:200]}...")
            self._messages.append({"role": "assistant", "content": llm_text})
            self._messages.append({
                "role": "user",
                "content": (
                    "Observation: Your response did not contain a valid Action or Final Answer. "
                    "You MUST respond in one of these formats:\n\n"
                    "Thought: ...\nAction: <tool_name>\nAction Input: <input>\n\n"
                    "OR:\nThought: ...\nFinal Answer: <answer>"
                ),
            })

    # ── Reflection & Replanning ──────────────────────────────────────────

    def _is_stalled(self, current_observation: str) -> bool:
        """Deterministic check: is the agent making progress?"""
        if self._last_observation is None:
            return False

        # Same observation as last time
        if current_observation.strip() == self._last_observation.strip():
            return True

        # Persistent errors
        if (
            current_observation.startswith("ERROR:")
            and self._last_observation.startswith("ERROR:")
        ):
            return True

        return False

    def _inject_replan(self, task: str) -> None:
        """Force a replanning frame when progress has stalled."""
        self._log(f"\n  {'='*56}")
        self._log(f"  🔄 REPLANNING TRIGGERED")
        self._log(f"  {'='*56}")
        self._log(f"     Reason: Progress stalled ({self._stall_count} consecutive stalls)")

        # Gather previous actions for the replan context
        actions = self._ledger.get_actions()
        action_summary = "\n".join(
            f"  - {a.content}" for a in actions[-5:]  # last 5 actions
        )

        self._log(f"     Previously tried actions:")
        for a in actions[-5:]:
            self._log(f"       • {a.content}")

        replan_prompt = build_replan_prompt(
            remaining_calls=self._sentinel.remaining_calls,
            remaining_budget=self._sentinel.remaining_budget,
            previous_actions=action_summary or "(none)",
        )

        self._ledger.append(EntryType.REPLAN, "Replanning triggered due to stalled progress")

        self._log(f"     Strategy: Clearing conversation context and injecting fresh strategy prompt")
        self._log(f"     Remaining budget: {self._sentinel.remaining_calls} calls, ${self._sentinel.remaining_budget:.6f}")

        # Reset conversation to break out of the loop — fresh context
        self._messages = [
            {"role": "user", "content": f"Task: {task}"},
            {
                "role": "user",
                "content": (
                    f"IMPORTANT: Your previous approach has stalled. "
                    f"You have tried these actions already:\n{action_summary}\n\n"
                    f"You MUST use a completely different strategy now. "
                    f"Remaining budget: {self._sentinel.remaining_calls} calls, "
                    f"${self._sentinel.remaining_budget:.6f}."
                ),
            },
        ]
        self._stall_count = 0
        self._log(f"     ✅ Replan complete — fresh context injected")
        self._log(f"  {'='*56}\n")

    # ── Graceful Exit ────────────────────────────────────────────────────

    def _handle_budget_exceeded(self, exc: BudgetExceededException) -> str:
        """Handle budget exhaustion with a graceful exit report."""
        self._log(f"\n🛑 {exc.reason}")
        self._log("\n--- GRACEFUL EXIT: Budget Exhausted ---")

        # Build partial completion report
        observations = self._ledger.get_observations()
        final_answers = [
            e for e in self._ledger.entries
            if e.entry_type == EntryType.FINAL_ANSWER
        ]

        report_lines = [
            "═══ BUDGET EXHAUSTED — PARTIAL COMPLETION REPORT ═══",
            "",
            f"Reason: {exc.reason}",
            "",
            self._ledger.print_summary(),
            "",
            "── What was accomplished ──",
        ]

        if observations:
            for i, obs in enumerate(observations, 1):
                report_lines.append(f"  {i}. {obs.content[:200]}")
        else:
            report_lines.append("  (No observations were collected)")

        if final_answers:
            report_lines.append("")
            report_lines.append(f"── Partial Answer ──")
            report_lines.append(f"  {final_answers[-1].content}")

        report = "\n".join(report_lines)
        self._log(f"\n{report}")
        return report

    # ── Logging ──────────────────────────────────────────────────────────

    def _log(self, message: str) -> None:
        """Print to stdout if verbose mode is on."""
        if self._verbose:
            print(message, flush=True)
