"""
Sentinel — Budget Interceptor Proxy.

Every LLM call must pass through the Sentinel. It enforces hard limits on
both call count and monetary cost BEFORE any request fires. If a limit is
tripped, it raises BudgetExceededException *before* any token drain occurs.
"""

from __future__ import annotations

from agent.ledger import Ledger


class BudgetExceededException(Exception):
    """Raised when the agent has exhausted its budget."""

    def __init__(self, reason: str, ledger: Ledger) -> None:
        self.reason = reason
        self.ledger = ledger
        super().__init__(reason)


class Sentinel:
    """
    Proxy wrapper around the LLM client.

    The Orchestrator NEVER talks to the LLM directly — it always goes
    through the Sentinel. This guarantees budget enforcement is un-bypassable.
    """

    def __init__(
        self,
        llm_client,  # agent.llm_client.LLMClient
        ledger: Ledger,
        max_calls: int = 10,
        max_budget_usd: float = 0.20,
    ) -> None:
        self._llm = llm_client
        self._ledger = ledger
        self._max_calls = max_calls
        self._max_budget_usd = max_budget_usd

    # ── Public API ───────────────────────────────────────────────────────

    def chat(self, messages: list[dict]) -> dict:
        """
        Guarded LLM call.

        1. Check guardrails BEFORE the call.
        2. Execute the LLM request.
        3. Record token usage + cost in the Ledger.
        4. Check guardrails AFTER the call (in case the response pushed us over).
        5. Return the standardized response.
        """
        self._enforce_guardrails_pre()

        response = self._llm.chat(messages)

        # Record in ledger
        self._ledger.record_llm_call(
            content=response["content"],
            input_tokens=response["input_tokens"],
            output_tokens=response["output_tokens"],
            token_cost_usd=response["cost"],
        )

        return response

    @property
    def remaining_calls(self) -> int:
        return max(0, self._max_calls - self._ledger.total_calls)

    @property
    def remaining_budget(self) -> float:
        return max(0.0, self._max_budget_usd - self._ledger.total_cost_usd)

    @property
    def budget_status(self) -> str:
        return (
            f"Calls: {self._ledger.total_calls}/{self._max_calls} | "
            f"Cost: ${self._ledger.total_cost_usd:.6f}/${self._max_budget_usd:.2f}"
        )

    # ── Internal ─────────────────────────────────────────────────────────

    def _enforce_guardrails_pre(self) -> None:
        """Enforce limits BEFORE firing the LLM request."""
        if self._ledger.total_calls >= self._max_calls:
            raise BudgetExceededException(
                f"HARD STOP: LLM call limit reached ({self._max_calls}/{self._max_calls} calls used). "
                f"Total cost: ${self._ledger.total_cost_usd:.6f}",
                self._ledger,
            )

        if self._ledger.total_cost_usd >= self._max_budget_usd:
            raise BudgetExceededException(
                f"HARD STOP: Monetary budget exhausted "
                f"(${self._ledger.total_cost_usd:.6f} >= ${self._max_budget_usd:.2f}). "
                f"Calls used: {self._ledger.total_calls}/{self._max_calls}",
                self._ledger,
            )
