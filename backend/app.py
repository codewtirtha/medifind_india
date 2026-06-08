"""
MediFind India — Flask Backend
Serves the frontend and exposes an SSE streaming endpoint
that runs the full MediFind pipeline.

Routes:
  GET /           → index.html
  GET /api/search → SSE stream (query param: medicine=...)
  GET /api/health → Health check
"""

import json
import os
import sys
import time

from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import settings
from backend.agents.orchestrator import MedicineFindOrchestrator

# ──────────────────────────────────────────────────────────────────
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

app = Flask(
    __name__,
    static_folder=os.path.abspath(FRONTEND_DIR),
    static_url_path="",
)
CORS(app, resources={r"/api/*": {"origins": "*"}})


# ══════════════════════════════════════════════════════════════════
#  STATIC ROUTES
# ══════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "model": settings.ORCHESTRATOR_MODEL})


# ══════════════════════════════════════════════════════════════════
#  SSE SEARCH ENDPOINT
# ══════════════════════════════════════════════════════════════════

@app.route("/api/search")
def search():
    """
    Main SSE endpoint.
    Streams events from the MediFind pipeline as 'data: <json>\n\n' lines.

    Query params:
      medicine (str, required): Name of the medicine to research
    """
    medicine = request.args.get("medicine", "").strip()

    if not medicine:
        return jsonify({"error": "medicine query parameter is required"}), 400

    # Validate API key is set
    try:
        settings.validate()
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 500

    def generate():
        orchestrator = MedicineFindOrchestrator()
        last_heartbeat = time.time()

        try:
            for event in orchestrator.run(medicine):
                payload = json.dumps(event, ensure_ascii=False)
                yield f"data: {payload}\n\n"

                # Keep-alive heartbeat every 15 s to prevent proxy timeouts
                now = time.time()
                if now - last_heartbeat > 15:
                    yield "data: {\"type\":\"heartbeat\"}\n\n"
                    last_heartbeat = now

        except Exception as exc:
            error_event = {
                "type":    "error",
                "message": str(exc),
            }
            yield f"data: {json.dumps(error_event)}\n\n"

        finally:
            yield "data: {\"type\":\"complete\"}\n\n"

    return Response(
        generate(),
        content_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":       "keep-alive",
        },
    )
