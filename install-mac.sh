#!/bin/bash
# Content Engine — Mac Installer
# Run with: curl -fsSL https://raw.githubusercontent.com/tgrabz/content-engine/main/install-mac.sh | bash

set -e

REPO="https://github.com/tgrabz/content-engine.git"
INSTALL_DIR="$HOME/content-engine"
DB_URL="postgresql://postgres:KbmcJjwkiYohSbOujdUiQBAsVOiHPUHU@gondola.proxy.rlwy.net:56830/railway"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║       Content Engine Installer       ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# ── Check / install Homebrew ──
if ! command -v brew &>/dev/null; then
    echo "→ Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add to path for Apple Silicon
    if [ -f /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
fi

# ── Check / install Python ──
if ! command -v python3 &>/dev/null; then
    echo "→ Installing Python..."
    brew install python@3.12
fi

# ── Check / install Node.js ──
if ! command -v node &>/dev/null; then
    echo "→ Installing Node.js..."
    brew install node
fi

# ── Check / install ffmpeg ──
if ! command -v ffmpeg &>/dev/null; then
    echo "→ Installing ffmpeg..."
    brew install ffmpeg
fi

# ── Clone or update repo ──
if [ -d "$INSTALL_DIR" ]; then
    echo "→ Updating existing install..."
    cd "$INSTALL_DIR"
    git pull origin main
else
    echo "→ Cloning Content Engine..."
    git clone "$REPO" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# ── Backend setup ──
echo "→ Setting up Python environment..."
cd "$INSTALL_DIR/backend"

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

.venv/bin/pip install -q -r requirements.txt

# ── Create .env if it doesn't exist ──
if [ ! -f ".env" ]; then
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    cat > .env << ENVEOF
SECRET_KEY=$SECRET_KEY
DATABASE_URL=$DB_URL
ENVEOF
    echo "→ Created .env with shared database connection"
fi

# ── Auto-detect Google Drive for MEDIA_ROOT ──
GDRIVE_DIR=""
for dir in "$HOME/Library/CloudStorage"/GoogleDrive-*/; do
    if [ -d "$dir" ]; then
        MEDIA_DIR="${dir}My Drive/content-engine-media"
        if [ -d "$MEDIA_DIR" ]; then
            GDRIVE_DIR="$MEDIA_DIR"
        fi
    fi
done

if [ -n "$GDRIVE_DIR" ]; then
    # Add MEDIA_ROOT if not already in .env
    if ! grep -q "MEDIA_ROOT" .env; then
        echo "MEDIA_ROOT=$GDRIVE_DIR" >> .env
        echo "→ Found Google Drive media folder: $GDRIVE_DIR"
    fi
fi

# ── Frontend setup ──
echo "→ Installing frontend dependencies..."
cd "$INSTALL_DIR/frontend"
npm ci --silent

# ── Create start script ──
cat > "$INSTALL_DIR/start.command" << 'STARTEOF'
#!/bin/bash
cd "$(dirname "$0")"

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
STARTEOF
chmod +x "$INSTALL_DIR/start.command"

# ── Create update script ──
cat > "$INSTALL_DIR/update.command" << 'UPDATEEOF'
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
UPDATEEOF
chmod +x "$INSTALL_DIR/update.command"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║         Installation Complete!       ║"
echo "  ╚══════════════════════════════════════╝"
echo ""
echo "  To start:  double-click ~/content-engine/start.command"
echo "  To update: double-click ~/content-engine/update.command"
echo ""
echo "  Or from terminal:"
echo "    cd ~/content-engine && ./start.command"
echo ""
