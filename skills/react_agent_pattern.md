# Skill: ReAct Agent Pattern

## Overview
ReAct (Reasoning + Acting) is an agent paradigm introduced by [Yao et al., 2023](https://arxiv.org/abs/2210.03629) that interleaves **verbal reasoning** (chain-of-thought) with **tool actions**, allowing the model to self-correct and gather information iteratively.

---

## Core Loop Structure

```
Prompt →
  Thought: [Model reasons about what to do next]
  Action: tool_name(input)
Observation: [Tool result injected into context]
  Thought: [Model processes observation and plans next step]
  Action: another_tool(input)
Observation: ...
  Thought: I now have enough information.
  Final Answer: { ... structured result ... }
```

---

## Implementation in MediFind

### File
`backend/agents/react_engine.py` — `ReActEngine` class

### Key Design Decisions

#### 1. Manual Function Calling (disable=True)
```python
automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
```
Why manual? It gives us:
- Visibility: we can emit `tool_call` SSE events before execution
- Control: we can validate, log, and handle errors around each tool call
- Interruptibility: we can stop the loop at any turn

#### 2. Thought Extraction
```python
def _parse_thought_action(self, text: str) -> tuple[str, str]:
    """Extract Thought and Action from a model text turn."""
```
The model output might be structured as:
```
Thought: I need composition data for this drug.
Action: search_drug_composition({"drug_name": "...", "search_focus": "..."})
```
or just as natural language with a function_call `Part`.

When a `function_call` Part is present, that takes precedence over text parsing.

#### 3. Conversation History
Multi-turn conversation is maintained as a list of `types.Content` objects:
```python
history: list[types.Content] = [
    # user message → model response → function_response → model response → ...
]
```
Each turn appends to history so the model retains full context.

#### 4. Final Answer Detection
```python
FINAL_ANSWER_PATTERNS = [
    r'Final Answer:\s*(\{.*?\})',          # inline JSON
    r'Final Answer:\s*```json\s*(\{.*?\})', # fenced JSON
    r'"composition":\s*\[',                # partial match fallback
]
```

#### 5. Best-Effort Extraction
If MAX_REACT_TURNS is reached without a Final Answer:
```python
def _best_effort_extract(self, history) -> dict:
    """Scan all model turns for any JSON-like structure with composition/price."""
```

---

## Prompt Engineering for ReAct

### What makes a good ReAct prompt?

1. **Explicit format instruction**: tell the model exactly what `Thought:` and `Final Answer:` mean
2. **Tool descriptions in the prompt**: reinforce what each tool does
3. **Output schema**: show the exact JSON structure you expect
4. **Context priming**: give the drug name, country context, and what data is needed

### Example (from prompts.py)
```
You are DrugResearch-Agent-3, a pharmaceutical research agent.

You have access to two tools:
- search_drug_composition: finds active ingredients on Indian pharmacy sites
- search_drug_price: finds current retail prices in India

Your goal: Find the composition and price of [drug] in India.

Format:
  Thought: [your reasoning]
  → use a tool if needed
  
When done, output EXACTLY:
Final Answer: {"composition": [...], "price_inr": ..., "source_urls": [...]}
```

---

## Comparison: Standard CoT vs ReAct

| | Chain-of-Thought | ReAct |
|---|---|---|
| Reasoning | ✅ Yes | ✅ Yes |
| Tool use | ❌ No | ✅ Yes |
| Grounded in real data | ❌ No | ✅ Yes |
| Self-correction | ❌ Limited | ✅ Via observation |
| Hallucination risk | Higher | Lower (tools verify) |

---

## Convergence Guarantees

The loop is bounded by `MAX_REACT_TURNS = 8`. Typical drug research completes in 2–4 turns:
- Turn 1: search composition
- Turn 2: search price
- Turn 3: Final Answer

Even if the model loops unnecessarily, it will be cut off and a best-effort result used.

---

## Papers & References
- [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629) — Yao et al., 2023
- [Chain-of-Thought Prompting](https://arxiv.org/abs/2201.11903) — Wei et al., 2022
- [Toolformer](https://arxiv.org/abs/2302.04761) — Schick et al., 2023
- [Gemini Function Calling](https://ai.google.dev/gemini-api/docs/function-calling)
