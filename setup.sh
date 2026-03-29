#!/bin/bash
set -e

echo "=== Content Engine Setup ==="
echo ""

# Backend
echo "Setting up backend..."
cd backend

if [ ! -f .env ]; then
  cp .env.example .env
  # Generate a random secret key
  SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/SECRET_KEY=change-me/SECRET_KEY=$SECRET/" .env
  else
    sed -i "s/SECRET_KEY=change-me/SECRET_KEY=$SECRET/" .env
  fi
  echo "Created .env with generated SECRET_KEY"
  echo ">>> Edit backend/.env and fill in your IG_APP_ID, IG_APP_SECRET, and PUBLIC_URL <<<"
else
  echo ".env already exists, skipping"
fi

python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt 2>/dev/null || .venv/bin/pip install -q -e ".[dev]" 2>/dev/null || .venv/bin/pip install -q -e .
echo "Backend dependencies installed"

cd ..

# Frontend
echo ""
echo "Setting up frontend..."
cd frontend
npm install --silent
echo "Frontend dependencies installed"

cd ..

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit backend/.env with your Instagram App credentials"
echo "  2. Start backend:  ./backend/dev.sh"
echo "  3. Start frontend: cd frontend && npm run dev"
echo ""
