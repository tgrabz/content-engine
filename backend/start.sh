#!/bin/bash
# Production start script
cd "$(dirname "$0")"
PORT=${PORT:-8000}
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
