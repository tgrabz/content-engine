"""Instagram Platform API OAuth service.

Uses Instagram's direct login (not Facebook Login) for authenticating
Instagram Business/Creator accounts.
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

import requests

GRAPH_API_VERSION = "v21.0"


def normalize_token(raw: str) -> str:
    """Clean and extract access token from various formats."""
    if not raw or not isinstance(raw, str):
        raise ValueError("Empty token")
    s = raw.strip().strip('"').strip("'")
    if s.lower().startswith("bearer "):
        s = s[7:].strip()
    if (s.startswith("{") and s.endswith("}")) or ("access_token" in s and "{" in s):
        try:
            j = json.loads(s)
            s = j.get("access_token") or ""
        except Exception:
            pass
    if "access_token=" in s and "&" in s:
        try:
            from urllib.parse import parse_qs
            parts = parse_qs(s)
            s = (parts.get("access_token") or [""])[0]
        except Exception:
            pass
    s = s.strip().strip('"').strip("'")
    if not s:
        raise ValueError("Could not extract access_token from input")
    return s

REQUIRED_SCOPES = [
    "instagram_business_basic",
    "instagram_business_content_publish",
]


def build_auth_url(app_id: str, redirect_uri: str, state: str) -> str:
    """Generate Instagram OAuth authorization URL."""
    params = {
        "client_id": app_id.strip(),
        "redirect_uri": redirect_uri.strip(),
        "state": state,
        "scope": ",".join(REQUIRED_SCOPES),
        "response_type": "code",
    }
    return f"https://www.instagram.com/oauth/authorize?{urlencode(params)}"


def exchange_code_for_token(
    app_id: str, app_secret: str, redirect_uri: str, code: str
) -> dict:
    """Exchange authorization code for short-lived Instagram token."""
    url = "https://api.instagram.com/oauth/access_token"
    r = requests.post(
        url,
        data={
            "client_id": app_id.strip(),
            "client_secret": app_secret.strip(),
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri.strip(),
            "code": code.strip(),
        },
        timeout=30,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"Code exchange failed: {r.text}")
    return r.json()  # {"access_token": "...", "user_id": 12345}


def exchange_long_lived_token(app_secret: str, short_token: str) -> dict:
    """Exchange short-lived token for long-lived token (~60 days)."""
    url = f"https://graph.instagram.com/access_token"
    r = requests.get(
        url,
        params={
            "grant_type": "ig_exchange_token",
            "client_secret": app_secret.strip(),
            "access_token": short_token.strip(),
        },
        timeout=30,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"Long-lived exchange failed: {r.text}")
    return r.json()  # {"access_token": "...", "token_type": "bearer", "expires_in": ...}


def get_ig_user_info(access_token: str) -> dict:
    """Get the authenticated Instagram user's profile info."""
    url = f"https://graph.instagram.com/{GRAPH_API_VERSION}/me"
    r = requests.get(
        url,
        params={
            "access_token": access_token.strip(),
            "fields": "user_id,username,name,profile_picture_url",
        },
        timeout=15,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"User info fetch failed: {r.text}")
    return r.json()
