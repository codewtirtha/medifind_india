"""
MediFind India — Utility Helpers
Shared utilities for JSON parsing, text cleaning, and data safety.
"""

import json
import re
from typing import Any


def safe_json_loads(text: str) -> Any:
    """
    Robustly parse JSON from text that may contain markdown code fences
    or extra prose around the JSON object.
    """
    if not text:
        return None

    # Remove markdown code fences
    cleaned = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()

    # 1. Try direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 2. Try to find the outermost { } block
    # Handle one level of nesting
    depth = 0
    start = -1
    for i, ch in enumerate(cleaned):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                candidate = cleaned[start: i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    start = -1

    # 3. Try the last JSON-looking thing
    matches = re.findall(r"\{[^{}]+\}", cleaned, re.DOTALL)
    for m in reversed(matches):
        try:
            return json.loads(m)
        except json.JSONDecodeError:
            continue

    return None


def clean_medicine_name(name: str) -> str:
    """
    Clean and normalise a medicine name input.
    - Strip whitespace
    - Title-case for consistent lookup
    - Remove excess punctuation
    """
    if not name:
        return ""
    name = name.strip()
    # Remove special chars except hyphen, parentheses, digits
    name = re.sub(r"[^\w\s\-()\+]", "", name)
    return name.strip()


def extract_price_numeric(price_str: str) -> float:
    """
    Extract numeric price from strings like '₹25', 'Rs. 25.50', '25 INR'.
    Returns 0.0 if extraction fails.
    """
    if not price_str:
        return 0.0
    if isinstance(price_str, (int, float)):
        return float(price_str)

    m = re.search(r"(\d+(?:\.\d+)?)", str(price_str))
    if m:
        return float(m.group(1))
    return 0.0


def truncate(text: str, max_chars: int = 200) -> str:
    """Truncate text to max_chars, adding ellipsis if needed."""
    if not text or len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"


def format_inr(amount: float) -> str:
    """Format a float as an INR currency string."""
    if not amount or amount <= 0:
        return "Price N/A"
    return f"₹{amount:.2f}"
