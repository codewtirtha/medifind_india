"""
MediFind India — ReAct Engine
Implements the ReAct (Reasoning + Acting) agent pattern.

Based on: "ReAct: Synergizing Reasoning and Acting in Language Models"
          Yao et al., 2022 (https://arxiv.org/abs/2210.03629)

Also incorporates Chain-of-Thought prompting:
          Wei et al., 2022 (https://arxiv.org/abs/2201.11903)

The ReAct loop:
  1. Thought  — Agent reasons about the current state and what to do next
  2. Action   — Agent calls a tool (search_drug_composition / search_drug_price)
  3. Observation — Tool result is fed back to the agent
  4. Repeat until Final Answer is produced

This engine manages multi-turn conversations with Gemini,
handles function call dispatch, and yields SSE-friendly events.
"""

from __future__ import annotations
import json
import re
import time
from typing import Generator, Any
from google import genai
from google.genai import types

from config.settings import settings
from backend.tools.search_tools import DRUG_RESEARCH_TOOLS, execute_tool, TOOL_PURPOSES


# ══════════════════════════════════════════════════════════════════
#  REACT ENGINE
# ══════════════════════════════════════════════════════════════════

class ReActEngine:
    """
    Manages the ReAct (Reasoning + Acting) loop for a single sub-agent.

    Each iteration:
      1. Sends conversation history to Gemini 2.0 Flash
      2. Parses function_call parts → dispatches to tool executor
      3. Adds tool results back to conversation
      4. Streams thought/action/observation events to caller
      5. Detects "Final Answer" in text → stops loop
    """

    def __init__(self, agent_id: int, drug_name: str, system_prompt: str):
        self.agent_id     = agent_id
        self.drug_name    = drug_name
        self.system_prompt = system_prompt
        self.client       = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.history: list[types.Content] = []
        self.all_tool_calls: list[dict]   = []

    # ──────────────────────────────────────────────────────────────
    def run(self, initial_prompt: str) -> Generator[dict, None, dict]:
        """
        Execute the full ReAct loop. Yields SSE events as a generator.
        Returns (via StopIteration value) the final structured data.

        Yields events of shape:
          {"type": "agent_thinking",   "agent_id": N, "text": "..."}
          {"type": "tool_call",        "agent_id": N, "tool": "...", "input": {...}, "purpose": "..."}
          {"type": "tool_result",      "agent_id": N, "tool": "...", "result": {...}, "sources": [...]}
          {"type": "agent_complete",   "agent_id": N, "data": {...}, "tool_calls": [...]}
        """
        # Seed conversation
        self.history.append(
            types.Content(role="user", parts=[types.Part(text=initial_prompt)])
        )

        config = types.GenerateContentConfig(
            tools=[DRUG_RESEARCH_TOOLS],
            system_instruction=self.system_prompt,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            max_output_tokens=4096,
        )

        final_data = {}

        for turn in range(settings.MAX_REACT_TURNS):
            # ── Call Gemini ──────────────────────────────────────
            try:
                response = self.client.models.generate_content(
                    model=settings.SUB_AGENT_MODEL,
                    contents=self.history,
                    config=config,
                )
            except Exception as e:
                yield {
                    "type":     "agent_error",
                    "agent_id": self.agent_id,
                    "message":  str(e),
                }
                break

            # Add model response to history
            if response.candidates:
                self.history.append(response.candidates[0].content)

            # ── Process each part in the response ───────────────
            function_calls_this_turn = []
            function_responses_parts = []
            text_this_turn = ""

            if response.candidates:
                for part in response.candidates[0].content.parts:
                    if part.function_call:
                        function_calls_this_turn.append(part.function_call)
                    elif part.text:
                        text_this_turn += part.text

            # ── Stream thought text ──────────────────────────────
            if text_this_turn.strip():
                thought, action = _parse_thought_action(text_this_turn)
                yield {
                    "type":     "agent_thinking",
                    "agent_id": self.agent_id,
                    "text":     text_this_turn,
                    "thought":  thought,
                    "action":   action,
                }

                # Check for Final Answer
                final_json = _extract_final_answer(text_this_turn)
                if final_json:
                    final_data = final_json
                    break

            # ── Execute function calls ───────────────────────────
            for fc in function_calls_this_turn:
                fn_name = fc.name
                fn_args = dict(fc.args) if fc.args else {}

                purpose = TOOL_PURPOSES.get(fn_name, f"Execute {fn_name}")

                # Emit tool_call event (before execution)
                yield {
                    "type":     "tool_call",
                    "agent_id": self.agent_id,
                    "tool":     fn_name,
                    "input":    fn_args,
                    "purpose":  purpose,
                    "turn":     turn + 1,
                }

                # Execute the tool
                t_start = time.time()
                result, sources = execute_tool(fn_name, fn_args)
                elapsed = round(time.time() - t_start, 2)

                # Record for summary
                call_record = {
                    "tool":     fn_name,
                    "input":    fn_args,
                    "result":   _summarise_result(result),
                    "sources":  sources,
                    "purpose":  purpose,
                    "elapsed_s": elapsed,
                    "agent_id": self.agent_id,
                    "drug_name": self.drug_name,
                }
                self.all_tool_calls.append(call_record)

                # Emit tool_result event
                yield {
                    "type":     "tool_result",
                    "agent_id": self.agent_id,
                    "tool":     fn_name,
                    "result":   result,
                    "sources":  sources,
                    "elapsed_s": elapsed,
                }

                # Build function response part
                function_responses_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=fn_name,
                            response={"result": json.dumps(result, ensure_ascii=False)},
                        )
                    )
                )

            # ── Add function responses to conversation ───────────
            if function_responses_parts:
                self.history.append(
                    types.Content(
                        role="user",
                        parts=function_responses_parts,
                    )
                )
            elif not function_calls_this_turn:
                # No function calls and no pending responses → agent is done
                # Try to extract structured data from last text
                if text_this_turn:
                    final_data = _extract_final_answer(text_this_turn) or _best_effort_extract(text_this_turn, self.drug_name)
                break

        # ── Emit completion ──────────────────────────────────────
        if not final_data:
            final_data = _best_effort_extract(
                " ".join(
                    p.text for c in self.history
                    for p in (c.parts or [])
                    if p.text
                ),
                self.drug_name,
            )

        yield {
            "type":       "agent_complete",
            "agent_id":   self.agent_id,
            "drug_name":  self.drug_name,
            "data":       final_data,
            "tool_calls": self.all_tool_calls,
        }


# ══════════════════════════════════════════════════════════════════
#  PRIVATE HELPERS
# ══════════════════════════════════════════════════════════════════

def _parse_thought_action(text: str) -> tuple[str, str]:
    """Extract Thought and Action lines from ReAct-formatted text."""
    thought = ""
    action  = ""

    thought_m = re.search(r"Thought\s*:\s*(.+?)(?=Action\s*:|Final Answer|$)", text, re.DOTALL | re.IGNORECASE)
    if thought_m:
        thought = thought_m.group(1).strip()

    action_m = re.search(r"Action\s*:\s*(.+?)(?=Action Input|Observation|Thought|$)", text, re.DOTALL | re.IGNORECASE)
    if action_m:
        action = action_m.group(1).strip()

    return thought, action


def _extract_final_answer(text: str) -> dict | None:
    """
    Look for 'Final Answer:' followed by a JSON block.
    Returns parsed dict or None.
    """
    fa_match = re.search(
        r"Final Answer\s*:\s*(\{.*\}|\[.*\])",
        text, re.DOTALL | re.IGNORECASE
    )
    if fa_match:
        try:
            return json.loads(fa_match.group(1))
        except json.JSONDecodeError:
            pass

    # Also try bare JSON at end of text
    json_match = re.search(r"(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})\s*$", text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            # Must have at least composition or price to be a "final answer"
            if "composition" in data or "price_inr" in data or "drug_name" in data:
                return data
        except json.JSONDecodeError:
            pass

    return None


def _best_effort_extract(full_text: str, drug_name: str) -> dict:
    """
    Last-resort extraction: pull whatever structured data is available
    from the full conversation history text.
    """
    from backend.tools.search_tools import _extract_json, _parse_composition_text, _parse_price_text

    # Try JSON extraction first
    data = _extract_json(full_text)
    if data and ("composition" in data or "price_inr" in data):
        return data

    # Manual extraction
    composition = _parse_composition_text(full_text, drug_name)
    price_inr, price_display = _parse_price_text(full_text)

    return {
        "drug_name":     drug_name,
        "brand_name":    drug_name,
        "generic_name":  "",
        "composition":   composition,
        "price_inr":     price_inr,
        "price_display": price_display,
        "pack_size":     "strip of 10 tablets",
        "manufacturer":  "",
        "availability":  "Available",
        "sources":       [],
        "partial":       True,   # flag that this is incomplete data
    }


def _summarise_result(result: dict) -> dict:
    """Trim large result dicts for the event stream (avoid huge payloads)."""
    if not result:
        return {}
    summary = {}
    if "composition" in result:
        summary["composition"] = result["composition"][:5]
    if "price_inr" in result:
        summary["price_inr"] = result["price_inr"]
    if "price_display" in result:
        summary["price_display"] = result["price_display"]
    if "brand_name" in result:
        summary["brand_name"] = result["brand_name"]
    if "generic_name" in result:
        summary["generic_name"] = result["generic_name"]
    if "error" in result:
        summary["error"] = result["error"]
    summary["success"] = result.get("success", False)
    return summary
