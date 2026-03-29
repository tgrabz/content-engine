#!/bin/bash
set -e

APP_NAME="Content Engine"
INSTALL_DIR="$HOME/.content-engine"
REPO_URL="https://github.com/tgrabz/content-engine.git"

echo ""
echo "=== Installing $APP_NAME ==="
echo ""

# ── Check prerequisites ──
missing=""
command -v git >/dev/null || missing="$missing git"
command -v python3 >/dev/null || missing="$missing python3"
command -v node >/dev/null || missing="$missing node"
command -v npm >/dev/null || missing="$missing npm"
command -v ffmpeg >/dev/null || missing="$missing ffmpeg"

if [ -n "$missing" ]; then
  echo "Missing required tools:$missing"
  echo ""
  if command -v brew >/dev/null; then
    echo "Installing via Homebrew..."
    for tool in $missing; do
      [ "$tool" = "node" ] && brew install node && continue
      [ "$tool" = "npm" ] && continue  # comes with node
      brew install "$tool"
    done
  else
    echo "Installing Homebrew first..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv 2>/dev/null)"
    for tool in $missing; do
      [ "$tool" = "node" ] && brew install node && continue
      [ "$tool" = "npm" ] && continue
      brew install "$tool"
    done
  fi
fi

# ── Clone repo ──
if [ -d "$INSTALL_DIR" ]; then
  echo "Updating existing installation..."
  cd "$INSTALL_DIR" && git pull --ff-only
else
  echo "Downloading $APP_NAME..."
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# ── Backend setup ──
echo "Setting up backend..."
cd backend

python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e .

if [ ! -f .env ]; then
  cp .env.example .env
  SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/SECRET_KEY=change-me/SECRET_KEY=$SECRET/" .env
  else
    sed -i "s/SECRET_KEY=change-me/SECRET_KEY=$SECRET/" .env
  fi
fi

cd ..

# ── Frontend setup ──
echo "Setting up frontend..."
cd frontend
npm install --silent
npm run build --silent
cd ..

# ── Create launcher script ──
LAUNCHER="$INSTALL_DIR/launch.sh"
cat > "$LAUNCHER" << 'LAUNCH'
#!/bin/bash
DIR="$HOME/.content-engine"
cd "$DIR/backend"

# Start backend
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

# Wait for backend to be ready
for i in {1..30}; do
  curl -s http://127.0.0.1:8000/api/health >/dev/null 2>&1 && break
  sleep 1
done

# Open browser
open "http://localhost:5173" 2>/dev/null || xdg-open "http://localhost:5173" 2>/dev/null

# Start frontend dev server (serves the UI)
cd "$DIR/frontend"
npx vite --host 127.0.0.1 --port 5173 &
FRONTEND_PID=$!

# Trap exit to clean up
cleanup() {
  kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
  exit 0
}
trap cleanup INT TERM

echo ""
echo "Content Engine is running at http://localhost:5173"
echo "Press Ctrl+C to stop"
echo ""

wait
LAUNCH
chmod +x "$LAUNCHER"

# ── Create macOS app ──
APP_DIR="$HOME/Applications/Content Engine.app"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

cat > "$APP_DIR/Contents/MacOS/Content Engine" << APPSCRIPT
#!/bin/bash
osascript -e 'tell application "Terminal"
  do script "~/.content-engine/launch.sh"
  activate
end tell'
APPSCRIPT
chmod +x "$APP_DIR/Contents/MacOS/Content Engine"

cat > "$APP_DIR/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>Content Engine</string>
  <key>CFBundleIdentifier</key>
  <string>com.contentengine.app</string>
  <key>CFBundleVersion</key>
  <string>1.0</string>
  <key>CFBundleExecutable</key>
  <string>Content Engine</string>
  <key>LSUIElement</key>
  <false/>
</dict>
</plist>
PLIST

echo ""
echo "=== Installation complete! ==="
echo ""
echo "BEFORE FIRST RUN:"
echo "  Edit ~/.content-engine/backend/.env with your Instagram credentials"
echo "  (IG_APP_ID, IG_APP_SECRET, PUBLIC_URL)"
echo ""
echo "TO LAUNCH:"
echo "  Double-click 'Content Engine' in ~/Applications"
echo "  Or run: ~/.content-engine/launch.sh"
echo ""
