import sys
from agent.ledger import Ledger
from agent.llm_client import LLMClient
from agent.sentinel import Sentinel
from agent.orchestrator import Orchestrator
from tools.registry import ToolRegistry

class FakeLLM:
    def __init__(self):
        self.count = 0
        self.model_name = "fake-model"
    def chat(self, messages):
        self.count += 1
        # It will endlessly try the exact same action to force a stall
        content = "Thought: I am stuck in a loop.\nAction: test_tool\nAction Input: trigger"
        # On the 4th tick, it will see the replanning prompt and reply with something else
        if self.count >= 4:
           content = "Thought: I am replanning.\nFinal Answer: Done!"
        
        return {"content": content, "input_tokens": 10, "output_tokens": 10, "cost": 0.0}

class FakeTool:
    name = "test_tool"
    description = "A fake tool."
    def run(self, input_str):
        return "ERROR: Something went wrong."

ledger = Ledger()
llm = FakeLLM()
sentinel = Sentinel(llm, ledger)
registry = ToolRegistry()
registry.register(FakeTool())

orchestrator = Orchestrator(llm, ledger, sentinel, registry, max_calls=10, max_budget=1.0, verbose=True)
orchestrator.run("Test replanning")
