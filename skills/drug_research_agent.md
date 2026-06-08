# Skill: Drug Research Sub-Agent

## Overview
Each `DrugResearchSubAgent` is a self-contained AI researcher that investigates one drug using a **ReAct (Reasoning + Acting) loop**. It uses Gemini 2.0 Flash with explicit function-calling to discover composition and price from Indian pharmacy websites.

---

## Model
`gemini-2.0-flash` via `google-genai` SDK

## Files
- `backend/agents/sub_agent.py` — Thin wrapper that creates and runs the ReAct engine
- `backend/agents/react_engine.py` — ReAct loop implementation

---

## Agent Identity
Each agent is assigned a unique identity:
```python
system_instruction = SUB_AGENT_SYSTEM_PROMPT_TEMPLATE.format(
    agent_id=self.agent_id,        # 1–10
    drug_name=self.drug_name,
)
```
This makes it appear as e.g. `DrugResearch-Agent-3` specialised on `Azithral 500`.

---

## ReAct Loop (react_engine.py)

The loop runs for up to `MAX_REACT_TURNS` (default: 8) turns:

```
Turn 1:
  Model output: Thought: I should search for composition first.
                Action: search_drug_composition(drug_name="Azithral 500", ...)
  → detect function call in response
  → execute tool
  → append FunctionResponse to conversation

Turn 2:
  Model output: Thought: I have composition. Now searching price.
                Action: search_drug_price(drug_name="Azithral 500", ...)
  → ...

Turn N:
  Model output: Thought: I have enough data.
                Final Answer: {"composition": [...], "price_inr": 185.0, ...}
  → detect "Final Answer:" in text → exit loop
```

### Implementation Detail — Manual Function Calling
```python
config=types.GenerateContentConfig(
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    tools=[DRUG_RESEARCH_TOOLS],       # two FunctionDeclarations
    system_instruction=...,
)
```
- `disable=True` means Gemini returns the function call as a `Part` rather than executing it
- The engine detects `part.function_call` and dispatches to `execute_tool()`
- Results are injected back as `types.FunctionResponse` content

### Conversation Multi-Turn Format
```python
history = [
    types.Content(role="user", parts=[types.Part(text=initial_prompt)]),
    types.Content(role="model", parts=[...previous_response...]),
    types.Content(role="user",  parts=[types.Part(function_response=...)]),
    ...
]
```

---

## SSE Events Emitted

| Event | Description |
|---|---|
| `agent_start` | Agent beginning its ReAct loop |
| `agent_thinking` | Extracted thought text from the model |
| `tool_call` | Tool about to be executed (`tool`, `purpose`, `input`) |
| `tool_result` | Tool executed, sources available |
| `agent_complete` | Final Answer parsed — contains `data: {composition, price_inr, ...}` |

---

## Final Answer Detection
The engine looks for this pattern in the model output:
```
Final Answer: { ... }
```
or
```
Final Answer:
```json
{ ... }
```
```

The JSON is parsed by `safe_json_loads()`. Expected fields:
```json
{
  "composition": ["amoxicillin 500mg", "clavulanic acid 125mg"],
  "price_inr": 185.0,
  "pack_info": "10 tablets",
  "manufacturer": "GSK",
  "source_urls": ["https://..."]
}
```

If a Final Answer is never produced within MAX_REACT_TURNS, the engine yields a `best_effort` result from `_best_effort_extract()`.

---

## Prompt Design (from prompts.py)

### SUB_AGENT_SYSTEM_PROMPT_TEMPLATE
Sets the agent's identity, goal (find composition + price in India), output format, and instructs it to always use the provided tools.

### Custom Prompt (from orchestrator)
The orchestrator writes a specific prompt per drug, e.g.:
```
Research Azithral 500 (Azithromycin 500mg by Cipla): Find its exact composition
and current price on Indian pharmacy sites (1mg.com, pharmeasy.in, netmeds.com).
Focus on the 500mg tablet strip. Confirm it is currently available in India.
```
This custom prompt provides the agent with context beyond just the drug name.

---

## Tool Capabilities Available to Each Sub-Agent

1. **`search_drug_composition`** — searches for active ingredients, salt names, and formulation details
2. **`search_drug_price`** — searches for current Indian retail price per strip/pack

See `skills/web_search_tool.md` and `skills/composition_price_finder.md` for details.
