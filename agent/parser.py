"""
Parser — Parse LLM output into structured Thought / Action / Observation components.

Handles both standard ReAct responses and Final Answer detection.
Gracefully handles malformed outputs (including duplicate responses from
models like nemotron) instead of crashing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedResponse:
    """Structured representation of an LLM ReAct response."""
    thought: str = ""
    action: Optional[str] = None
    action_input: Optional[str] = None
    final_answer: Optional[str] = None
    is_final: bool = False
    raw: str = ""
    parse_error: Optional[str] = None


def _deduplicate_response(text: str) -> str:
    """
    Some models (e.g. nemotron) duplicate their entire response.
    Detect and strip the duplicate half.

    Strategy: If the text contains 'Thought:' more than once, take only
    the content up to the second 'Thought:'.
    """
    # Find all occurrences of "Thought:" (case-insensitive)
    thought_positions = [m.start() for m in re.finditer(r"Thought\s*:", text, re.IGNORECASE)]

    if len(thought_positions) >= 2:
        # Take only the first complete block
        text = text[:thought_positions[1]].strip()

    return text


def parse_react_response(text: str) -> ParsedResponse:
    """
    Parse LLM text output into structured components.

    Expected formats:
        Thought: ...
        Action: tool_name
        Action Input: ...

    OR:
        Thought: ...
        Final Answer: ...

    Returns a ParsedResponse with parse_error set if the output is malformed.
    """
    result = ParsedResponse(raw=text)

    if not text or not text.strip():
        result.parse_error = "Empty response from LLM."
        return result

    # Deduplicate responses from models that repeat themselves
    text = _deduplicate_response(text)

    # ── Check for Final Answer ───────────────────────────────────────
    final_match = re.search(
        r"Final\s*Answer\s*:\s*(.+)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if final_match:
        # Extract thought if present before Final Answer
        thought_match = re.search(
            r"Thought\s*:\s*(.+?)(?=Final\s*Answer\s*:)",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        if thought_match:
            result.thought = thought_match.group(1).strip()

        result.final_answer = final_match.group(1).strip()
        result.is_final = True
        return result

    # ── Extract Thought ──────────────────────────────────────────────
    thought_match = re.search(
        r"Thought\s*:\s*(.+?)(?=Action\s*:|$)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if thought_match:
        result.thought = thought_match.group(1).strip()

    # ── Extract Action (take only the first line — tool name) ────────
    action_match = re.search(
        r"Action\s*:\s*(\S+)",
        text,
        re.IGNORECASE,
    )
    if action_match:
        result.action = action_match.group(1).strip()

    # ── Extract Action Input ─────────────────────────────────────────
    input_match = re.search(
        r"Action\s*Input\s*:\s*(.+)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if input_match:
        action_input = input_match.group(1).strip()
        # Clean: if the action input ends with another "Thought:" block, strip it
        thought_cutoff = re.search(r"Thought\s*:", action_input, re.IGNORECASE)
        if thought_cutoff:
            action_input = action_input[:thought_cutoff.start()].strip()
        result.action_input = action_input

    # ── Validate ─────────────────────────────────────────────────────
    if not result.action:
        result.parse_error = (
            "Could not parse a valid Action from the LLM response. "
            "Expected format: 'Action: <tool_name>'"
        )
    elif not result.action_input:
        result.parse_error = (
            "Could not parse Action Input from the LLM response. "
            "Expected format: 'Action Input: <input>'"
        )

    return result
