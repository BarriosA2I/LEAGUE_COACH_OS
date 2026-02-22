"""
================================================================================
LEAGUE COACH OS — GLOBAL HOTKEY LISTENER
================================================================================
Captures PrintScreen (and configurable hotkeys) globally on Windows.
Routes captures directly to the coaching pipeline.

Supports:
- PrintScreen: Capture and analyze
- Ctrl+PrintScreen: Capture with FULL mode
- F9: Toggle overlay visibility
- Ctrl+Shift+L: Open settings / re-analyze last screenshot

Author: Barrios A2I | Version: 1.0.0
================================================================================
"""
import logging
import threading
import time
from typing import Callable, Dict, Optional

try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False

try:
    from PIL import ImageGrab
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

logger = logging.getLogger("league_coach.hotkey")


class HotkeyConfig:
    """Hotkey bindings — all customizable."""
    CAPTURE_AND_COACH = "print screen"          # Standard PrintScreen
    CAPTURE_FULL_MODE = "ctrl+print screen"     # PrintScreen with FULL mode
    TOGGLE_OVERLAY = "F9"                        # Toggle overlay on/off
    REANALYZE = "ctrl+shift+l"                   # Re-analyze last screenshot
    DISMISS_OVERLAY = "escape"                    # Dismiss overlay
    TOGGLE_COMPACT = "F10"                        # Toggle compact/expanded overlay


class HotkeyListener:
    """
    Global hotkey listener for the coaching daemon.

    Uses the `keyboard` library for system-wide hotkey capture.
    This works even when LoL is in the foreground (fullscreen).
    """

    def __init__(self, on_capture: Callable, on_toggle: Callable = None,
                 on_reanalyze: Callable = None):
        self.on_capture = on_capture
        self.on_toggle = on_toggle or (lambda: None)
        self.on_reanalyze = on_reanalyze or (lambda: None)
        self._running = False
        self._last_capture_time = 0
        self._cooldown = 3.0  # seconds between captures
        self._mode = "FAST"   # default mode

    def _handle_printscreen(self):
        """Handle PrintScreen keypress — grab screen and route to pipeline."""
        now = time.time()
        if now - self._last_capture_time < self._cooldown:
            logger.debug("PrintScreen cooldown active, ignoring")
            return

        self._last_capture_time = now
        self._mode = "FAST"

        logger.info("🖨️  PrintScreen detected — capturing screen...")
        self._capture_and_route()

    def _handle_full_mode(self):
        """Handle Ctrl+PrintScreen — FULL mode analysis."""
        now = time.time()
        if now - self._last_capture_time < self._cooldown:
            return

        self._last_capture_time = now
        self._mode = "FULL"

        logger.info("🖨️  Ctrl+PrintScreen detected — FULL MODE capture...")
        self._capture_and_route()

    def _capture_and_route(self):
        """Grab the screen and send to the coaching pipeline."""
        if not HAS_PIL:
            logger.error("PIL not available — cannot capture screen")
            return

        try:
            # Grab the entire screen
            img = ImageGrab.grab()
            if img:
                img = img.convert("RGB")
                logger.info(f"📸 Screen captured: {img.size[0]}x{img.size[1]}")

                # Fire callback in a new thread to not block hotkey listener
                thread = threading.Thread(
                    target=self.on_capture,
                    args=(img, time.time()),
                    daemon=True,
                    name="capture-handler"
                )
                thread.start()
            else:
                logger.warning("Screen capture returned None")

        except Exception as e:
            logger.error(f"Screen capture error: {e}", exc_info=True)

    def start(self):
        """Register all hotkeys and start listening."""
        if not HAS_KEYBOARD:
            logger.warning(
                "⚠️  'keyboard' library not available. "
                "Install with: pip install keyboard\n"
                "Falling back to clipboard polling only."
            )
            return False

        try:
            # Register hotkeys
            keyboard.add_hotkey(
                HotkeyConfig.CAPTURE_AND_COACH,
                self._handle_printscreen,
                suppress=False  # Don't suppress — let PrintScreen also work normally
            )
            keyboard.add_hotkey(
                HotkeyConfig.CAPTURE_FULL_MODE,
                self._handle_full_mode,
                suppress=False
            )
            keyboard.add_hotkey(
                HotkeyConfig.TOGGLE_OVERLAY,
                self.on_toggle
            )
            keyboard.add_hotkey(
                HotkeyConfig.REANALYZE,
                self.on_reanalyze
            )

            self._running = True
            logger.info("🎹 Hotkey listener active:")
            logger.info(f"   PrintScreen     → Capture + FAST coach")
            logger.info(f"   Ctrl+PrtSc      → Capture + FULL coach")
            logger.info(f"   F9              → Toggle overlay")
            logger.info(f"   Ctrl+Shift+L    → Re-analyze last")

            return True

        except Exception as e:
            logger.error(f"Failed to register hotkeys: {e}")
            logger.info("Try running as Administrator for global hotkeys")
            return False

    def stop(self):
        """Unregister all hotkeys."""
        if HAS_KEYBOARD:
            try:
                keyboard.unhook_all_hotkeys()
            except Exception:
                pass
        self._running = False
