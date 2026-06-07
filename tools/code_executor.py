"""
CodeExecutionTool — Sandboxed Python code execution via subprocess.

Runs user-provided Python code in a completely isolated subprocess with:
  - Strict timeout (default 30 seconds)
  - Stdout/stderr capture
  - Temp file cleanup
  - Output truncation to prevent context flooding

NEVER uses exec() or eval() in the main process.
"""

from __future__ import annotations

import os
import subprocess
import tempfile

MAX_OUTPUT_CHARS = 2000
DEFAULT_TIMEOUT = 30


class CodeExecutionTool:
    """
    Execute Python code safely in an isolated subprocess.

    The code is written to a temporary file, executed via subprocess.run()
    with a strict timeout, and stdout/stderr are captured and returned.
    """

    name = "code_execution"
    description = (
        "Execute Python code in a sandboxed subprocess. "
        "Input: a string of valid Python code. "
        "Output: the stdout and stderr from running the code. "
        "The code runs with a 30-second timeout. Use this for calculations, "
        "data processing, or any computational task."
    )

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout

    def run(self, code: str) -> str:
        """Execute the provided Python code in a sandboxed subprocess."""
        code = code.strip()
        if not code:
            return "ERROR: No code provided to execute."

        # Strip markdown code fences if the LLM wraps them
        if code.startswith("```python"):
            code = code[len("```python"):].strip()
        if code.startswith("```"):
            code = code[3:].strip()
        if code.endswith("```"):
            code = code[:-3].strip()

        # LLMs often send literal \n instead of actual newlines
        # Detect: if code has literal \n but no real newlines, convert them
        if "\\n" in code and "\n" not in code:
            code = code.replace("\\n", "\n")
        # Also handle \\t for indented code
        if "\\t" in code:
            code = code.replace("\\t", "\t")

        tmp_path = None
        try:
            # Write code to temp file
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                prefix="agent_exec_",
                delete=False,
                encoding="utf-8",
            ) as tmp:
                tmp.write(code)
                tmp_path = tmp.name

            # Execute in isolated subprocess
            result = subprocess.run(
                ["python3", tmp_path],
                capture_output=True,
                text=True,
                timeout=self._timeout,
                cwd=tempfile.gettempdir(),
            )

            output_parts = []
            if result.stdout:
                stdout = result.stdout[:MAX_OUTPUT_CHARS]
                if len(result.stdout) > MAX_OUTPUT_CHARS:
                    stdout += f"\n... [output truncated, {len(result.stdout)} total chars]"
                output_parts.append(f"STDOUT:\n{stdout}")

            if result.stderr:
                stderr = result.stderr[:MAX_OUTPUT_CHARS]
                if len(result.stderr) > MAX_OUTPUT_CHARS:
                    stderr += f"\n... [stderr truncated, {len(result.stderr)} total chars]"
                output_parts.append(f"STDERR:\n{stderr}")

            if not output_parts:
                output_parts.append("(Code executed successfully with no output)")

            if result.returncode != 0:
                output_parts.insert(0, f"Exit Code: {result.returncode}")

            return "\n".join(output_parts)

        except subprocess.TimeoutExpired:
            return (
                f"ERROR: Code execution timed out after {self._timeout} seconds. "
                "The code may contain an infinite loop or long-running operation."
            )
        except FileNotFoundError:
            return "ERROR: Python3 interpreter not found in the system."
        except OSError as e:
            return f"ERROR: Failed to execute code: {e}"
        finally:
            # Always clean up temp file
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
