"""
LLM Client — Groq provider via OpenAI-compatible SDK.

Uses the standard openai Python client pointed at Groq's endpoint.
Extracts real token counts from response.usage and computes mock costs
using simulated GPT-5.4-mini pricing:
  - $0.00075 per 1k input tokens
  - $0.0045  per 1k output tokens

Handles Qwen 3's <think>...</think> reasoning tags by stripping them
from the final content so the agent parser only sees clean output.
"""

from __future__ import annotations

import re

from openai import OpenAI


# ── Mock pricing (simulated GPT-5.4-mini reasoning model) ────────────────
INPUT_COST_PER_1K = 0.00075   # $0.00075 per 1k input tokens
OUTPUT_COST_PER_1K = 0.0045   # $0.0045  per 1k output tokens


def compute_mock_cost(input_tokens: int, output_tokens: int) -> float:
    """Compute mock USD cost from real token counts."""
    input_cost = (input_tokens / 1000.0) * INPUT_COST_PER_1K
    output_cost = (output_tokens / 1000.0) * OUTPUT_COST_PER_1K
    return round(input_cost + output_cost, 8)


def strip_think_tags(text: str) -> str:
    """
    Strip Qwen 3's <think>...</think> reasoning blocks from the response.
    The agent parser only needs the final output, not internal reasoning.
    """
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()


class LLMClient:
    """
    Groq LLM client using the OpenAI-compatible SDK.

    All responses are standardized to:
        {
            "content": str,
            "input_tokens": int,
            "output_tokens": int,
            "cost": float,  # mock USD cost
        }
    """

    def __init__(
        self,
        api_key: str,
        model: str = "qwen/qwen3-32b",
        base_url: str = "https://api.groq.com/openai/v1",
        timeout: int = 60,
    ) -> None:
        self._model = model
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

    def chat(self, messages: list[dict]) -> dict:
        """
        Send a chat completion request and return standardized response.

        Extracts real prompt_tokens and completion_tokens from response.usage
        and computes mock cost. Strips <think> tags from Qwen 3 output.
        """
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.6,
                max_tokens=2048,
            )

            content = response.choices[0].message.content or ""
            # Strip Qwen 3's <think> reasoning blocks
            content = strip_think_tags(content)

            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0
            cost = compute_mock_cost(input_tokens, output_tokens)

            return {
                "content": content,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": cost,
            }

        except Exception as e:
            error_msg = f"LLM API Error: {type(e).__name__}: {e}"
            return {
                "content": error_msg,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0,
            }

    @property
    def model_name(self) -> str:
        return self._model
