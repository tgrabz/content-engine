import os
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/

# Build default CORS origins — include Railway domain if deployed there
_default_origins = ["http://localhost:5173", "https://localhost:5173"]
_railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
if _railway_domain:
    _default_origins.append(f"https://{_railway_domain}")


class Settings(BaseSettings):
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'content_engine.db'}"
    secret_key: str = "change-me-in-production"  # used for Fernet encryption
    cors_origins: list[str] = _default_origins
    downloads_dir: Path = BASE_DIR / "downloads"
    exports_dir: Path = BASE_DIR / "exports"
    templates_dir: Path = BASE_DIR / "templates"
    cookies_dir: Path = BASE_DIR / "cookies"
    port: int = 8000

    # Instagram Graph API (optional, set in .env)
    ig_app_id: str = ""
    ig_app_secret: str = ""
    ig_redirect_uri: str = "https://localhost:5173/auth/callback"

    # Public URL for serving videos to Instagram API (ngrok URL in dev, real domain in prod)
    public_url: str = ""

    # Anthropic API (for AI caption generation)
    anthropic_api_key: str = ""

    model_config = {"env_file": BASE_DIR / ".env", "env_file_encoding": "utf-8"}


settings = Settings()

# Ensure directories exist
for d in [settings.downloads_dir, settings.exports_dir, settings.templates_dir, settings.cookies_dir, BASE_DIR / "data"]:
    d.mkdir(parents=True, exist_ok=True)

THUMB_DIR = settings.downloads_dir.parent / "data" / "thumbnails"
THUMB_DIR.mkdir(parents=True, exist_ok=True)
