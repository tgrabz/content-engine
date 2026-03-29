"""Auto-crop service — content-aware crop detection for video frames.

Ported from sm-tester-polished/pages/2 Edit Videos.py.
Multi-stage algorithm: motion mask → energy projection trim → edge snap.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple

import numpy as np
from PIL import Image, ImageFilter

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import imageio_ffmpeg

    FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_BIN = "ffmpeg"


# ──────────────────── Frame extraction ────────────────────


def extract_frames(
    video_path: str, num_frames: int = 16, duration: float | None = None
) -> List[Image.Image]:
    """Extract evenly-spaced frames from a video using ffmpeg."""
    if duration is None:
        duration = _probe_duration(video_path)
    if duration <= 0:
        duration = 10.0

    timestamps = [
        float(i) / (num_frames + 1) * duration for i in range(1, num_frames + 1)
    ]
    frames = []
    for t in timestamps:
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        try:
            subprocess.run(
                [
                    FFMPEG_BIN,
                    "-ss",
                    str(t),
                    "-i",
                    video_path,
                    "-vframes",
                    "1",
                    "-q:v",
                    "2",
                    "-y",
                    tmp.name,
                ],
                capture_output=True,
                check=True,
                timeout=15,
            )
            frames.append(Image.open(tmp.name).convert("RGB"))
        except Exception:
            pass
        finally:
            Path(tmp.name).unlink(missing_ok=True)
    return frames


def _probe_duration(video_path: str) -> float:
    try:
        result = subprocess.run(
            [
                FFMPEG_BIN.replace("ffmpeg", "ffprobe")
                if "ffmpeg" in FFMPEG_BIN
                else "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                video_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return 10.0


# ──────────────────── Helpers ────────────────────


def _to_gray_np(img: Image.Image) -> np.ndarray:
    if cv2 is not None:
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
    return np.array(img.convert("L"))


def _resize_np(arr: np.ndarray, new_w: int) -> np.ndarray:
    H, W = arr.shape[:2]
    if W == new_w:
        return arr
    scale = new_w / float(W)
    new_h = int(round(H * scale))
    if cv2 is not None:
        return cv2.resize(arr, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return np.array(Image.fromarray(arr).resize((new_w, new_h), Image.LANCZOS))


def _morph_close(mask: np.ndarray, ksize: int) -> np.ndarray:
    if ksize <= 1:
        return (mask > 0).astype(np.uint8)
    if cv2 is not None:
        kernel = np.ones((ksize, ksize), np.uint8)
        closed = cv2.morphologyEx(
            (mask > 0).astype(np.uint8) * 255, cv2.MORPH_CLOSE, kernel
        )
        return (closed > 127).astype(np.uint8)
    pil = Image.fromarray((mask > 0).astype(np.uint8) * 255, mode="L")
    pil = pil.filter(ImageFilter.MaxFilter(ksize)).filter(
        ImageFilter.MinFilter(ksize)
    )
    return (np.array(pil) > 127).astype(np.uint8)


def _smooth1d(arr: np.ndarray, k: int) -> np.ndarray:
    k = max(1, int(k))
    if k == 1:
        return arr
    pad = k // 2
    padded = np.pad(arr, (pad, pad), mode="edge")
    ker = np.ones(k, dtype=np.float32) / float(k)
    return np.convolve(padded, ker, mode="valid")


def _trim_by_energy_projection(
    dyn: np.ndarray,
    box_xyxy: Tuple[int, int, int, int],
    keep: float,
    smooth_px: int,
) -> Tuple[int, int, int, int]:
    x1, y1, x2, y2 = box_xyxy
    x1 = max(0, min(x1, dyn.shape[1] - 1))
    x2 = max(x1 + 1, min(x2, dyn.shape[1]))
    y1 = max(0, min(y1, dyn.shape[0] - 1))
    y2 = max(y1 + 1, min(y2, dyn.shape[0]))
    crop_dyn = dyn[y1:y2, x1:x2].astype(np.float32)
    if crop_dyn.size == 0 or crop_dyn.max() <= 1e-6:
        return x1, y1, x2, y2
    row_e = _smooth1d(crop_dyn.sum(axis=1), max(1, smooth_px))
    col_e = _smooth1d(crop_dyn.sum(axis=0), max(1, smooth_px))
    keep = float(np.clip(keep, 0.5, 0.999))
    tail = (1.0 - keep) / 2.0

    def _trim_axis(e: np.ndarray):
        total = float(e.sum())
        if total <= 0:
            return 0, len(e)
        c = np.cumsum(e) / total
        lo = int(np.searchsorted(c, tail))
        hi = int(np.searchsorted(c, 1.0 - tail))
        lo = max(0, min(lo, len(e) - 1))
        hi = max(lo + 1, min(hi, len(e)))
        return lo, hi

    r0, r1 = _trim_axis(row_e)
    c0, c1 = _trim_axis(col_e)
    return (x1 + c0, y1 + r0, x1 + c1, y1 + r1)


def _tighten_box_edges_fullres(
    ref_rgb: Image.Image,
    X1: int,
    Y1: int,
    X2: int,
    Y2: int,
    ratio: float = 0.06,
    max_trim_px: int = 24,
) -> Tuple[int, int, int, int]:
    g = _to_gray_np(ref_rgb)
    X1 = max(0, min(X1, g.shape[1] - 1))
    X2 = max(X1 + 1, min(X2, g.shape[1]))
    Y1 = max(0, min(Y1, g.shape[0] - 1))
    Y2 = max(Y1 + 1, min(Y2, g.shape[0]))
    roi = g[Y1:Y2, X1:X2]
    if roi.size == 0:
        return X1, Y1, X2, Y2
    if cv2 is not None:
        edges = cv2.Canny(roi, 60, 160)
    else:
        gy, gx = np.gradient(roi.astype(np.float32))
        edges = np.sqrt(gx * gx + gy * gy)
        m = edges.max()
        edges = (edges / (m + 1e-6) * 255).astype(np.uint8)
    row_e = edges.sum(axis=1).astype(np.float32)
    col_e = edges.sum(axis=0).astype(np.float32)
    r_thr = max(8.0, float(row_e.max()) * ratio)
    c_thr = max(8.0, float(col_e.max()) * ratio)
    t_in = next((i for i, v in enumerate(row_e) if v >= r_thr), 0)
    b_in = next((i for i, v in enumerate(row_e[::-1]) if v >= r_thr), 0)
    l_in = next((i for i, v in enumerate(col_e) if v >= c_thr), 0)
    r_in = next((i for i, v in enumerate(col_e[::-1]) if v >= c_thr), 0)
    t_in = int(min(max_trim_px, t_in))
    b_in = int(min(max_trim_px, b_in))
    l_in = int(min(max_trim_px, l_in))
    r_in = int(min(max_trim_px, r_in))
    Y1n = min(Y2 - 2, Y1 + t_in)
    Y2n = max(Y1n + 2, Y2 - b_in)
    X1n = min(X2 - 2, X1 + l_in)
    X2n = max(X1n + 2, X2 - r_in)
    return (X1n, Y1n, X2n, Y2n)


def _letterbox_detect(
    frame: Image.Image, min_bar_px: int = 6, threshold: float = 5.0
) -> Tuple[float, float, float, float]:
    """Detect and remove only black/solid-color bars (letterboxing/pillarboxing).

    Only crops when there are clear uniform bars at the edges — does NOT crop
    content. Returns (0,0,1,1) if no bars are detected.
    """
    arr = np.array(frame.convert("RGB"))
    H, W, _ = arr.shape

    # Detect top bar: rows where pixel variance is very low (solid color)
    top = 0
    for y in range(H // 4):  # only check top 25%
        row_var = arr[y].astype(float).std()
        if row_var > threshold:
            top = y
            break
    else:
        top = 0  # no bar detected

    # Detect bottom bar
    bot = H
    for y in range(H - 1, H * 3 // 4, -1):
        row_var = arr[y].astype(float).std()
        if row_var > threshold:
            bot = y + 1
            break
    else:
        bot = H

    # Detect left bar
    left = 0
    for x in range(W // 4):
        col_var = arr[:, x, :].astype(float).std()
        if col_var > threshold:
            left = x
            break
    else:
        left = 0

    # Detect right bar
    right = W
    for x in range(W - 1, W * 3 // 4, -1):
        col_var = arr[:, x, :].astype(float).std()
        if col_var > threshold:
            right = x + 1
            break
    else:
        right = W

    # Only apply if bars are at least min_bar_px thick
    if top < min_bar_px:
        top = 0
    if H - bot < min_bar_px:
        bot = H
    if left < min_bar_px:
        left = 0
    if W - right < min_bar_px:
        right = W

    # Safety: ensure we keep at least 80% of each dimension
    if (right - left) < W * 0.8 or (bot - top) < H * 0.8:
        return (0.0, 0.0, 1.0, 1.0)

    return (left / W, top / H, right / W, bot / H)


# ──────────────────── Main auto-crop ────────────────────


def static_overlay_autocrop(
    frames: List[Image.Image],
    dyn_percentile: float = 65.0,
    dyn_abs_floor: int = 8,
    close_ksize: int = 7,
    min_keep_area_pct: float = 15.0,
    keep_energy_pct: float = 98.8,
    proj_smooth_px: int = 9,
    edge_snap_on: bool = True,
    edge_snap_ratio: float = 0.06,
    edge_snap_max_px: int = 24,
    post_trim_pad_pct: float = 0.0,
) -> Tuple[float, float, float, float]:
    """Multi-stage content-aware auto-crop. Returns normalized (x1,y1,x2,y2)."""
    if not frames:
        return (0.0, 0.0, 1.0, 1.0)

    ref = frames[len(frames) // 2]
    target_w = 360 if ref.width > 360 else ref.width
    gr = [_resize_np(_to_gray_np(f), target_w) for f in frames]
    stack = np.stack(gr, axis=0).astype(np.float32)
    dyn = stack.max(axis=0) - stack.min(axis=0)

    if cv2 is not None:
        dyn = cv2.GaussianBlur(dyn, (5, 5), 0)
    else:
        dyn = np.array(
            Image.fromarray(dyn.astype(np.uint8)).filter(
                ImageFilter.GaussianBlur(radius=1.0)
            )
        ).astype(np.float32)

    pthr = np.percentile(dyn, float(np.clip(dyn_percentile, 1.0, 99.0)))
    thr = max(float(dyn_abs_floor), float(pthr))
    mask = (dyn >= thr).astype(np.uint8)
    mask = _morph_close(mask, int(max(1, round(close_ksize))))

    ys, xs = np.where(mask > 0)
    if len(xs) < 20 or len(ys) < 20:
        return _letterbox_detect(ref)

    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0b, y0b, x1b, y1b = _trim_by_energy_projection(
        dyn,
        (x0, y0, x1, y1),
        keep=float(keep_energy_pct) / 100.0,
        smooth_px=int(max(1, proj_smooth_px)),
    )

    Wd, Hd = dyn.shape[1], dyn.shape[0]
    sx = ref.width / float(Wd)
    sy = ref.height / float(Hd)
    X1 = max(0, int(round(x0b * sx)))
    Y1 = max(0, int(round(y0b * sy)))
    X2 = min(ref.width - 1, int(round(x1b * sx)))
    Y2 = min(ref.height - 1, int(round(y1b * sy)))

    if X2 <= X1 + 3 or Y2 <= Y1 + 3:
        return _letterbox_detect(ref)

    if edge_snap_on:
        X1, Y1, X2, Y2 = _tighten_box_edges_fullres(
            ref,
            X1,
            Y1,
            X2,
            Y2,
            ratio=float(edge_snap_ratio),
            max_trim_px=int(max(0, edge_snap_max_px)),
        )

    if post_trim_pad_pct != 0.0:
        pad_x = int(round((X2 - X1) * (post_trim_pad_pct / 100.0)))
        pad_y = int(round((Y2 - Y1) * (post_trim_pad_pct / 100.0)))
        X1 = max(0, X1 - pad_x)
        Y1 = max(0, Y1 - pad_y)
        X2 = min(ref.width - 1, X2 + pad_x)
        Y2 = min(ref.height - 1, Y2 + pad_y)

    if X2 <= X1 + 3 or Y2 <= Y1 + 3:
        return _letterbox_detect(ref)

    return (X1 / ref.width, Y1 / ref.height, X2 / ref.width, Y2 / ref.height)


def auto_crop_video(video_path: str, num_samples: int = 8) -> Tuple[float, float, float, float]:
    """Find the moving video rectangle inside a static template.

    Most scraped IG reels have a static template (branding, text, profile
    pic) with an embedded video clip that is the only thing moving.
    This function builds a frame-difference map and returns the tight
    bounding box of all pixels that changed — i.e. the actual video.

    Returns normalized (x1, y1, x2, y2).
    """
    frames = extract_frames(video_path, num_frames=num_samples)
    if not frames:
        return (0.0, 0.0, 1.0, 1.0)

    ref = frames[len(frames) // 2]
    target_w = 360 if ref.width > 360 else ref.width
    gr = [_resize_np(_to_gray_np(f), target_w) for f in frames]
    stack = np.stack(gr, axis=0).astype(np.float32)
    # Max pixel change across all frames
    dyn = stack.max(axis=0) - stack.min(axis=0)

    if cv2 is not None:
        dyn = cv2.GaussianBlur(dyn, (5, 5), 0)
    else:
        dyn = np.array(
            Image.fromarray(dyn.astype(np.uint8)).filter(
                ImageFilter.GaussianBlur(radius=1.0)
            )
        ).astype(np.float32)

    Hd, Wd = dyn.shape

    # Threshold: any pixel that changed by more than 10 levels is "moving"
    mask = (dyn > 10).astype(np.uint8)

    # Morphological close to fill small gaps inside the video rectangle
    ksize = max(3, Hd // 80)
    mask = _morph_close(mask, ksize)

    ys, xs = np.where(mask > 0)
    if len(ys) < 50:
        # No significant motion — fall back to letterbox detection
        return _letterbox_detect(ref)

    # Bounding box of all moving pixels = the video rectangle
    y1 = int(ys.min())
    y2 = int(ys.max()) + 1
    x1 = int(xs.min())
    x2 = int(xs.max()) + 1

    # Normalize
    nx1 = x1 / float(Wd)
    ny1 = y1 / float(Hd)
    nx2 = x2 / float(Wd)
    ny2 = y2 / float(Hd)

    # Safety: if the box is basically the whole frame, no useful crop
    if (nx2 - nx1) > 0.95 and (ny2 - ny1) > 0.95:
        return (0.0, 0.0, 1.0, 1.0)

    return (nx1, ny1, nx2, ny2)
