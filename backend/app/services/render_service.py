"""Render service — single-pass FFmpeg video compositing pipeline.

Pipeline: crop+scale source → composite with template + caption overlay → export MP4.
Uses hardware encoding (VideoToolbox on macOS) when available for ~5-10x speed.
"""

from __future__ import annotations

import json
import logging
import random
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Tuple

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

try:
    import imageio_ffmpeg

    FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_BIN = "ffmpeg"

DESIGN_W = 1080
DESIGN_H = 1920

# canvas_h: internal processing resolution (smaller = faster overlay compositing)
# Instagram re-encodes everything to ~720p, so lower canvas is fine for speed.
QUALITY_PROFILES = {
    "Native 1920": {"canvas_h": 1920, "crf": 22, "preset": "ultrafast", "hw_bitrate": "10M"},
    "Medium 1280p": {"canvas_h": 1280, "crf": 26, "preset": "ultrafast", "hw_bitrate": "6M"},
    "Fast 960p":    {"canvas_h": 960,  "crf": 30, "preset": "ultrafast", "hw_bitrate": "3M"},
}


# ──────────────────── Hardware encoder detection ────────────────────

_hw_encoder: str | None = None
_hw_checked = False


def _detect_hw_encoder() -> str | None:
    """Detect hardware H.264 encoder (VideoToolbox on macOS)."""
    global _hw_encoder, _hw_checked
    if _hw_checked:
        return _hw_encoder
    _hw_checked = True
    try:
        result = subprocess.run(
            [FFMPEG_BIN, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=5,
        )
        if "h264_videotoolbox" in result.stdout:
            _hw_encoder = "h264_videotoolbox"
            logger.info("Hardware encoder detected: h264_videotoolbox")
        else:
            logger.info("No hardware encoder found, using libx264")
    except Exception:
        pass
    return _hw_encoder

# ──────────────────── In-memory job tracker ────────────────────

_render_jobs: Dict[str, dict] = {}
_lock = threading.Lock()


def get_render_job(job_id: str) -> dict | None:
    with _lock:
        return _render_jobs.get(job_id, {}).copy() if job_id in _render_jobs else None


def _update_job(job_id: str, **kwargs: object) -> None:
    with _lock:
        if job_id in _render_jobs:
            _render_jobs[job_id].update(kwargs)


def _create_job(job_id: str) -> None:
    with _lock:
        _render_jobs[job_id] = {
            "status": "pending",
            "progress": 0,
            "output_path": None,
            "error": None,
        }


# ──────────────────── Helpers ────────────────────


def _probe_duration(video_path: str) -> float:
    """Get video duration in seconds via ffprobe."""
    try:
        probe = FFMPEG_BIN.replace("ffmpeg", "ffprobe") if "ffmpeg" in FFMPEG_BIN else "ffprobe"
        result = subprocess.run(
            [probe, "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", video_path],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return 10.0


def _probe_video_dimensions(video_path: str) -> Tuple[int, int]:
    """Get video width and height via ffmpeg -i (parse stderr)."""
    import re
    try:
        result = subprocess.run(
            [FFMPEG_BIN, "-i", video_path, "-hide_banner"],
            capture_output=True, text=True, timeout=10,
        )
        # Parse "Stream #0:0: Video: ..., 576x1024, ..." from stderr
        match = re.search(r"Stream.*Video:.* (\d{2,5})x(\d{2,5})", result.stderr)
        if match:
            return int(match.group(1)), int(match.group(2))
    except Exception:
        pass
    return 1080, 1920


def _quantize_crop(
    crop_norm: Tuple[float, float, float, float],
    vid_w: int,
    vid_h: int,
) -> Tuple[int, int, int, int]:
    """Convert normalized crop box to pixel coordinates, ensuring even dimensions."""
    x1, y1, x2, y2 = crop_norm
    # Clamp normalized values to [0, 1]
    x1 = max(0.0, min(1.0, x1))
    y1 = max(0.0, min(1.0, y1))
    x2 = max(0.0, min(1.0, x2))
    y2 = max(0.0, min(1.0, y2))

    cx = max(0, int(round(x1 * vid_w)))
    cy = max(0, int(round(y1 * vid_h)))
    cw = max(2, int(round((x2 - x1) * vid_w)))
    ch = max(2, int(round((y2 - y1) * vid_h)))

    # Clamp dimensions to video bounds
    cw = min(cw, vid_w)
    ch = min(ch, vid_h)

    # Ensure even dimensions for yuv420p
    cw -= cw % 2
    ch -= ch % 2

    # Ensure crop fits within video
    if cx + cw > vid_w:
        cx = max(0, vid_w - cw)
    if cy + ch > vid_h:
        cy = max(0, vid_h - ch)
    return cx, cy, cw, ch


def _font_path(bold: bool = True) -> str | None:
    """Find a system font for caption rendering. Defaults to bold."""
    if bold:
        candidates = [
            "/System/Library/Fonts/Helvetica.ttc",  # index 1 = bold
            "/System/Library/Fonts/SFNSText-Bold.otf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        ]
    else:
        candidates = [
            "/System/Library/Fonts/Helvetica.ttc",  # index 0 = regular
            "/System/Library/Fonts/SFNSText.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
        ]
    for p in candidates:
        if Path(p).exists():
            return p
    return None


def _render_text_rgba(
    text: str,
    target_w: int,
    target_h: int,
    color: Tuple[int, int, int] = (0, 0, 0),
    align: str = "center",
    valign: str = "top",
    pad: int = 6,
    bold: bool = True,
) -> Image.Image:
    """Render text into an RGBA image with auto-sized bold font."""
    target_w = max(4, int(target_w))
    target_h = max(4, int(target_h))
    pad = max(0, int(pad))
    inner_w = max(2, target_w - 2 * pad)
    inner_h = max(2, target_h - 2 * pad)
    img = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    fp = _font_path(bold=bold)

    def _font(sz: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        try:
            if fp and fp.endswith(".ttc"):
                # .ttc: index 1 = bold, index 0 = regular
                return ImageFont.truetype(fp, sz, index=1 if bold else 0)
            return ImageFont.truetype(fp, sz) if fp else ImageFont.load_default()
        except Exception:
            return ImageFont.load_default()

    def _wrap(para: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
        words = para.split()
        if not words:
            return [""]
        lines: list[str] = []
        cur = words[0]
        for w in words[1:]:
            test = f"{cur} {w}"
            bbox = dr.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] <= max_w:
                cur = test
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        return lines

    # Binary search for best font size
    # Cap at 52px for bold caption sizing — matches TeachYouVids style.
    # Short text stays readable at 52px; long text shrinks only if it exceeds box height.
    MAX_CAPTION_FONT = 52
    lo, hi = 10, min(MAX_CAPTION_FONT, max(12, int(inner_h * 0.95)))
    best = lo
    best_lines: list[str] = [text]
    while lo <= hi:
        mid = (lo + hi) // 2
        f = _font(mid)
        lines: list[str] = []
        for para in text.replace("\r", "").split("\n"):
            if not para.strip():
                lines.append("")
                continue
            lines.extend(_wrap(para, f, int(inner_w * 0.96)))
        bbox = dr.multiline_textbbox(
            (0, 0), "\n".join(lines), font=f, spacing=int(mid * 0.2), align=align
        )
        bw = bbox[2] - bbox[0]
        bh = bbox[3] - bbox[1]
        if bw <= int(inner_w * 0.98) and bh <= int(inner_h * 0.95):
            best = mid
            best_lines = lines
            lo = mid + 1
        else:
            hi = mid - 1

    f = _font(best)
    block = "\n".join(best_lines)
    bbox = dr.multiline_textbbox(
        (0, 0), block, font=f, spacing=int(best * 0.2), align=align
    )
    bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if align == "center":
        x = pad + max(0, (inner_w - bw) // 2) - bbox[0]
    else:
        x = pad + 2 - bbox[0]
    if valign == "top":
        y = pad - bbox[1]
    else:
        y = pad + max(0, (inner_h - bh) // 2) - bbox[1]
    dr.multiline_text(
        (x, y), block, fill=color + (255,), font=f,
        spacing=int(best * 0.2), align=align,
    )
    return img


def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 6:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    return (0, 0, 0)


# ──────────────────── Fingerprint obfuscation ────────────────────


def _obfuscation_vfilters() -> str:
    """Build a chain of subtle, randomized FFmpeg video filters.

    Each render produces a unique pixel-level fingerprint that defeats
    content-matching / duplicate-detection systems while remaining
    imperceptible to viewers.

    Only uses lightweight filters — micro-crop and color shift are nearly
    free. The expensive noise/unsharp filters are skipped; uniqueness comes
    from the encoding params (random GOP, B-frames, CRF jitter) instead.
    """
    filters: list[str] = []

    # 1. Micro-crop: trim 1-3 pixels from each edge (changes every frame hash)
    pad = random.randint(1, 3)
    filters.append(f"crop=iw-{pad * 2}:ih-{pad * 2}:{pad}:{pad}")

    # 2. Micro color/brightness shift via eq filter (nearly free)
    bright = random.uniform(-0.03, 0.03)
    contrast = random.uniform(0.98, 1.02)
    saturation = random.uniform(0.97, 1.03)
    filters.append(
        f"eq=brightness={bright:.4f}:contrast={contrast:.4f}:saturation={saturation:.4f}"
    )

    return ",".join(filters)


def _obfuscation_encoding_args() -> list[str]:
    """Randomize encoding parameters so the bitstream structure differs per render."""
    # CRF jitter: ±1-2 from base (applied on top of quality profile CRF)
    crf_jitter = random.choice([-2, -1, 0, 1, 2])

    # GOP / keyframe interval: random between 24-72 frames
    gop = random.randint(24, 72)

    # B-frame count: 0-4
    bframes = random.randint(0, 4)

    return [
        "-g", str(gop),
        "-bf", str(bframes),
    ], crf_jitter


def _obfuscation_afilters() -> str:
    """Subtle audio modifications to defeat audio fingerprinting."""
    filters: list[str] = []

    # Micro tempo shift: 0.98x - 1.02x (nearly inaudible)
    tempo = random.uniform(0.98, 1.02)
    filters.append(f"atempo={tempo:.4f}")

    # Micro pitch-preserving volume jitter
    vol = random.uniform(0.97, 1.03)
    filters.append(f"volume={vol:.4f}")

    return ",".join(filters)


# ──────────────────── Main render pipeline ────────────────────


def render_video(
    video_path: str,
    output_path: str,
    crop_box: Tuple[float, float, float, float],
    video_box: Tuple[float, float, float, float],
    template_image_path: str | None = None,
    caption_text: str = "",
    caption_color: str = "#000000",
    caption_box: Tuple[float, float, float, float] = (0.06, 0.08, 0.94, 0.16),
    quality: str = "Native 1920",
    include_audio: bool = False,
    job_id: str | None = None,
) -> str:
    """Single-pass FFmpeg render pipeline. Returns output path.

    All inputs (source video, template image, caption overlay) are fed into one
    FFmpeg complex filtergraph — crop, scale, obfuscate, composite, and encode
    in a single pass. This eliminates the intermediate file and double-encode
    that the old two-pass approach required.
    """
    if job_id:
        _update_job(job_id, status="rendering", progress=10)

    opts = QUALITY_PROFILES.get(quality, QUALITY_PROFILES["Native 1920"])
    crf = opts["crf"]
    preset = opts["preset"]

    # ── Internal canvas size ──
    # Medium/Fast use a smaller canvas so the overlay filter processes
    # fewer pixels per frame (the biggest performance bottleneck).
    # Instagram re-encodes everything, so lower internal resolution is fine.
    canvas_h = opts.get("canvas_h", DESIGN_H)
    canvas_w = int(round(DESIGN_W * (canvas_h / DESIGN_H)))
    canvas_w -= canvas_w % 2
    canvas_h -= canvas_h % 2

    # Probe source video dimensions
    vid_w, vid_h = _probe_video_dimensions(video_path)

    # Calculate crop in pixels
    cx, cy, cw, ch = _quantize_crop(crop_box, vid_w, vid_h)

    # Calculate video placement on canvas (using canvas size, not design size)
    vx1, vy1, vx2, vy2 = video_box
    bx = int(vx1 * canvas_w)
    by = int(vy1 * canvas_h)
    bw = int((vx2 - vx1) * canvas_w)
    bh = int((vy2 - vy1) * canvas_h)

    # Ensure box dimensions are even for yuv420p
    bw -= bw % 2
    bh -= bh % 2

    # WIDTH-FILL scaling: match box width, crop height if overflow
    scale = bw / float(max(1, cw))
    sw = max(2, int(round(cw * scale)))
    sw -= sw % 2
    sh = max(2, int(round(ch * scale)))
    sh -= sh % 2
    ox = bx
    oy = by

    tmpdir = Path(tempfile.gettempdir()) / "content_engine_render"
    tmpdir.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time() * 1000)

    # ── Pre-compose template + caption into a single RGBA overlay ──
    # Generated at canvas_w × canvas_h (not full 1080×1920 for Medium/Fast).
    # The overlay has a transparent hole where the video goes.

    overlay_img = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255))

    if template_image_path and Path(template_image_path).exists():
        tmpl = Image.open(template_image_path).convert("RGBA")
        tmpl = tmpl.resize((canvas_w, canvas_h), Image.LANCZOS)
        overlay_img = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255))
        overlay_img.alpha_composite(tmpl)

    # Cut out the video box area (make transparent so video shows through)
    draw_ol = ImageDraw.Draw(overlay_img)
    draw_ol.rectangle([bx, by, bx + bw, by + bh], fill=(0, 0, 0, 0))

    # Render caption directly onto the overlay
    if caption_text.strip():
        cbx1, cby1, cbx2, cby2 = caption_box
        cap_x = int(cbx1 * canvas_w)
        cap_y = int(cby1 * canvas_h)
        cap_w = max(4, int((cbx2 - cbx1) * canvas_w))
        cap_h = max(4, int((cby2 - cby1) * canvas_h))
        caption_img = _render_text_rgba(
            caption_text, cap_w, cap_h, _hex_to_rgb(caption_color),
            valign="center",
        )
        overlay_img.paste(caption_img, (cap_x, cap_y), caption_img)

    overlay_path = tmpdir / f"overlay_{stamp}.png"
    overlay_img.save(str(overlay_path), "PNG")

    if job_id:
        _update_job(job_id, progress=20)

    # ── Generate per-render obfuscation params ──
    obfusc_vf = _obfuscation_vfilters()
    obfusc_enc_args, crf_jitter = _obfuscation_encoding_args()

    # Probe video duration for real-time progress
    duration = _probe_duration(video_path)

    # ── Single-pass FFmpeg ──
    #
    # Strategy: crop/scale the source video, pad to canvas size at the
    # correct position, then overlay the pre-composed template+caption
    # image on top. The template has a transparent hole where the video
    # is, so only 1 overlay operation per frame.
    #
    # Inputs:
    #   [0] source video
    #   [1] pre-composed overlay (template + caption, RGBA, looped)

    inputs = [
        "-i", video_path,                                                 # [0]
        "-loop", "1", "-framerate", "30", "-i", str(overlay_path),        # [1]
    ]

    # Build complex filtergraph
    steps: list[str] = []

    # Source video: crop → scale → obfuscate → position on canvas
    crop_f = f"crop={cw}:{ch}:{cx}:{cy}"
    scale_f = f"scale={sw}:{sh}"

    # If scaled video is taller than box, crop the overflow; otherwise use as-is
    if sh > bh:
        fill_crop = f"crop={bw}:{bh}:(iw-{bw})/2:0"
        pad_f = f"pad={canvas_w}:{canvas_h}:{ox}:{oy}:white"
        steps.append(f"[0:v]{crop_f},{scale_f},{obfusc_vf},{fill_crop},{pad_f},setsar=1[base]")
    else:
        # Video is shorter than box — pad within box, position at top
        pad_f = f"pad={canvas_w}:{canvas_h}:{ox}:{oy}:white"
        steps.append(f"[0:v]{crop_f},{scale_f},{obfusc_vf},{pad_f},setsar=1[base]")

    # Overlay template+caption on top (single overlay at canvas resolution)
    steps.append("[1:v]format=rgba,setsar=1[ovr]")
    steps.append("[base][ovr]overlay=0:0:shortest=1:eof_action=pass[vout]")

    # Audio obfuscation — use audio from input [0] (source video)
    if include_audio:
        obfusc_af = _obfuscation_afilters()
        steps.append(f"[0:a]{obfusc_af}[aout]")

    vf = ";".join(steps)
    final_crf = max(0, min(51, crf + crf_jitter))
    hw_bitrate = opts.get("hw_bitrate", "10M")

    cmd = [
        FFMPEG_BIN, "-y", "-hide_banner",
        "-loglevel", "error",
        "-progress", "pipe:1",
    ] + inputs + [
        "-filter_complex", vf,
        "-map", "[vout]",
    ]

    if include_audio:
        cmd += ["-map", "[aout]", "-c:a", "aac"]
    else:
        cmd += ["-an"]

    cmd += [
        "-map_metadata", "-1",
        "-map_chapters", "-1",
    ]

    # Encoder selection: hardware (VideoToolbox) >> software (libx264 ultrafast)
    hw_enc = _detect_hw_encoder()
    if hw_enc:
        cmd += [
            "-c:v", hw_enc,
            "-pix_fmt", "yuv420p",
            "-b:v", hw_bitrate,
            "-r", "30",
        ]
    else:
        cmd += [
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-preset", preset, "-crf", str(final_crf),
            "-r", "30",
            "-threads", "0",
        ] + obfusc_enc_args

    cmd += [
        "-shortest",
        output_path,
    ]

    # ── Run with real-time progress parsing ──
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for line in proc.stdout:
            text = line.decode("utf-8", "ignore").strip()
            if text.startswith("out_time_us=") and job_id and duration > 0:
                try:
                    us = int(text.split("=", 1)[1])
                    cur_sec = us / 1_000_000.0
                    # Map encoding progress to 25-95% range
                    pct = min(95, 25 + int((cur_sec / duration) * 70))
                    _update_job(job_id, progress=pct)
                except (ValueError, IndexError):
                    pass
        proc.wait(timeout=300)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        if job_id:
            _update_job(job_id, status="failed", error="Render timed out (5 min)")
        raise RuntimeError("Render timed out")

    # Clean up temp files
    if overlay_path.exists():
        try:
            overlay_path.unlink()
        except Exception:
            pass

    if proc.returncode != 0:
        err = proc.stderr.read().decode("utf-8", "ignore")
        if job_id:
            _update_job(job_id, status="failed", error=f"Render failed: {err}")
        raise RuntimeError(f"Render failed: {err}")

    if job_id:
        _update_job(job_id, status="complete", progress=100, output_path=output_path)

    return output_path


# ──────────────────── Background render launcher ────────────────────


def start_render_job(
    job_id: str,
    video_path: str,
    output_path: str,
    crop_box: Tuple[float, float, float, float],
    video_box: Tuple[float, float, float, float],
    template_image_path: str | None = None,
    caption_text: str = "",
    caption_color: str = "#000000",
    caption_box: Tuple[float, float, float, float] = (0.06, 0.08, 0.94, 0.16),
    quality: str = "Native 1920",
    include_audio: bool = False,
    on_complete: "Callable[[str, str], None] | None" = None,
) -> None:
    """Launch render in a background thread.

    on_complete(job_id, output_path) is called in the thread after success.
    """
    _create_job(job_id)

    def _run() -> None:
        try:
            render_video(
                video_path=video_path,
                output_path=output_path,
                crop_box=crop_box,
                video_box=video_box,
                template_image_path=template_image_path,
                caption_text=caption_text,
                caption_color=caption_color,
                caption_box=caption_box,
                quality=quality,
                include_audio=include_audio,
                job_id=job_id,
            )
            if on_complete:
                try:
                    on_complete(job_id, output_path)
                except Exception as cb_err:
                    import logging
                    logging.getLogger(__name__).error("on_complete callback failed: %s", cb_err)
        except Exception as e:
            _update_job(job_id, status="failed", error=str(e))

    t = threading.Thread(target=_run, daemon=True)
    t.start()
