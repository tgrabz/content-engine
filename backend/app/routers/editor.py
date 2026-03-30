import io
import json
import subprocess
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from PIL import Image
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings, THUMB_DIR
from app.database import get_db, SessionLocal
from app.models.edit import EditSession
from app.models.post import PostQueue
from app.models.profile import Profile
from app.models.template import Template
from app.models.video import Video
from app.schemas.editor import EditSessionOut, EditSessionUpdate
from app.models.niche import Niche
from app.services.caption_service import auto_place_caption
from app.services.caption_ai_service import analyze_video, extract_frames, generate_captions, generate_caption_from_description
from app.services.crop_service import auto_crop_video


def _resolve(path_str: str | None) -> Path | None:
    """Resolve a possibly-relative path against media_root."""
    if not path_str:
        return None
    p = Path(path_str)
    if p.is_absolute():
        return p
    return settings.media_root / p
from app.services.render_service import (
    get_render_job,
    start_render_job,
    _render_text_rgba,
    _hex_to_rgb,
    _probe_video_dimensions,
)

try:
    import imageio_ffmpeg

    FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_BIN = "ffmpeg"

router = APIRouter()

# Cache directory for extracted frames
_FRAME_CACHE = Path(tempfile.gettempdir()) / "content_engine_frames"
_FRAME_CACHE.mkdir(parents=True, exist_ok=True)


@router.get("/session", response_model=EditSessionOut)
def get_or_create_session(
    video_id: int = Query(...),
    profile_id: int = Query(...),
    db: Session = Depends(get_db),
):
    session = (
        db.query(EditSession)
        .filter(
            EditSession.video_id == video_id,
            EditSession.profile_id == profile_id,
        )
        .first()
    )
    if not session:
        session = EditSession(video_id=video_id, profile_id=profile_id)
        db.add(session)
        db.commit()
        db.refresh(session)
    return session


@router.patch("/session/{session_id}", response_model=EditSessionOut)
def update_session(
    session_id: int, body: EditSessionUpdate, db: Session = Depends(get_db)
):
    session = db.get(EditSession, session_id)
    if not session:
        raise HTTPException(404, "Edit session not found")
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(session, key, val)
    db.commit()
    db.refresh(session)
    return session


@router.get("/session/{session_id}", response_model=EditSessionOut)
def get_session(session_id: int, db: Session = Depends(get_db)):
    session = db.get(EditSession, session_id)
    if not session:
        raise HTTPException(404, "Edit session not found")
    return session


@router.get("/frame/{video_id}")
def get_video_frame(
    video_id: int,
    t: float = Query(1.0, ge=0),
    db: Session = Depends(get_db),
):
    video = db.get(Video, video_id)
    if not video or not video.local_path:
        raise HTTPException(404, "Video not found")

    src = _resolve(video.local_path)
    if not src.exists():
        raise HTTPException(404, "Video file missing from disk")

    # Cache frame by video_id + timestamp
    cache_key = f"{video_id}_{int(t * 10)}"
    cached = _FRAME_CACHE / f"{cache_key}.jpg"
    if cached.exists():
        return FileResponse(str(cached), media_type="image/jpeg")

    try:
        subprocess.run(
            [
                FFMPEG_BIN,
                "-ss",
                str(t),
                "-i",
                str(src),
                "-vframes",
                "1",
                "-q:v",
                "2",
                "-y",
                str(cached),
            ],
            capture_output=True,
            check=True,
            timeout=15,
        )
    except Exception:
        raise HTTPException(500, "Failed to extract frame")

    if not cached.exists():
        raise HTTPException(500, "Frame extraction produced no output")

    return FileResponse(str(cached), media_type="image/jpeg")


# ──────────────────── Composite preview ────────────────────


def _parse_box_with_default(
    val: str, default: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    try:
        arr = json.loads(val)
        if isinstance(arr, list) and len(arr) == 4:
            return tuple(arr)  # type: ignore[return-value]
    except Exception:
        pass
    return default


def _extract_frame(video_path: str, video_id: int, t: float) -> Image.Image | None:
    """Extract a video frame, using the shared frame cache."""
    cache_key = f"{video_id}_{int(t * 10)}"
    cached = _FRAME_CACHE / f"{cache_key}.jpg"
    if not cached.exists():
        try:
            subprocess.run(
                [FFMPEG_BIN, "-ss", str(t), "-i", video_path,
                 "-vframes", "1", "-q:v", "2", "-y", str(cached)],
                capture_output=True, check=True, timeout=15,
            )
        except Exception:
            return None
    if cached.exists():
        return Image.open(str(cached)).convert("RGB")
    return None


@router.get("/preview")
def get_preview(
    video_id: int = Query(...),
    t: float = Query(1.0, ge=0),
    template_id: int | None = Query(None),
    crop_box: str = Query(""),
    video_box: str = Query(""),
    caption_text: str = Query(""),
    caption_color: str = Query("#000000"),
    caption_box: str = Query(""),
    db: Session = Depends(get_db),
):
    """Generate a composite preview frame using the same pipeline as the render.

    This guarantees the canvas preview matches the final rendered video exactly.
    """
    W, H = 1080, 1920

    video = db.get(Video, video_id)
    if not video or not video.local_path:
        raise HTTPException(404, "Video not found")
    src = _resolve(video.local_path)
    if not src.exists():
        raise HTTPException(404, "Video file missing from disk")

    # Parse boxes
    crop = _parse_box_with_default(crop_box, (0.0, 0.0, 1.0, 1.0))
    vbox = _parse_box_with_default(video_box, (0.06, 0.18, 0.94, 0.94))
    cbox = _parse_box_with_default(caption_box, (0.06, 0.08, 0.94, 0.16))

    # ── 1. Template base ──
    comp = Image.new("RGB", (W, H), (255, 255, 255))
    if template_id:
        tmpl = db.get(Template, template_id)
        tmpl_path = _resolve(tmpl.image_path) if tmpl else None
        if tmpl_path and tmpl_path.exists():
            tmpl_img = Image.open(str(tmpl_path)).convert("RGBA")
            tmpl_img = tmpl_img.resize((W, H), Image.LANCZOS)
            comp_rgba = comp.convert("RGBA")
            comp_rgba.alpha_composite(tmpl_img)
            comp = comp_rgba.convert("RGB")

    # ── 2. Video frame: crop + scale into video_box ──
    frame = _extract_frame(str(src), video_id, t)
    if frame:
        vid_w, vid_h = frame.size
        cx1, cy1, cx2, cy2 = crop
        cx = max(0, int(round(cx1 * vid_w)))
        cy = max(0, int(round(cy1 * vid_h)))
        cw = max(2, int(round((cx2 - cx1) * vid_w)))
        ch = max(2, int(round((cy2 - cy1) * vid_h)))
        cw = min(cw, vid_w)
        ch = min(ch, vid_h)
        if cx + cw > vid_w:
            cx = max(0, vid_w - cw)
        if cy + ch > vid_h:
            cy = max(0, vid_h - ch)

        cropped = frame.crop((cx, cy, cx + cw, cy + ch))

        vx1, vy1, vx2, vy2 = vbox
        bx = int(vx1 * W)
        by = int(vy1 * H)
        bw = int((vx2 - vx1) * W)
        bh = int((vy2 - vy1) * H)

        # WIDTH-FILL scaling: match box width, crop height if overflow
        scale = bw / float(max(1, cw))
        sw = max(2, int(round(cw * scale)))
        sh = max(2, int(round(ch * scale)))
        scaled_vid = cropped.resize((sw, sh), Image.LANCZOS)

        # If taller than box, crop from bottom
        if sh > bh:
            scaled_vid = scaled_vid.crop((0, 0, sw, bh))
            sh = bh

        ox = bx
        oy = by

        comp.paste(scaled_vid, (ox, oy))

    # ── 3. Caption overlay (same as render_service) ──
    if caption_text.strip():
        cbx1, cby1, cbx2, cby2 = cbox
        cap_x = int(cbx1 * W)
        cap_y = int(cby1 * H)
        cap_w = max(4, int((cbx2 - cbx1) * W))
        cap_h = max(4, int((cby2 - cby1) * H))
        caption_img = _render_text_rgba(
            caption_text, cap_w, cap_h, _hex_to_rgb(caption_color),
            valign="center",
        )
        comp.paste(caption_img, (cap_x, cap_y), caption_img)

    # Return as JPEG
    buf = io.BytesIO()
    comp.save(buf, "JPEG", quality=85)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/jpeg")


# ──────────────────── Auto-crop ────────────────────


class AutoCropRequest(BaseModel):
    video_id: int
    num_samples: int = 16


class AutoCropResponse(BaseModel):
    crop_box: list[float]


@router.post("/auto-crop", response_model=AutoCropResponse)
def run_auto_crop(body: AutoCropRequest, db: Session = Depends(get_db)):
    video = db.get(Video, body.video_id)
    if not video or not video.local_path:
        raise HTTPException(404, "Video not found")
    src = _resolve(video.local_path)
    if not src.exists():
        raise HTTPException(404, "Video file missing from disk")

    try:
        x1, y1, x2, y2 = auto_crop_video(
            str(src), num_samples=body.num_samples
        )
    except Exception as e:
        raise HTTPException(500, f"Auto-crop failed: {e}")

    return {"crop_box": [x1, y1, x2, y2]}


# ──────────────────── Caption placement ────────────────────


class CaptionPlaceRequest(BaseModel):
    video_id: int
    template_id: int | None = None
    video_box: list[float] = [0.06, 0.18, 0.94, 0.94]
    crop_box: list[float] | None = None


class CaptionPlaceResponse(BaseModel):
    caption_box: list[float]
    caption_color: str


@router.post("/caption-place", response_model=CaptionPlaceResponse)
def run_caption_place(body: CaptionPlaceRequest, db: Session = Depends(get_db)):
    video = db.get(Video, body.video_id)
    if not video or not video.local_path:
        raise HTTPException(404, "Video not found")

    # Load template image and default caption box if specified
    template_img = None
    template_caption_box = None
    if body.template_id:
        tmpl = db.get(Template, body.template_id)
        if tmpl:
            _tmpl_path = _resolve(tmpl.image_path)
            if _tmpl_path and _tmpl_path.exists():
                template_img = Image.open(str(_tmpl_path)).convert("RGBA")
            # Pass template's designed caption_box as a preferred candidate
            if tmpl.caption_box:
                try:
                    import json
                    cbox = json.loads(tmpl.caption_box)
                    if isinstance(cbox, list) and len(cbox) == 4:
                        template_caption_box = tuple(cbox)
                except Exception:
                    pass

    # Load a video frame for color analysis
    video_frame = None
    src = _resolve(video.local_path)
    if src.exists():
        cache_key = f"{body.video_id}_10"
        frame_cached = _FRAME_CACHE / f"{cache_key}.jpg"
        if frame_cached.exists():
            video_frame = Image.open(str(frame_cached)).convert("RGB")
        else:
            try:
                subprocess.run(
                    [FFMPEG_BIN, "-ss", "1", "-i", str(src),
                     "-vframes", "1", "-q:v", "2", "-y", str(frame_cached)],
                    capture_output=True, check=True, timeout=15,
                )
                if frame_cached.exists():
                    video_frame = Image.open(str(frame_cached)).convert("RGB")
            except Exception:
                pass

    vbox = tuple(body.video_box) if len(body.video_box) == 4 else (0.06, 0.18, 0.94, 0.94)
    cbox = tuple(body.crop_box) if body.crop_box and len(body.crop_box) == 4 else None

    # Get video dimensions for FIT scaling calculation
    vid_dims = None
    if video_frame is not None:
        vid_dims = video_frame.size
    elif video:
        w, h = video.width, video.height
        if w and h:
            vid_dims = (w, h)

    try:
        caption_box, caption_color = auto_place_caption(
            video_box=vbox,
            template_img=template_img,
            video_frame=video_frame,
            template_caption_box=template_caption_box,
            crop_box=cbox,
            video_dimensions=vid_dims,
        )
    except Exception as e:
        raise HTTPException(500, f"Caption placement failed: {e}")

    return {
        "caption_box": list(caption_box),
        "caption_color": caption_color,
    }


# ──────────────────── Render pipeline ────────────────────


class RenderRequest(BaseModel):
    session_id: int
    quality: str = "Native 1920"
    include_audio: bool = False


class RenderStartResponse(BaseModel):
    job_id: str


class RenderStatusResponse(BaseModel):
    status: str
    progress: int
    error: str | None = None


def _parse_box(val: str) -> tuple[float, float, float, float]:
    try:
        arr = json.loads(val)
        if isinstance(arr, list) and len(arr) == 4:
            return tuple(arr)  # type: ignore[return-value]
    except Exception:
        pass
    return (0.0, 0.0, 1.0, 1.0)


@router.post("/render", response_model=RenderStartResponse)
def start_render(body: RenderRequest, db: Session = Depends(get_db)):
    session = db.get(EditSession, body.session_id)
    if not session:
        raise HTTPException(404, "Edit session not found")

    video = db.get(Video, session.video_id)
    if not video or not video.local_path:
        raise HTTPException(404, "Video not found")
    src = _resolve(video.local_path)
    if not src.exists():
        raise HTTPException(404, "Video file missing from disk")

    # Resolve template
    template_image_path = None
    template_img = None
    video_box = (0.06, 0.18, 0.94, 0.94)
    if session.template_id:
        tmpl = db.get(Template, session.template_id)
        if tmpl:
            template_image_path = str(_resolve(tmpl.image_path))
            video_box = _parse_box(tmpl.video_box)
            _tmpl_path = _resolve(tmpl.image_path)
            if _tmpl_path and _tmpl_path.exists():
                template_img = Image.open(str(_tmpl_path)).convert("RGBA")

    # Use session caption_box if set (by Smart Placement), otherwise auto-compute
    caption_box = None
    if session.caption_box:
        session_cbox = _parse_box(session.caption_box)
        if session_cbox != (0.08, 0.12, 0.92, 0.92):  # not the fallback
            caption_box = session_cbox

    # Auto-compute caption placement if not explicitly set
    if caption_box is None and session.caption_text and session.caption_text.strip():
        try:
            caption_box, auto_color = auto_place_caption(
                video_box=video_box,
                template_img=template_img,
            )
            # Use auto-computed color if session doesn't have one set
            if not session.caption_color or session.caption_color == "#000000":
                session.caption_color = auto_color
        except Exception:
            caption_box = (0.06, 0.08, 0.94, 0.16)  # safe fallback

    if caption_box is None:
        caption_box = (0.06, 0.08, 0.94, 0.16)

    crop_box = _parse_box(session.crop_box)

    # Output path
    out_name = f"{src.stem}_edited_{int(uuid.uuid4().int % 1e8)}.mp4"
    output_path = str(settings.exports_dir / out_name)

    job_id = str(uuid.uuid4())
    session_id_val = session.id
    video_id_val = video.id

    profile_id_val = session.profile_id

    def _on_render_complete(jid: str, out_path: str):
        """Auto-mark video as ready and add to post queue."""
        cb_db = SessionLocal()
        try:
            s = cb_db.get(EditSession, session_id_val)
            v = cb_db.get(Video, video_id_val)
            if s:
                s.profile_status = "ready"
                s.exported_path = out_path
            if v:
                v.status = "ready"
                v.exported_path = out_path

            # Auto-create or update PostQueue entry
            existing_post = (
                cb_db.query(PostQueue)
                .filter(
                    PostQueue.video_id == video_id_val,
                    PostQueue.profile_id == profile_id_val,
                )
                .order_by(PostQueue.id.desc())
                .first()
            )
            if existing_post and existing_post.status in ("queued", "scheduled"):
                # Update existing queued post with new caption
                existing_post.caption = s.post_caption or "" if s else ""
            elif not existing_post or existing_post.status in ("published", "failed"):
                # Create fresh post entry
                max_pos = (
                    cb_db.query(PostQueue.position)
                    .filter(PostQueue.profile_id == profile_id_val)
                    .order_by(PostQueue.position.desc())
                    .first()
                )
                pos = (max_pos[0] + 1) if max_pos else 0
                post = PostQueue(
                    video_id=video_id_val,
                    profile_id=profile_id_val,
                    caption=s.post_caption or "" if s else "",
                    share_to_feed=True,
                    position=pos,
                    status="queued",
                    network_id=v.network_id if v else None,
                )
                cb_db.add(post)

            cb_db.commit()
        except Exception as cb_err:
            import logging
            logging.getLogger(__name__).error("on_complete callback failed: %s", cb_err)
            cb_db.rollback()
        finally:
            cb_db.close()

    start_render_job(
        job_id=job_id,
        video_path=str(src),
        output_path=output_path,
        crop_box=crop_box,
        video_box=video_box,
        template_image_path=template_image_path,
        caption_text=session.caption_text or "",
        caption_color=session.caption_color or "#000000",
        caption_box=caption_box,
        quality=body.quality,
        include_audio=body.include_audio,
        on_complete=_on_render_complete,
    )

    # Update per-profile state on EditSession (NOT the global Video record)
    session.exported_path = output_path
    session.profile_status = "rendering"
    # Invalidate cached edited thumbnails
    for suffix in [f"{video.id}_edited.jpg", f"{video.id}_edited_p{session.profile_id}.jpg"]:
        thumb = THUMB_DIR / suffix
        if thumb.exists():
            thumb.unlink()
    db.commit()

    return {"job_id": job_id}


@router.get("/render/{job_id}", response_model=RenderStatusResponse)
def render_status(job_id: str):
    job = get_render_job(job_id)
    if not job:
        raise HTTPException(404, "Render job not found")
    return {
        "status": job["status"],
        "progress": job["progress"],
        "error": job.get("error"),
    }


@router.get("/render/{job_id}/download")
def render_download(job_id: str):
    job = get_render_job(job_id)
    if not job:
        raise HTTPException(404, "Render job not found")
    if job["status"] != "complete":
        raise HTTPException(400, "Render not complete yet")
    path = job.get("output_path")
    if not path or not Path(path).exists():
        raise HTTPException(404, "Rendered file not found")
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=Path(path).name,
    )


@router.post("/export/{session_id}")
def export_to_profile(session_id: int, db: Session = Depends(get_db)):
    """Mark the video as ready after export."""
    session = db.get(EditSession, session_id)
    if not session:
        raise HTTPException(404, "Edit session not found")
    video = db.get(Video, session.video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    exported = session.exported_path
    if not exported or not Path(exported).exists():
        raise HTTPException(400, "No exported video found. Render first.")
    session.profile_status = "ready"
    # Also update the Video record so it shows up in Posts
    video.status = "ready"
    video.exported_path = exported
    db.commit()
    return {"status": "ok", "exported_path": exported}


# ──────────────────── Auto-edit pipeline ────────────────────


class AutoEditRequest(BaseModel):
    profile_id: int
    video_ids: list[int] | None = None


class AutoEditItem(BaseModel):
    video_id: int
    session_id: int
    job_id: str
    status: str


@router.post("/auto-edit", response_model=list[AutoEditItem])
def auto_edit(body: AutoEditRequest, db: Session = Depends(get_db)):
    """Auto-edit videos for a profile: auto-crop, caption-place, render.

    If video_ids is None, finds unprocessed videos in the profile's niche (limit 20).
    """
    profile = db.get(Profile, body.profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found")
    if not profile.default_template_id:
        raise HTTPException(400, "Profile has no default template. Set one first.")

    tmpl = db.get(Template, profile.default_template_id)
    if not tmpl:
        raise HTTPException(400, "Default template not found.")

    video_box = _parse_box(tmpl.video_box)
    template_image_path = str(_resolve(tmpl.image_path))

    # Load template image for caption placement
    template_img = None
    if template_image_path and Path(template_image_path).exists():
        template_img = Image.open(template_image_path).convert("RGBA")

    # Parse template caption_box as candidate
    template_caption_box = None
    if tmpl.caption_box:
        try:
            cbox = json.loads(tmpl.caption_box)
            if isinstance(cbox, list) and len(cbox) == 4:
                template_caption_box = tuple(cbox)
        except Exception:
            pass

    # Determine video IDs
    if body.video_ids:
        video_ids = body.video_ids[:20]
    else:
        # Find videos in profile's niche without a "ready" or "rendering" EditSession
        if not profile.niche_id:
            return []
        existing = (
            db.query(EditSession.video_id)
            .filter(
                EditSession.profile_id == body.profile_id,
                EditSession.profile_status.in_(["ready", "rendering"]),
            )
            .subquery()
        )
        videos = (
            db.query(Video)
            .filter(
                Video.niche_id == profile.niche_id,
                Video.local_path.isnot(None),
                ~Video.id.in_(db.query(existing.c.video_id)),
            )
            .order_by(Video.scraped_at.desc())
            .limit(20)
            .all()
        )
        video_ids = [v.id for v in videos]

    if not video_ids:
        return []

    results: list[dict] = []

    for vid_id in video_ids:
        video = db.get(Video, vid_id)
        if not video or not video.local_path:
            continue
        src = _resolve(video.local_path)
        if not src.exists():
            continue

        # 1. Get or create EditSession
        session = (
            db.query(EditSession)
            .filter(EditSession.video_id == vid_id, EditSession.profile_id == body.profile_id)
            .first()
        )
        if not session:
            session = EditSession(
                video_id=vid_id,
                profile_id=body.profile_id,
                template_id=profile.default_template_id,
            )
            db.add(session)
            db.flush()
        else:
            session.template_id = profile.default_template_id

        # 2. Auto-crop
        try:
            cx1, cy1, cx2, cy2 = auto_crop_video(str(src), num_samples=16)
            crop_box = (cx1, cy1, cx2, cy2)
            session.crop_box = json.dumps([cx1, cy1, cx2, cy2])
        except Exception:
            crop_box = (0.0, 0.0, 1.0, 1.0)
            session.crop_box = "[0.0, 0.0, 1.0, 1.0]"

        # 3. Caption placement (with actual video dimensions for accurate FIT-scale math)
        vid_w, vid_h = _probe_video_dimensions(str(src))
        try:
            caption_box_result, caption_color = auto_place_caption(
                video_box=video_box,
                template_img=template_img,
                template_caption_box=template_caption_box,
                crop_box=crop_box,
                video_dimensions=(vid_w, vid_h),
            )
            session.caption_box = json.dumps(list(caption_box_result))
            session.caption_color = caption_color
        except Exception:
            caption_box_result = (0.06, 0.08, 0.94, 0.16)
            session.caption_box = "[0.06, 0.08, 0.94, 0.16]"

        # 4. Output path
        out_name = f"{src.stem}_edited_{int(uuid.uuid4().int % 1e8)}.mp4"
        output_path = str(settings.exports_dir / out_name)

        # 5. Start render
        job_id = str(uuid.uuid4())

        # Callback to update session status when render completes
        session_id_val = session.id
        profile_id_val = body.profile_id
        video_id_val = vid_id

        def _make_callback(sid, pid, vidid):
            def _on_complete(jid: str, out_path: str):
                cb_db = SessionLocal()
                try:
                    s = cb_db.get(EditSession, sid)
                    if s:
                        s.profile_status = "edited"
                        s.exported_path = out_path
                    # Invalidate thumbnails
                    for suffix in [f"{vidid}_edited.jpg", f"{vidid}_edited_p{pid}.jpg"]:
                        t = THUMB_DIR / suffix
                        if t.exists():
                            t.unlink()
                    cb_db.commit()
                finally:
                    cb_db.close()
            return _on_complete

        start_render_job(
            job_id=job_id,
            video_path=str(src),
            output_path=output_path,
            crop_box=crop_box,
            video_box=video_box,
            template_image_path=template_image_path,
            caption_text=session.caption_text or "",
            caption_color=session.caption_color or "#000000",
            caption_box=caption_box_result,
            quality="Native 1920",
            include_audio=True,
            on_complete=_make_callback(session_id_val, profile_id_val, video_id_val),
        )

        # 6. Update per-profile state (NOT the global Video record)
        session.exported_path = output_path
        session.profile_status = "rendering"

        # Invalidate cached thumbnails
        for suffix in [f"{vid_id}_edited.jpg", f"{vid_id}_edited_p{body.profile_id}.jpg"]:
            thumb = THUMB_DIR / suffix
            if thumb.exists():
                thumb.unlink()

        results.append({
            "video_id": vid_id,
            "session_id": session.id,
            "job_id": job_id,
            "status": "rendering",
        })

    db.commit()
    return results


# ──────────────────── Batch render status ────────────────────


class BatchStatusRequest(BaseModel):
    job_ids: list[str]


class BatchStatusItem(BaseModel):
    job_id: str
    status: str
    progress: int
    error: str | None = None


@router.post("/render/batch-status", response_model=list[BatchStatusItem])
def batch_render_status(body: BatchStatusRequest):
    """Get status of multiple render jobs at once."""
    results = []
    for jid in body.job_ids:
        job = get_render_job(jid)
        if job:
            results.append({
                "job_id": jid,
                "status": job["status"],
                "progress": job["progress"],
                "error": job.get("error"),
            })
        else:
            results.append({
                "job_id": jid,
                "status": "unknown",
                "progress": 0,
                "error": None,
            })
    return results


# ──────────────────── AI Caption Generation ────────────────────


class GenerateCaptionRequest(BaseModel):
    video_id: int
    profile_id: int


class GenerateCaptionResponse(BaseModel):
    overlay: str
    caption: str
    cached: bool  # True if video analysis was already cached


@router.post("/generate-caption", response_model=GenerateCaptionResponse)
def generate_caption(body: GenerateCaptionRequest, db: Session = Depends(get_db)):
    """Two-step AI caption generation with caching.

    Step 1: Analyze video (vision call) — cached on Video.ai_description
    Step 2: Generate captions (text-only call) — profile-specific, cheap
    """
    video = db.get(Video, body.video_id)
    if not video or not video.local_path:
        raise HTTPException(404, "Video not found")
    src = _resolve(video.local_path)
    if not src.exists():
        raise HTTPException(404, "Video file missing from disk")

    profile = db.get(Profile, body.profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found")

    # Get niche name for context
    niche_name = "general"
    if profile.niche_id:
        niche = db.get(Niche, profile.niche_id)
        if niche:
            niche_name = niche.name

    # Step 1: Get or create video analysis (expensive vision call, cached)
    cached = bool(video.ai_description)
    if not video.ai_description:
        try:
            frames = extract_frames(str(src), count=4)
        except Exception as e:
            raise HTTPException(500, f"Frame extraction failed: {e}")
        if not frames:
            raise HTTPException(500, "Could not extract any frames from video")
        try:
            video.ai_description = analyze_video(frames)
            db.commit()
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(500, f"Video analysis failed: {e}")

    # Step 2: Generate captions from cached description (cheap text-only call)
    try:
        result = generate_captions(
            ai_description=video.ai_description,
            niche=niche_name,
            source_account=video.source_account or "unknown",
            profile_name=profile.name,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"AI caption generation failed: {e}")

    result["cached"] = cached
    return result


# ──────────────────── Caption from description ────────────────────


class DescribeCaptionRequest(BaseModel):
    description: str


class DescribeCaptionResponse(BaseModel):
    caption: str


@router.post("/describe-caption", response_model=DescribeCaptionResponse)
def describe_caption(body: DescribeCaptionRequest):
    """Generate a formatted post caption from a user-provided description.

    User describes what's happening → AI formats it into a short, educational
    caption with disclaimer and hashtags. No video analysis needed.
    """
    if not body.description.strip():
        raise HTTPException(400, "Description cannot be empty")
    try:
        caption = generate_caption_from_description(body.description.strip())
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Caption generation failed: {e}")
    return {"caption": caption}
