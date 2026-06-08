# Skill: Orchestrator Agent

## Overview
The `MedicineFindOrchestrator` is the master controller of the MediFind pipeline. It uses **Gemini 2.5 Flash with extended thinking** to reason about medicine alternatives, generate sub-agent prompts, and coordinate the full 4-phase pipeline.

---

## Model
`gemini-2.5-flash` via `google-genai` SDK

## Key Capabilities

### Extended Thinking
```python
types.ThinkingConfig(
    include_thoughts=True,
    thinking_budget=8000   # tokens allocated for reasoning
)
```
- Parts with `part.thought == True` are internal reasoning tokens — shown to users as chain-of-thought
- Parts with `part.thought == False` are the final output
- Streamed token-by-token using `generate_content_stream()`

### Google Search Grounding
```python
tools=[types.Tool(google_search=types.GoogleSearch())]
```
- Built-in Gemini tool — no external API calls needed
- Results are automatically injected into the model's context
- Source URLs available in `response.candidates[0].grounding_metadata.grounding_chunks`

---

## Pipeline Phases

### Phase 1 — Validation
- Calls `validate_medicine_india(medicine_name)` from `search_tools.py`
- If not valid: emits `validation_failed` and aborts
- If valid: emits `validation_success` with drug metadata, sets `self._original_medicine`

### Phase 2 — Discovery
- Prompts Gemini 2.5 Flash with thinking to find 10 alternatives
- Yields `orchestrator_thinking` events for each thought chunk
- Yields `orchestrator_response` events for the final answer
- Parses JSON from the response: `{ "alternatives": [...] }`
- Each alternative includes a `sub_agent_prompt` written by the orchestrator

### Phase 3 — Agent Research
- Iterates alternatives, creates `DrugResearchSubAgent` per drug
- Yields all sub-agent events unchanged (agent_start, tool_call, tool_result, etc.)
- Collects tool calls into `self.global_tool_log`

### Phase 4 — Ranking
- Calls `rank_alternatives(original, agent_results)` from `jaccard.py`
- Streams `similarity_score` events one by one (with 50ms delay for visual effect)
- Emits `final_results` with full ranked list
- Emits `tool_summary` with all tool calls made during the pipeline

---

## SSE Events Emitted

| Event | Phase | Description |
|---|---|---|
| `pipeline_start` | - | Search initiated |
| `phase` | All | Phase transition with progress message |
| `validation_success` / `validation_failed` | 1 | Validation result |
| `orchestrator_thinking` | 2 | Thought token stream |
| `orchestrator_response` | 2 | Orchestrator plan text |
| `alternatives_found` | 2 | Parsed list of 10 alternatives |
| `agent_deploy` | 3 | Agent created for a drug |
| (sub-agent events) | 3 | Passed through from sub-agents |
| `similarity_score` | 4 | Per-drug score |
| `final_results` | 4 | Full ranked list |
| `tool_summary` | - | Audit log of all tool calls |

---

## Prompt Design
The orchestrator uses two prompts (in `prompts.py`):
- `ORCHESTRATOR_SYSTEM_PROMPT`: Establishes the orchestrator identity and output format
- `ORCHESTRATOR_ALTERNATIVES_PROMPT`: The actual task prompt including medicine info

The orchestrator is instructed to output strict JSON:
```json
{
  "alternatives": [
    {
      "rank": 1,
      "brand_name": "...",
      "generic_name": "...",
      "manufacturer": "...",
      "therapeutic_reason": "...",
      "sub_agent_prompt": "Research [drug]: ..."
    }
  ]
}
```

---

## Error Handling
- If streaming fails: falls back to `_fallback_find_alternatives()` using `gemini-2.0-flash` without thinking
- If JSON parsing fails: uses regex-based `_extract_alternatives_from_text()` as last resort
- Both fallback paths emit `orchestrator_fallback` so the frontend can show a message

---

## File Location
`backend/agents/orchestrator.py`
