#!/bin/bash
# Start backend dev server with reload excludes for video/template dirs
cd "$(dirname "$0")"
PORT=${PORT:-8000}
.venv/bin/python -m uvicorn app.main:app \
  --reload \
  --reload-exclude "exports/*" \
  --reload-exclude "downloads/*" \
  --reload-exclude "templates/*" \
  --port "$PORT"
