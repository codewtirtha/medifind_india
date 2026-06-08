# Skill: Composition & Price Finder

## Overview
This skill documents how MediFind discovers, normalises, and scores drug composition and price data from Indian pharmacy websites.

---

## Data Discovery

### Composition Discovery
`search_drug_composition()` in `search_tools.py` finds:
- **Active pharmaceutical ingredients (APIs)**: e.g. "Paracetamol 500mg"
- **Salt names (INN)**: e.g. "Acetaminophen"
- **Combination formulas**: e.g. "Amoxicillin 500mg + Clavulanic Acid 125mg"

The search prompt instructs Gemini to:
1. Look on Indian pharmacy sites (1mg, PharmEasy, NetMeds, Apollo)
2. Extract the composition from product descriptions
3. Return a JSON list of ingredients with concentrations
4. Include the source URL

### Price Discovery
`search_drug_price()` finds:
- **MRP** (Maximum Retail Price) in ₹
- **Online pharmacy price** (often 10-20% less than MRP)
- **Pack size** normalisation (per-tablet price if needed)

The search prompt instructs Gemini to:
1. Find the standard pack (10 tablets / 30 capsules / most common)
2. Return the price in INR as a number
3. Include source URL for verification

---

## Normalisation (jaccard.py)

### `extract_ingredient_set(composition_text_or_list) → set[str]`

Converts raw composition data to a normalised ingredient set for Jaccard comparison.

**Steps:**
1. **Join**: if a list, join with space
2. **Lowercase**: `"Amoxicillin 500mg + Clavulanic Acid"` → `"amoxicillin 500mg + clavulanic acid"`
3. **Strip units**: remove `mg`, `mcg`, `ml`, `iu`, `%`, numbers
4. **Remove stopwords**: `"and"`, `"with"`, `"+"`, `"/"`, `"&"`
5. **Tokenise**: split on whitespace and punctuation
6. **Filter**: remove tokens shorter than 3 characters

**Example:**
```python
"Amoxicillin 500mg + Clavulanic Acid 125mg"
→ {"amoxicillin", "clavulanic", "acid"}
```

### `jaccard_similarity(set_a, set_b) → float`
```python
def jaccard_similarity(a: set, b: set) -> float:
    if not a and not b:
        return 1.0     # both empty → identical (unknown = equal)
    if not a or not b:
        return 0.0     # one empty → completely different
    return len(a & b) / len(a | b)
```

---

## Price Similarity

### `price_similarity(price_alt, price_original, all_prices) → float`

The price similarity measures how close the alternative's price is to the original, normalised across all alternatives.

```python
def price_similarity(price_alt, price_original, all_prices):
    if price_alt <= 0 or price_original <= 0:
        return 0.5   # neutral score when price unknown
    
    max_price = max(all_prices or [price_original, price_alt])
    if max_price == 0:
        return 1.0
    
    diff = abs(price_alt - price_original)
    raw_sim = 1.0 - (diff / max_price)
    return max(0.0, min(1.0, raw_sim))
```

A drug priced exactly the same as the original gets 1.0. A drug that is much more expensive gets a lower score.

---

## Composite Scoring

### `rank_alternatives(original, alternatives) → list[dict]`

```python
composite = PRICE_WEIGHT * price_sim + COMPOSITION_WEIGHT * jaccard_sim
```

Default weights: `PRICE_WEIGHT = 0.60`, `COMPOSITION_WEIGHT = 0.40`

Each ranked result includes:
```python
{
    "rank": 1,
    "composite_score": 87.3,          # 0–100
    "composition_similarity": 95.0,   # Jaccard × 100
    "price_similarity": 82.0,         # price closeness × 100
    "common_ingredients": [...],       # A ∩ B
    "missing_ingredients": [...],      # in original but not in alternative
    "extra_ingredients": [...],        # in alternative but not in original
    # + all original drug data fields
}
```

---

## Why 60:40 Price:Composition?

**Price (60%)** is weighted higher because:
- Indian patients are highly price-sensitive
- Therapeutic equivalence often only requires similar (not identical) composition
- The primary use case is cost savings for equivalent treatment

**Composition (40%)** ensures:
- Core active ingredients are preserved
- Safety: wildly different compositions are ranked lower
- Efficacy: most similar formulations are preferred

The weights are configurable in `config/settings.py`:
```python
PRICE_WEIGHT = float(os.getenv("PRICE_WEIGHT", "0.60"))
COMPOSITION_WEIGHT = float(os.getenv("COMPOSITION_WEIGHT", "0.40"))
```

---

## Edge Cases

| Case | Handling |
|---|---|
| Composition not found | `composition = []`, jaccard = 0.0 → ranked lower |
| Price not found | `price_inr = 0.0`, price_sim = 0.5 (neutral) |
| Both compositions empty | jaccard = 1.0 (unknown = equal, by convention) |
| Identical drug (same composition, similar price) | Scores near 100% |
| Combination vs single ingredient | Jaccard catches partial matches fairly |

---

## Files
- `backend/similarity/jaccard.py` — Jaccard computation + ranking
- `backend/tools/search_tools.py` — Composition + price search tools
- `backend/utils/helpers.py` — `extract_price_numeric()`, `clean_medicine_name()`
