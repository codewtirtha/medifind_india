# MediFind India 🇮🇳

**AI-Powered Medicine Alternative Finder for the Indian Pharmaceutical Market**

A multi-agent AI system that finds ranked alternatives to any Indian medicine using **Gemini 3.5 Flash** (with extended thinking), **10 parallel ReAct research agents**, Google Search grounding, and **Jaccard similarity scoring** — all streamed live to a dark-themed frontend via Server-Sent Events.

---

## ✨ Features

| Capability | Implementation |
|---|---|
| **Medicine validation** | Gemini + Google Search confirms the drug exists in India |
| **Chain-of-thought orchestration** | Gemini 3.5 Flash with `thinking_budget=8000` reasons about alternatives |
| **10 ReAct sub-agents** | Each agent runs Thought→Action→Observation loops with tool calls |
| **Live streaming** | Every thought, tool call, and result streamed via SSE |
| **Jaccard similarity** | Ingredient-set intersection/union on normalised compositions |
| **Weighted scoring** | 60 % price similarity + 40 % Jaccard = composite rank |
| **Full tool audit** | Every tool call logged with source URLs at the end |
| **Indian context** | All searches restricted to 1mg, PharmEasy, NetMeds, Apollo Pharmacy |

---

## 🗂 Repository Structure

```
medifind-india/
├── run.py                          ← Entry point
├── setup.sh                        ← One-command installer
├── requirements.txt
├── .env.example                    ← Copy → .env and add API key
│
├── config/
│   └── settings.py                 ← All config / env vars
│
├── backend/
│   ├── app.py                      ← Flask + SSE endpoint
│   ├── agents/
│   │   ├── orchestrator.py         ← Phase 1-4 pipeline controller
│   │   ├── sub_agent.py            ← Per-drug agent wrapper
│   │   ├── react_engine.py         ← ReAct Thought→Action→Observation loop
│   │   └── prompts.py              ← All LLM prompt templates
│   ├── tools/
│   │   └── search_tools.py         ← Tool definitions + Gemini dispatchers
│   ├── similarity/
│   │   └── jaccard.py              ← Jaccard + price similarity + ranking
│   └── utils/
│       └── helpers.py              ← JSON parsing, text cleaning
│
├── frontend/
│   ├── index.html                  ← Full app shell
│   ├── css/styles.css              ← Dark theme, saffron/gold palette
│   └── js/
│       ├── components.js           ← Pure DOM component builders
│       ├── stream.js               ← SSE event router + UI state object
│       └── main.js                 ← App bootstrap + form handling
│
└── skills/
    ├── orchestrator_agent.md       ← How the orchestrator works
    ├── drug_research_agent.md      ← How sub-agents work
    ├── react_agent_pattern.md      ← ReAct pattern reference
    ├── web_search_tool.md          ← Search tool capabilities
    └── composition_price_finder.md ← Drug data retrieval patterns
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- A free **Gemini API key** from [Google AI Studio](https://aistudio.google.com/app/apikey)

### 1 — Clone & enter the project

```bash
git clone <repo-url>
cd medifind-india
```

### 2 — Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

You should see `(.venv)` appear at the start of your prompt.

### 3 — Install dependencies

> ⚠️ **Do this manually** — `bash setup.sh` installs packages inside the script's subprocess, but that activation does not persist back to your terminal. Always run this in your active shell:

```bash
pip install -r requirements.txt
```

### 4 — Set up your `.env` file

```bash
cp .env.example .env
```

Then open `.env` and fill in your API key:

```
GEMINI_API_KEY=AIza...your_key_here
```

Get a free key at [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) — no billing required.

### 5 — Run

```bash
python run.py
```

Then open **http://localhost:5000** in your browser.

---

## 🔧 Troubleshooting

### `ModuleNotFoundError: No module named 'flask'`

Your virtual environment is active but packages were not installed into it. Fix:

```bash
pip install -r requirements.txt
```

### `GEMINI_API_KEY is not set`

You haven't created a `.env` file yet:

```bash
cp .env.example .env
# Then edit .env and add: GEMINI_API_KEY=your_key_here
```

### `Port 5000 is in use` (macOS)

macOS Monterey and later reserves port 5000 for **AirPlay Receiver** (the `ControlCenter` process). Two fixes:

**Option A — Change the port** (quickest): add this to your `.env`:
```
PORT=5001
```
Then open `http://localhost:5001`.

**Option B — Disable AirPlay Receiver permanently**:
> System Settings → General → AirDrop & Handoff → AirPlay Receiver → **Off**

Then the app runs on the default port 5000.

### To override any model without editing code

Add any of these to your `.env`:
```
ORCHESTRATOR_MODEL=gemini-3.5-flash
SUB_AGENT_MODEL=gemini-3.1-flash-lite
SEARCH_MODEL=gemini-3.1-flash-lite
PORT=5001
```

---

## 🧠 How It Works — Pipeline

```
User Input: "Augmentin 625"
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  Phase 1 — VALIDATION                                    │
│  validate_medicine_india("Augmentin 625")                │
│  → Gemini 3.1 Flash Lite + Google Search                 │
│  → Confirms brand, manufacturer, composition, price      │
└────────────────────────┬────────────────────────────────┘
                         │ valid ✅
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Phase 2 — DISCOVERY  (Gemini 3.5 Flash + thinking)     │
│  Extended thinking visible on screen in real time        │
│  → Finds 10 therapeutically equivalent alternatives      │
│  → Writes a custom research prompt for EACH alternative  │
│  → Streamed token-by-token to the frontend               │
└────────────────────────┬────────────────────────────────┘
                         │ 10 alternatives
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Phase 3 — RESEARCH  (10 × ReAct Sub-Agents)            │
│  For each drug, one agent runs a ReAct loop:             │
│    Thought → Action (tool call) → Observation → …        │
│  Tools used:                                             │
│    search_drug_composition(drug, focus)                  │
│    search_drug_price(drug, pack_size)                    │
│  All thoughts, tool calls, source URLs streamed live     │
└────────────────────────┬────────────────────────────────┘
                         │ 10 results
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Phase 4 — RANKING  (Jaccard + Price similarity)         │
│  Composition similarity: Jaccard(ingredientSetA, B)      │
│  Price similarity: normalised closeness to original ₹    │
│  Composite = 0.6 × price + 0.4 × composition            │
│  → Top-10 ranked cards displayed with score breakdown    │
└─────────────────────────────────────────────────────────┘
```

---

## 🤖 Agent Architecture

### Orchestrator (Gemini 3.5 Flash)
- Uses **extended thinking** (`include_thoughts=True`) to reason about which alternatives to search
- Generates a **custom prompt** for each sub-agent (meta-prompting)
- Searches via built-in **Google Search grounding** (`types.Tool(google_search=types.GoogleSearch())`)

### Sub-Agent ReAct Loop (Gemini 3.1 Flash Lite)
Each sub-agent follows the **ReAct** (Reasoning + Acting) pattern from [Yao et al., 2023]:
```
Thought: I need to find the composition of [drug] on Indian pharmacy sites.
Action: search_drug_composition(drug_name="[drug]", search_focus="composition ingredients")
Observation: [tool result with sources]
Thought: Now I need the price.
Action: search_drug_price(drug_name="[drug]", pack_size="standard")
Observation: [tool result with price]
Thought: I have all the information.
Final Answer: { "composition": [...], "price_inr": ... }
```

### Tool Definitions
| Tool | Purpose | Inputs |
|---|---|---|
| `validate_medicine_india` | Check drug exists in India | `medicine_name` |
| `search_drug_composition` | Find active ingredients | `drug_name`, `search_focus` |
| `search_drug_price` | Find current Indian price | `drug_name`, `pack_size` |

---

## ⚖️ Jaccard Similarity

The composition similarity between the original medicine and each alternative is computed as:

```
Jaccard(A, B) = |A ∩ B| / |A ∪ B|
```

Where `A` and `B` are sets of normalised active ingredients (lowercase, units stripped, stopwords removed).

**Composite score:**
```
score = 0.60 × price_similarity + 0.40 × jaccard_similarity
```

Price similarity is normalised: `1 - |price_alt - price_original| / max(all_prices)`.

---

## 🌐 SSE Event Reference

The backend streams these events on `GET /api/search?medicine=...`:

| Event | When emitted | Key fields |
|---|---|---|
| `pipeline_start` | Search begins | `medicine` |
| `phase` | Phase changes | `phase`, `message` |
| `validation_success` | Drug found | `data` (brand, composition, price) |
| `validation_failed` | Drug not found | `reason`, `suggestion` |
| `orchestrator_thinking` | Thought tokens | `text` |
| `orchestrator_response` | Final plan text | `text` |
| `alternatives_found` | 10 drugs ready | `alternatives`, `count` |
| `agent_deploy` | Agent created | `agent_id`, `drug_name` |
| `agent_thinking` | Agent thought | `agent_id`, `thought` |
| `tool_call` | Tool invoked | `agent_id`, `tool`, `purpose`, `input` |
| `tool_result` | Tool returned | `agent_id`, `tool`, `sources` |
| `agent_complete` | Agent finished | `agent_id`, `data` (composition, price) |
| `similarity_score` | One score computed | `drug_name`, `composite_score` |
| `final_results` | All ranked | `results`, `count` |
| `tool_summary` | Audit log | `all_tool_calls`, `total_calls` |
| `heartbeat` | Keep-alive (15 s) | — |
| `complete` | Stream done | — |
| `error` | Pipeline error | `message` |

---

## 🛠 Configuration

All config lives in `config/settings.py` and is overridable via `.env`:

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | *required* | Your Gemini API key |
| `ORCHESTRATOR_MODEL` | `gemini-3.5-flash` | Model for orchestration + thinking |
| `SUB_AGENT_MODEL` | `gemini-3.1-flash-lite` | Model for ReAct sub-agents |
| `MAX_ALTERNATIVES` | `10` | Number of alternatives to find |
| `MAX_REACT_TURNS` | `8` | Max tool-call iterations per agent |
| `THINKING_BUDGET` | `8000` | Thinking token budget for orchestrator |
| `PRICE_WEIGHT` | `0.60` | Weight for price in composite score |
| `COMPOSITION_WEIGHT` | `0.40` | Weight for Jaccard in composite score |
| `PORT` | `5000` | Flask server port |
| `DEBUG` | `false` | Flask debug mode |

---

## 🔒 Indian Pharmacy Sites Searched

All agent searches are restricted to these verified Indian pharmacy platforms:
- **1mg.com** — tata.1mg.com
- **PharmEasy** — pharmeasy.in
- **NetMeds** — netmeds.com
- **Apollo Pharmacy** — apollopharmacy.in
- **MedPlus** — medplusmart.com

---

## 📚 References

- [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629) — Yao et al., 2023
- [Chain-of-Thought Prompting Elicits Reasoning in Large Language Models](https://arxiv.org/abs/2201.11903) — Wei et al., 2022
- [Google Gemini Gen AI SDK (Python)](https://github.com/googleapis/python-genai)
- [Gemini API: Thinking](https://ai.google.dev/gemini-api/docs/thinking)

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch
3. Make changes
4. Run a quick test with `python run.py` and try a search
5. Open a PR

---

## 📄 Licence

MIT — free to use, modify, and distribute.
