#!/usr/bin/env python3
"""
JoBins Agent — Resource-Constrained Agentic Planning Loop

Entry point for the agent. Wires up all components:
  Ledger → Sentinel → Tool Registry → Orchestrator

Usage:
  Interactive:   python main.py
  Single task:   python main.py --task "Your task here"
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv


def build_agent(verbose: bool = True):
    """Wire up all agent components and return the Orchestrator."""
    from agent.ledger import Ledger
    from agent.llm_client import LLMClient
    from agent.orchestrator import Orchestrator
    from agent.sentinel import Sentinel
    from tools.ast_explorer import ASTCodeMapExplorer
    from tools.code_executor import CodeExecutionTool
    from tools.registry import ToolRegistry
    from tools.web_search import WebSearchTool

    # ── Configuration ────────────────────────────────────────────────
    api_key = os.getenv("GROQ_API_KEY", "")
    model = os.getenv("GROQ_MODEL", "qwen/qwen3-32b")
    max_calls = int(os.getenv("MAX_LLM_CALLS", "10"))
    max_budget = float(os.getenv("MAX_BUDGET_USD", "0.20"))

    if not api_key:
        print("ERROR: GROQ_API_KEY is not set.", file=sys.stderr)
        print("Set it in your .env file or as an environment variable.", file=sys.stderr)
        sys.exit(1)

    # ── Initialize Components ────────────────────────────────────────
    llm_client = LLMClient(api_key=api_key, model=model)
    ledger = Ledger()
    sentinel = Sentinel(llm_client, ledger, max_calls=max_calls, max_budget_usd=max_budget)

    # ── Register Tools ───────────────────────────────────────────────
    tool_registry = ToolRegistry()
    tool_registry.register(WebSearchTool(timeout=5), timeout=10)
    tool_registry.register(CodeExecutionTool(timeout=30), timeout=35)
    tool_registry.register(ASTCodeMapExplorer(), timeout=10)

    # ── Build Orchestrator ───────────────────────────────────────────
    orchestrator = Orchestrator(
        llm_client=llm_client,
        ledger=ledger,
        sentinel=sentinel,
        tool_registry=tool_registry,
        max_calls=max_calls,
        max_budget=max_budget,
        verbose=verbose,
    )

    return orchestrator, ledger


def run_interactive():
    """Run the agent in interactive mode."""
    print("╔══════════════════════════════════════════════╗")
    print("║   JoBins Agent — Resource-Constrained AI    ║")
    print("║   Type 'quit' or 'exit' to stop             ║")
    print("╚══════════════════════════════════════════════╝")
    print()

    while True:
        try:
            task = input("📝 Enter task: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not task:
            continue
        if task.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        # Build fresh agent for each task (clean ledger)
        orchestrator, ledger = build_agent(verbose=True)

        result = orchestrator.run(task)
        print(f"\n{'='*60}")
        print(f"  RESULT: {result}")
        print(f"{'='*60}")
        print(f"\n{ledger.print_summary()}\n")


def run_single_task(task: str):
    """Run the agent on a single task and exit."""
    orchestrator, ledger = build_agent(verbose=True)
    result = orchestrator.run(task)

    print(f"\n{'='*60}")
    print(f"  RESULT: {result}")
    print(f"{'='*60}")
    print(f"\n{ledger.print_summary()}")

    # Also dump full ledger JSON to file for inspection
    with open("last_run_ledger.json", "w") as f:
        f.write(ledger.serialize_json())
    print(f"\n📄 Full ledger saved to: last_run_ledger.json")


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="JoBins Agent — Resource-Constrained Agentic Planning Loop"
    )
    parser.add_argument(
        "--task", "-t",
        type=str,
        default=None,
        help="Run the agent on a single task (non-interactive mode)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress verbose output",
    )

    args = parser.parse_args()

    if args.task:
        run_single_task(args.task)
    else:
        run_interactive()


if __name__ == "__main__":
    main()
