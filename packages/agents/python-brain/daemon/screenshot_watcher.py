"""
================================================================================
LEAGUE COACH OS — SCREENSHOT WATCHER DAEMON
================================================================================
Autonomous daemon that runs in your system tray.
Hit PrintScreen on a LoL loading screen → full coaching plan in <7 seconds.

Flow:
  [PrintScreen] → Clipboard Watch → LoL Detector → Champion Parse →
  Role Inference → Build Plan → Coaching Tips → Overlay Display

Zero clicks. Zero typing. Just PrintScreen and play.

Author: Barrios A2I | Version: 1.0.0
================================================================================
"""
import asyncio
import base64
import io
import json
import logging
import os
import sys
import time
import threading
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Image handling
try:
    from PIL import Image, ImageGrab, ImageDraw, ImageFont, ImageFilter
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Clipboard monitoring
try:
    import win32clipboard
    import win32con
    import win32gui
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

# System tray
try:
    import pystray
    from pystray import MenuItem as item
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

logger = logging.getLogger("league_coach.daemon")


# =============================================================================
# CONFIGURATION
# =============================================================================

class DaemonConfig:
    """Daemon configuration — all tunables in one place."""

    # Polling
    CLIPBOARD_POLL_INTERVAL: float = 0.3          # seconds between clipboard checks
    SCREENSHOT_COOLDOWN: float = 5.0               # ignore duplicate screenshots within N seconds

    # Detection thresholds
    LOL_DETECTION_CONFIDENCE: float = 0.70         # minimum to consider it a loading screen
    CHAMPION_ID_CONFIDENCE: float = 0.60           # minimum per-champion confidence
    FALLBACK_ASK_THRESHOLD: float = 0.50           # below this, ask user to type champ

    # Paths
    SCREENSHOT_DIR: str = os.path.expanduser("~/BarriosA2I/LEAGUE_COACH_OS/fixtures/screenshots")
    COACHING_OUTPUT_DIR: str = os.path.expanduser("~/BarriosA2I/LEAGUE_COACH_OS/fixtures/coaching_outputs")
    LOG_DIR: str = os.path.expanduser("~/BarriosA2I/LEAGUE_COACH_OS/logs")
    VAULT_DIR: str = os.path.expanduser("~/BarriosA2I/LEAGUE_COACH_OS/vault")

    # Display
    OVERLAY_DURATION: int = 30                     # seconds to show overlay
    OVERLAY_OPACITY: float = 0.92
    OVERLAY_WIDTH: int = 480
    OVERLAY_POSITION: str = "top-right"            # top-right, top-left, center

    # API
    ANTHROPIC_MODEL_VISION: str = "claude-sonnet-4-20250514"
    ANTHROPIC_MODEL_COACH: str = "claude-sonnet-4-20250514"
    ANTHROPIC_MODEL_FAST: str = "claude-haiku-4-5-20251001"

    # Sound
    PLAY_SOUND_ON_DETECT: bool = True
    SOUND_FILE: str = "coach_ready.wav"


# =============================================================================
# LOL LOADING SCREEN DETECTOR
# =============================================================================

class LoadingScreenDetector:
    """
    Fast heuristic detector for League of Legends loading screens.

    Loading screens have distinctive visual signatures:
    - 16:9 or 16:10 aspect ratio (fullscreen game)
    - Two rows of 5 champion splash arts
    - Dark background with specific UI elements
    - Champion name text overlays
    - Summoner spell icons in consistent positions
    - Loading progress bars

    Uses a combination of:
    1. Aspect ratio check
    2. Color histogram analysis (LoL loading screens have specific palettes)
    3. Structural layout detection (5+5 champion grid)
    4. Edge detection for UI elements
    """

    # LoL loading screen color signatures (HSV ranges for common elements)
    LOL_UI_COLORS = {
        "dark_bg": {"h": (0, 360), "s": (0, 30), "v": (0, 40)},
        "blue_team": {"h": (190, 230), "s": (40, 100), "v": (30, 80)},
        "red_team": {"h": (340, 20), "s": (40, 100), "v": (30, 80)},
        "gold_border": {"h": (35, 55), "s": (50, 100), "v": (60, 100)},
        "loading_bar": {"h": (80, 140), "s": (30, 100), "v": (40, 100)},
    }

    # Expected layout proportions
    CHAMPION_GRID = {
        "top_row_y": (0.05, 0.48),      # Blue team: top ~5%-48% of screen
        "bottom_row_y": (0.52, 0.95),    # Red team: bottom ~52%-95%
        "champion_width_ratio": 0.18,     # Each champ splash ≈18% of screen width
        "champion_count": 5,              # 5 per row
    }

    def __init__(self):
        self.detection_history: List[Dict] = []

    def detect(self, image: Image.Image) -> Dict[str, Any]:
        """
        Analyze image and return detection result.

        Returns:
            {
                "is_loading_screen": bool,
                "confidence": float (0-1),
                "signals": {
                    "aspect_ratio": float,
                    "color_match": float,
                    "layout_match": float,
                    "dark_ratio": float,
                },
                "detected_regions": {
                    "blue_team_area": (x1, y1, x2, y2),
                    "red_team_area": (x1, y1, x2, y2),
                    "champion_slots": [(x1,y1,x2,y2), ...],  # 10 slots
                }
            }
        """
        w, h = image.size
        result = {
            "is_loading_screen": False,
            "confidence": 0.0,
            "signals": {},
            "detected_regions": {},
        }

        # --- Signal 1: Aspect Ratio ---
        aspect = w / h
        # LoL runs at 16:9 (1.777) or 16:10 (1.6) or ultrawide (2.333)
        aspect_score = 0.0
        if 1.7 <= aspect <= 1.85:    # 16:9 ± tolerance
            aspect_score = 1.0
        elif 1.55 <= aspect <= 1.65:  # 16:10
            aspect_score = 0.9
        elif 2.2 <= aspect <= 2.5:    # Ultrawide
            aspect_score = 0.8
        elif 1.2 <= aspect <= 2.5:    # Playable but unusual
            aspect_score = 0.3
        result["signals"]["aspect_ratio"] = aspect_score

        # --- Signal 2: Color Distribution ---
        # Resize for fast analysis
        thumb = image.resize((160, 90), Image.LANCZOS)
        pixels = list(thumb.getdata())

        dark_pixels = sum(1 for r, g, b in pixels if r < 50 and g < 50 and b < 50)
        dark_ratio = dark_pixels / len(pixels)

        # LoL loading screens are ~30-60% dark background
        if 0.25 <= dark_ratio <= 0.70:
            color_score = 0.5 + (0.5 * min(dark_ratio / 0.5, 1.0))
        elif dark_ratio > 0.70:
            color_score = 0.4  # Too dark, might be just a black screen
        else:
            color_score = 0.2  # Not enough dark, probably not loading screen

        # Check for blue/red team accent colors
        blue_pixels = sum(1 for r, g, b in pixels
                         if b > 120 and b > r * 1.3 and b > g * 1.1)
        red_pixels = sum(1 for r, g, b in pixels
                         if r > 120 and r > b * 1.3 and r > g * 1.1)
        blue_ratio = blue_pixels / len(pixels)
        red_ratio = red_pixels / len(pixels)

        # Loading screen should have SOME blue and red team indicators
        if blue_ratio > 0.02 and red_ratio > 0.02:
            color_score += 0.15
        elif blue_ratio > 0.01 or red_ratio > 0.01:
            color_score += 0.05

        color_score = min(color_score, 1.0)
        result["signals"]["color_match"] = color_score
        result["signals"]["dark_ratio"] = dark_ratio

        # --- Signal 3: Structural Layout (Champion Grid) ---
        # Check for bright rectangular regions in the expected 5+5 grid positions
        layout_score = self._check_champion_grid(thumb, w, h)
        result["signals"]["layout_match"] = layout_score

        # --- Composite Confidence ---
        confidence = (
            aspect_score * 0.20 +
            color_score * 0.35 +
            layout_score * 0.45
        )
        result["confidence"] = round(confidence, 3)
        result["is_loading_screen"] = confidence >= DaemonConfig.LOL_DETECTION_CONFIDENCE

        # --- Detect Regions ---
        if result["is_loading_screen"]:
            result["detected_regions"] = self._compute_regions(w, h)

        return result

    def _check_champion_grid(self, thumb: Image.Image, orig_w: int, orig_h: int) -> float:
        """Check if image has 5+5 bright rectangular regions matching champion splash layout."""
        tw, th = thumb.size
        pixels = thumb.load()

        # Check brightness variance in expected champion slot positions
        slot_scores = []

        for row_idx, (y_start, y_end) in enumerate([
            (int(th * 0.08), int(th * 0.45)),   # Blue team row
            (int(th * 0.55), int(th * 0.92)),    # Red team row
        ]):
            for col in range(5):
                x_start = int(tw * (0.01 + col * 0.195))
                x_end = int(tw * (0.01 + col * 0.195 + 0.17))
                x_start = max(0, min(x_start, tw - 1))
                x_end = max(x_start + 1, min(x_end, tw))
                y_start_c = max(0, min(y_start, th - 1))
                y_end_c = max(y_start_c + 1, min(y_end, th))

                # Sample pixels in this region
                region_brightness = []
                for y in range(y_start_c, y_end_c, 2):
                    for x in range(x_start, x_end, 2):
                        try:
                            r, g, b = pixels[x, y][:3]
                            region_brightness.append((r + g + b) / 3)
                        except (IndexError, TypeError):
                            pass

                if region_brightness:
                    avg_brightness = sum(region_brightness) / len(region_brightness)
                    # Champion splashes are typically 40-180 brightness (not pitch black, not pure white)
                    if 30 < avg_brightness < 200:
                        brightness_var = sum((b - avg_brightness) ** 2 for b in region_brightness) / len(region_brightness)
                        # Splashes have moderate variance (detail), not flat color
                        if brightness_var > 100:
                            slot_scores.append(1.0)
                        elif brightness_var > 30:
                            slot_scores.append(0.5)
                        else:
                            slot_scores.append(0.1)
                    else:
                        slot_scores.append(0.1)
                else:
                    slot_scores.append(0.0)

        if not slot_scores:
            return 0.0

        # If 7+ of 10 slots match, strong signal
        matched = sum(1 for s in slot_scores if s > 0.4)
        return min(matched / 8.0, 1.0)

    def _compute_regions(self, w: int, h: int) -> Dict:
        """Compute expected champion slot bounding boxes for a given resolution."""
        slots = []
        for row_idx, (y_frac_start, y_frac_end) in enumerate([
            (0.05, 0.48),   # Blue team
            (0.52, 0.95),   # Red team
        ]):
            for col in range(5):
                x1 = int(w * (0.01 + col * 0.195))
                x2 = int(w * (0.01 + col * 0.195 + 0.17))
                y1 = int(h * y_frac_start)
                y2 = int(h * y_frac_end)
                slots.append({
                    "team": "blue" if row_idx == 0 else "red",
                    "slot_index": col,
                    "bbox": (x1, y1, x2, y2),
                })

        return {
            "blue_team_area": (0, int(h * 0.05), w, int(h * 0.48)),
            "red_team_area": (0, int(h * 0.52), w, int(h * 0.95)),
            "champion_slots": slots,
        }


# =============================================================================
# CLIPBOARD WATCHER (Windows-native)
# =============================================================================

class ClipboardWatcher:
    """
    Watches the Windows clipboard for new images (PrintScreen captures).

    Uses polling with deduplication to detect new screenshots.
    On detection, fires the callback with the PIL Image.
    """

    def __init__(self, on_screenshot: Callable[[Image.Image, float], None]):
        self.on_screenshot = on_screenshot
        self._running = False
        self._last_hash: Optional[str] = None
        self._last_capture_time: float = 0
        self._thread: Optional[threading.Thread] = None

    def _get_clipboard_image(self) -> Optional[Image.Image]:
        """Grab image from clipboard if available."""
        if HAS_PIL:
            try:
                img = ImageGrab.grabclipboard()
                if isinstance(img, Image.Image):
                    return img.convert("RGB")
            except Exception as e:
                logger.debug(f"Clipboard read error: {e}")
        return None

    def _image_hash(self, img: Image.Image) -> str:
        """Fast perceptual hash to detect duplicate screenshots."""
        thumb = img.resize((16, 16), Image.LANCZOS).convert("L")
        pixels = list(thumb.getdata())
        avg = sum(pixels) / len(pixels)
        bits = "".join("1" if p > avg else "0" for p in pixels)
        return hex(int(bits, 2))

    def _poll_loop(self):
        """Main polling loop — runs in background thread."""
        logger.info("🎯 Clipboard watcher started — press PrintScreen on your loading screen!")

        while self._running:
            try:
                img = self._get_clipboard_image()

                if img is not None:
                    now = time.time()
                    img_hash = self._image_hash(img)

                    # Dedup: skip if same image or too soon after last capture
                    if (img_hash != self._last_hash and
                            now - self._last_capture_time > DaemonConfig.SCREENSHOT_COOLDOWN):

                        self._last_hash = img_hash
                        self._last_capture_time = now

                        logger.info(f"📸 New screenshot detected ({img.size[0]}x{img.size[1]})")
                        self.on_screenshot(img, now)

            except Exception as e:
                logger.error(f"Clipboard poll error: {e}")

            time.sleep(DaemonConfig.CLIPBOARD_POLL_INTERVAL)

    def start(self):
        """Start watching clipboard in background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="clipboard-watcher")
        self._thread.start()

    def stop(self):
        """Stop the watcher."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)


# =============================================================================
# SCREENSHOT FOLDER WATCHER (Cross-platform fallback)
# =============================================================================

class FolderWatcher:
    """
    Watches a folder for new screenshot files.
    Fallback for systems where clipboard monitoring isn't available.

    Works with:
    - Windows Screenshots folder
    - Steam/LoL screenshot directories
    - Custom screenshot tools (ShareX, Lightshot, etc.)
    """

    def __init__(self, watch_dirs: List[str], on_screenshot: Callable[[Image.Image, float], None]):
        self.watch_dirs = [Path(d) for d in watch_dirs if Path(d).exists()]
        self.on_screenshot = on_screenshot
        self._running = False
        self._known_files: set = set()
        self._thread: Optional[threading.Thread] = None

    def _scan_existing(self):
        """Record existing files so we only react to NEW ones."""
        for d in self.watch_dirs:
            for f in d.glob("*.png"):
                self._known_files.add(str(f))
            for f in d.glob("*.jpg"):
                self._known_files.add(str(f))

    def _poll_loop(self):
        self._scan_existing()
        logger.info(f"📁 Folder watcher started — monitoring {len(self.watch_dirs)} directories")

        while self._running:
            try:
                for d in self.watch_dirs:
                    for pattern in ["*.png", "*.jpg", "*.bmp"]:
                        for f in d.glob(pattern):
                            fstr = str(f)
                            if fstr not in self._known_files:
                                self._known_files.add(fstr)
                                # Check file age (only process files < 10 seconds old)
                                age = time.time() - f.stat().st_mtime
                                if age < 10:
                                    try:
                                        img = Image.open(f).convert("RGB")
                                        logger.info(f"📸 New file detected: {f.name}")
                                        self.on_screenshot(img, time.time())
                                    except Exception as e:
                                        logger.debug(f"Failed to open {f}: {e}")
            except Exception as e:
                logger.error(f"Folder poll error: {e}")

            time.sleep(1.0)

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="folder-watcher")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)


# =============================================================================
# COACHING PIPELINE TRIGGER
# =============================================================================

class CoachingPipeline:
    """
    The bridge between screenshot detection and the coaching swarm.

    Flow:
    1. Receive screenshot Image
    2. Run LoadingScreenDetector
    3. If LoL detected → extract champion slots + encode for vision API
    4. Fire the full swarm (async)
    5. Return GameCoachPackage
    6. Trigger overlay display
    """

    def __init__(self, swarm=None, config: Optional[DaemonConfig] = None):
        self.detector = LoadingScreenDetector()
        self.config = config or DaemonConfig()
        self.swarm = swarm  # LeagueCoachingSwarm instance
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._processing = False

        # Stats
        self.stats = {
            "screenshots_seen": 0,
            "lol_detected": 0,
            "coaching_runs": 0,
            "total_latency_ms": 0,
            "last_run": None,
        }

    def _ensure_dirs(self):
        """Create output directories if they don't exist."""
        for d in [self.config.SCREENSHOT_DIR, self.config.COACHING_OUTPUT_DIR, self.config.LOG_DIR]:
            Path(d).mkdir(parents=True, exist_ok=True)

    def _image_to_base64(self, img: Image.Image) -> str:
        """Convert PIL Image to base64 string for Claude Vision API."""
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _extract_champion_crops(self, img: Image.Image, regions: Dict) -> List[Dict]:
        """Crop individual champion splash regions from the loading screen."""
        crops = []
        for slot in regions.get("champion_slots", []):
            bbox = slot["bbox"]
            try:
                crop = img.crop(bbox)
                crops.append({
                    "team": slot["team"],
                    "slot_index": slot["slot_index"],
                    "image_b64": self._image_to_base64(crop),
                    "bbox": bbox,
                })
            except Exception as e:
                logger.warning(f"Failed to crop slot {slot}: {e}")
        return crops

    def _save_screenshot(self, img: Image.Image, timestamp: float) -> str:
        """Save screenshot to disk for debugging/history."""
        self._ensure_dirs()
        fname = f"loading_screen_{datetime.fromtimestamp(timestamp).strftime('%Y%m%d_%H%M%S')}.png"
        fpath = os.path.join(self.config.SCREENSHOT_DIR, fname)
        img.save(fpath, "PNG")
        logger.info(f"💾 Screenshot saved: {fpath}")
        return fpath

    async def _run_swarm(self, image_b64: str, champion_crops: List[Dict]) -> Dict:
        """Execute the full coaching swarm pipeline."""
        if self.swarm is None:
            # Import here to avoid circular deps
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from orchestrator.swarm import LeagueCoachingSwarm
            self.swarm = LeagueCoachingSwarm()

        # Run with the full image — swarm handles vision parsing internally
        result = await self.swarm.run(
            image_data=image_b64,
            mode="FAST",
            # Pass pre-computed crops as hints to speed up vision parsing
            vision_hints={
                "champion_crops": champion_crops,
                "pre_detected": True,
            }
        )
        return result

    def process_screenshot(self, img: Image.Image, timestamp: float):
        """
        Main entry point — called by clipboard/folder watcher.
        Runs detection + coaching pipeline.
        """
        if self._processing:
            logger.info("⏳ Already processing a screenshot, skipping...")
            return

        self._processing = True
        self.stats["screenshots_seen"] += 1
        start = time.time()

        try:
            # Step 1: Detect if this is a LoL loading screen
            detection = self.detector.detect(img)
            logger.info(
                f"🔍 Detection: is_lol={detection['is_loading_screen']}, "
                f"confidence={detection['confidence']:.2f}, "
                f"signals={detection['signals']}"
            )

            if not detection["is_loading_screen"]:
                logger.info("❌ Not a loading screen — ignoring")
                self._processing = False
                return

            self.stats["lol_detected"] += 1

            # Step 2: Save screenshot
            saved_path = self._save_screenshot(img, timestamp)

            # Step 3: Extract champion crops from detected regions
            crops = self._extract_champion_crops(img, detection["detected_regions"])
            logger.info(f"✂️  Extracted {len(crops)} champion crops")

            # Step 4: Encode full image for vision API
            full_image_b64 = self._image_to_base64(img)

            # Step 5: Run the coaching swarm (async)
            logger.info("🧠 Launching coaching swarm...")
            self._notify_user("🎮 LoL Loading Screen Detected!", "Running coaching analysis...")

            # Get or create event loop for async execution
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    raise RuntimeError
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            result = loop.run_until_complete(self._run_swarm(full_image_b64, crops))

            elapsed = (time.time() - start) * 1000
            self.stats["coaching_runs"] += 1
            self.stats["total_latency_ms"] += elapsed
            self.stats["last_run"] = datetime.now().isoformat()

            # Step 6: Save coaching output
            self._save_coaching_output(result, timestamp)

            # Step 7: Display overlay
            logger.info(f"✅ Coaching complete in {elapsed:.0f}ms")
            self._display_result(result, elapsed)

        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            self._notify_user("❌ Coaching Error", str(e))

        finally:
            self._processing = False

    def _save_coaching_output(self, result: Dict, timestamp: float):
        """Save coaching output as JSON."""
        self._ensure_dirs()
        fname = f"coach_{datetime.fromtimestamp(timestamp).strftime('%Y%m%d_%H%M%S')}.json"
        fpath = os.path.join(self.config.COACHING_OUTPUT_DIR, fname)
        with open(fpath, "w") as f:
            json.dump(result, f, indent=2, default=str)
        logger.info(f"💾 Coaching output saved: {fpath}")

    def _display_result(self, result: Dict, latency_ms: float):
        """Display the coaching result — delegates to overlay or console."""
        # Extract key info for quick display
        if isinstance(result, dict):
            user_champ = result.get("user", {}).get("champion", "Unknown")
            user_role = result.get("user", {}).get("role", "Unknown")
            opponent = result.get("user", {}).get("lane_opponent", "Unknown")

            summary_lines = [
                f"🎮 You: {user_champ} ({user_role})",
                f"⚔️  vs: {opponent}",
            ]

            # Build
            build = result.get("build", {})
            if build:
                core = build.get("core_items", [])
                if core:
                    summary_lines.append(f"🔨 Core: {' → '.join(core[:3])}")
                runes = build.get("runes", {})
                if runes:
                    summary_lines.append(f"📜 Keystone: {runes.get('primary', ['?'])[0]}")

            # Next 30 seconds
            n30 = result.get("next_30_seconds", {})
            dos = n30.get("do", [])
            avoids = n30.get("avoid", [])
            if dos:
                summary_lines.append(f"✅ DO: {dos[0]}")
            if avoids:
                summary_lines.append(f"🚫 DON'T: {avoids[0]}")

            summary = "\n".join(summary_lines)
            logger.info(f"\n{'='*50}\n{summary}\n{'='*50}")

            self._notify_user(
                f"🧠 Coach Ready ({latency_ms:.0f}ms)",
                summary
            )
        else:
            logger.warning("Result is not a dict — cannot display")

    def _notify_user(self, title: str, message: str):
        """Send system notification."""
        try:
            # Windows toast notification
            if sys.platform == "win32":
                try:
                    from win10toast_click import ToastNotifier
                    toaster = ToastNotifier()
                    toaster.show_toast(
                        title, message,
                        duration=DaemonConfig.OVERLAY_DURATION,
                        threaded=True
                    )
                    return
                except ImportError:
                    pass

                try:
                    from plyer import notification
                    notification.notify(
                        title=title,
                        message=message,
                        timeout=DaemonConfig.OVERLAY_DURATION,
                        app_name="League Coach OS"
                    )
                    return
                except ImportError:
                    pass

            # Fallback: just print
            print(f"\n🔔 {title}\n{message}\n")

        except Exception as e:
            logger.debug(f"Notification error: {e}")
            print(f"\n🔔 {title}\n{message}\n")


# =============================================================================
# SYSTEM TRAY APPLICATION
# =============================================================================

class LeagueCoachTray:
    """
    System tray icon + menu for the coaching daemon.

    Tray icon shows:
    - Green: Active and watching
    - Yellow: Processing a screenshot
    - Red: Error state

    Menu options:
    - Status info
    - Pause/Resume watching
    - Settings
    - Quit
    """

    def __init__(self, pipeline: CoachingPipeline):
        self.pipeline = pipeline
        self.icon = None
        self._paused = False

    def _create_icon_image(self, color: str = "green") -> Image.Image:
        """Create a simple colored circle icon."""
        colors = {"green": "#00CED1", "yellow": "#FFD700", "red": "#FF4444"}
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, 60, 60], fill=colors.get(color, "#00CED1"))
        # Draw a small "L" for League
        try:
            draw.text((20, 15), "L", fill="white")
        except Exception:
            pass
        return img

    def _build_menu(self):
        stats = self.pipeline.stats
        return pystray.Menu(
            item(f"League Coach OS v1.0", lambda: None, enabled=False),
            item(f"Status: {'Paused' if self._paused else 'Watching'}", lambda: None, enabled=False),
            pystray.Menu.SEPARATOR,
            item(f"Screenshots seen: {stats['screenshots_seen']}", lambda: None, enabled=False),
            item(f"LoL detected: {stats['lol_detected']}", lambda: None, enabled=False),
            item(f"Coaching runs: {stats['coaching_runs']}", lambda: None, enabled=False),
            pystray.Menu.SEPARATOR,
            item("Pause" if not self._paused else "Resume", self._toggle_pause),
            item("Quit", self._quit),
        )

    def _toggle_pause(self):
        self._paused = not self._paused
        logger.info(f"{'⏸️  Paused' if self._paused else '▶️  Resumed'}")
        if self.icon:
            self.icon.icon = self._create_icon_image("yellow" if self._paused else "green")
            self.icon.menu = self._build_menu()

    def _quit(self):
        logger.info("🛑 Shutting down League Coach daemon...")
        if self.icon:
            self.icon.stop()

    def run(self):
        """Start the system tray icon."""
        if not HAS_TRAY or not HAS_PIL:
            logger.warning("System tray not available — running headless")
            return

        self.icon = pystray.Icon(
            "league_coach",
            self._create_icon_image("green"),
            "League Coach OS",
            menu=self._build_menu(),
        )
        self.icon.run()


# =============================================================================
# MAIN DAEMON
# =============================================================================

class LeagueCoachDaemon:
    """
    The autonomous coaching daemon.

    Lifecycle:
    1. Start clipboard watcher + folder watcher
    2. Start system tray icon
    3. On screenshot → detect → coach → display
    4. Runs until user quits from tray

    Usage:
        python -m daemon.screenshot_watcher

    Or from the main entry point:
        python main.py daemon
    """

    def __init__(self, config: Optional[DaemonConfig] = None):
        self.config = config or DaemonConfig()
        self.pipeline = CoachingPipeline(config=self.config)
        self.clipboard_watcher: Optional[ClipboardWatcher] = None
        self.folder_watcher: Optional[FolderWatcher] = None
        self.tray: Optional[LeagueCoachTray] = None

    def _on_screenshot(self, img: Image.Image, timestamp: float):
        """Callback fired when a new screenshot is detected."""
        # Run processing in a separate thread to not block the watcher
        thread = threading.Thread(
            target=self.pipeline.process_screenshot,
            args=(img, timestamp),
            daemon=True,
            name="coaching-pipeline",
        )
        thread.start()

    def start(self):
        """Start the full daemon."""
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            handlers=[
                logging.StreamHandler(),
            ]
        )

        # Ensure directories
        Path(self.config.SCREENSHOT_DIR).mkdir(parents=True, exist_ok=True)
        Path(self.config.COACHING_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        Path(self.config.LOG_DIR).mkdir(parents=True, exist_ok=True)

        print(r"""
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║   ██╗     ██████╗  █████╗  ██████╗██╗  ██╗              ║
║   ██║    ██╔════╝ ██╔══██╗██╔════╝██║  ██║              ║
║   ██║    ██║      ██║  ██║██║     ███████║              ║
║   ██║    ██║      ██║  ██║██║     ██╔══██║              ║
║   ███████╗╚██████╗╚█████╔╝╚██████╗██║  ██║              ║
║   ╚══════╝ ╚═════╝ ╚════╝  ╚═════╝╚═╝  ╚═╝              ║
║                                                          ║
║          LEAGUE COACH OS — Barrios A2I                   ║
║          Autonomous Coaching Daemon v1.0                 ║
║                                                          ║
║   🎯 Hit PrintScreen on your loading screen              ║
║   🧠 9 agents analyze your game in <7 seconds            ║
║   ⚡ Zero clicks. Zero typing. Just play.                ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
        """)

        # Start clipboard watcher (primary)
        if HAS_PIL:
            self.clipboard_watcher = ClipboardWatcher(self._on_screenshot)
            self.clipboard_watcher.start()
            print("  ✅ Clipboard watcher: ACTIVE")
        else:
            print("  ⚠️  Clipboard watcher: DISABLED (install Pillow)")

        # Start folder watcher (secondary/fallback)
        screenshot_dirs = [
            self.config.SCREENSHOT_DIR,
            os.path.expanduser("~/Pictures/Screenshots"),
            os.path.expanduser("~/Videos/League of Legends"),
        ]
        self.folder_watcher = FolderWatcher(screenshot_dirs, self._on_screenshot)
        self.folder_watcher.start()
        print(f"  ✅ Folder watcher: ACTIVE ({len(self.folder_watcher.watch_dirs)} dirs)")

        # Start system tray
        if HAS_TRAY and HAS_PIL:
            self.tray = LeagueCoachTray(self.pipeline)
            print("  ✅ System tray: ACTIVE")
            print("\n  👁️  Watching for screenshots... (Ctrl+C to stop)\n")
            try:
                self.tray.run()  # Blocks until quit
            except KeyboardInterrupt:
                pass
        else:
            print("  ⚠️  System tray: DISABLED (install pystray)")
            print("\n  👁️  Watching for screenshots... (Ctrl+C to stop)\n")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass

        self.stop()

    def stop(self):
        """Graceful shutdown."""
        print("\n🛑 Shutting down...")
        if self.clipboard_watcher:
            self.clipboard_watcher.stop()
        if self.folder_watcher:
            self.folder_watcher.stop()
        print("👋 League Coach daemon stopped.")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    daemon = LeagueCoachDaemon()
    daemon.start()
