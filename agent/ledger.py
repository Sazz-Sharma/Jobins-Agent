"""
Ledger — Append-only transactional state database.

Stores a complete chronological history of every action, thought, observation,
and cost that flows through the agent. Once appended, entries are immutable.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EntryType(str, Enum):
    """Classification of ledger entries."""
    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"
    ERROR = "error"
    BUDGET = "budget"
    REFLECTION = "reflection"
    REPLAN = "replan"
    FINAL_ANSWER = "final_answer"
    SYSTEM = "system"


class LedgerEntry(BaseModel):
    """A single immutable entry in the ledger."""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    entry_type: EntryType
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    token_cost_usd: float = 0.0
    cumulative_cost_usd: float = 0.0
    cumulative_calls: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class Ledger:
    """
    Append-only state vault.

    Every interaction is recorded here. The Sentinel reads from this to enforce
    budget limits. The Orchestrator reads from this to detect repeated actions
    and stalled progress.
    """

    def __init__(self) -> None:
        self._entries: list[LedgerEntry] = []
        self._total_cost_usd: float = 0.0
        self._total_calls: int = 0
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0

    # ── Mutations (append-only) ──────────────────────────────────────────

    def append(
        self,
        entry_type: EntryType,
        content: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        token_cost_usd: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> LedgerEntry:
        """Record a new entry. Returns the created entry."""
        if entry_type in (EntryType.THOUGHT, EntryType.ACTION, EntryType.REFLECTION, EntryType.REPLAN):
            if input_tokens > 0 or output_tokens > 0:
                self._total_calls += 1

        self._total_cost_usd += token_cost_usd
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens

        entry = LedgerEntry(
            entry_type=entry_type,
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            token_cost_usd=token_cost_usd,
            cumulative_cost_usd=self._total_cost_usd,
            cumulative_calls=self._total_calls,
            metadata=metadata or {},
        )
        self._entries.append(entry)
        return entry

    def record_llm_call(
        self,
        content: str,
        input_tokens: int,
        output_tokens: int,
        token_cost_usd: float,
    ) -> LedgerEntry:
        """Convenience: record an LLM call and bump the call counter."""
        self._total_calls += 1
        self._total_cost_usd += token_cost_usd
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens

        entry = LedgerEntry(
            entry_type=EntryType.THOUGHT,
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            token_cost_usd=token_cost_usd,
            cumulative_cost_usd=self._total_cost_usd,
            cumulative_calls=self._total_calls,
        )
        self._entries.append(entry)
        return entry

    # ── Queries ──────────────────────────────────────────────────────────

    @property
    def total_cost_usd(self) -> float:
        return self._total_cost_usd

    @property
    def total_calls(self) -> int:
        return self._total_calls

    @property
    def total_input_tokens(self) -> int:
        return self._total_input_tokens

    @property
    def total_output_tokens(self) -> int:
        return self._total_output_tokens

    @property
    def entries(self) -> list[LedgerEntry]:
        return list(self._entries)  # defensive copy

    def get_last_n(self, n: int) -> list[LedgerEntry]:
        """Return the last N entries."""
        return list(self._entries[-n:])

    def get_actions(self) -> list[LedgerEntry]:
        """Return all ACTION entries (used for deduplication)."""
        return [e for e in self._entries if e.entry_type == EntryType.ACTION]

    def get_observations(self) -> list[LedgerEntry]:
        """Return all OBSERVATION entries (used for progress evaluation)."""
        return [e for e in self._entries if e.entry_type == EntryType.OBSERVATION]

    def has_duplicate_action(self, action_content: str) -> bool:
        """Check if the exact same action+input was already executed."""
        return any(e.content == action_content for e in self.get_actions())

    # ── Serialization ────────────────────────────────────────────────────

    def serialize(self) -> dict[str, Any]:
        """Dump full ledger state for graceful exit reporting."""
        return {
            "summary": {
                "total_llm_calls": self._total_calls,
                "total_cost_usd": round(self._total_cost_usd, 6),
                "total_input_tokens": self._total_input_tokens,
                "total_output_tokens": self._total_output_tokens,
                "total_entries": len(self._entries),
            },
            "entries": [e.model_dump() for e in self._entries],
        }

    def serialize_json(self, indent: int = 2) -> str:
        """JSON string representation of the full ledger."""
        return json.dumps(self.serialize(), indent=indent, default=str)

    def print_summary(self) -> str:
        """Human-readable cost summary."""
        return (
            f"╔══════════════════════════════════════╗\n"
            f"║        LEDGER EXECUTION SUMMARY      ║\n"
            f"╠══════════════════════════════════════╣\n"
            f"║  LLM Calls:      {self._total_calls:>6}              ║\n"
            f"║  Input Tokens:   {self._total_input_tokens:>6}              ║\n"
            f"║  Output Tokens:  {self._total_output_tokens:>6}              ║\n"
            f"║  Total Cost:   ${self._total_cost_usd:>8.6f}           ║\n"
            f"╚══════════════════════════════════════╝"
        )
