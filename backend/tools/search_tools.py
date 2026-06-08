"""
MediFind India — Search Tools
These tool functions are called by sub-agents via explicit function calling.
Each tool internally uses Gemini 2.0 Flash with Google Search grounding
to retrieve real-time information from Indian pharmacy websites.

Tool Design follows the ReAct paper (Yao et al., 2022):
- Tools have precise, narrow responsibilities
- They return structured JSON-serialisable strings
- Source URLs are always captured for transparency
"""

import json
import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from google import genai
from google.genai import types
from config.settings import settings
from backend.agents.prompts import COMPOSITION_SEARCH_PROMPT, PRICE_SEARCH_PROMPT

# ──────────────────────────────────────────────────────────────────
_client: genai.Client | None = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


# ══════════════════════════════════════════════════════════════════
#  TOOL REGISTRY
#  Maps function names to callable implementations.
# ══════════════════════════════════════════════════════════════════

TOOL_PURPOSES = {
    "search_drug_composition": "Find the exact active ingredients and their strengths for a drug from Indian medical databases",
    "search_drug_price":       "Find the current retail price of a drug on Indian pharmacy websites (1mg, PharmEasy, Netmeds)",
    "validate_medicine_india": "Verify that a medicine is available and sold in the Indian pharmaceutical market",
}


def search_drug_composition(drug_name: str, search_focus: str = "composition ingredients active") -> dict:
    """
    Search Indian pharmaceutical databases for the drug composition.
    Returns a dict with composition list, names, and source URLs.

    Called by sub-agents during the ReAct loop (Action: search_drug_composition).

    Args:
        drug_name: Brand name or generic name of the drug (e.g. "Crocin 500mg")
        search_focus: Optional additional search context

    Returns:
        dict: {
            "composition": ["Paracetamol 500mg", ...],
            "brand_name": "...",
            "generic_name": "...",
            "manufacturer": "...",
            "source_urls": ["https://..."],
            "raw_text": "...",
            "success": true/false
        }
    """
    client = _get_client()
    prompt = COMPOSITION_SEARCH_PROMPT.format(drug_name=drug_name)

    try:
        response = client.models.generate_content(
            model=settings.SEARCH_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                response_modalities=["TEXT"],
            ),
        )

        raw_text = response.text or ""
        source_urls = _extract_sources(response)

        # Try to parse JSON from response
        parsed = _extract_json(raw_text)
        if parsed:
            parsed["source_urls"] = source_urls or parsed.get("source_urls", [])
            parsed["success"] = True
            parsed["raw_text"] = raw_text
            return parsed

        # Fallback: extract composition from raw text
        composition = _parse_composition_text(raw_text, drug_name)
        return {
            "composition": composition,
            "brand_name": drug_name,
            "generic_name": "",
            "manufacturer": "",
            "source_urls": source_urls,
            "raw_text": raw_text,
            "success": bool(composition),
        }

    except Exception as e:
        return {
            "composition": [],
            "brand_name": drug_name,
            "generic_name": "",
            "manufacturer": "",
            "source_urls": [],
            "raw_text": f"Search error: {str(e)}",
            "success": False,
            "error": str(e),
        }


def search_drug_price(drug_name: str, pack_size: str = "10 tablets strip") -> dict:
    """
    Search Indian pharmacy websites for the current retail price of a drug.
    Focuses on 1mg.com, pharmeasy.in, netmeds.com.

    Called by sub-agents during the ReAct loop (Action: search_drug_price).

    Args:
        drug_name: Brand or generic name of the drug
        pack_size: Standard pack size to search for

    Returns:
        dict: {
            "price_inr": 25.50,
            "price_display": "₹25.50 per strip of 10 tablets",
            "pack_size": "10 tablets",
            "mrp": 30.00,
            "source_urls": [...],
            "success": true/false
        }
    """
    client = _get_client()
    prompt = PRICE_SEARCH_PROMPT.format(drug_name=drug_name)

    try:
        response = client.models.generate_content(
            model=settings.SEARCH_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                response_modalities=["TEXT"],
            ),
        )

        raw_text = response.text or ""
        source_urls = _extract_sources(response)

        # Try to parse JSON from response
        parsed = _extract_json(raw_text)
        if parsed:
            parsed["source_urls"] = source_urls or parsed.get("source_urls", [])
            parsed["success"] = True
            parsed["raw_text"] = raw_text
            # Ensure price_inr is a float
            if "price_inr" in parsed:
                try:
                    parsed["price_inr"] = float(parsed["price_inr"])
                except (ValueError, TypeError):
                    parsed["price_inr"] = 0.0
            return parsed

        # Fallback: extract price from raw text
        price_inr, price_display = _parse_price_text(raw_text)
        return {
            "price_inr": price_inr,
            "price_display": price_display or f"₹{price_inr:.2f}" if price_inr else "Price not available",
            "pack_size": pack_size,
            "mrp": price_inr,
            "source_urls": source_urls,
            "raw_text": raw_text,
            "success": price_inr > 0,
        }

    except Exception as e:
        return {
            "price_inr": 0.0,
            "price_display": "Price unavailable",
            "pack_size": pack_size,
            "mrp": 0.0,
            "source_urls": [],
            "raw_text": f"Search error: {str(e)}",
            "success": False,
            "error": str(e),
        }


def validate_medicine_india(medicine_name: str) -> dict:
    """
    Validate whether a medicine exists in the Indian pharmaceutical market.
    Uses Gemini with Google Search grounding.

    Args:
        medicine_name: Name of the medicine to validate

    Returns:
        dict with 'valid' bool and medicine details if found
    """
    from backend.agents.prompts import VALIDATION_PROMPT
    client = _get_client()
    prompt = VALIDATION_PROMPT.format(medicine_name=medicine_name)

    try:
        response = client.models.generate_content(
            model=settings.SEARCH_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                response_modalities=["TEXT"],
            ),
        )

        raw_text = response.text or ""
        source_urls = _extract_sources(response)
        parsed = _extract_json(raw_text)

        if parsed:
            parsed["source_urls"] = source_urls
            return parsed

        # If JSON parsing fails, default to valid=False
        return {
            "valid": False,
            "reason": f"Could not determine availability of {medicine_name}",
            "raw_text": raw_text,
            "source_urls": source_urls,
        }

    except Exception as e:
        return {
            "valid": False,
            "reason": f"Validation error: {str(e)}",
            "source_urls": [],
        }


# ══════════════════════════════════════════════════════════════════
#  TOOL EXECUTOR — maps function_call.name → actual function
# ══════════════════════════════════════════════════════════════════

TOOL_REGISTRY = {
    "search_drug_composition": search_drug_composition,
    "search_drug_price":       search_drug_price,
    "validate_medicine_india": validate_medicine_india,
}

def execute_tool(name: str, args: dict) -> tuple[dict, list[str]]:
    """
    Execute a named tool with the given args.
    Returns (result_dict, source_urls).
    """
    fn = TOOL_REGISTRY.get(name)
    if not fn:
        return {"error": f"Unknown tool: {name}", "success": False}, []

    result = fn(**args)
    sources = result.get("source_urls", [])
    return result, sources


# ══════════════════════════════════════════════════════════════════
#  FUNCTION DECLARATIONS (for Gemini function-calling API)
# ══════════════════════════════════════════════════════════════════

SEARCH_COMPOSITION_DECLARATION = types.FunctionDeclaration(
    name="search_drug_composition",
    description=(
        "Search Indian pharmaceutical databases (1mg.com, pharmeasy.in, netmeds.com) "
        "for the exact drug composition — active ingredients and their strengths. "
        "Returns structured JSON with composition list and source URLs."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "drug_name": {
                "type": "STRING",
                "description": "Brand name or generic name of the drug (e.g. 'Crocin 500mg', 'Paracetamol')",
            },
            "search_focus": {
                "type": "STRING",
                "description": "Additional search context like 'tablet capsule syrup'",
            },
        },
        "required": ["drug_name"],
    },
)

SEARCH_PRICE_DECLARATION = types.FunctionDeclaration(
    name="search_drug_price",
    description=(
        "Search Indian pharmacy websites (1mg.com, pharmeasy.in, netmeds.com, apollopharmacy.in) "
        "for the current retail price of a drug in Indian Rupees (₹). "
        "Returns price per standard pack (10 or 15 tablet strip)."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "drug_name": {
                "type": "STRING",
                "description": "Brand name or generic name of the drug to price",
            },
            "pack_size": {
                "type": "STRING",
                "description": "Standard pack size to search for, e.g. '10 tablets strip'",
            },
        },
        "required": ["drug_name"],
    },
)

# Combined tool with both function declarations
DRUG_RESEARCH_TOOLS = types.Tool(
    function_declarations=[
        SEARCH_COMPOSITION_DECLARATION,
        SEARCH_PRICE_DECLARATION,
    ]
)


# ══════════════════════════════════════════════════════════════════
#  PRIVATE HELPERS
# ══════════════════════════════════════════════════════════════════

def _extract_sources(response) -> list[str]:
    """Extract source URLs from Gemini grounding metadata."""
    sources = []
    try:
        meta = response.candidates[0].grounding_metadata
        if meta and meta.grounding_chunks:
            for chunk in meta.grounding_chunks:
                if chunk.web and chunk.web.uri:
                    sources.append(chunk.web.uri)
    except (AttributeError, IndexError):
        pass
    return list(set(sources))[:5]  # Deduplicate, max 5 sources


def _extract_json(text: str) -> dict | None:
    """
    Extract the first JSON object from a text string.
    Handles markdown code blocks and bare JSON.
    """
    if not text:
        return None

    # Remove markdown code fences
    cleaned = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()

    # Try to find JSON object
    for pattern in [
        r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}",   # nested one level
        r"\{.*\}",                              # simple greedy
    ]:
        matches = re.findall(pattern, cleaned, re.DOTALL)
        for m in reversed(matches):           # try longest match first
            try:
                return json.loads(m)
            except json.JSONDecodeError:
                continue

    # Try the whole cleaned text
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def _parse_composition_text(text: str, drug_name: str) -> list[str]:
    """
    Fallback: extract composition ingredients from unstructured text.
    Looks for patterns like 'Ingredient Strength Unit'.
    """
    ingredients = []
    # Common patterns: "Paracetamol 500mg", "Amoxicillin 250 mg"
    patterns = [
        r"([A-Z][a-z]+(?:\s+[a-z]+)*)\s+(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|IU|iu|%|units?)\b",
        r"([A-Z][a-zA-Z\s\-]+?)\s+(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|IU|iu|%)\b",
    ]
    seen = set()
    for pat in patterns:
        for m in re.finditer(pat, text):
            entry = f"{m.group(1).strip()} {m.group(2)}{m.group(3)}"
            key = entry.lower()
            if key not in seen:
                seen.add(key)
                ingredients.append(entry)
    return ingredients[:8]   # max 8 ingredients


def _parse_price_text(text: str) -> tuple[float, str]:
    """
    Fallback: extract price from unstructured text.
    Returns (price_float, display_string).
    """
    # Pattern: ₹25.50 or Rs 25.50 or INR 25
    patterns = [
        r"[₹Rs\.INR]+\s*(\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?)\s*(?:rupees?|INR|Rs)",
        r"price[:\s]+(\d+(?:\.\d+)?)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            price = float(m.group(1))
            return price, f"₹{price:.2f}"
    return 0.0, "Price not available"
