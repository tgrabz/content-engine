"""Programmatic template generator — Instagram reel-style branding headers.

Generates 1080x1920 PNG templates with:
- Circular profile picture
- Display name + optional verified badge
- @handle in gray
- Header block centered horizontally
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont

DESIGN_W = 1080
DESIGN_H = 1920

# ── Sizing constants ──
# Layout optimized for visibility in BOTH reels (9:16) AND posts grid (4:5 center-crop).
# Instagram 4:5 crop of 1080x1920: visible y=285..1635 (cuts 285px top + bottom).
# Header starts at y=290 so pfp/name/caption are visible in posts view too.
PFP_DIAMETER = 195       # 18% of 1080 — circular profile pic
PFP_TEXT_GAP = 26        # gap between PFP right edge and text
HEADER_TOP = 290         # just inside the 4:5 crop line (285px)

NAME_FONT_SIZE = 58      # bold — "TeachYouZone" spans ~37% of width
HANDLE_FONT_SIZE = 42    # regular — "@teachyouzone" spans ~28% of width

HANDLE_COLOR = (142, 142, 142)  # #8e8e8e — Instagram gray
NAME_COLOR = (0, 0, 0)

VERIFIED_BADGE_SIZE = 40  # 3.7% of 1080
VERIFIED_GAP = 10         # gap between name text and badge

NAME_HANDLE_GAP = 4       # tight vertical gap matching reference

# ── Standard geometry for generated templates ──
# Header bottom ~y=485. Caption fills gap between header and video (centered text).
# Video starts at 0.345 (y=662) giving ~175px for caption with balanced whitespace.
GENERATED_VIDEO_BOX = "[0.04, 0.345, 0.96, 0.95]"
GENERATED_CAPTION_BOX = "[0.04, 0.255, 0.96, 0.341]"


def _font_path(bold: bool = False) -> str | None:
    """Find a system font."""
    if bold:
        candidates = [
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFNSText-Bold.otf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    else:
        candidates = [
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFNSText.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    for p in candidates:
        if Path(p).exists():
            return p
    return None


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    fp = _font_path(bold)
    try:
        if fp and fp.endswith(".ttc"):
            # .ttc files: index 0 = regular, index 1 = bold (Helvetica.ttc)
            return ImageFont.truetype(fp, size, index=1 if bold else 0)
        elif fp:
            return ImageFont.truetype(fp, size)
    except Exception:
        pass
    return ImageFont.load_default()


def _make_circular(img: Image.Image, diameter: int) -> Image.Image:
    """Crop image to square and apply circular mask."""
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    square = img.crop((left, top, left + side, top + side))
    square = square.resize((diameter, diameter), Image.LANCZOS).convert("RGBA")

    mask = Image.new("L", (diameter, diameter), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, diameter - 1, diameter - 1), fill=255)

    result = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    result.paste(square, (0, 0), mask)
    return result


def _draw_verified_badge(
    draw: ImageDraw.ImageDraw, x: int, y: int, size: int
) -> None:
    """Draw an Instagram-style blue verified badge."""
    draw.ellipse(
        (x, y, x + size, y + size),
        fill=(0, 149, 246),  # Instagram blue #0095f6
    )
    cx, cy = x + size / 2, y + size / 2
    r = size * 0.32
    points = [
        (cx - r * 0.6, cy + r * 0.05),
        (cx - r * 0.1, cy + r * 0.55),
        (cx + r * 0.75, cy - r * 0.5),
    ]
    draw.line(points, fill=(255, 255, 255), width=max(2, int(size * 0.14)))


def generate_template_image(
    display_name: str,
    handle: str,
    pfp_image: Image.Image,
    verified: bool = True,
) -> Image.Image:
    """Generate a 1080x1920 Instagram reel-style template.

    Header block (PFP + name/handle) centered horizontally,
    with sizes pixel-matched to the Instagram reel reference.
    """
    canvas = Image.new("RGBA", (DESIGN_W, DESIGN_H), (255, 255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    # Load fonts
    name_font = _load_font(NAME_FONT_SIZE, bold=True)
    handle_font = _load_font(HANDLE_FONT_SIZE, bold=False)
    handle_text = handle if handle.startswith("@") else f"@{handle}"

    # Measure text widths to center the whole block
    name_bbox = draw.textbbox((0, 0), display_name, font=name_font)
    name_w = name_bbox[2] - name_bbox[0]
    name_h = name_bbox[3] - name_bbox[1]

    handle_bbox = draw.textbbox((0, 0), handle_text, font=handle_font)
    handle_w = handle_bbox[2] - handle_bbox[0]

    # Total text width includes verified badge
    badge_extra = (VERIFIED_GAP + VERIFIED_BADGE_SIZE) if verified else 0
    text_w = max(name_w + badge_extra, handle_w)

    # Total header block width: PFP + gap + text — then center it
    block_w = PFP_DIAMETER + PFP_TEXT_GAP + text_w
    block_x = (DESIGN_W - block_w) // 2

    pfp_x = block_x
    pfp_y = HEADER_TOP

    # Text position (right of PFP)
    text_x = block_x + PFP_DIAMETER + PFP_TEXT_GAP

    # Vertically center text block against PFP
    text_block_h = name_h + NAME_HANDLE_GAP + HANDLE_FONT_SIZE
    text_y_start = pfp_y + (PFP_DIAMETER - text_block_h) // 2

    name_y = text_y_start
    handle_y = name_y + name_h + NAME_HANDLE_GAP

    # 1. Profile picture (circular)
    pfp = _make_circular(pfp_image, PFP_DIAMETER)
    canvas.paste(pfp, (pfp_x, pfp_y), pfp)

    # 2. Display name (bold)
    draw.text((text_x, name_y), display_name, fill=NAME_COLOR + (255,), font=name_font)

    # 3. Verified badge
    if verified:
        badge_x = text_x + name_w + VERIFIED_GAP
        badge_y = name_y + (name_h - VERIFIED_BADGE_SIZE) // 2
        _draw_verified_badge(draw, badge_x, badge_y, VERIFIED_BADGE_SIZE)

    # 4. Handle (@username)
    draw.text((text_x, handle_y), handle_text, fill=HANDLE_COLOR + (255,), font=handle_font)

    return canvas
