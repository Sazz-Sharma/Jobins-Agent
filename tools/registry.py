"""
Tool Registry — Centralized tool management with timeout wrappers.

Every tool execution is wrapped in a ThreadPoolExecutor with a forced timeout.
No bare `except: pass` blocks. All errors are captured and returned as
structured error text to the agent.
"""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass, field
from typing import Any, Callable


DEFAULT_TOOL_TIMEOUT = 30  # seconds


@dataclass
class ToolSpec:
    """Specification for a registered tool."""
    name: str
    description: str
    executor: Any  # object with .run(input: str) -> str
    timeout: int = DEFAULT_TOOL_TIMEOUT


class ToolRegistry:
    """
    Registry for agent tools with enforced timeout wrappers.

    Tools are treated as isolated, untrusted execution contexts.
    Each tool call is wrapped in a ThreadPoolExecutor with a hard timeout
    to prevent adversarial hangs.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, tool: Any, timeout: int = DEFAULT_TOOL_TIMEOUT) -> None:
        """
        Register a tool object. The tool must have:
          - .name: str
          - .description: str
          - .run(input: str) -> str
        """
        if not hasattr(tool, "name") or not hasattr(tool, "run"):
            raise ValueError(
                f"Tool must have 'name' and 'run' attributes. Got: {type(tool)}"
            )

        spec = ToolSpec(
            name=tool.name,
            description=tool.description,
            executor=tool,
            timeout=timeout,
        )
        self._tools[tool.name] = spec

    def execute(self, tool_name: str, tool_input: str) -> str:
        """
        Execute a tool by name with timeout wrapping.

        Returns the tool output string, or an error message if:
          - Tool not found
          - Tool timed out
          - Tool raised an exception
        """
        if tool_name not in self._tools:
            available = ", ".join(self._tools.keys())
            return (
                f"ERROR: Unknown tool '{tool_name}'. "
                f"Available tools: {available}"
            )

        spec = self._tools[tool_name]

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(spec.executor.run, tool_input)
                result = future.result(timeout=spec.timeout)
                return str(result)

        except concurrent.futures.TimeoutError:
            return (
                f"ERROR: Tool '{tool_name}' timed out after {spec.timeout} seconds. "
                "Consider using a different approach."
            )
        except Exception as e:
            # Never bare except:pass — always capture and return the error
            return f"ERROR: Tool '{tool_name}' failed: {type(e).__name__}: {e}"

    def get_tool_descriptions(self) -> str:
        """
        Return formatted tool descriptions for injection into the system prompt.
        """
        if not self._tools:
            return "(No tools available)"

        lines = []
        for spec in self._tools.values():
            lines.append(f"- **{spec.name}**: {spec.description}")
        return "\n".join(lines)

    def list_tools(self) -> list[str]:
        """Return names of all registered tools."""
        return list(self._tools.keys())

    def has_tool(self, name: str) -> bool:
        return name in self._tools
