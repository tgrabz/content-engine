"""Scheduled posting service — slot assignment + background publish loop.

Handles:
- Assigning posts to the next available schedule slot with jitter
- Background daemon that polls for due posts and publishes them
- Stale post recovery on startup
"""

import base64
import hashlib
import json
import logging
import random
import subprocess
import threading
import time
from datetime import datetime, time as dt_time, timedelta, timezone
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import and_

from app.config import settings
from app.database import SessionLocal
from app.models.credential import OAuthToken
from app.models.edit import EditSession
from app.models.post import PostQueue
from app.models.profile import Profile
from app.models.video import Video
from app.services.post_service import IGGraph

logger = logging.getLogger("scheduler")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(name)s %(levelname)s: %(message)s"))
    logger.addHandler(handler)

_stop_event = threading.Event()
_thread: threading.Thread | None = None

try:
    import imageio_ffmpeg
    _FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    _FFMPEG_BIN = "ffmpeg"


def _reencode_for_profile(video_path: str, profile_id: int) -> str:
    """Create a unique re-encoded copy for a specific profile upload.

    Slightly randomizes encoding parameters (CRF, bitrate) so each profile's
    upload has unique binary content — prevents Instagram from fingerprinting
    the same video across multiple accounts.

    Returns path to the re-encoded copy (in exports dir).
    """
    src = Path(video_path)
    # Always save re-encoded file to exports_dir so it's served via /static/exports/
    out = settings.exports_dir / f"{src.stem}_p{profile_id}_{random.randint(1000,9999)}.mp4"

    crf = random.randint(21, 24)
    audio_br = random.choice([126, 128, 130, 132])

    cmd = [
        _FFMPEG_BIN, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src),
        "-map_metadata", "-1",
        "-c:v", "libx264", "-crf", str(crf), "-preset", "fast",
        "-c:a", "aac", "-b:a", f"{audio_br}k",
        "-movflags", "+faststart",
        str(out),
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=120)
        if out.exists() and out.stat().st_size > 0:
            return str(out)
    except Exception as e:
        logger.warning(f"Re-encode for profile {profile_id} failed: {e}")
        if out.exists():
            out.unlink()
    return video_path  # fallback to original if re-encode fails


# ── Crypto helper (mirrors posts router) ──

def _get_fernet() -> Fernet:
    key = hashlib.sha256(settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _decrypt(enc: str) -> str:
    return _get_fernet().decrypt(enc.encode()).decode()


# ── Warmup / effective daily limit ──

def get_effective_daily_limit(profile: Profile) -> int:
    """Apply warmup ramp to the profile's daily_post_limit.

    Week 1: 1/day, Week 2: 2/day, Week 3+: full limit.
    """
    if not profile.warmup_started_at:
        return profile.daily_post_limit

    now = datetime.now(timezone.utc)
    days = (now - profile.warmup_started_at).days

    if days < 7:
        return 1
    elif days < 14:
        return min(2, profile.daily_post_limit)
    else:
        return profile.daily_post_limit


# ── Schedule slot assignment ──

def assign_schedule_slot(db, profile: Profile) -> datetime | None:
    """Find the next available schedule slot for a profile.

    Returns a UTC datetime, or None if profile has no schedule configured.
    """
    if not profile.schedule_times:
        return None

    try:
        times_raw = json.loads(profile.schedule_times)
    except (json.JSONDecodeError, TypeError):
        return None

    if not times_raw:
        return None

    # Parse time strings → sorted time objects
    slot_times = sorted(
        dt_time(int(t.split(":")[0]), int(t.split(":")[1]))
        for t in times_raw
    )

    effective_limit = get_effective_daily_limit(profile)
    # Only use the first N slots per day based on limit
    active_slots = slot_times[:effective_limit]

    if not active_slots:
        return None

    now = datetime.now(timezone.utc)

    # Scan forward day-by-day, up to 30 days
    for day_offset in range(31):
        check_date = (now + timedelta(days=day_offset)).date()

        # Count how many posts are already scheduled/active on this day
        day_start = datetime(check_date.year, check_date.month, check_date.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)

        occupied_count = (
            db.query(PostQueue)
            .filter(
                PostQueue.profile_id == profile.id,
                PostQueue.scheduled_for >= day_start,
                PostQueue.scheduled_for < day_end,
                PostQueue.status.in_(("scheduled", "queued", "uploading", "processing")),
            )
            .count()
        )

        if occupied_count >= effective_limit:
            continue  # day is full

        # Get the specific scheduled times already taken on this day
        occupied_times = (
            db.query(PostQueue.scheduled_for)
            .filter(
                PostQueue.profile_id == profile.id,
                PostQueue.scheduled_for >= day_start,
                PostQueue.scheduled_for < day_end,
                PostQueue.status.in_(("scheduled", "queued", "uploading", "processing")),
            )
            .all()
        )
        occupied_hours = {sf[0].hour for sf in occupied_times if sf[0]}

        # Find first unused slot time on this day
        for slot_time in active_slots:
            if slot_time.hour in occupied_hours:
                continue

            # Build candidate datetime
            candidate = datetime(
                check_date.year, check_date.month, check_date.day,
                slot_time.hour, slot_time.minute,
                tzinfo=timezone.utc,
            )

            # Skip if it's already in the past
            if candidate <= now:
                continue

            # Apply jitter: ±5-30 min random offset for human-like timing
            jitter_minutes = random.randint(-5, 30)
            candidate += timedelta(minutes=jitter_minutes)

            # Clamp to not go negative into previous day
            if candidate.date() < check_date:
                candidate = datetime(
                    check_date.year, check_date.month, check_date.day,
                    0, random.randint(0, 15),
                    tzinfo=timezone.utc,
                )

            return candidate

    return None  # all slots full for next 30 days


# ── Publish a single post (runs in its own DB session) ──

def _publish_post(post_id: int) -> None:
    """Publish one post via Instagram Graph API. Opens its own DB session."""
    db = SessionLocal()
    try:
        post = db.get(PostQueue, post_id)
        if not post:
            logger.error(f"Post {post_id} not found")
            return
        if post.status not in ("scheduled", "queued", "failed", "uploading"):
            logger.warning(f"Post {post_id} status is '{post.status}', skipping")
            return

        # Get OAuth token
        oauth = (
            db.query(OAuthToken)
            .filter(OAuthToken.profile_id == post.profile_id)
            .first()
        )
        if not oauth or not oauth.ig_user_id:
            post.status = "failed"
            post.error_message = "No OAuth tokens for this profile"
            db.commit()
            logger.error(f"Post {post_id}: no OAuth tokens for profile {post.profile_id}")
            return

        token_enc = oauth.user_access_token_enc or oauth.page_access_token_enc
        if not token_enc:
            post.status = "failed"
            post.error_message = "No access token found"
            db.commit()
            return

        page_token = _decrypt(token_enc)

        # Get video file path
        video = db.get(Video, post.video_id)
        if not video:
            post.status = "failed"
            post.error_message = "Video not found"
            db.commit()
            return

        session = (
            db.query(EditSession)
            .filter(EditSession.video_id == post.video_id, EditSession.profile_id == post.profile_id)
            .first()
        )
        video_path_raw = (
            (session.exported_path if session and session.exported_path else None)
            or video.local_path
        )
        # Resolve relative paths against media_root
        if video_path_raw and not Path(video_path_raw).is_absolute():
            video_path = str(settings.media_root / video_path_raw)
        else:
            video_path = video_path_raw
        if not video_path or not Path(video_path).exists():
            post.status = "failed"
            post.error_message = "Video file not found on disk"
            db.commit()
            return

        # Re-encode with unique parameters per profile (prevents cross-account fingerprinting)
        upload_path = _reencode_for_profile(video_path, post.profile_id)
        logger.info(f"Post {post_id}: using upload file {upload_path}")

        # Update post status
        post.status = "uploading"
        db.commit()

        cli = IGGraph(oauth.ig_user_id, page_token)

        # Resolve public_url: per-network first, fallback to settings
        public_url = settings.public_url
        if post.network_id:
            from app.models.user import Network
            network = db.get(Network, post.network_id)
            if network and network.public_url:
                public_url = network.public_url

        if not public_url:
            raise RuntimeError("PUBLIC_URL not configured (set on network or in .env)")

        # Build public URL for Instagram to download the video
        # Try exports_dir, downloads_dir, or media_root as base paths
        vp = Path(upload_path)
        video_url = None
        for base_dir, static_prefix in [
            (settings.exports_dir, "static/exports"),
            (settings.downloads_dir, "static/downloads"),
        ]:
            try:
                rel = vp.relative_to(base_dir)
                video_url = f"{public_url}/{static_prefix}/{rel}"
                break
            except ValueError:
                continue

        if not video_url:
            # Fallback: serve via the video stream API endpoint
            video_url = f"{public_url}/api/videos/{post.video_id}/stream?edited=true&profile_id={post.profile_id}"

        logger.info(f"Post {post_id}: video_url={video_url}")
        container_id = cli.create_container(
            video_url=video_url,
            caption=post.caption,
            share_to_feed=post.share_to_feed,
            thumb_offset_ms=post.thumb_offset_ms or None,
        )
        post.ig_container_id = container_id
        post.status = "processing"
        db.commit()

        cli.wait_for_container(container_id)

        media_id = cli.publish(container_id)
        permalink = cli.permalink(media_id)

        post.ig_media_id = media_id
        post.ig_permalink = permalink
        post.status = "published"
        post.published_at = datetime.now(timezone.utc)
        post.error_message = None
        db.commit()
        logger.info(f"Post {post_id} published successfully: {permalink}")

    except Exception as e:
        logger.exception(f"Post {post_id} publish failed: {e}")
        try:
            post = db.get(PostQueue, post_id)
            if post:
                post.status = "failed"
                post.error_message = (str(e) or repr(e))[:500]
            db.commit()
        except Exception:
            logger.exception("Failed to update post status after error")
    finally:
        # Clean up per-profile re-encoded file (don't keep copies on disk)
        try:
            if upload_path != video_path and Path(upload_path).exists():
                Path(upload_path).unlink()
        except Exception:
            pass
        db.close()


# ── Stale post recovery ──

def recover_stale_posts() -> int:
    """Reset posts stuck in uploading/processing back to queued (server crashed mid-publish)."""
    db = SessionLocal()
    try:
        stale = (
            db.query(PostQueue)
            .filter(PostQueue.status.in_(("uploading", "processing")))
            .all()
        )
        count = len(stale)
        for post in stale:
            logger.info(f"Recovering stale post {post.id} (was {post.status}) → queued")
            post.status = "queued"
            post.error_message = "Recovered after server restart"
        db.commit()
        if count:
            logger.info(f"Recovered {count} stale posts")
        return count
    finally:
        db.close()


# ── Background scheduler loop ──

def _scheduler_loop() -> None:
    """Poll every 30s for posts due for publishing."""
    logger.info("Scheduler started")
    while not _stop_event.is_set():
        try:
            db = SessionLocal()
            now = datetime.now(timezone.utc)
            due_posts = (
                db.query(PostQueue)
                .filter(
                    PostQueue.status == "scheduled",
                    PostQueue.scheduled_for <= now,
                )
                .order_by(PostQueue.scheduled_for)
                .all()
            )
            db.close()

            for post in due_posts:
                if _stop_event.is_set():
                    break
                logger.info(f"Publishing scheduled post {post.id} (due {post.scheduled_for})")
                _publish_post(post.id)

        except Exception:
            logger.exception("Scheduler loop error")

        # Sleep in 1-second increments so we can stop quickly
        for _ in range(30):
            if _stop_event.is_set():
                break
            time.sleep(1)

    logger.info("Scheduler stopped")


def start_scheduler() -> None:
    """Start the background scheduler thread."""
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_scheduler_loop, daemon=True, name="post-scheduler")
    _thread.start()


def stop_scheduler() -> None:
    """Stop the background scheduler thread."""
    _stop_event.set()
    if _thread:
        _thread.join(timeout=5)
