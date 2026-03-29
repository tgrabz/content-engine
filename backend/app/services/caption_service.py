"""Caption placement service — content-aware caption positioning.

Analyzes the composed frame (template + video) to find the optimal caption
position by scoring candidate regions for contrast, uniformity, and available
space.  Returns normalized coordinates + text color.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np
from PIL import Image

DESIGN_W = 1080
DESIGN_H = 1920

# ── Layout constants ──
SIDE_MARGIN = 0.05          # 5% side padding within video width
GAP_BELOW_HEADER = 0.005    # small gap under template header
GAP_ABOVE_VIDEO = 0.005     # small gap above video box
MIN_HEADER_ROW_PCT = 0.004
MIN_VALID_HEADER_RUN = 6

# Caption height limits (fraction of canvas height)
CAP_H_PREFERRED = 0.12      # use available gap for large text
CAP_H_MIN = 0.03            # absolute minimum (~58px, enough for 1-2 lines)
CAP_H_MAX = 0.16            # absolute maximum


# ──────────────────── Image analysis helpers ────────────────────


def _luminance(arr: np.ndarray) -> np.ndarray:
    """ITU-R BT.709 luminance from RGB float array (H,W,3) -> (H,W)."""
    return 0.2126 * arr[:, :, 0] + 0.7152 * arr[:, :, 1] + 0.0722 * arr[:, :, 2]


def _region_busyness(gray: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> float:
    """Measure how 'busy' a region is (0=uniform, 1=very noisy).

    Uses local standard deviation of luminance — uniform backgrounds score low,
    detailed/textured areas score high.
    """
    roi = gray[y1:y2, x1:x2]
    if roi.size < 4:
        return 0.0
    # Compute std dev in small blocks then average
    bh, bw = max(1, roi.shape[0] // 4), max(1, roi.shape[1] // 4)
    stds = []
    for r in range(0, roi.shape[0] - bh + 1, bh):
        for c in range(0, roi.shape[1] - bw + 1, bw):
            block = roi[r:r + bh, c:c + bw]
            stds.append(float(block.std()))
    return float(np.mean(stds)) if stds else 0.0


def _region_contrast_score(gray: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> float:
    """Score how readable text would be in this region (higher = better).

    Prefers uniform backgrounds with clear luminance extremes (very dark or very light)
    because text can be the opposite color.
    """
    roi = gray[y1:y2, x1:x2]
    if roi.size < 4:
        return 0.0
    mean_lum = float(roi.mean())
    std_lum = float(roi.std())
    # Best contrast: very dark (mean near 0) or very light (mean near 1)
    # with low variance (uniform background)
    distance_from_mid = abs(mean_lum - 0.5)  # 0..0.5
    uniformity = max(0.0, 1.0 - std_lum * 4.0)  # penalize variance
    return distance_from_mid * 2.0 * uniformity  # 0..1


def _choose_text_color(
    comp: Image.Image, x1: int, y1: int, x2: int, y2: int
) -> Tuple[int, int, int]:
    """Pick black or white text based on background luminance in region."""
    roi = comp.convert("RGB").crop((max(0, x1), max(0, y1), max(x1 + 1, x2), max(y1 + 1, y2)))
    arr = np.asarray(roi).astype(np.float32) / 255.0
    if arr.size == 0:
        return (0, 0, 0)
    Y = _luminance(arr)
    mean_lum = float(Y.mean())
    if mean_lum > 0.55:
        return (0, 0, 0)
    return (255, 255, 255)


# ──────────────────── Template analysis ────────────────────


def _video_band_inside(bx: int, bw: int) -> Tuple[int, int]:
    """Horizontal band for caption aligned to video with side margins."""
    side = int(max(8, SIDE_MARGIN * bw))
    x1 = bx + side
    x2 = bx + bw - side
    if x2 <= x1 + 8:
        mid = bx + bw // 2
        x1 = max(0, mid - 40)
        x2 = min(DESIGN_W, mid + 40)
    return x1, x2


def _template_bottom_px(
    template_img: Image.Image | None, xL: int, xR: int, y_limit: int
) -> int:
    """Find bottom of template header above the video using non-white row detection."""
    if template_img is None:
        return -1

    # Composite onto white background first so transparent areas
    # (where the video shows through) register as white, not black
    flat = Image.new("RGBA", template_img.size, (255, 255, 255, 255))
    flat.alpha_composite(template_img.convert("RGBA"))
    arr = np.asarray(flat.convert("RGB"))
    H, W, _ = arr.shape
    x1 = max(0, min(xL, W - 1))
    x2 = max(x1 + 1, min(xR, W))
    lim = max(0, min(y_limit, H))
    band = arr[:lim, x1:x2, :]
    if band.size == 0:
        return -1

    delta = np.abs(band.astype(np.int16) - 255).max(axis=2)
    nonwhite = delta > 14
    row_pct = nonwhite.mean(axis=1)

    thr = max(0.003, float(MIN_HEADER_ROW_PCT))
    hit = row_pct >= thr

    last = -1
    run = 0
    for y, v in enumerate(hit):
        if v:
            run += 1
        else:
            if run >= int(MIN_VALID_HEADER_RUN):
                last = y - 1
            run = 0
    if run >= int(MIN_VALID_HEADER_RUN):
        last = len(hit) - 1
    return int(last)


def _compose_for_analysis(
    template_img: Image.Image | None,
    video_frame: Image.Image | None,
    video_box: Tuple[float, float, float, float],
) -> Image.Image:
    """Compose template + video frame for analysis.

    Matches the render pipeline layer order:
    1. Template as base (opaque background)
    2. Video pasted ON TOP at video_box position
    """
    comp = Image.new("RGB", (DESIGN_W, DESIGN_H), (255, 255, 255))

    # Layer 1: template as base
    if template_img is not None:
        tmpl = template_img.convert("RGBA").resize(
            (DESIGN_W, DESIGN_H), Image.LANCZOS
        )
        comp_rgba = comp.convert("RGBA")
        comp_rgba.alpha_composite(tmpl)
        comp = comp_rgba.convert("RGB")

    # Layer 2: video on top within video_box
    if video_frame is not None:
        vx1, vy1, vx2, vy2 = video_box
        bx = int(vx1 * DESIGN_W)
        by = int(vy1 * DESIGN_H)
        bw = int((vx2 - vx1) * DESIGN_W)
        bh = int((vy2 - vy1) * DESIGN_H)
        if bw > 0 and bh > 0:
            vf = video_frame.resize((bw, bh), Image.LANCZOS)
            comp.paste(vf, (bx, by))

    return comp


# ──────────────────── Candidate scoring ────────────────────


def _score_candidate(
    gray: np.ndarray,
    xL: int, xR: int,
    y1: int, y2: int,
    avail_h: int,
    position_type: str,
) -> float:
    """Score a candidate caption region.  Higher = better placement.

    Factors:
      - contrast:   how readable text will be (uniform dark or light bg)
      - busyness:   penalize detailed/noisy regions (faces, text, patterns)
      - size:       prefer having enough vertical space for text
      - position:   slight preference for above-video over below
    """
    h = y2 - y1
    if h < 20 or xR - xL < 40:
        return -1.0

    contrast = _region_contrast_score(gray, xL, y1, xR, y2)
    busyness = _region_busyness(gray, xL, y1, xR, y2)

    # Size score: 1.0 when height >= preferred, tapers down for smaller
    pref_h = int(CAP_H_PREFERRED * DESIGN_H)
    size_score = min(1.0, h / max(1, pref_h))

    # Position bonus: above video is best, overlay is last resort
    pos_bonus = {
        "above": 0.20, "compact_above": 0.15, "below": 0.05, "overlay": 0.0,
    }.get(position_type, 0.0)

    score = (
        contrast * 0.35          # 35% weight: good contrast
        + (1.0 - busyness) * 0.25  # 25% weight: clean background
        + size_score * 0.20       # 20% weight: adequate size
        + pos_bonus              # 20% max: position preference
    )
    return score


# ──────────────────── Main placement function ────────────────────


def _video_content_rect(
    video_box: Tuple[float, float, float, float],
    crop_box: Tuple[float, float, float, float] | None,
    vid_w: int,
    vid_h: int,
) -> Tuple[int, int, int, int]:
    """Calculate where the actual video content appears (ox, oy, sw, sh in pixels).

    After cropping, the video is FIT-scaled into video_box and centered.
    Returns (x, y, width, height) of the visible video content on canvas.
    """
    W, H = DESIGN_W, DESIGN_H
    vx1, vy1, vx2, vy2 = video_box
    bx = int(vx1 * W)
    by = int(vy1 * H)
    bw = int((vx2 - vx1) * W)
    bh = int((vy2 - vy1) * H)

    if crop_box is None or vid_w <= 0 or vid_h <= 0:
        return bx, by, bw, bh  # no crop info — fall back to video_box

    cx1, cy1_c, cx2, cy2_c = crop_box
    cw = max(1, int(round((cx2 - cx1) * vid_w)))
    ch = max(1, int(round((cy2_c - cy1_c) * vid_h)))

    # FIT scale: same math as render_service
    scale = min(bw / float(max(1, cw)), bh / float(max(1, ch)))
    sw = max(2, int(round(cw * scale)))
    sh = max(2, int(round(ch * scale)))
    ox = int(round(bx + (bw - sw) / 2.0))  # center horizontally
    oy = by  # top-align vertically (matches render pipeline)
    return max(0, ox), max(by, oy), sw, sh


def auto_place_caption(
    video_box: Tuple[float, float, float, float],
    template_img: Image.Image | None = None,
    video_frame: Image.Image | None = None,
    template_caption_box: Tuple[float, float, float, float] | None = None,
    crop_box: Tuple[float, float, float, float] | None = None,
    video_dimensions: Tuple[int, int] | None = None,
) -> Tuple[Tuple[float, float, float, float], str]:
    """Place caption centered between the template branding and the video box.

    The render pipeline uses FILL scaling, so the video always fills the
    entire video_box.  The caption goes in the gap between branding and
    video_box top, centered vertically.

    Returns (caption_box_normalized, hex_color).
    """
    W, H = DESIGN_W, DESIGN_H

    # Unpack video_box to pixel coords
    vx1, vy1, vx2, vy2 = video_box
    bx = int(vx1 * W)
    by = int(vy1 * H)
    bw = int((vx2 - vx1) * W)
    bh = int((vy2 - vy1) * H)

    # Horizontal band: span the full video_box width with side margins
    side = int(SIDE_MARGIN * bw)
    xL = bx + side
    xR = bx + bw - side

    # Always dynamically center the caption between branding header
    # bottom and video_box top — regardless of template caption_box
    tpl_bottom = _template_bottom_px(template_img, xL, xR, by)
    branding_clear = (tpl_bottom + 1 + int(0.005 * H)) if tpl_bottom >= 0 else int(0.02 * H)

    # Caption goes between branding and video_box top, centered
    cap_h = int(CAP_H_PREFERRED * H)
    avail = by - branding_clear
    if avail >= int(CAP_H_MIN * H):
        actual_h = min(cap_h, avail)
        cy1 = branding_clear + (avail - actual_h) // 2
        cy2 = cy1 + actual_h
    else:
        # Not enough space — overlay on upper portion of video
        cy1 = branding_clear
        cy2 = cy1 + cap_h
        cy2 = min(cy2, by + bh // 3)

    # Compose for color analysis
    comp = _compose_for_analysis(template_img, video_frame, video_box)
    col = _choose_text_color(comp, xL, cy1, xR, cy2)

    box = (xL / float(W), cy1 / float(H), xR / float(W), cy2 / float(H))
    return box, _rgb_to_hex(col)


def _rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
