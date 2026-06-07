# Engineering Decisions

This document records the core architectural and engineering trade-offs made during the development of this agent. Rather than framing every choice as a simple binary "A vs. B", these entries reflect how multiple competing approaches were evaluated to solve complex operational constraints, ultimately leading to the single most effective solution.

---

**1. Context Compression & Codebase Navigation**

When figuring out how the agent should read local files, I considered several approaches. I thought about building a full RAG (Retrieval-Augmented Generation) pipeline with vector embeddings to search code, or maybe an HTML link tree parser to scrape documentation. I also considered just letting the agent read raw `.py` files dumped straight into the prompt. Ultimately, I went with an **AST (Abstract Syntax Tree) code explorer**. Setting up RAG for a local sandbox is overkill, and raw file reads risk blowing up the token budget instantly. The AST explorer hits the perfect sweet spot: it allows the agent to navigate massive, 5,000-line Python files securely by distilling them down to their structural bones (classes, functions, docs) without risking prompt size exhaustion—plus it's incredibly fun to build.

---

**2. State Management & Budget Tracking**

To track the budget constraint and LLM calls, I looked at a few options. I could have spun up a quick SQLite database, or kept a running, mutable JSON payload in memory that updates as the agent navigates. Mutating state across deep ReAct loops makes debugging a total nightmare later on, and spinning up an external database adds unnecessary heavy dependencies. Emulating an **append-only transaction 'Ledger'**—similar to an event sourcing model—ended up being the most robust choice. It guarantees we have a perfect, chronological historical trace that we can dump out clearly during those "Graceful Exit" limit hits, ensuring we catch exactly when a specific fraction of a cent breaches the $0.20 limit organically without losing or overwriting tracking data.

---

**3. Implementing Guardrails & Security**

It is standard practice to just throw an `if total_calls >= 10: break` check at the very top or bottom of the main orchestration loop. I also considered implementing post-action cost calculations where the agent checks its wallet *after* spending. However, wrapping the LLM directly behind a **"Sentinel" proxy interceptor** felt significantly more bulletproof than all of those. By placing the budget guardrail directly over the network interface layer, it is physically impossible for the orchestrator to accidentally squeeze out an 11th call, no matter how weird the internal Python execution gets, if a sub-loop spawns unexpectedly, or what exceptions are thrown elsewhere.

---

**4. Breaking Infinite ReAct Loops**

When an agent hits a wall or executes bad syntax, the default approach is usually to zero-shot retry or just dump the raw `stderr` traceback back into the prompt hoping it self-corrects. While that works occasionally, naive models will predictably get stuck repeating the exact same bad string indefinitely. Instead of hoping for self-correction or simply killing the process entirely on an error, I built an **active stall detector and replanner**. If it notices consecutive repeated actions or repetitive failures, it actively intercepts the flow, wipes the immediate local tool context, and injects a hard 'replanning' prompt to completely force the agent to devise a fresh strategy from scratch.

---

**5. LLM Provider & Cost Modeling**

For the brain of the agent, I evaluated several APIs. I was incredibly tempted to just use OpenRouter to tap into premium, ultra-reliable models like GPT-4o or Claude 3.5 Sonnet, mostly because they never fail strict ReAct formatting requirements and require zero hand-holding. However, sticking exclusively to **Groq with the open-source Qwen 3 32B model** (using mock pricing to simulate cost) felt like a much better engineering challenge. It forced me to actually build a robust parser that manually strips `<think>` tokens and natively handles format degradation when the model gets confused under pressure. It proves the architecture's guardrails and string manipulators hold up beautifully even if the LLM behaves unexpectedly, which makes the entire project inherently more resilient.
