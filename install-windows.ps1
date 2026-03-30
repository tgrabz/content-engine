# Content Engine — Windows Installer
# Run with: irm https://raw.githubusercontent.com/tgrabz/content-engine/main/install-windows.ps1 | iex

$ErrorActionPreference = "Stop"

$REPO = "https://github.com/tgrabz/content-engine.git"
$INSTALL_DIR = "$env:USERPROFILE\content-engine"
$DB_URL = if ($env:CONTENT_ENGINE_DB_URL) { $env:CONTENT_ENGINE_DB_URL } else { "postgresql://postgres:KbmcJjwkiYohSbOujdUiQBAsVOiHPUHU@gondola.proxy.rlwy.net:56830/railway" }

Write-Host ""
Write-Host "  ======================================" -ForegroundColor Cyan
Write-Host "       Content Engine Installer" -ForegroundColor Cyan
Write-Host "  ======================================" -ForegroundColor Cyan
Write-Host ""

# ── Check / install Python ──
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "-> Installing Python via winget..."
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}

# ── Check / install Node.js ──
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "-> Installing Node.js via winget..."
    winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}

# ── Check / install Git ──
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "-> Installing Git via winget..."
    winget install Git.Git --accept-package-agreements --accept-source-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}

# ── Check / install ffmpeg ──
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "-> Installing ffmpeg via winget..."
    winget install Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}

# ── Clone or update repo ──
if (Test-Path $INSTALL_DIR) {
    Write-Host "-> Updating existing install..."
    Set-Location $INSTALL_DIR
    git pull origin main
} else {
    Write-Host "-> Cloning Content Engine..."
    git clone $REPO $INSTALL_DIR
    Set-Location $INSTALL_DIR
}

# ── Backend setup ──
Write-Host "-> Setting up Python environment..."
Set-Location "$INSTALL_DIR\backend"

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

& .venv\Scripts\pip install -q -r requirements.txt

# ── Create .env if it doesn't exist ──
if (-not (Test-Path ".env")) {
    $SECRET = python -c "import secrets; print(secrets.token_urlsafe(32))"
    @"
SECRET_KEY=$SECRET
DATABASE_URL=$DB_URL
"@ | Out-File -FilePath ".env" -Encoding utf8
    Write-Host "-> Created .env with shared database connection"
}

# ── Auto-detect Google Drive for MEDIA_ROOT ──
$gdriveBase = "$env:USERPROFILE\Google Drive\My Drive\content-engine-media"
if (-not (Test-Path $gdriveBase)) {
    # Try alternate Google Drive path
    $gdriveBase = "$env:USERPROFILE\GoogleDrive\My Drive\content-engine-media"
}
if (Test-Path $gdriveBase) {
    $envContent = Get-Content ".env" -Raw
    if ($envContent -notmatch "MEDIA_ROOT") {
        Add-Content ".env" "MEDIA_ROOT=$gdriveBase"
        Write-Host "-> Found Google Drive media folder: $gdriveBase"
    }
}

# ── Frontend setup ──
Write-Host "-> Installing frontend dependencies..."
Set-Location "$INSTALL_DIR\frontend"
npm ci --silent

# ── Create start script ──
@'
@echo off
title Content Engine
cd /d "%~dp0"

echo   Checking for updates...
git pull origin main --ff-only 2>nul && echo   Updated! || echo   Already up to date.
cd backend && .venv\Scripts\pip install -q -r requirements.txt 2>nul && cd ..
cd frontend && npm ci --silent 2>nul && cd ..

echo.
echo   Starting Content Engine...
echo.

start "Content Engine Updater" /min cmd /c "cd backend && .venv\Scripts\python auto_updater.py"

start "Content Engine Backend" /min cmd /c "cd backend && .venv\Scripts\python -m uvicorn app.main:app --reload --reload-exclude exports/* --reload-exclude downloads/* --reload-exclude templates/* --port 8000"

start "Content Engine Frontend" /min cmd /c "cd frontend && npm run dev"

timeout /t 4 /nobreak > nul

start http://localhost:5173

echo.
echo   Content Engine is running!
echo   Frontend: http://localhost:5173
echo   Backend:  http://localhost:8000
echo.
echo   Close this window to stop.
pause
taskkill /fi "windowtitle eq Content Engine Updater" /f > nul 2>&1
taskkill /fi "windowtitle eq Content Engine Backend" /f > nul 2>&1
taskkill /fi "windowtitle eq Content Engine Frontend" /f > nul 2>&1
'@ | Out-File -FilePath "$INSTALL_DIR\Start Content Engine.bat" -Encoding ascii

# ── Create update script ──
@'
@echo off
title Content Engine Update
cd /d "%~dp0"

echo -> Pulling latest code...
git pull origin main

echo -> Updating backend dependencies...
cd backend && .venv\Scripts\pip install -q -r requirements.txt

echo -> Updating frontend dependencies...
cd ..\frontend && npm ci --silent

echo.
echo   Updated! Run "Start Content Engine.bat" to launch.
echo.
pause
'@ | Out-File -FilePath "$INSTALL_DIR\Update Content Engine.bat" -Encoding ascii

# ── Create desktop shortcut ──
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\Content Engine.lnk")
$Shortcut.TargetPath = "$INSTALL_DIR\Start Content Engine.bat"
$Shortcut.WorkingDirectory = $INSTALL_DIR
$Shortcut.Description = "Launch Content Engine"
$Shortcut.Save()

Write-Host ""
Write-Host "  ======================================" -ForegroundColor Green
Write-Host "       Installation Complete!" -ForegroundColor Green
Write-Host "  ======================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Desktop shortcut created: Content Engine"
Write-Host "  Or run: $INSTALL_DIR\Start Content Engine.bat"
Write-Host ""
