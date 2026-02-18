from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


class Settings(BaseSettings):
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'content_engine.db'}"
    secret_key: str = "change-me-in-production"  # used for Fernet encryption
    cors_origins: list[str] = ["http://localhost:5173"]
    downloads_dir: Path = BASE_DIR / "downloads"
    exports_dir: Path = BASE_DIR / "exports"
    templates_dir: Path = BASE_DIR / "templates"
    cookies_dir: Path = BASE_DIR / "cookies"

    # Instagram Graph API (optional, set in .env)
    ig_app_id: str = ""
    ig_app_secret: str = ""
    ig_redirect_uri: str = "http://localhost:8000/api/auth/oauth/callback"

    model_config = {"env_file": BASE_DIR / ".env", "env_file_encoding": "utf-8"}


settings = Settings()

# Ensure directories exist
for d in [settings.downloads_dir, settings.exports_dir, settings.templates_dir, settings.cookies_dir, BASE_DIR / "data"]:
    d.mkdir(parents=True, exist_ok=True)
