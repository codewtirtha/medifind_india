# Skill: Web Search Tool

## Overview
MediFind uses **Gemini's built-in Google Search grounding** as its search mechanism. This is different from calling the Google Search API directly — the search is handled natively inside the Gemini API call.

---

## Two Search Modes Used

### Mode 1 — Orchestrator (Auto-grounding)
```python
tools=[types.Tool(google_search=types.GoogleSearch())]
```
Used by the **orchestrator** (Gemini 2.5 Flash). Gemini decides when to search and what to search for. Source URLs appear in:
```python
response.candidates[0].grounding_metadata.grounding_chunks[i].web.uri
```

### Mode 2 — Sub-Agents (Function Declaration tools)
```python
types.FunctionDeclaration(
    name="search_drug_composition",
    description="Search Indian pharmacy websites for the drug's composition...",
    parameters={
        "type": "OBJECT",
        "properties": {
            "drug_name":     {"type": "STRING", "description": "..."},
            "search_focus":  {"type": "STRING", "description": "..."},
        },
        "required": ["drug_name"]
    }
)
```
The sub-agents have `search_drug_composition` and `search_drug_price` declared as tools. When Gemini returns a `function_call` Part, `react_engine.py` dispatches to `execute_tool()` in `search_tools.py`, which itself calls **another Gemini instance with Google Search grounding** to perform the actual web lookup.

---

## Tool Definitions (search_tools.py)

### `search_drug_composition(drug_name, search_focus="")`
**Purpose**: Find the active ingredient(s) and their quantities for a drug in India.

**What it searches for**:
- Salt names (INN generic names)
- Active ingredient concentrations (e.g. "500mg")
- Formulation type (tablet, capsule, syrup)
- Source: 1mg.com, pharmeasy.in, netmeds.com, apollopharmacy.in

**Returns**:
```python
{
    "composition": ["amoxicillin 500mg", "clavulanic acid 125mg"],
    "source_urls": ["https://1mg.com/..."],
    "raw_text": "...",
}
```

**Internal implementation**:
```python
response = client.models.generate_content(
    model=settings.SUB_AGENT_MODEL,
    contents=COMPOSITION_SEARCH_PROMPT.format(...),
    config=types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
    )
)
```

---

### `search_drug_price(drug_name, pack_size="")`
**Purpose**: Find the current retail price in ₹ for a drug in India.

**What it searches for**:
- MRP / retail price in Indian Rupees
- Pack size (e.g. "10 tablets", "30 capsules")
- Availability on Indian online pharmacies
- Source: 1mg.com, pharmeasy.in, netmeds.com, apollopharmacy.in, medplusmart.com

**Returns**:
```python
{
    "price_inr": 185.0,
    "pack_info": "10 tablets",
    "source_urls": ["https://pharmeasy.in/..."],
}
```

---

### `validate_medicine_india(medicine_name)`
**Purpose**: Verify the medicine exists in the Indian pharmaceutical market.

**What it checks**:
- Is this a known Indian brand name or INN?
- Who is the manufacturer?
- What is the generic composition?
- Is it currently available on major Indian pharmacy platforms?

**Returns**:
```python
{
    "valid": True,
    "brand_name": "Augmentin 625",
    "generic_name": "Amoxicillin + Clavulanic Acid",
    "manufacturer": "GSK",
    "composition": ["amoxicillin 500mg", "clavulanic acid 125mg"],
    "typical_price_inr": 220.0,
    "category": "Antibiotic",
    "source_urls": [...],
}
```
or
```python
{ "valid": False, "reason": "...", "suggestion": "Did you mean..." }
```

---

## Indian Pharmacy Sites

All search prompts are restricted to these sites:
```python
INDIAN_PHARMACY_SITES = [
    "1mg.com",
    "pharmeasy.in",
    "netmeds.com",
    "apollopharmacy.in",
    "medplusmart.com",
]
```

The prompts include instructions like:
> Search on Indian pharmacy websites (1mg.com, pharmeasy.in, netmeds.com, apollopharmacy.in) only.

---

## JSON Extraction
Tool results from LLMs can contain prose + JSON. The `_extract_json()` helper:
1. Strips markdown code fences
2. Tries direct `json.loads()`
3. Finds outermost `{ }` with depth counting
4. Falls back to regex pattern matching

The result is always normalised via `_parse_composition_text()` and `_parse_price_text()`.

---

## Source URL Extraction
```python
def _extract_sources(response) -> list[str]:
    try:
        chunks = response.candidates[0].grounding_metadata.grounding_chunks
        return [c.web.uri for c in chunks if c.web]
    except (AttributeError, IndexError):
        return []
```

---

## File Location
`backend/tools/search_tools.py`
