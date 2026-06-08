"""
MediFind India — Master Orchestrator
The orchestrator is the brain of the system. It uses Gemini 2.5 Flash
with extended thinking to reason, plan, and coordinate the entire pipeline.

Pipeline:
  Phase 1 — Validation
    └─ Validate that the input medicine exists in India (Gemini + search)

  Phase 2 — Discovery (Gemini 2.5 Flash + thinking + search)
    └─ Find 10 alternatives + generate custom sub-agent prompts

  Phase 3 — Deep Research (10 sub-agents in parallel simulation)
    └─ Each sub-agent runs ReAct loop: composition + price

  Phase 4 — Ranking (Jaccard + price-weighted scoring)
    └─ Rank 10 alternatives and emit final results

The orchestrator's thinking is streamed live to the frontend.
"""

from __future__ import annotations
import json
import re
import time
from typing import Generator

from google import genai
from google.genai import types

from config.settings import settings
from backend.agents.prompts import (
    ORCHESTRATOR_SYSTEM_PROMPT,
    ORCHESTRATOR_ALTERNATIVES_PROMPT,
    MEDICINE_NOT_FOUND_MESSAGE,
)
from backend.agents.sub_agent import DrugResearchSubAgent
from backend.similarity.jaccard import rank_alternatives
from backend.tools.search_tools import validate_medicine_india
from backend.utils.helpers import safe_json_loads, clean_medicine_name


class MedicineFindOrchestrator:
    """
    Master orchestrator for the MediFind India pipeline.
    Yields SSE-compatible event dicts throughout execution.
    """

    def __init__(self):
        self.client          = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.global_tool_log: list[dict] = []

    # ══════════════════════════════════════════════════════════════
    #  MAIN ENTRY POINT
    # ══════════════════════════════════════════════════════════════

    def run(self, medicine_name: str) -> Generator[dict, None, None]:
        """
        Execute the full MediFind pipeline.
        Yields SSE events for every significant step.
        """
        medicine_name = clean_medicine_name(medicine_name)

        yield {"type": "pipeline_start", "medicine": medicine_name,
               "message": f"🔬 Starting MediFind research for: {medicine_name}"}

        # ── Phase 1: Validation ──────────────────────────────────
        yield from self._phase_validation(medicine_name)
        if hasattr(self, "_abort"):
            return

        # ── Phase 2: Find Alternatives ───────────────────────────
        yield from self._phase_find_alternatives(medicine_name)
        if hasattr(self, "_abort") or not self._alternatives:
            return

        # ── Phase 3: Sub-Agent Research ──────────────────────────
        yield from self._phase_agent_research()

        # ── Phase 4: Rank & Display ──────────────────────────────
        yield from self._phase_ranking(medicine_name)

        # ── Final: Tool Call Summary ─────────────────────────────
        yield {
            "type":           "tool_summary",
            "all_tool_calls": self.global_tool_log,
            "total_calls":    len(self.global_tool_log),
        }

    # ══════════════════════════════════════════════════════════════
    #  PHASE 1 — VALIDATION
    # ══════════════════════════════════════════════════════════════

    def _phase_validation(self, medicine_name: str) -> Generator[dict, None, None]:
        yield {"type": "phase", "phase": "validation",
               "message": "⚡ Validating medicine in Indian pharmaceutical database..."}

        result = validate_medicine_india(medicine_name)

        # Log validation as a tool call
        self.global_tool_log.append({
            "tool":    "validate_medicine_india",
            "input":   {"medicine_name": medicine_name},
            "purpose": "Verify the medicine exists in the Indian pharmaceutical market",
            "agent":   "Orchestrator",
            "sources": result.get("source_urls", []),
        })

        if not result.get("valid"):
            self._abort = True
            yield {
                "type":       "validation_failed",
                "medicine":   medicine_name,
                "reason":     result.get("reason", "Medicine not found"),
                "suggestion": result.get("suggestion", ""),
                "message":    MEDICINE_NOT_FOUND_MESSAGE.format(medicine_name=medicine_name),
            }
        else:
            self._original_medicine = result
            yield {
                "type":        "validation_success",
                "medicine":    medicine_name,
                "data":        result,
                "message":     f"✅ Found: {result.get('brand_name', medicine_name)}",
            }

    # ══════════════════════════════════════════════════════════════
    #  PHASE 2 — FIND ALTERNATIVES (Gemini 2.5 Flash + thinking)
    # ══════════════════════════════════════════════════════════════

    def _phase_find_alternatives(self, medicine_name: str) -> Generator[dict, None, None]:
        self._alternatives = []

        yield {"type": "phase", "phase": "discovery",
               "message": "🧠 Orchestrator reasoning about alternatives..."}

        # Build medicine info string for the prompt
        medicine_info = json.dumps(self._original_medicine, indent=2, ensure_ascii=False)
        prompt = ORCHESTRATOR_ALTERNATIVES_PROMPT.format(
            medicine_name=medicine_name,
            medicine_info=medicine_info,
            generic_name=self._original_medicine.get("generic_name", medicine_name),
        )

        # Stream the thinking from Gemini 2.5 Flash
        thinking_buffer = ""
        response_buffer = ""

        try:
            for chunk in self.client.models.generate_content_stream(
                model=settings.ORCHESTRATOR_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=ORCHESTRATOR_SYSTEM_PROMPT,
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    thinking_config=types.ThinkingConfig(
                        include_thoughts=True,
                        thinking_budget=settings.THINKING_BUDGET,
                    ),
                    response_modalities=["TEXT"],
                ),
            ):
                if not chunk.candidates:
                    continue
                for part in chunk.candidates[0].content.parts:
                    if part.thought and part.text:
                        thinking_buffer += part.text
                        yield {
                            "type":   "orchestrator_thinking",
                            "text":   part.text,
                            "buffer": thinking_buffer[-800:],  # last 800 chars
                        }
                    elif part.text:
                        response_buffer += part.text
                        yield {
                            "type": "orchestrator_response",
                            "text": part.text,
                        }

        except Exception as e:
            yield {"type": "orchestrator_error", "message": str(e)}
            # Fallback: try without thinking
            yield {"type": "orchestrator_fallback",
                   "message": "Retrying without thinking mode..."}
            response_buffer = self._fallback_find_alternatives(medicine_name, medicine_info)

        # Extract grounding sources from the last non-streaming call if needed
        self.global_tool_log.append({
            "tool":    "google_search_grounding",
            "input":   {"query": f"{medicine_name} alternatives India"},
            "purpose": "Find 10 therapeutically equivalent alternatives available in India",
            "agent":   "Orchestrator",
            "sources": [],
        })

        # Parse alternatives from response
        parsed = safe_json_loads(response_buffer)
        alts = []
        if parsed and "alternatives" in parsed:
            alts = parsed["alternatives"]
        elif isinstance(parsed, list):
            alts = parsed

        if not alts:
            # Last-ditch extraction
            alts = self._extract_alternatives_from_text(response_buffer, medicine_name)

        # Limit to MAX_ALTERNATIVES
        self._alternatives = alts[: settings.MAX_ALTERNATIVES]

        if not self._alternatives:
            self._abort = True
            yield {"type": "no_alternatives",
                   "message": f"Could not find alternatives for {medicine_name}"}
            return

        yield {
            "type":         "alternatives_found",
            "alternatives": self._alternatives,
            "count":        len(self._alternatives),
            "message":      f"🎯 Found {len(self._alternatives)} alternatives — creating research agents...",
        }

    def _fallback_find_alternatives(self, medicine_name: str, medicine_info: str) -> str:
        """Non-streaming fallback for alternative discovery."""
        from backend.agents.prompts import ORCHESTRATOR_ALTERNATIVES_PROMPT
        prompt = ORCHESTRATOR_ALTERNATIVES_PROMPT.format(
            medicine_name=medicine_name,
            medicine_info=medicine_info,
            generic_name=medicine_name,
        )
        try:
            resp = self.client.models.generate_content(
                model=settings.SUB_AGENT_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
            )
            return resp.text or ""
        except Exception:
            return ""

    def _extract_alternatives_from_text(self, text: str, base_name: str) -> list[dict]:
        """Last-resort: extract medicine names from unstructured text."""
        # Look for numbered lists: 1. Name, 2. Name, etc.
        pattern = r"\d+[\.\)]\s+([A-Z][A-Za-z0-9\-\s]+?)(?:\s*[-–]|\n|,|$)"
        matches = re.findall(pattern, text)
        alts = []
        for i, m in enumerate(matches[:10]):
            name = m.strip()
            if name and len(name) > 2:
                alts.append({
                    "rank":             i + 1,
                    "brand_name":       name,
                    "generic_name":     name,
                    "manufacturer":     "Unknown",
                    "therapeutic_reason": "Therapeutically equivalent",
                    "sub_agent_prompt": f"Research {name}: find its composition and price on Indian pharmacy websites.",
                })
        return alts

    # ══════════════════════════════════════════════════════════════
    #  PHASE 3 — SUB-AGENT RESEARCH
    # ══════════════════════════════════════════════════════════════

    def _phase_agent_research(self) -> Generator[dict, None, None]:
        self._agent_results: list[dict] = []

        yield {"type": "phase", "phase": "agents",
               "message": f"🤖 Deploying {len(self._alternatives)} research agents..."}

        for i, alt in enumerate(self._alternatives):
            drug_name     = alt.get("brand_name") or alt.get("generic_name", f"Drug {i+1}")
            custom_prompt = alt.get("sub_agent_prompt", "")
            agent_id      = i + 1

            yield {
                "type":             "agent_deploy",
                "agent_id":         agent_id,
                "drug_name":        drug_name,
                "therapeutic_reason": alt.get("therapeutic_reason", ""),
                "total_agents":     len(self._alternatives),
                "message":          f"🚀 Deploying Agent {agent_id}: Researching {drug_name}",
            }

            # Create and run the sub-agent
            agent = DrugResearchSubAgent(
                agent_id=agent_id,
                drug_name=drug_name,
                custom_prompt=custom_prompt,
            )

            agent_result = None
            for event in agent.run():
                yield event
                # Collect tool calls for global log
                if event["type"] == "tool_call":
                    self.global_tool_log.append({
                        "tool":      event["tool"],
                        "input":     event["input"],
                        "purpose":   event["purpose"],
                        "agent":     f"Agent {agent_id} ({drug_name})",
                        "agent_id":  agent_id,
                        "drug_name": drug_name,
                    })
                elif event["type"] == "agent_complete":
                    agent_result = event.get("data", {})

            if agent_result:
                # Merge alternative metadata with agent result
                merged = {**alt, **agent_result}
                self._agent_results.append(merged)
            else:
                # Partial result with no data
                self._agent_results.append({
                    **alt,
                    "drug_name":   drug_name,
                    "composition": [],
                    "price_inr":   0.0,
                    "partial":     True,
                })

            yield {
                "type":     "agent_done",
                "agent_id": agent_id,
                "drug_name": drug_name,
                "progress": f"{i+1}/{len(self._alternatives)}",
            }

    # ══════════════════════════════════════════════════════════════
    #  PHASE 4 — RANKING
    # ══════════════════════════════════════════════════════════════

    def _phase_ranking(self, medicine_name: str) -> Generator[dict, None, None]:
        yield {"type": "phase", "phase": "ranking",
               "message": "⚖️  Computing Jaccard similarity and price scores..."}

        original = {
            **self._original_medicine,
            "price_inr": self._original_medicine.get("typical_price_inr", 0.0),
        }

        ranked = rank_alternatives(original, self._agent_results)

        # Stream individual similarity scores
        for item in ranked:
            yield {
                "type":                 "similarity_score",
                "drug_name":            item.get("brand_name", ""),
                "composition_similarity": item.get("composition_similarity", 0),
                "price_similarity":     item.get("price_similarity", 0),
                "composite_score":      item.get("composite_score", 0),
            }
            time.sleep(0.05)   # small delay for visual effect

        yield {
            "type":    "final_results",
            "results": ranked,
            "original": original,
            "count":   len(ranked),
            "message": f"🏆 Top {len(ranked)} alternatives ranked by composite score",
        }
