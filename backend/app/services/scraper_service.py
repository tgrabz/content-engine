"""Instagram Reel Scraper Service

Ported from sm-tester-polished/src/scrapers/ig_selenium_scraper.py.
Writes directly to SQLite (videos table) instead of ledger/Google Sheets.
Pushes log messages to a thread-safe queue for WebSocket streaming.
"""

from __future__ import annotations

import base64
import hashlib
import json
import queue as _queue
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from cryptography.fernet import Fernet
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from yt_dlp import YoutubeDL

try:
    import undetected_chromedriver as uc
except ImportError:
    uc = None

try:
    import imageio_ffmpeg

    FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_BIN = None

from app.config import settings
from app.database import SessionLocal
from app.models.credential import IGLoginCredential
from app.models.niche import Niche, NicheAccount
from app.models.scrape import ScrapeJob
from app.models.video import Video

# ──────────────────── Log queue management ────────────────────

_log_queues: dict[int, _queue.Queue] = {}

SENTINEL = None  # signals end of log stream


def get_log_queue(job_id: int) -> _queue.Queue:
    if job_id not in _log_queues:
        _log_queues[job_id] = _queue.Queue()
    return _log_queues[job_id]


def cleanup_queue(job_id: int):
    _log_queues.pop(job_id, None)


# ──────────────────── Constants ────────────────────

VALID_VIDEO_EXTS = {".mp4", ".mov", ".webm", ".m4v"}

# Rotating pool of recent Chrome user agents (macOS + Windows)
_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
]

# Randomized viewport sizes (common desktop resolutions)
_VIEWPORTS = [
    (1280, 800), (1366, 768), (1440, 900), (1536, 864),
    (1600, 900), (1680, 1050), (1920, 1080), (1280, 1024),
]

_NUM_SUFFIX = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}

# Per-session state: chosen UA stays consistent for browser + yt-dlp
_session_ua: str = ""


def _pick_session_ua() -> str:
    """Pick a random UA for this scrape session (consistent across browser + downloads)."""
    global _session_ua
    _session_ua = random.choice(_USER_AGENTS)
    return _session_ua


# ──────────────────── Helpers ────────────────────


def _rand_pause(scroll_pause: Union[float, Tuple[float, float]]) -> float:
    """Human-like pause using gaussian distribution (clustered around center)."""
    if isinstance(scroll_pause, (tuple, list)) and len(scroll_pause) == 2:
        lo, hi = float(scroll_pause[0]), float(scroll_pause[1])
        if hi < lo:
            lo, hi = hi, lo
        # Gaussian centered at midpoint, clipped to range
        mu = (lo + hi) / 2.0
        sigma = (hi - lo) / 4.0  # 95% falls within range
        val = random.gauss(mu, sigma)
        return max(lo, min(hi, val))
    return float(scroll_pause)


def _human_delay(lo: float = 0.3, hi: float = 1.5) -> None:
    """Short human-like delay for interactions (clicks, typing gaps)."""
    time.sleep(random.uniform(lo, hi))


_STEALTH_JS = """
// Hide webdriver flag
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// Realistic plugins array
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
        {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
        {name: 'Native Client', filename: 'internal-nacl-plugin'},
    ],
});

// Realistic languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en'],
});

// Chrome runtime
window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}};

// Permissions API
const origQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({state: Notification.permission})
        : origQuery(parameters);
"""


def _build_driver(headless: bool):
    """Build a stealth Chrome driver using undetected-chromedriver."""
    ua = _pick_session_ua()
    vw, vh = random.choice(_VIEWPORTS)

    if uc is not None:
        # undetected-chromedriver: auto-patches ChromeDriver to avoid detection
        options = uc.ChromeOptions()
        options.add_argument(f"--window-size={vw},{vh}")
        options.add_argument("--lang=en-US,en")
        options.add_argument("--disable-blink-features=AutomationControlled")
        driver = uc.Chrome(options=options, headless=headless)
    else:
        # Fallback to regular selenium with manual stealth
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        opts = Options()
        if headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument(f"--window-size={vw},{vh}")
        opts.add_argument("--lang=en-US,en")
        opts.add_argument(f"--user-agent={ua}")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        driver = webdriver.Chrome(options=opts)

    # Inject stealth JS on every page load
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": _STEALTH_JS})
    return driver


def _js_click(driver, el):
    driver.execute_script("arguments[0].click();", el)


def _click_any_button_text(driver, keywords: List[str], timeout_s: float = 0.5) -> bool:
    kw = [k.lower() for k in keywords]
    try:
        candidates = driver.find_elements(By.XPATH, "//button|//div[@role='button']")
        for el in candidates:
            txt = (el.text or "").strip().lower()
            if any(k in txt for k in kw):
                try:
                    _js_click(driver, el)
                except Exception:
                    try:
                        el.click()
                    except Exception:
                        continue
                _human_delay(0.3, 0.8)
                return True
    except Exception:
        pass
    _human_delay(timeout_s, timeout_s + 0.5)
    return False


def _maybe_accept_cookies(driver, log, debug: bool):
    if _click_any_button_text(
        driver,
        ["allow essential cookies", "accept all", "allow all", "accept"],
    ):
        log("Dismissed cookie banner")


def _dismiss_post_login_prompts(driver, log, debug: bool):
    if _click_any_button_text(driver, ["not now"]):
        log("Dismissed 'Save your login info'")
    if _click_any_button_text(driver, ["not now"]):
        log("Dismissed 'Turn on notifications'")


def _login(
    driver,
    username: str,
    password: str,
    log,
    debug: bool,
    *,
    headless: bool,
    quick_timeout: int = 45,
    manual_timeout: int = 300,
):
    driver.get("https://www.instagram.com/accounts/login/")
    log("Waiting for login page to load...")
    _human_delay(3.0, 5.0)
    wait = WebDriverWait(driver, quick_timeout)
    _maybe_accept_cookies(driver, log, debug)
    _human_delay(1.0, 2.0)

    log("Looking for login form fields...")
    # Instagram's login form uses various attributes — try multiple selectors
    _user_selectors = [
        (By.NAME, "username"),
        (By.CSS_SELECTOR, "input[autocomplete='username']"),
        (By.CSS_SELECTOR, "input[aria-label*='username' i]"),
        (By.CSS_SELECTOR, "input[aria-label*='phone' i]"),
        (By.CSS_SELECTOR, "input[aria-label*='email' i]"),
        (By.CSS_SELECTOR, "form input[type='text']"),
    ]
    _pass_selectors = [
        (By.NAME, "password"),
        (By.CSS_SELECTOR, "input[autocomplete='current-password']"),
        (By.CSS_SELECTOR, "input[aria-label*='password' i]"),
        (By.CSS_SELECTOR, "input[type='password']"),
    ]

    user_el = None
    for by, sel in _user_selectors:
        try:
            user_el = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((by, sel))
            )
            if user_el:
                log(f"Found username field via: {sel}")
                break
        except Exception:
            continue

    if not user_el:
        # Last resort: dump all inputs for debugging
        try:
            inputs = driver.find_elements(By.TAG_NAME, "input")
            for inp in inputs:
                attrs = driver.execute_script(
                    "var el=arguments[0]; return {"
                    "type: el.type, name: el.name, "
                    "aria: el.getAttribute('aria-label'), "
                    "auto: el.getAttribute('autocomplete'), "
                    "placeholder: el.placeholder};", inp
                )
                log(f"  input found: {attrs}")
        except Exception:
            pass
        log(f"Current URL: {driver.current_url}")
        raise RuntimeError("Could not find username field on login page")

    pass_el = None
    for by, sel in _pass_selectors:
        try:
            pass_el = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((by, sel))
            )
            if pass_el:
                log(f"Found password field via: {sel}")
                break
        except Exception:
            continue

    if not pass_el:
        log(f"Current URL: {driver.current_url}")
        raise RuntimeError("Could not find password field on login page")

    log("Found login fields, entering credentials...")
    user_el.clear()
    _human_delay(0.2, 0.6)
    # Type characters one-by-one with random delays to mimic a real person
    for ch in username:
        user_el.send_keys(ch)
        time.sleep(random.uniform(0.04, 0.18))
    _human_delay(0.3, 0.8)
    pass_el.clear()
    for ch in password:
        pass_el.send_keys(ch)
        time.sleep(random.uniform(0.04, 0.18))
    _human_delay(0.2, 0.5)
    pass_el.submit()
    log("Credentials submitted, waiting for login to complete...")

    start = time.time()
    logged_in = False
    already_notified = False

    while True:
        cur = driver.current_url

        if ("challenge" in cur) or ("two_factor" in cur):
            if headless:
                raise RuntimeError(
                    "Login requires challenge/2FA — run with headless OFF to complete manually."
                )
            if not already_notified:
                log("Challenge/2FA detected — please complete it in the browser window.")
                log(f"Waiting up to {manual_timeout // 60} minutes...")
                already_notified = True
            if time.time() - start > manual_timeout:
                raise RuntimeError("Manual challenge window expired.")
            try:
                if driver.find_elements(By.TAG_NAME, "nav"):
                    logged_in = True
                    break
            except Exception:
                pass
            time.sleep(1.0)
            continue

        try:
            if driver.find_elements(By.TAG_NAME, "nav"):
                logged_in = True
                break
        except Exception:
            pass

        if time.time() - start > quick_timeout:
            if headless:
                raise RuntimeError("Login did not reach home within timeout.")
            if not already_notified:
                log(f"Still logging in... extending wait to {manual_timeout // 60} min.")
                already_notified = True
            if time.time() - start > manual_timeout:
                raise RuntimeError("Login window expired.")
        time.sleep(0.5)

    if not logged_in:
        raise RuntimeError("Login failed unexpectedly.")
    log("Logged in successfully")
    _dismiss_post_login_prompts(driver, log, debug)


def _extract_reel_links_js(driver) -> List[str]:
    try:
        links = driver.execute_script(
            """
            return Array.from(document.querySelectorAll('a[href*="/reel/"]'))
                        .map(a => a.href.split('#')[0].split('?')[0]);
        """
        )
        seen = set()
        out = []
        for u in links:
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out
    except Exception:
        return []


def _human_scroll(driver) -> None:
    """Scroll down with randomized behavior — variable distance, occasional scroll-up."""
    # 80% chance: full scroll to bottom.  20% chance: partial scroll.
    if random.random() < 0.8:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    else:
        # Scroll a random portion (50-90% of viewport)
        frac = random.uniform(0.5, 0.9)
        driver.execute_script(f"window.scrollBy(0, window.innerHeight * {frac});")

    # 10% chance: briefly scroll up a bit (mimics human scanning)
    if random.random() < 0.1:
        time.sleep(random.uniform(0.3, 0.7))
        up = random.randint(100, 300)
        driver.execute_script(f"window.scrollBy(0, -{up});")


def _collect_reel_links(
    driver,
    account: str,
    max_scrolls: int,
    pause: Union[float, Tuple[float, float]],
    log,
) -> List[str]:
    driver.get(f"https://www.instagram.com/{account}/reels/")
    _human_delay(1.0, 2.5)
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.TAG_NAME, "main"))
    )

    all_links: List[str] = []
    last_count = 0
    stale_scrolls = 0
    for i in range(max_scrolls):
        batch = _extract_reel_links_js(driver)
        for u in batch:
            if u not in all_links:
                all_links.append(u)
        log(f"Scroll {i + 1}/{max_scrolls}: found {len(all_links)} reel links")
        if len(all_links) == last_count:
            stale_scrolls += 1
            if stale_scrolls >= 3:
                log("No new links after 3 scrolls; stopping early.")
                break
        else:
            stale_scrolls = 0
        last_count = len(all_links)
        _human_scroll(driver)
        time.sleep(_rand_pause(pause))
        # Periodic longer pause during scrolling to avoid rate limits
        if (i + 1) % 20 == 0 and i < max_scrolls - 1:
            extra = random.uniform(3.0, 6.0)
            log(f"Scroll pause ({len(all_links)} links collected)...")
            time.sleep(extra)
    return all_links


def _fallback_grid_links(
    driver,
    account: str,
    max_scrolls: int,
    pause: Union[float, Tuple[float, float]],
    log,
) -> List[str]:
    log("Fallback: scanning profile grid for reel links")
    driver.get(f"https://www.instagram.com/{account}/")
    _human_delay(1.0, 2.5)
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.TAG_NAME, "main"))
    )

    all_links: List[str] = []
    last_count = 0
    for i in range(max_scrolls):
        batch = _extract_reel_links_js(driver)
        for u in batch:
            if u not in all_links:
                all_links.append(u)
        log(f"Grid scroll {i + 1}/{max_scrolls}: {len(all_links)} reel links")
        if len(all_links) == last_count and i >= 2:
            break
        last_count = len(all_links)
        _human_scroll(driver)
        time.sleep(_rand_pause(pause))
    return all_links


def _write_netscape_cookiefile(cookies: List[Dict], dest: Path) -> Path:
    lines = ["# Netscape HTTP Cookie File", "# Generated from Selenium session", ""]
    now = int(time.time())
    for c in cookies:
        dom = c.get("domain", "")
        if "instagram.com" not in dom:
            continue
        include_sub = "TRUE" if dom.startswith(".") else "FALSE"
        path = c.get("path", "/") or "/"
        secure = "TRUE" if c.get("secure") else "FALSE"
        expiry = int(c.get("expiry", now + 180 * 24 * 3600))
        name = c.get("name", "")
        value = c.get("value", "")
        lines.append(
            f"{dom}\t{include_sub}\t{path}\t{secure}\t{expiry}\t{name}\t{value}"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines), encoding="utf-8")
    return dest


def _strip_metadata(video_path: Path) -> None:
    """Strip metadata and lightly re-encode to make the video untraceable.

    1. Strips all container/stream metadata, chapter markers, identifiers
    2. Re-encodes with slightly randomized parameters so the binary output
       differs from the Instagram original (defeats hash-based matching)
    3. Randomizes CRF ±1 and adds a unique encoding seed
    """
    import subprocess

    ffmpeg = FFMPEG_BIN or "ffmpeg"
    tmp = video_path.with_suffix(".tmp.mp4")

    # Randomize encoding parameters so each download is unique
    crf = random.randint(22, 24)          # slight quality jitter
    preset = random.choice(["fast", "medium"])

    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(video_path),
        "-map", "0",
        "-map_metadata", "-1",            # strip global metadata
        "-map_metadata:s:v", "-1",        # strip video stream metadata
        "-map_metadata:s:a", "-1",        # strip audio stream metadata
        "-map_chapters", "-1",            # strip chapter markers
        # Light re-encode video (makes binary content unique)
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", preset,
        # Re-encode audio too
        "-c:a", "aac",
        "-b:a", f"{random.choice([126, 128, 130, 132])}k",
        "-movflags", "+faststart",
        str(tmp),
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=120)
        tmp.replace(video_path)       # atomic swap
    except Exception:
        if tmp.exists():
            tmp.unlink()


def _compute_video_hash(video_path: Path) -> Optional[str]:
    """Compute perceptual hash of a video by sampling a frame.

    Returns a hex string (16 chars) that can be compared across videos.
    Two videos with hamming distance <= 10 are considered the same content.
    """
    import subprocess as _sp
    import tempfile as _tf

    try:
        import imagehash
        from PIL import Image
    except ImportError:
        return None

    ffmpeg = FFMPEG_BIN or "ffmpeg"

    # Extract a frame from ~25% into the video (avoids intros/black frames)
    with _tf.TemporaryDirectory() as tmpdir:
        frame_path = Path(tmpdir) / "hash_frame.jpg"
        try:
            # Probe duration
            probe = _sp.run(
                [ffmpeg, "-i", str(video_path)],
                capture_output=True, text=True, timeout=10,
            )
            duration = 5.0
            for line in probe.stderr.splitlines():
                if "Duration:" in line:
                    parts = line.split("Duration:")[1].split(",")[0].strip()
                    h, m, s = parts.split(":")
                    duration = int(h) * 3600 + int(m) * 60 + float(s)
                    break

            seek_to = duration * 0.25

            _sp.run(
                [ffmpeg, "-ss", str(seek_to), "-i", str(video_path),
                 "-vframes", "1", "-q:v", "2", "-y", str(frame_path)],
                capture_output=True, check=True, timeout=15,
            )
        except Exception:
            return None

        if not frame_path.exists():
            return None

        img = Image.open(str(frame_path))
        h = imagehash.phash(img, hash_size=16)
        return str(h)


def _is_duplicate_hash(db, video_hash: str, threshold: int = 10) -> Optional[Video]:
    """Check if a video with a similar perceptual hash already exists.

    Returns the matching Video if found, None otherwise.
    Hamming distance <= threshold means same content.
    """
    if not video_hash:
        return None

    try:
        import imagehash
    except ImportError:
        return None

    new_hash = imagehash.hex_to_hash(video_hash)

    # Query all videos that have a hash (indexed column, fast lookup)
    existing = db.query(Video).filter(Video.video_hash.isnot(None)).all()
    for v in existing:
        try:
            existing_hash = imagehash.hex_to_hash(v.video_hash)
            distance = new_hash - existing_hash
            if distance <= threshold:
                return v
        except Exception:
            continue

    return None


def _download_with_ytdlp(
    video_url: str,
    out_dir: Path,
    overwrite: bool,
    *,
    cookiefile: Optional[Path] = None,
    ig_www_claim: Optional[str] = None,
) -> Tuple[Path, int, Dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(out_dir / "%(id)s.%(ext)s")
    # Use the session UA (matches browser) or fall back to a random one
    dl_ua = _session_ua or random.choice(_USER_AGENTS)
    ydl_opts: Dict = {
        "quiet": True,
        "noprogress": True,
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "format": "mp4/bestvideo+bestaudio/best",
        "overwrites": overwrite,
        "http_headers": {
            "User-Agent": dl_ua,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-Dest": "document",
        },
        "socket_timeout": 30,
        "retries": 3,
    }
    if ig_www_claim:
        ydl_opts["http_headers"]["X-IG-WWW-Claim"] = ig_www_claim
    if cookiefile and cookiefile.exists():
        ydl_opts["cookiefile"] = str(cookiefile)
    if FFMPEG_BIN:
        ydl_opts["ffmpeg_location"] = FFMPEG_BIN

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        if "requested_downloads" in info and info["requested_downloads"]:
            f = Path(info["requested_downloads"][0]["filepath"])
            size = f.stat().st_size if f.exists() else 0
            _strip_metadata(f)
            size = f.stat().st_size if f.exists() else size
            return f, size, info
        file_guess = outtmpl.replace("%(id)s", info.get("id", "video")).replace(
            "%(ext)s", info.get("ext", "mp4")
        )
        f = Path(file_guess)
        size = f.stat().st_size if f.exists() else 0
        _strip_metadata(f)
        size = f.stat().st_size if f.exists() else size
        return f, size, info


def _parse_count_like_instagram(x) -> Optional[int]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        try:
            v = int(float(x))
            return v if v >= 0 else None
        except Exception:
            return None
    s = str(x).strip().lower()
    if not s:
        return None
    if re.fullmatch(r"[0-9][0-9,.\s]*", s):
        s2 = s.replace(",", "").replace(" ", "")
        try:
            return int(float(s2))
        except Exception:
            return None
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([kmb])", s)
    if m:
        val = float(m.group(1))
        mul = _NUM_SUFFIX.get(m.group(2), 1)
        return int(val * mul)
    return None


def _extract_views_from_info(
    info: Dict, *, fallback_to_likes: bool = False
) -> Tuple[Optional[int], Optional[str]]:
    for key in ("play_count", "view_count"):
        v = info.get(key)
        pv = _parse_count_like_instagram(v)
        if pv is not None:
            return pv, key
    if fallback_to_likes:
        v = info.get("like_count")
        pv = _parse_count_like_instagram(v)
        if pv is not None:
            return pv, "like_count"
    return None, None


def _shortcode_from_url(url: str) -> Optional[str]:
    m = re.search(r"/reel/([^/]+)/?", url)
    return m.group(1) if m else None


def _decrypt_password(cred: IGLoginCredential) -> str:
    key = hashlib.sha256(settings.secret_key.encode()).digest()
    f = Fernet(base64.urlsafe_b64encode(key))
    return f.decrypt(cred.password_enc.encode()).decode()


# ──────────────────── Main scrape job ────────────────────


def run_scrape_job(
    job_id: int,
    niche_id: int,
    credential_id: int,
    target_accounts: List[str],
    max_reels: int = 10,
    min_views: int = 10000,
    max_scrolls: int = 15,
    scroll_pause: Tuple[float, float] = (1.5, 3.0),
    headless: bool = True,
    early_stop_dupes: int = 5,
    unknown_views_pass: bool = True,
    fallback_to_likes: bool = False,
):
    """Run a full scrape job in a background thread.

    Pushes log messages to a queue for WebSocket streaming.
    Writes Video records directly to SQLite.
    """
    q = get_log_queue(job_id)

    def log(msg: str):
        q.put({"type": "log", "message": msg})

    def emit_result(data: dict):
        q.put({"type": "result", "data": data})

    db = SessionLocal()
    all_results = []

    try:
        # Update job status
        job = db.get(ScrapeJob, job_id)
        if not job:
            log("ERROR: Job not found in database")
            return
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        db.commit()

        # Get credential and decrypt password
        cred = db.get(IGLoginCredential, credential_id)
        if not cred:
            raise RuntimeError("Credential not found")
        ig_username = cred.username
        ig_password = _decrypt_password(cred)

        # Get niche info
        niche = db.get(Niche, niche_id)
        if not niche:
            raise RuntimeError("Niche not found")
        niche_name = niche.name

        # If no specific accounts, get all from niche
        if not target_accounts:
            accounts = (
                db.query(NicheAccount)
                .filter(
                    NicheAccount.niche_id == niche_id,
                    NicheAccount.platform == "instagram",
                )
                .all()
            )
            target_accounts = [a.username for a in accounts]

        if not target_accounts:
            raise RuntimeError("No target accounts to scrape")

        log(
            f"Starting scrape: niche={niche_name}, "
            f"accounts={target_accounts}, max_reels={max_reels}"
        )

        # Build driver and login
        log("Opening browser and logging in...")
        driver = _build_driver(headless=headless)
        cookiefile_path = settings.cookies_dir / "instagram_cookies.txt"
        ig_www_claim = None
        cookiefile_for_dl: Optional[Path] = None

        try:
            _login(
                driver,
                ig_username,
                ig_password,
                log,
                False,
                headless=headless,
            )

            # Export cookies for yt-dlp
            driver.get("https://www.instagram.com/")
            time.sleep(1.0)
            cookies = driver.get_cookies()
            for c in cookies:
                if c.get("name") == "www-claim-v2" and c.get("value"):
                    ig_www_claim = c["value"]
                    break
            cookiefile_for_dl = _write_netscape_cookiefile(cookies, cookiefile_path)
            log("Exported login cookies for downloads")

            # Scrape each target account
            for acct_idx, account in enumerate(target_accounts):
                # Pause between accounts to look like natural browsing
                if acct_idx > 0:
                    pause_sec = random.uniform(3.0, 8.0)
                    log(f"Pausing {pause_sec:.1f}s before next account...")
                    time.sleep(pause_sec)
                log(f"--- Scraping @{account} ---")
                out_dir = settings.downloads_dir / niche_name / account
                out_dir.mkdir(parents=True, exist_ok=True)

                # Collect reel links
                log(f"Visiting @{account} Reels...")
                links = _collect_reel_links(
                    driver, account, max_scrolls, scroll_pause, log
                )
                if not links:
                    links = _fallback_grid_links(
                        driver, account, max_scrolls, scroll_pause, log
                    )
                log(f"Total reel links collected: {len(links)}")

                if not links:
                    log(f"No reels found for @{account}, skipping")
                    continue

                # Process links
                scan_limit = max(max_reels * 10, 50)
                max_scan = min(len(links), scan_limit)
                log(f"Scanning up to {max_scan} links for up to {max_reels} reels")

                dup_streak = 0
                checked = 0
                account_results = 0
                min_scan_before_stop = max(10, min(100, max_reels * 3))

                for url in links[:max_scan]:
                    if account_results >= max_reels:
                        break
                    checked += 1

                    sc = _shortcode_from_url(url)
                    if not sc:
                        continue

                    # Check duplicate in videos table
                    existing = (
                        db.query(Video)
                        .filter(
                            Video.source_account == account,
                            Video.shortcode == sc,
                        )
                        .first()
                    )

                    if existing:
                        dup_streak += 1
                        log(
                            f"Duplicate: {sc} "
                            f"(streak {dup_streak}/{early_stop_dupes or 'inf'}, "
                            f"checked {checked})"
                        )
                        if (
                            early_stop_dupes
                            and dup_streak >= early_stop_dupes
                            and checked >= min_scan_before_stop
                        ):
                            log(
                                f"Early-stop: {dup_streak} consecutive dupes "
                                f"after {checked} links"
                            )
                            break
                        continue
                    else:
                        dup_streak = 0

                    # Throttle: progressive delays to avoid detection
                    if account_results > 0:
                        # Base delay increases as we download more
                        if account_results % 25 == 0:
                            # Every 25 downloads: take a longer "coffee break"
                            pause_secs = random.uniform(30, 60)
                            log(f"Throttle break ({account_results} downloaded) — pausing {pause_secs:.0f}s")
                            time.sleep(pause_secs)
                        elif account_results > 50:
                            delay = random.uniform(5.0, 12.0)
                            time.sleep(delay)
                        elif account_results > 20:
                            delay = random.uniform(3.0, 8.0)
                            time.sleep(delay)
                        else:
                            delay = random.uniform(2.0, 6.0)
                            time.sleep(delay)

                    # Download
                    try:
                        log(f"Downloading {url}...")
                        file_path, size_bytes, info = _download_with_ytdlp(
                            url,
                            out_dir,
                            overwrite=False,
                            cookiefile=cookiefile_for_dl,
                            ig_www_claim=ig_www_claim,
                        )
                    except Exception as e:
                        log(f"Download failed for {url}: {e}")
                        continue

                    # Compute perceptual hash for cross-account dedup
                    video_hash = _compute_video_hash(file_path)
                    if video_hash:
                        dup_video = _is_duplicate_hash(db, video_hash)
                        if dup_video:
                            log(
                                f"Content duplicate: {sc} matches "
                                f"video #{dup_video.id} from @{dup_video.source_account} "
                                f"(shortcode {dup_video.shortcode}) — skipping"
                            )
                            # Clean up downloaded file
                            try:
                                file_path.unlink()
                            except Exception:
                                pass
                            dup_streak += 1
                            continue
                        dup_streak = 0

                    # Extract metadata
                    views, views_key = _extract_views_from_info(
                        info, fallback_to_likes=fallback_to_likes
                    )

                    # Filter by min_views
                    if views is not None and views < min_views:
                        log(f"Skipping {sc}: views {views:,} < {min_views:,}")
                        continue
                    if views is None and not unknown_views_pass:
                        log(f"Skipping {sc}: unknown views (policy=fail)")
                        continue

                    caption = (
                        info.get("title") or info.get("description") or ""
                    )[:250]
                    duration = info.get("duration")
                    width = info.get("width")
                    height = info.get("height")

                    # Write Video record
                    video = Video(
                        platform="instagram",
                        niche_id=niche_id,
                        source_account=account,
                        shortcode=sc,
                        source_url=url,
                        local_path=str(file_path.resolve()),
                        file_bytes=size_bytes,
                        views=views,
                        caption=caption,
                        duration_sec=duration,
                        width=width,
                        height=height,
                        video_hash=video_hash,
                        status="downloaded",
                    )
                    db.add(video)
                    db.commit()
                    db.refresh(video)

                    result = {
                        "video_id": video.id,
                        "account": account,
                        "shortcode": sc,
                        "views": views,
                        "file_bytes": size_bytes,
                        "file": str(file_path.resolve()),
                    }
                    all_results.append(result)
                    emit_result(result)
                    account_results += 1
                    log(
                        f"Saved {sc} "
                        f"(views: {views if views is not None else 'unknown'}, "
                        f"{size_bytes:,} bytes)"
                    )

                log(f"@{account}: {account_results} new reels downloaded")

        finally:
            try:
                driver.quit()
            except Exception:
                pass

        # Update job as completed
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        job.results_json = json.dumps(all_results)
        db.commit()

        log(f"Scrape complete! {len(all_results)} total reels downloaded.")
        q.put({"type": "done", "total": len(all_results), "results": all_results})

    except Exception as e:
        log(f"ERROR: {e}")
        try:
            job = db.get(ScrapeJob, job_id)
            if job:
                job.status = "failed"
                job.error_message = str(e)
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            pass
        q.put({"type": "error", "message": str(e)})

    finally:
        db.close()
        q.put(SENTINEL)
