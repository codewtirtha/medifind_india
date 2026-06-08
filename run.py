"""
MediFind India — Application Entry Point
─────────────────────────────────────────
Run with:
    python run.py
or:
    FLASK_ENV=development python run.py
"""

import os
import sys

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()       # load .env before importing settings

from config.settings import settings
from backend.app import app

if __name__ == "__main__":
    try:
        settings.validate()
    except ValueError as e:
        print(f"\n❌  Configuration error: {e}")
        print("    → Set GEMINI_API_KEY in your .env file (see .env.example)\n")
        sys.exit(1)

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║       MediFind India — AI Medicine Alternative Finder        ║
╠══════════════════════════════════════════════════════════════╣
║  Orchestrator : {settings.ORCHESTRATOR_MODEL:<46}║
║  Sub-Agents   : {settings.SUB_AGENT_MODEL:<46}║
║  Port         : {settings.PORT:<46}║
╚══════════════════════════════════════════════════════════════╝
    """)
    print(f"  → Open http://localhost:{settings.PORT} in your browser\n")

    app.run(
        host="0.0.0.0",
        port=settings.PORT,
        debug=settings.DEBUG,
        threaded=True,
    )
