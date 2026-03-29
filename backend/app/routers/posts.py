"""Post queue router — CRUD + publish to Instagram Graph API."""

import base64
import hashlib
import threading
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.credential import OAuthToken
from app.models.edit import EditSession
from app.models.post import PostQueue
from app.models.profile import Profile
from app.models.video import Video
from app.schemas.post import PostQueueCreate, PostQueueOut, PostQueueUpdate
from app.services.post_service import IGGraph
from app.services.scheduler_service import assign_schedule_slot, _publish_post

router = APIRouter()


def _get_fernet() -> Fernet:
    key = hashlib.sha256(settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _decrypt(enc: str) -> str:
    f = _get_fernet()
    return f.decrypt(enc.encode()).decode()


# ──── CRUD ────


@router.get("", response_model=list[PostQueueOut])
def list_posts(
    profile_id: int | None = None,
    status: str | None = None,
    network_id: int | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(PostQueue)
    if network_id is not None:
        q = q.filter(PostQueue.network_id == network_id)
    if profile_id is not None:
        q = q.filter(PostQueue.profile_id == profile_id)
    if status:
        q = q.filter(PostQueue.status == status)
    return q.order_by(PostQueue.position, PostQueue.created_at.desc()).all()


@router.post("", response_model=PostQueueOut, status_code=201)
def create_post(body: PostQueueCreate, network_id: int | None = None, db: Session = Depends(get_db)):
    video = db.get(Video, body.video_id)
    if not video:
        raise HTTPException(404, "Video not found")

    # Determine position (append to end)
    max_pos = (
        db.query(PostQueue.position)
        .filter(PostQueue.profile_id == body.profile_id)
        .order_by(PostQueue.position.desc())
        .first()
    )
    pos = (max_pos[0] + 1) if max_pos else 0

    post = PostQueue(
        video_id=body.video_id,
        profile_id=body.profile_id,
        caption=body.caption,
        share_to_feed=body.share_to_feed,
        thumb_offset_ms=body.thumb_offset_ms,
        position=pos,
        network_id=network_id,
    )

    # Auto-schedule if profile has schedule config
    if body.auto_schedule:
        profile = db.get(Profile, body.profile_id)
        if profile:
            slot = assign_schedule_slot(db, profile)
            if slot:
                post.scheduled_for = slot
                post.status = "scheduled"

    db.add(post)
    db.commit()
    db.refresh(post)
    return post


@router.get("/{post_id}", response_model=PostQueueOut)
def get_post(post_id: int, db: Session = Depends(get_db)):
    post = db.get(PostQueue, post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    return post


@router.patch("/{post_id}", response_model=PostQueueOut)
def update_post(post_id: int, body: PostQueueUpdate, db: Session = Depends(get_db)):
    post = db.get(PostQueue, post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(post, key, val)
    db.commit()
    db.refresh(post)
    return post


@router.delete("/{post_id}", status_code=204)
def delete_post(post_id: int, db: Session = Depends(get_db)):
    post = db.get(PostQueue, post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    db.delete(post)
    db.commit()


# ──── Publish ────


@router.post("/{post_id}/publish", response_model=PostQueueOut)
def publish_post(post_id: int, db: Session = Depends(get_db)):
    """Publish a post to Instagram via Graph API.

    Non-blocking: sets status to 'queued', fires publish in a background thread,
    and returns immediately. Poll GET /posts/{id} to track progress.
    """
    post = db.get(PostQueue, post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    if post.status not in ("queued", "scheduled", "failed"):
        raise HTTPException(400, f"Post is in '{post.status}' state, cannot publish")

    # Quick validation before firing background work
    oauth = (
        db.query(OAuthToken)
        .filter(OAuthToken.profile_id == post.profile_id)
        .first()
    )
    if not oauth or not oauth.ig_user_id:
        raise HTTPException(400, "No OAuth tokens for this profile. Connect via Settings first.")

    token_enc = oauth.user_access_token_enc or oauth.page_access_token_enc
    if not token_enc:
        raise HTTPException(400, "No access token found. Reconnect via Settings.")

    # Set to uploading immediately to prevent duplicate publish from rapid clicks
    post.status = "uploading"
    post.scheduled_for = None
    db.commit()
    db.refresh(post)

    # Fire publish in background thread
    threading.Thread(
        target=_publish_post, args=(post_id,), daemon=True, name=f"publish-{post_id}"
    ).start()

    return post
