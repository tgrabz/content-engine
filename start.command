#!/bin/bash
cd "$(dirname "$0")"

echo ""
echo "  Checking for updates..."
git pull origin main --ff-only 2>/dev/null && echo "  Updated!" || echo "  Already up to date."

# Auto-install any new deps
cd backend && .venv/bin/pip install -q -r requirements.txt 2>/dev/null && cd ..
cd frontend && npm ci --silent 2>/dev/null && cd ..

echo ""
echo "  Starting Content Engine..."
echo ""

# Start backend
cd backend
.venv/bin/python -m uvicorn app.main:app \
    --reload \
    --reload-exclude "exports/*" \
    --reload-exclude "downloads/*" \
    --reload-exclude "templates/*" \
    --port 8000 &
BACKEND_PID=$!

# Start frontend
cd ../frontend
npm run dev &
FRONTEND_PID=$!

# Wait for servers to start
sleep 3

# Open browser
open http://localhost:5173

echo ""
echo "  Content Engine is running!"
echo "  Frontend: http://localhost:5173"
echo "  Backend:  http://localhost:8000"
echo ""
echo "  Press Ctrl+C to stop"
echo ""

# Wait and cleanup on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
