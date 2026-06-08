"""
MediFind India — Jaccard Similarity & Ranking Module

Implements:
  1. Jaccard similarity on drug composition ingredient SETS
  2. Price similarity normalised to [0, 1]
  3. Composite score = 0.60 × price_similarity + 0.40 × jaccard_similarity

Jaccard Similarity (Jaccard, 1901):
  J(A, B) = |A ∩ B| / |A ∪ B|
  where A = ingredient set of original, B = ingredient set of alternative.

Price Similarity:
  We want drugs close in price to score higher.
  Closer to the original price → higher score.
  score = 1 − |p_alt − p_orig| / max(p_range, 1)
  clamped to [0, 1].

Composite Score (60:40 price:composition):
  S = 0.60 × price_score + 0.40 × jaccard_score
"""

from __future__ import annotations
import re
from typing import Optional


# ═══════════════════════════════════════════════════════════════════
#  INGREDIENT EXTRACTION
# ═══════════════════════════════════════════════════════════════════

# Units to strip when normalising ingredient names
_UNIT_PATTERN = re.compile(
    r"\s+\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu|units?|%|mmol|meq)\b.*$",
    re.IGNORECASE,
)
# Common filler words to ignore
_STOP_WORDS = {
    "and", "with", "plus", "each", "tablet", "capsule", "contains",
    "per", "ml", "of", "in", "ip", "bp", "usp", "eq", "equivalent",
}


def extract_ingredient_set(composition: list[str]) -> set[str]:
    """
    Convert a composition list into a normalised set of ingredient names.

    Examples:
      ["Paracetamol 500mg", "Caffeine 30mg"] → {"paracetamol", "caffeine"}
      ["Amoxicillin 250mg", "Clavulanic Acid 125mg"] → {"amoxicillin", "clavulanic acid"}
    """
    ingredients: set[str] = set()
    for item in composition:
        if not item or not isinstance(item, str):
            continue
        # Strip strength unit and everything after
        clean = _UNIT_PATTERN.sub("", item)
        # Lowercase and strip punctuation
        clean = re.sub(r"[^a-z0-9 ]", " ", clean.lower())
        # Remove stop words
        words = [w for w in clean.split() if w not in _STOP_WORDS and len(w) > 2]
        if words:
            ingredients.add(" ".join(words).strip())
    return ingredients


# ═══════════════════════════════════════════════════════════════════
#  JACCARD SIMILARITY
# ═══════════════════════════════════════════════════════════════════

def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """
    Compute Jaccard similarity between two ingredient sets.

    J(A, B) = |A ∩ B| / |A ∪ B|

    Returns 0.0 if either set is empty.
    Returns 1.0 if both sets are identical.
    """
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union        = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


# ═══════════════════════════════════════════════════════════════════
#  PRICE SIMILARITY
# ═══════════════════════════════════════════════════════════════════

def price_similarity(
    price_alt: Optional[float],
    price_original: Optional[float],
    all_prices: list[float],
) -> float:
    """
    Compute price similarity of an alternative relative to the original medicine.

    We reward alternatives that are:
      1. Close in price to the original (or cheaper)
      2. Not wildly more expensive

    Formula:
      - Compute price range of all alternatives + original
      - Score = 1 − |price_alt − price_original| / price_range
      - Clamp to [0, 1]
      - If price unavailable, return neutral 0.5

    Args:
        price_alt:      Price of alternative in INR (or None if unknown)
        price_original: Price of original medicine in INR (or None)
        all_prices:     All prices (alternatives + original) for normalisation

    Returns:
        float in [0, 1]
    """
    if price_alt is None or price_alt <= 0:
        return 0.5   # neutral score when price unknown

    if price_original is None or price_original <= 0:
        # No reference price — just rank by absolute price (cheaper = better)
        valid = [p for p in all_prices if p and p > 0]
        if not valid:
            return 0.5
        min_p, max_p = min(valid), max(valid)
        if max_p == min_p:
            return 1.0
        return 1.0 - (price_alt - min_p) / (max_p - min_p)

    valid = [p for p in all_prices if p and p > 0]
    if not valid:
        return 0.5

    min_p = min(valid)
    max_p = max(valid)
    price_range = max_p - min_p

    if price_range == 0:
        return 1.0   # all prices the same

    diff  = abs(price_alt - price_original)
    score = 1.0 - diff / price_range
    return max(0.0, min(1.0, score))


# ═══════════════════════════════════════════════════════════════════
#  COMPOSITE RANKING (60:40 price:composition)
# ═══════════════════════════════════════════════════════════════════

def rank_alternatives(original: dict, alternatives: list[dict]) -> list[dict]:
    """
    Rank alternatives using a composite score:
      S = 0.60 × price_similarity + 0.40 × jaccard_composition_similarity

    Args:
        original:     Original medicine dict (must have 'composition' and optionally 'price_inr')
        alternatives: List of alternative medicine dicts from sub-agents

    Returns:
        Sorted list (highest composite score first) with scoring fields added.
    """
    from config.settings import settings

    original_ingredients = extract_ingredient_set(original.get("composition") or [])
    original_price       = _safe_price(original)

    # Collect all prices for normalisation
    all_prices = [_safe_price(a) for a in alternatives] + [original_price]
    all_prices = [p for p in all_prices if p and p > 0]

    scored: list[dict] = []

    for alt in alternatives:
        alt_ingredients = extract_ingredient_set(alt.get("composition") or [])
        alt_price       = _safe_price(alt)

        # Jaccard similarity on ingredient sets
        j_score = jaccard_similarity(original_ingredients, alt_ingredients)

        # Price similarity
        p_score = price_similarity(alt_price, original_price, all_prices)

        # Composite score (60% price, 40% composition)
        composite = (
            settings.PRICE_WEIGHT        * p_score +
            settings.COMPOSITION_WEIGHT  * j_score
        )

        # Common ingredients for display
        common  = sorted(original_ingredients & alt_ingredients)
        missing = sorted(original_ingredients - alt_ingredients)
        extra   = sorted(alt_ingredients - original_ingredients)

        enriched = {
            **alt,
            # Scores (0–100 for display)
            "composition_similarity": round(j_score * 100, 1),
            "price_similarity":       round(p_score * 100, 1),
            "composite_score":        round(composite * 100, 1),
            # Raw floats for sorting
            "_j_score":    j_score,
            "_p_score":    p_score,
            "_composite":  composite,
            # Debug / display
            "common_ingredients":  common,
            "missing_ingredients": missing,
            "extra_ingredients":   extra,
            "original_ingredients": sorted(original_ingredients),
        }
        scored.append(enriched)

    # Sort by composite score descending, then by price ascending as tiebreaker
    scored.sort(key=lambda x: (-x["_composite"], x.get("price_inr") or 9999))

    # Add rank
    for rank, item in enumerate(scored, start=1):
        item["rank"] = rank

    return scored


# ═══════════════════════════════════════════════════════════════════
#  PRIVATE HELPERS
# ═══════════════════════════════════════════════════════════════════

def _safe_price(d: dict) -> float:
    """Safely extract price_inr from a dict."""
    p = d.get("price_inr") or d.get("typical_price_inr") or 0.0
    try:
        return float(p)
    except (TypeError, ValueError):
        return 0.0
