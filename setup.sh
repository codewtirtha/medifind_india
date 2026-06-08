#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  MediFind India — Setup Script
#  Usage:  bash setup.sh
# ─────────────────────────────────────────────────────────────

set -e

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║         MediFind India — Setup                           ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── 1. Python version check ──────────────────────────────────
PYTHON=$(command -v python3 || command -v python || true)
if [ -z "$PYTHON" ]; then
  echo "❌  Python 3.10+ is required. Install from https://python.org"
  exit 1
fi

PY_VER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  ✅  Python $PY_VER found at $PYTHON"

# ── 2. Virtual environment ───────────────────────────────────
if [ ! -d ".venv" ]; then
  echo "  📦  Creating virtual environment (.venv)…"
  $PYTHON -m venv .venv
fi
echo "  ✅  Virtual environment ready"

# Activate
if [ -f ".venv/Scripts/activate" ]; then
  # Windows Git Bash
  source .venv/Scripts/activate
else
  source .venv/bin/activate
fi

# ── 3. Install dependencies ──────────────────────────────────
echo "  📥  Installing dependencies from requirements.txt…"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo "  ✅  Dependencies installed"

# ── 4. Create .env if missing ────────────────────────────────
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  echo "  ⚠️   Created .env from .env.example"
  echo "       → Edit .env and add your GEMINI_API_KEY"
  echo "       → Get one free at: https://aistudio.google.com/app/apikey"
  echo ""
else
  echo "  ✅  .env file exists"
fi

# ── 5. Done ──────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Setup complete! To start the app:                       ║"
echo "║                                                          ║"
echo "║    source .venv/bin/activate   # (or .venv\\Scripts\\activate on Windows)"
echo "║    python run.py               ║"
echo "║                                                          ║"
echo "║  Then open: http://localhost:5000                        ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
