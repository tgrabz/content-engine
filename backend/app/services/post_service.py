"""Instagram Content Publishing service.

Uses the Instagram Platform API (graph.instagram.com) for publishing reels.
Requires videos to be accessible via a public URL.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional, Tuple

import requests

from app.services.oauth_service import GRAPH_API_VERSION, normalize_token


class IGGraph:
    """Instagram Graph API client for content publishing."""

    def __init__(self, ig_user_id: str, access_token: str):
        self.ig_user_id = ig_user_id.strip()
        self.token = normalize_token(access_token)
        self.base = f"https://graph.instagram.com/{GRAPH_API_VERSION}"

    def _get(self, path: str, **params: str) -> dict:
        params["access_token"] = self.token
        r = requests.get(f"{self.base}/{path}", params=params, timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"GET {path} failed ({r.status_code}): {r.text}")
        return r.json()

    def _post(self, path: str, **params: str | int | None) -> dict:
        data = {k: v for k, v in params.items() if v is not None}
        data["access_token"] = self.token
        r = requests.post(f"{self.base}/{path}", data=data, timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"POST {path} failed ({r.status_code}): {r.text}")
        return r.json()

    def whoami(self) -> dict:
        """Get the IG account info."""
        return self._get("me", fields="user_id,username,name")

    # ── Container creation ──

    def create_container(
        self,
        *,
        video_url: str,
        caption: str = "",
        share_to_feed: bool = True,
        thumb_offset_ms: int | None = None,
    ) -> str:
        """Create a media container from a publicly accessible video URL."""
        j = self._post(
            f"{self.ig_user_id}/media",
            media_type="REELS",
            video_url=video_url,
            caption=caption,
            share_to_feed="true" if share_to_feed else "false",
            thumb_offset=thumb_offset_ms,
        )
        cid = j.get("id")
        if not cid:
            raise RuntimeError(f"No container ID returned: {j}")
        return cid

    # ── Status polling ──

    def container_status(self, container_id: str) -> Tuple[str, str]:
        """Check container processing status. Returns (status_code, status)."""
        j = self._get(container_id, fields="status_code,status")
        return str(j.get("status_code", "")), str(j.get("status", ""))

    def wait_for_container(
        self, container_id: str, timeout_sec: int = 480, poll_interval: float = 3.0
    ) -> None:
        """Poll until container is FINISHED or raise on error/timeout."""
        t0 = time.time()
        while True:
            code, status = self.container_status(container_id)
            if code.upper() == "FINISHED" or status.upper() == "FINISHED":
                return
            if "ERROR" in code.upper() or "ERROR" in status.upper():
                raise RuntimeError(
                    f"Container error: status_code={code} status={status}"
                )
            if time.time() - t0 > timeout_sec:
                raise TimeoutError("Timed out waiting for container processing")
            time.sleep(poll_interval)

    # ── Publish ──

    def publish(self, container_id: str) -> str:
        """Publish a processed container. Returns media_id."""
        j = self._post(
            f"{self.ig_user_id}/media_publish", creation_id=container_id
        )
        mid = j.get("id")
        if not mid:
            raise RuntimeError(f"Publish returned no media_id: {j}")
        return mid

    def permalink(self, media_id: str) -> Optional[str]:
        """Get the permalink for a published media."""
        try:
            j = self._get(media_id, fields="permalink")
            return j.get("permalink")
        except Exception:
            return None
