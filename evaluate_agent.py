import json
from agent.ledger import Ledger
from agent.llm_client import LLMClient
from agent.sentinel import Sentinel, BudgetExceededException
from agent.orchestrator import Orchestrator
from tools.registry import ToolRegistry
from tools.ast_explorer import ASTCodeMapExplorer
from tools.code_executor import CodeExecutionTool
from tools.web_search import WebSearchTool
import os
from dotenv import load_dotenv

load_dotenv()

# The 5 evaluation tasks
TASKS = [
    {
        "name": "Task 1: Mathematical Code Execution",
        "description": "Tests the sandboxed execution environment.",
        "prompt": "Use the python code execution tool to calculate exactly what 2 to the power of 128 is, and return the numerical result."
    },
    {
        "name": "Task 2: Web Search Retrieval",
        "description": "Tests the web search tool for external knowledge retrieval.",
        "prompt": "Search the web to find out the exact release date of Python 3.12."
    },
    {
        "name": "Task 3: AST File Distillation",
        "description": "Tests the AST tool's ability to protect the context window by summarizing large files.",
        "prompt": "Use the AST code map explorer to map out 'agent/ledger.py' and tell me the names of all the entry types in the EntryType enum."
    },
    {
        "name": "Task 4: Infinite Loop Timeout",
        "description": "Tests the code executor's timeout guardrail preventing agent hangs.",
        "prompt": "Write a python script that loops infinitely while sleeping for 0.1s, execute it, and tell me what the result was."
    },
    {
        "name": "Task 5: Hard Budget Exhaustion",
        "description": "Tests the Sentinel proxy guardrail enforcing the 10-call strict limit.",
        "prompt": "Use the web search tool 12 times in a row for different random numbers. Do not yield a final answer until you have searched 12 distinct times."
    }
]

with open("test_results.md", "w") as f:
    f.write("# JoBins Agent — Evaluation Results\n\n")
    f.write("This document summarizes the execution of 5 distinct evaluation tasks designed to test the agent's capabilities, tool integration, and hard resource guardrails.\n\n")

api_key = os.getenv("GROQ_API_KEY", "")
model = os.getenv("GROQ_MODEL", "qwen/qwen3-32b")

for idx, t in enumerate(TASKS, 1):
    print(f"Running {t['name']}...")
    
    # Initialize fresh components
    llm = LLMClient(api_key=api_key, model=model)
    ledger = Ledger()
    # Enforce strict assignment budget
    sentinel = Sentinel(llm, ledger, max_calls=10, max_budget_usd=0.20)
    registry = ToolRegistry()
    registry.register(WebSearchTool(timeout=5), timeout=10)
    registry.register(CodeExecutionTool(timeout=30), timeout=35)
    registry.register(ASTCodeMapExplorer(), timeout=10)
    
    # Suppress verbose output for the tests so it doesn't flood stdout
    orchestrator = Orchestrator(llm, ledger, sentinel, registry, max_calls=10, max_budget=0.20, verbose=True)
    
    result = orchestrator.run(t["prompt"])
    
    # Format the report
    report = f"## {t['name']}\n\n"
    report += f"**Description:** {t['description']}\n\n"
    report += f"**Prompt:** `{t['prompt']}`\n\n"
    report += f"**Result / Partial Output (if exited):**\n> {result.strip().replace(chr(10), chr(10)+'> ')}\n\n"
    report += f"### Ledger Execution Summary\n"
    report += f"- **LLM Calls Used:** {ledger.total_calls}/10\n"
    report += f"- **Input Tokens:** {ledger.total_input_tokens}\n"
    report += f"- **Output Tokens:** {ledger.total_output_tokens}\n"
    report += f"- **Total Cost:** ${ledger.total_cost_usd:.6f} / $0.200000\n\n"
    
    # Extract the tool actions taken
    actions = ledger.get_actions()
    if actions:
        report += "### Actions Taken\n"
        for i, a in enumerate(actions, 1):
            act_name = a.content.split(":")[0]
            report += f"{i}. Executed `{act_name}`\n"
    report += "\n---\n\n"
    
    with open("test_results.md", "a") as f:
        f.write(report)
        
print("Evaluation complete. Results written to test_results.md")

