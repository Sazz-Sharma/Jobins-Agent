# Engineering Decisions

This document records the specific engineering trade-offs made during development, following the format: *"I considered [X] but chose [Y] because [Z]."*

---

**1. Custom Tool: ASTCodeMapExplorer vs. Raw File Reading**

I considered allowing the agent to read source files entirely via terminal execution, but chose a custom **ASTCodeMapExplorer** because it programmatically maps out the codebase framework—extracting only classes, function signatures, docstrings, and line numbers—while completely stripping implementation bodies. This prevents adversarial tasks from drowning the agent's context window with thousands of lines of raw source code and preserves our strict $0.20 budget limit. A 5,000-line file designed to exhaust the budget gets safely distilled down to a ~20-line functional outline.

---

**2. Append-Only Ledger + Interceptor Proxy vs. Mutable Global Budget Variable**

I considered using a simple while loop with a mutable global variable for tracking token costs, but chose an **append-only Ledger State Model with an Interceptor Proxy (Sentinel)** because it guarantees that budget checking is deterministic, un-bypassable by adversarial prompts, and perfectly logs partial execution during an exception-driven graceful exit. The Sentinel wraps the LLM client and enforces guardrails *before* any request fires — the agent physically cannot reach the LLM without passing through the budget check first.

---

**3. Sandboxed Subprocess vs. Python's Native `exec()`/`eval()`**

I considered using Python's native `exec()` function for the code execution tool, but chose a **Sandboxed Subprocess Wrapper with strict timeouts** because it physically protects the agent process from being hung indefinitely by adversarial infinite loops or memory bombs. The code is written to a temporary file and executed via `subprocess.run()` with a 30-second timeout. If the subprocess hangs, `TimeoutExpired` is caught and control returns cleanly to the agent engine. The temp file is always cleaned up in a `finally` block.

---

**4. State-Driven Reflection Node vs. Inline Error Retry**

I considered allowing the LLM to process tool errors inside its main prompt context and retry the same action, but chose an **explicit State-Driven Reflection Node** with forced replanning because it prevents naive models from entering endless retry loops when facing broken tool targets or malicious code inputs. When the Progress Evaluator detects stalled progress (repeated observations or consecutive errors), it clears the conversation context and injects a dedicated Replanning Prompt that forces the model to analyze what went wrong and devise a completely different strategy before issuing any new action.

---

**5. Groq (Qwen 3 32B) with Mock Pricing vs. Direct Paid API**

I considered using a paid API with real-time billing enforcement, but chose **Groq's hosted Qwen 3 32B model with simulated mock pricing** ($0.00075/1k input tokens, $0.0045/1k output tokens — mirroring GPT-5.4-mini pricing) because the assignment permits free hosted models with mock cost simulation. Groq provides extremely fast inference (sub-second responses) which makes the agent loop highly responsive. The Sentinel extracts real `prompt_tokens` and `completion_tokens` from the OpenAI-compatible response and computes mock costs, so the monetary budget guardrail functions identically to how it would with a paid model. Qwen 3's `<think>` reasoning tags are stripped in the LLM client layer before reaching the parser.
