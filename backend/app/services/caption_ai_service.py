"""AI caption generation — two-step: analyze once, generate per-profile.

Step 1: analyze_video() — expensive vision call, cached on Video.ai_description
Step 2: generate_captions() — cheap text-only call, profile-specific

This means the same video used by 10 profiles = 1 vision call + 10 text calls
instead of 10 vision calls.
"""

from __future__ import annotations

import base64
import logging
import subprocess
import tempfile
from pathlib import Path

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

try:
    import imageio_ffmpeg

    FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_BIN = "ffmpeg"


def extract_frames(video_path: str, count: int = 4) -> list[bytes]:
    """Extract evenly-spaced frames from a video as JPEG bytes."""
    # Get video duration
    try:
        result = subprocess.run(
            [FFMPEG_BIN, "-i", video_path],
            capture_output=True, text=True, timeout=10,
        )
        duration = 0.0
        for line in result.stderr.splitlines():
            if "Duration:" in line:
                parts = line.split("Duration:")[1].split(",")[0].strip()
                h, m, s = parts.split(":")
                duration = int(h) * 3600 + int(m) * 60 + float(s)
                break
    except Exception:
        duration = 10.0

    if duration <= 0:
        duration = 10.0

    start = duration * 0.05
    end = duration * 0.95
    step = (end - start) / max(1, count - 1) if count > 1 else 0
    timestamps = [start + i * step for i in range(count)]

    frames: list[bytes] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, ts in enumerate(timestamps):
            out_path = Path(tmpdir) / f"frame_{i}.jpg"
            try:
                subprocess.run(
                    [
                        FFMPEG_BIN,
                        "-ss", str(ts),
                        "-i", video_path,
                        "-vframes", "1",
                        "-q:v", "3",
                        "-y", str(out_path),
                    ],
                    capture_output=True,
                    check=True,
                    timeout=15,
                )
                if out_path.exists() and out_path.stat().st_size > 0:
                    frames.append(out_path.read_bytes())
            except Exception as e:
                logger.warning("Failed to extract frame at %.1fs: %s", ts, e)

    return frames


def analyze_video(frames: list[bytes]) -> str:
    """Step 1: Vision call — analyze frames and return a detailed description.

    This is the expensive call (~$0.01-0.02 with images). The result should be
    cached on Video.ai_description so it never needs to run twice for the same video.

    Returns a detailed text description of the video content.
    """
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    content: list[dict] = []
    for frame_bytes in frames:
        b64 = base64.standard_b64encode(frame_bytes).decode("utf-8")
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": b64,
            },
        })

    content.append({
        "type": "text",
        "text": (
            "Analyze these video frames in detail. Describe:\n"
            "1. What is happening in the video (the main subject, action, process)\n"
            "2. Key visual elements (objects, people, environments, text on screen)\n"
            "3. The topic/educational content being shown\n"
            "4. The mood/tone of the content\n"
            "5. Any text or graphics visible in the frames\n\n"
            "Be thorough and specific — this description will be used to generate "
            "captions without seeing the video again."
        ),
    })

    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=1024,
        messages=[{"role": "user", "content": content}],
    )

    return response.content[0].text.strip()


def generate_captions(
    ai_description: str,
    niche: str,
    source_account: str,
    profile_name: str,
) -> dict[str, str]:
    """Step 2: Text-only call — generate profile-specific captions from cached description.

    This is cheap (~$0.001, no images). Can be called many times for different
    profiles or to regenerate/rewrite captions.

    Returns {"overlay": "...", "caption": "..."}.
    """
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": (
                f"You are writing captions for the Instagram reel account @{profile_name} "
                f'in the "{niche}" niche. You have a detailed AI analysis of the video '
                f"(originally by @{source_account}):\n\n"
                f"---\n{ai_description}\n---\n\n"
                "Write two things:\n\n"
                "1. **OVERLAY**: A short 1-2 sentence hook burned onto the video. "
                "Casual, sounds like a real person talking. NOT marketing copy.\n"
                "   Good: 'Most people do this wrong and don't realize it.'\n"
                "   Good: 'I wish someone showed me this years ago.'\n"
                "   Bad: 'Master the art of the perfect knot.'\n\n"
                "2. **CAPTION**: An Instagram post caption.\n"
                "   - 1-3 sentences. Keep it casual and relatable, like you're posting "
                "about something cool you found.\n"
                "   - You CAN reference specific things from the video analysis above, "
                "but keep it conversational — not like a tutorial or textbook.\n"
                "   - No emojis. No exclamation marks.\n"
                "   - Don't start with 'The secret to' or 'The key to'.\n"
                "   - Then a BLANK LINE, then this EXACT disclaimer:\n"
                "     This video is for education purposes only. DM for credit/removal.\n"
                "   - Then another BLANK LINE, then EXACTLY 3 hashtags: "
                "#Tutoring plus 2 relevant single-word hashtags.\n\n"
                "   GOOD example:\n"
                '     "Tying a Windsor knot doesn\'t have to be complicated. This '
                "breaks it down clean and you can actually follow along.\n"
                "\n"
                "     This video is for education purposes only. DM for credit/removal.\n"
                "\n"
                '     #Tutoring #Fashion #Neckties"\n\n'
                '   ALSO GOOD (references a specific thing from the video):\n'
                '     "Most people pull too tight on the first loop — that\'s why it '
                "always comes out lopsided. Once you see the fix it's obvious.\n"
                "\n"
                "     This video is for education purposes only. DM for credit/removal.\n"
                "\n"
                '     #Tutoring #Fashion #Neckties"\n\n'
                "Respond in EXACTLY this format (no other text):\n"
                "OVERLAY: <your overlay text>\n"
                "CAPTION: <your caption text>"
            ),
        }],
    )

    text = response.content[0].text.strip()
    overlay = ""
    caption = ""

    current_section = None
    for line in text.split("\n"):
        if line.startswith("OVERLAY:"):
            current_section = "overlay"
            overlay = line[len("OVERLAY:"):].strip()
        elif line.startswith("CAPTION:"):
            current_section = "caption"
            caption = line[len("CAPTION:"):].strip()
        elif current_section == "caption":
            caption += "\n" + line

    if not overlay and not caption:
        overlay = text[:200]

    return {
        "overlay": overlay.strip(),
        "caption": caption.strip(),
    }


def generate_caption_from_description(description: str) -> str:
    """Generate a formatted post caption from a user-provided description.

    No video analysis needed — just formats the description into the standard
    caption format with disclaimer and hashtags.
    """
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": (
                "Write an Instagram reel caption based on this short description of a video. "
                "You have NOT watched the video — you only know what's described below. "
                "Do NOT make up specific techniques, steps, or details that aren't in the "
                "description. Keep it honest and general.\n\n"
                f'Video description: "{description}"\n\n'
                "Rules:\n"
                "- 1-3 sentences. Casual, conversational, like a real person posting.\n"
                "- Reference the TOPIC of the video in a relatable way. Don't pretend to "
                "teach specific steps you can't see.\n"
                "- Good vibes: 'this doesn't have to be complicated', 'once you see it you "
                "won't forget', 'saved this one for later', etc.\n"
                "- No emojis. No exclamation marks.\n"
                "- Do NOT fabricate specific how-to details, tips, or techniques.\n"
                "- Then a BLANK LINE, then this EXACT disclaimer:\n"
                "  This video is for education purposes only. DM for credit/removal.\n"
                "- Then another BLANK LINE, then EXACTLY 3 hashtags: #Tutoring plus 2 relevant ones.\n\n"
                "GOOD examples (honest, general, relatable):\n"
                '"Tying a tie doesn\'t have to be complicated. This breaks it down in like 30 seconds.\n'
                "\n"
                "This video is for education purposes only. DM for credit/removal.\n"
                "\n"
                '#Tutoring #Fashion #Neckties"\n\n'
                '"Parallel parking used to stress me out every single time. Turns out there\'s a method to it.\n'
                "\n"
                "This video is for education purposes only. DM for credit/removal.\n"
                "\n"
                '#Tutoring #Driving #Parking"\n\n'
                "BAD examples (fabricates details the writer can't know):\n"
                '"The dimple in the center of your knot comes from pinching the fabric right '
                'before you slide the knot up." (Making up specific technique)\n'
                '"The trick is to turn the wheel all the way right before backing in." '
                "(Inventing steps not in the description)\n\n"
                "Return ONLY the caption text, nothing else."
            ),
        }],
    )

    return response.content[0].text.strip()
