"""
MediFind India - Configuration Settings
Loads environment variables and defines global configuration.
"""

import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # ── API Keys ─────────────────────────────────────────────
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # ── Models ───────────────────────────────────────────────
    # Orchestrator: Gemini 3.5 Flash with thinking for reasoning + search grounding
    ORCHESTRATOR_MODEL: str = os.getenv("ORCHESTRATOR_MODEL", "gemini-3.5-flash")
    # Sub-agents: Gemini 3.1 Flash Lite for speed + search grounding + function calling
    SUB_AGENT_MODEL: str = os.getenv("SUB_AGENT_MODEL", "gemini-3.1-flash-lite")
    # Search model: Gemini 3.1 Flash Lite for tool-level searches
    SEARCH_MODEL: str = os.getenv("SEARCH_MODEL", "gemini-3.1-flash-lite")

    # ── Thinking Configuration ────────────────────────────────
    THINKING_BUDGET: int = int(os.getenv("THINKING_BUDGET", "8000"))

    # ── Agent Configuration ───────────────────────────────────
    MAX_ALTERNATIVES: int = 10
    MAX_REACT_TURNS: int = 8          # Max ReAct loop iterations per sub-agent
    MAX_SEARCH_RESULTS: int = 5

    # ── Indian Pharmacy Websites (search focus) ───────────────
    INDIAN_PHARMACY_SITES = [
        "1mg.com",
        "pharmeasy.in",
        "netmeds.com",
        "apollopharmacy.in",
        "medplusmart.com",
        "tatahealth.com",
        "practo.com",
    ]

    # ── Scoring Weights ───────────────────────────────────────
    PRICE_WEIGHT: float = 0.60          # 60% weight on price similarity
    COMPOSITION_WEIGHT: float = 0.40    # 40% weight on Jaccard composition similarity

    # ── Server ───────────────────────────────────────────────
    PORT: int = int(os.getenv("PORT", "5000"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    HOST: str = "0.0.0.0"

    def validate(self):
        if not self.GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY is not set. "
                "Please copy .env.example to .env and add your key."
            )

settings = Settings()
