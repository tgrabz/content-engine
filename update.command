#!/bin/bash
cd "$(dirname "$0")"

echo "→ Pulling latest code..."
git pull origin main

echo "→ Updating backend dependencies..."
cd backend && .venv/bin/pip install -q -r requirements.txt

echo "→ Updating frontend dependencies..."
cd ../frontend && npm ci --silent

echo ""
echo "  Updated! Run start.command to launch."
echo ""
