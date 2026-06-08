"""
MediFind India — Drug Research Sub-Agent
Each sub-agent is responsible for researching ONE alternative medicine.
It uses the ReAct engine to find composition and price via tool calls.

Sub-agent creation is orchestrated by the Orchestrator:
  1. Orchestrator generates a custom prompt for this specific drug
  2. Sub-agent initialises with that prompt
  3. Sub-agent runs ReAct loop until it has composition + price data
  4. Sub-agent reports results back via SSE events

Design inspired by ReAct (Yao et al., 2022) and
"Toolformer: Language Models Can Teach Themselves to Use Tools" (Schick et al., 2023)
"""

from __future__ import annotations
from typing import Generator

from backend.agents.react_engine import ReActEngine
from backend.agents.prompts import SUB_AGENT_SYSTEM_PROMPT_TEMPLATE
from config.settings import settings


class DrugResearchSubAgent:
    """
    A single drug research sub-agent.

    Responsibilities:
    - Accept a drug name and an orchestrator-generated research prompt
    - Run a ReAct loop using two tools: search_drug_composition, search_drug_price
    - Yield SSE events documenting every step (thoughts, tool calls, results)
    - Return structured drug data: composition + price
    """

    def __init__(self, agent_id: int, drug_name: str, custom_prompt: str = ""):
        self.agent_id     = agent_id
        self.drug_name    = drug_name
        self.custom_prompt = custom_prompt
        self._results: dict = {}

    # ──────────────────────────────────────────────────────────────
    def run(self) -> Generator[dict, None, None]:
        """
        Run this sub-agent's full research task.
        Yields SSE-compatible event dicts.
        """
        # Announce agent creation
        yield {
            "type":     "agent_start",
            "agent_id": self.agent_id,
            "drug_name": self.drug_name,
            "message":  f"Agent {self.agent_id} initialised for: {self.drug_name}",
        }

        # Build system prompt from template (orchestrator may override)
        system_prompt = SUB_AGENT_SYSTEM_PROMPT_TEMPLATE.format(
            agent_id=self.agent_id,
            drug_name=self.drug_name,
        )

        # Build the initial user prompt — use custom if orchestrator provided one
        if self.custom_prompt:
            initial_prompt = (
                f"Research task from Orchestrator:\n\n"
                f"{self.custom_prompt}\n\n"
                f"Remember to follow the ReAct pattern (Thought → Action → Observation → ... → Final Answer)."
            )
        else:
            initial_prompt = (
                f"Research the medicine '{self.drug_name}' available in India.\n\n"
                f"Find:\n"
                f"1. Exact drug composition (active ingredients with strengths)\n"
                f"2. Current retail price in India (₹ per standard pack)\n\n"
                f"Use your tools: search_drug_composition and search_drug_price.\n"
                f"Follow the ReAct pattern and end with a Final Answer in JSON."
            )

        # Run the ReAct engine
        engine = ReActEngine(
            agent_id=self.agent_id,
            drug_name=self.drug_name,
            system_prompt=system_prompt,
        )

        last_event = None
        for event in engine.run(initial_prompt):
            last_event = event
            yield event
            if event.get("type") == "agent_complete":
                self._results = event.get("data", {})

        # Ensure we always emit agent_complete
        if not last_event or last_event.get("type") != "agent_complete":
            self._results = {
                "drug_name":   self.drug_name,
                "brand_name":  self.drug_name,
                "composition": [],
                "price_inr":   0.0,
                "partial":     True,
            }
            yield {
                "type":       "agent_complete",
                "agent_id":   self.agent_id,
                "drug_name":  self.drug_name,
                "data":       self._results,
                "tool_calls": engine.all_tool_calls,
            }

    @property
    def results(self) -> dict:
        return self._results
