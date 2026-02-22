"""
================================================================================
LEAGUE COACH OS — GAME STATE DETECTOR
================================================================================
Identifies what the player is seeing at ANY point in a League of Legends game.
Every PrintScreen triggers different coaching logic based on the detected state.

Detectable States:
  LOADING_SCREEN    → Full pre-game plan (existing flow)
  TAB_SCOREBOARD    → Item tracking, gold leads, build adjustments
  SHOP_OPEN         → "Buy this NOW" recommendations
  IN_GAME_LANING    → Lane state, trade opportunities, wave management
  IN_GAME_TEAMFIGHT → Who to focus, positioning, cooldown tracking
  IN_GAME_OBJECTIVES→ Dragon/Baron/Herald setup, ward placement
  DEATH_SCREEN      → What went wrong, what to change
  POST_GAME_STATS   → Game review, improvement tips
  CHAMPION_SELECT   → Draft advice (future)
  NOT_LOL           → Ignore (desktop, browser, etc.)

Detection Method:
  Multi-signal heuristic classifier that checks:
  - UI element positions (minimap, health bars, shop button, tab overlay)
  - Color distributions per screen region
  - Text/UI patterns unique to each state
  - Temporal context (what state were we in 5 seconds ago?)

Author: Barrios A2I | Version: 2.0.0
================================================================================
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

import numpy as np

logger = logging.getLogger("league_coach.game_state")


# =============================================================================
# GAME STATES
# =============================================================================

class GameState(str, Enum):
    """All detectable states in a League of Legends session."""
    LOADING_SCREEN = "loading_screen"
    TAB_SCOREBOARD = "tab_scoreboard"
    SHOP_OPEN = "shop_open"
    IN_GAME_LANING = "in_game_laning"
    IN_GAME_TEAMFIGHT = "in_game_teamfight"
    IN_GAME_OBJECTIVES = "in_game_objectives"
    DEATH_SCREEN = "death_screen"
    POST_GAME_STATS = "post_game_stats"
    CHAMPION_SELECT = "champion_select"
    NOT_LOL = "not_lol"


class GamePhase(str, Enum):
    """High-level game timeline phases."""
    PRE_GAME = "pre_game"
    EARLY_LANING = "early_laning"       # 0-8 min
    MID_LANING = "mid_laning"           # 8-14 min
    MID_GAME = "mid_game"               # 14-25 min
    LATE_GAME = "late_game"             # 25+ min
    POST_GAME = "post_game"


class LanePhase(str, Enum):
    """Laning sub-phases for detailed coaching."""
    LEVEL_1 = "level_1"
    LEVELS_2_3 = "levels_2_3"
    LEVELS_4_5 = "levels_4_5"
    LEVEL_6_PLUS = "level_6_plus"
    ROAMING = "roaming"


# =============================================================================
# DETECTION RESULT
# =============================================================================

@dataclass
class GameStateResult:
    """Full detection result with confidence and context."""
    state: GameState
    confidence: float
    phase: Optional[GamePhase] = None
    lane_phase: Optional[LanePhase] = None

    # Extracted data from the screenshot
    extracted: Dict[str, Any] = field(default_factory=dict)

    # What coaching to provide
    coaching_action: str = ""

    # Screen regions of interest
    regions: Dict[str, Tuple[int, int, int, int]] = field(default_factory=dict)

    # Game clock if detected
    game_time_seconds: Optional[int] = None

    # Temporal context
    previous_state: Optional[GameState] = None
    state_duration_seconds: float = 0.0


# =============================================================================
# SCREEN REGION DEFINITIONS (for 1920x1080 — scaled for other resolutions)
# =============================================================================

class ScreenRegions:
    """
    Known UI element positions in League of Legends at 1920x1080.
    All coordinates are fractional (0-1) for resolution independence.
    """

    # Minimap (bottom-right corner)
    MINIMAP = (0.78, 0.74, 1.0, 1.0)

    # Game clock (top-center)
    GAME_CLOCK = (0.46, 0.0, 0.54, 0.03)

    # Player HUD (bottom-center)
    PLAYER_HUD = (0.30, 0.85, 0.70, 1.0)

    # Health/Mana bars on HUD
    HEALTH_BAR = (0.38, 0.90, 0.62, 0.92)
    MANA_BAR = (0.38, 0.93, 0.62, 0.95)

    # Kill score (top-center, below clock)
    KILL_SCORE = (0.43, 0.0, 0.57, 0.05)

    # Tab scoreboard (covers most of center screen when pressed)
    TAB_OVERLAY = (0.10, 0.05, 0.90, 0.85)

    # Shop window (covers center-right when open)
    SHOP_WINDOW = (0.20, 0.05, 0.85, 0.90)
    SHOP_SEARCH_BAR = (0.25, 0.08, 0.55, 0.12)
    SHOP_GOLD_DISPLAY = (0.72, 0.06, 0.82, 0.10)

    # Death screen (gray overlay + death timer)
    DEATH_TIMER_AREA = (0.44, 0.30, 0.56, 0.40)
    DEATH_RECAP = (0.30, 0.20, 0.70, 0.80)

    # CS counter (top-right area near minimap)
    CS_COUNTER = (0.73, 0.0, 0.78, 0.03)

    # Champion portraits (top of screen, both teams)
    ALLY_PORTRAITS = (0.30, 0.0, 0.48, 0.04)
    ENEMY_PORTRAITS = (0.52, 0.0, 0.70, 0.04)

    # Items display (bottom-center HUD)
    ITEMS_AREA = (0.43, 0.88, 0.57, 0.96)

    # Spell icons (bottom-center)
    SPELL_ICONS = (0.35, 0.92, 0.65, 1.0)

    # Loading screen champion grid
    LOADING_BLUE_ROW = (0.01, 0.05, 0.99, 0.48)
    LOADING_RED_ROW = (0.01, 0.52, 0.99, 0.95)

    # Post-game stats screen
    POSTGAME_HEADER = (0.0, 0.0, 1.0, 0.08)
    POSTGAME_STATS = (0.05, 0.10, 0.95, 0.90)

    @classmethod
    def get_pixel_region(cls, region: Tuple[float, float, float, float],
                         width: int, height: int) -> Tuple[int, int, int, int]:
        """Convert fractional region to pixel coordinates."""
        x1, y1, x2, y2 = region
        return (int(x1 * width), int(y1 * height), int(x2 * width), int(y2 * height))


# =============================================================================
# GAME STATE DETECTOR
# =============================================================================

class GameStateDetector:
    """
    Multi-signal heuristic classifier for League of Legends game states.

    Uses a combination of color analysis, UI element detection, and
    temporal context to determine what the player is currently seeing.

    The detector maintains state history for temporal reasoning:
    - If we were in LOADING_SCREEN and now see a minimap → IN_GAME_LANING
    - If we were IN_GAME and see a gray overlay → DEATH_SCREEN
    - If we've been in LANING for 15+ minutes → transition to MID_GAME
    """

    def __init__(self):
        self._state_history: List[Tuple[float, GameState]] = []
        self._game_start_time: Optional[float] = None
        self._current_state = GameState.NOT_LOL
        self._last_detection_time = 0.0

        # Accumulated game knowledge from this session
        self.session = GameSession()

    def detect(self, image: Image.Image) -> GameStateResult:
        """
        Analyze a screenshot and determine the current game state.

        Returns a GameStateResult with the detected state, confidence,
        extracted data, and recommended coaching action.
        """
        w, h = image.size
        now = time.time()

        # Run all detectors and pick highest confidence
        candidates = [
            self._check_loading_screen(image, w, h),
            self._check_tab_scoreboard(image, w, h),
            self._check_shop_open(image, w, h),
            self._check_death_screen(image, w, h),
            self._check_post_game(image, w, h),
            self._check_in_game(image, w, h),
        ]

        # Sort by confidence, pick best
        candidates.sort(key=lambda r: r.confidence, reverse=True)
        best = candidates[0]

        # Apply temporal reasoning
        best = self._apply_temporal_context(best, now)

        # Update history
        self._state_history.append((now, best.state))
        if len(self._state_history) > 100:
            self._state_history = self._state_history[-50:]

        best.previous_state = self._current_state
        self._current_state = best.state
        self._last_detection_time = now

        # Set coaching action
        best.coaching_action = self._determine_coaching_action(best)

        logger.info(
            f"🎮 State: {best.state.value} | Confidence: {best.confidence:.2f} | "
            f"Phase: {best.phase} | Action: {best.coaching_action}"
        )

        return best

    # =========================================================================
    # INDIVIDUAL STATE DETECTORS
    # =========================================================================

    def _check_loading_screen(self, img: Image.Image, w: int, h: int) -> GameStateResult:
        """Detect loading screen (5+5 champion grid, dark background)."""
        thumb = img.resize((160, 90), Image.LANCZOS)
        pixels = list(thumb.getdata())

        # Loading screen signals
        dark_pixels = sum(1 for r, g, b in pixels if r < 50 and g < 50 and b < 50)
        dark_ratio = dark_pixels / len(pixels)

        # Check for champion splash grid (bright rectangles in expected positions)
        tw, th = thumb.size
        pix = thumb.load()
        grid_score = self._check_5x2_grid(pix, tw, th)

        # No minimap (loading screen doesn't have one)
        minimap_region = ScreenRegions.get_pixel_region(ScreenRegions.MINIMAP, 160, 90)
        minimap_brightness = self._region_avg_brightness(pix, *minimap_region, tw, th)

        # Loading screen: dark bg, grid pattern, no bright minimap
        confidence = 0.0
        if 0.25 <= dark_ratio <= 0.70:
            confidence += 0.25
        if grid_score > 0.5:
            confidence += 0.45 * grid_score
        if minimap_brightness < 60:  # No minimap = darker corner
            confidence += 0.15

        # Aspect ratio
        aspect = w / h
        if 1.7 <= aspect <= 1.85:
            confidence += 0.10

        return GameStateResult(
            state=GameState.LOADING_SCREEN,
            confidence=min(confidence, 1.0),
            phase=GamePhase.PRE_GAME,
            coaching_action="full_pregame_plan",
        )

    def _check_tab_scoreboard(self, img: Image.Image, w: int, h: int) -> GameStateResult:
        """
        Detect TAB scoreboard overlay.

        TAB scoreboard has:
        - Semi-transparent dark overlay covering center screen
        - Two columns of 5 player rows (items, CS, KDA visible)
        - Gold/KDA numbers in structured grid
        - Still shows minimap and HUD underneath
        """
        thumb = img.resize((320, 180), Image.LANCZOS)
        pix = thumb.load()
        tw, th = 320, 180

        # Tab overlay covers the center ~80% of the screen with a dark tint
        center_region = ScreenRegions.get_pixel_region(ScreenRegions.TAB_OVERLAY, tw, th)
        center_brightness = self._region_avg_brightness(pix, *center_region, tw, th)
        center_dark_ratio = self._region_dark_ratio(pix, *center_region, tw, th)

        # Tab has structured rows — check for horizontal brightness banding
        band_score = self._check_horizontal_banding(pix, tw, th,
                                                      y_start=int(th * 0.10),
                                                      y_end=int(th * 0.80),
                                                      expected_bands=10)

        # Minimap should still be visible (tab doesn't cover it)
        minimap_region = ScreenRegions.get_pixel_region(ScreenRegions.MINIMAP, tw, th)
        minimap_brightness = self._region_avg_brightness(pix, *minimap_region, tw, th)
        has_minimap = minimap_brightness > 30

        confidence = 0.0
        if center_dark_ratio > 0.4:  # Dark overlay
            confidence += 0.25
        if 30 < center_brightness < 100:  # Not pitch black, has content
            confidence += 0.15
        if band_score > 0.4:  # Structured rows
            confidence += 0.35
        if has_minimap:
            confidence += 0.15

        return GameStateResult(
            state=GameState.TAB_SCOREBOARD,
            confidence=min(confidence, 1.0),
            coaching_action="item_check_and_build_adjust",
            extracted={"has_minimap": has_minimap},
        )

    def _check_shop_open(self, img: Image.Image, w: int, h: int) -> GameStateResult:
        """
        Detect shop window.

        Shop has:
        - Large panel covering center-right of screen
        - Search bar at top
        - Gold display
        - Item grid with icons
        - Distinct golden/brown color palette
        """
        thumb = img.resize((320, 180), Image.LANCZOS)
        pix = thumb.load()
        tw, th = 320, 180

        # Shop window region — should be brighter than in-game, has UI panel
        shop_region = ScreenRegions.get_pixel_region(ScreenRegions.SHOP_WINDOW, tw, th)
        shop_brightness = self._region_avg_brightness(pix, *shop_region, tw, th)

        # Shop has warm colors (gold, brown UI theme)
        shop_warm_ratio = self._region_warm_ratio(pix, *shop_region, tw, th)

        # Gold display area should have bright yellow text
        gold_region = ScreenRegions.get_pixel_region(ScreenRegions.SHOP_GOLD_DISPLAY, tw, th)
        gold_yellow = self._region_color_ratio(pix, *gold_region, tw, th, "yellow")

        # Minimap still visible
        minimap_region = ScreenRegions.get_pixel_region(ScreenRegions.MINIMAP, tw, th)
        minimap_brightness = self._region_avg_brightness(pix, *minimap_region, tw, th)
        has_minimap = minimap_brightness > 30

        confidence = 0.0
        if shop_brightness > 60:
            confidence += 0.20
        if shop_warm_ratio > 0.15:
            confidence += 0.30
        if gold_yellow > 0.05:
            confidence += 0.25
        if has_minimap:
            confidence += 0.15

        return GameStateResult(
            state=GameState.SHOP_OPEN,
            confidence=min(confidence, 1.0),
            coaching_action="buy_recommendation",
        )

    def _check_death_screen(self, img: Image.Image, w: int, h: int) -> GameStateResult:
        """
        Detect death/respawn screen.

        Death screen has:
        - Gray/desaturated color overlay on the entire game view
        - Death timer countdown in center
        - Death recap panel (who killed you, damage breakdown)
        - Reduced saturation across the entire image
        """
        thumb = img.resize((160, 90), Image.LANCZOS)
        pixels = list(thumb.getdata())

        # Death screen is heavily desaturated (gray tint)
        saturation_values = []
        for r, g, b in pixels:
            max_c = max(r, g, b)
            min_c = min(r, g, b)
            if max_c > 0:
                saturation_values.append((max_c - min_c) / max_c)
            else:
                saturation_values.append(0)

        avg_saturation = sum(saturation_values) / len(saturation_values)

        # Death screen also has a grayish tone — check for gray dominance
        gray_pixels = sum(1 for r, g, b in pixels
                         if abs(r - g) < 30 and abs(g - b) < 30 and abs(r - b) < 30
                         and 30 < r < 180)
        gray_ratio = gray_pixels / len(pixels)

        # Should still have some structure (not just a blank gray screen)
        brightness_values = [(r + g + b) / 3 for r, g, b in pixels]
        brightness_variance = sum((b - sum(brightness_values) / len(brightness_values)) ** 2
                                  for b in brightness_values) / len(brightness_values)

        confidence = 0.0
        if avg_saturation < 0.15:  # Very desaturated
            confidence += 0.40
        elif avg_saturation < 0.25:
            confidence += 0.20
        if gray_ratio > 0.35:
            confidence += 0.30
        if brightness_variance > 200:  # Still has game content (not blank)
            confidence += 0.15

        # Temporal: more likely if we were just in-game
        if self._current_state in (GameState.IN_GAME_LANING, GameState.IN_GAME_TEAMFIGHT):
            confidence += 0.10

        return GameStateResult(
            state=GameState.DEATH_SCREEN,
            confidence=min(confidence, 1.0),
            coaching_action="death_review_and_recovery",
        )

    def _check_post_game(self, img: Image.Image, w: int, h: int) -> GameStateResult:
        """
        Detect post-game stats/lobby screen.

        Post-game has:
        - "VICTORY" or "DEFEAT" banner
        - Stats table with all 10 players
        - Dark background with structured layout
        - No minimap
        - Different layout from loading screen
        """
        thumb = img.resize((160, 90), Image.LANCZOS)
        pixels = list(thumb.getdata())
        pix = thumb.load()
        tw, th = 160, 90

        # Post-game header area — check for bright banner text
        header_region = ScreenRegions.get_pixel_region(ScreenRegions.POSTGAME_HEADER, tw, th)
        header_brightness = self._region_avg_brightness(pix, *header_region, tw, th)

        # Blue/gold for Victory, red for Defeat
        blue_gold_pixels = sum(1 for r, g, b in pixels
                               if (b > 150 and b > r) or (r > 180 and g > 150 and b < 100))
        victory_ratio = blue_gold_pixels / len(pixels)

        # Structured stats table in center
        stats_region = ScreenRegions.get_pixel_region(ScreenRegions.POSTGAME_STATS, tw, th)
        band_score = self._check_horizontal_banding(pix, tw, th,
                                                      y_start=int(th * 0.15),
                                                      y_end=int(th * 0.85),
                                                      expected_bands=10)

        # No minimap
        minimap_region = ScreenRegions.get_pixel_region(ScreenRegions.MINIMAP, tw, th)
        minimap_brightness = self._region_avg_brightness(pix, *minimap_region, tw, th)

        confidence = 0.0
        if header_brightness > 80:
            confidence += 0.20
        if victory_ratio > 0.03:
            confidence += 0.20
        if band_score > 0.3:
            confidence += 0.30
        if minimap_brightness < 50:  # No minimap
            confidence += 0.10

        return GameStateResult(
            state=GameState.POST_GAME_STATS,
            confidence=min(confidence, 1.0),
            phase=GamePhase.POST_GAME,
            coaching_action="game_review",
        )

    def _check_in_game(self, img: Image.Image, w: int, h: int) -> GameStateResult:
        """
        Detect active in-game state (laning, teamfighting, objectives).

        In-game always has:
        - Minimap in bottom-right
        - HUD bar at bottom (health, mana, abilities, items)
        - Game terrain (green/brown ground, structures)
        - Champion portraits at top

        Sub-classification:
        - LANING: calm, 1-2 champions visible, minion waves
        - TEAMFIGHT: 3+ champion health bars, lots of particles/effects
        - OBJECTIVES: near dragon/baron pit (minimap position analysis)
        """
        thumb = img.resize((320, 180), Image.LANCZOS)
        pix = thumb.load()
        tw, th = 320, 180

        # Signal 1: Minimap present (bright colored square in bottom-right)
        minimap_region = ScreenRegions.get_pixel_region(ScreenRegions.MINIMAP, tw, th)
        minimap_brightness = self._region_avg_brightness(pix, *minimap_region, tw, th)
        minimap_saturation = self._region_avg_saturation(pix, *minimap_region, tw, th)
        has_minimap = minimap_brightness > 35 and minimap_saturation > 0.10

        # Signal 2: HUD bar at bottom (ability icons, health bar)
        hud_region = ScreenRegions.get_pixel_region(ScreenRegions.PLAYER_HUD, tw, th)
        hud_brightness = self._region_avg_brightness(pix, *hud_region, tw, th)
        has_hud = hud_brightness > 25

        # Signal 3: Health bar (green/yellow/red gradient)
        health_region = ScreenRegions.get_pixel_region(ScreenRegions.HEALTH_BAR, tw, th)
        health_green = self._region_color_ratio(pix, *health_region, tw, th, "green")
        has_health = health_green > 0.05

        # Signal 4: Game terrain in center (not a UI panel)
        center_saturation = self._region_avg_saturation(
            pix, int(tw * 0.2), int(th * 0.2), int(tw * 0.7), int(th * 0.7), tw, th
        )

        confidence = 0.0
        if has_minimap:
            confidence += 0.35
        if has_hud:
            confidence += 0.25
        if has_health:
            confidence += 0.20
        if center_saturation > 0.12:
            confidence += 0.15

        # Determine sub-state
        state = GameState.IN_GAME_LANING  # Default
        phase = self._estimate_game_phase()

        return GameStateResult(
            state=state,
            confidence=min(confidence, 1.0),
            phase=phase,
            coaching_action="live_coaching",
        )

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _check_5x2_grid(self, pix, tw: int, th: int) -> float:
        """Check for 5+5 champion splash grid pattern (loading screen)."""
        slot_scores = []
        for row_y_start, row_y_end in [(0.08, 0.45), (0.55, 0.92)]:
            for col in range(5):
                x1 = int(tw * (0.01 + col * 0.195))
                x2 = int(tw * (0.01 + col * 0.195 + 0.17))
                y1 = int(th * row_y_start)
                y2 = int(th * row_y_end)
                x1, x2 = max(0, x1), min(tw - 1, x2)
                y1, y2 = max(0, y1), min(th - 1, y2)

                brightness = []
                for y in range(y1, y2, 2):
                    for x in range(x1, x2, 2):
                        try:
                            r, g, b = pix[x, y][:3]
                            brightness.append((r + g + b) / 3)
                        except (IndexError, TypeError):
                            pass

                if brightness:
                    avg = sum(brightness) / len(brightness)
                    var = sum((b - avg) ** 2 for b in brightness) / len(brightness)
                    if 30 < avg < 200 and var > 100:
                        slot_scores.append(1.0)
                    elif var > 30:
                        slot_scores.append(0.5)
                    else:
                        slot_scores.append(0.1)

        matched = sum(1 for s in slot_scores if s > 0.4)
        return min(matched / 8.0, 1.0)

    def _region_avg_brightness(self, pix, x1: int, y1: int, x2: int, y2: int,
                                tw: int, th: int) -> float:
        """Average brightness of a pixel region."""
        x1, x2 = max(0, x1), min(tw - 1, x2)
        y1, y2 = max(0, y1), min(th - 1, y2)
        vals = []
        for y in range(y1, y2, 2):
            for x in range(x1, x2, 2):
                try:
                    r, g, b = pix[x, y][:3]
                    vals.append((r + g + b) / 3)
                except (IndexError, TypeError):
                    pass
        return sum(vals) / len(vals) if vals else 0

    def _region_dark_ratio(self, pix, x1: int, y1: int, x2: int, y2: int,
                            tw: int, th: int) -> float:
        """Ratio of dark pixels in a region."""
        x1, x2 = max(0, x1), min(tw - 1, x2)
        y1, y2 = max(0, y1), min(th - 1, y2)
        total = 0
        dark = 0
        for y in range(y1, y2, 2):
            for x in range(x1, x2, 2):
                try:
                    r, g, b = pix[x, y][:3]
                    total += 1
                    if r < 60 and g < 60 and b < 60:
                        dark += 1
                except (IndexError, TypeError):
                    pass
        return dark / total if total else 0

    def _region_avg_saturation(self, pix, x1: int, y1: int, x2: int, y2: int,
                                tw: int, th: int) -> float:
        """Average color saturation of a region."""
        x1, x2 = max(0, x1), min(tw - 1, x2)
        y1, y2 = max(0, y1), min(th - 1, y2)
        sats = []
        for y in range(y1, y2, 2):
            for x in range(x1, x2, 2):
                try:
                    r, g, b = pix[x, y][:3]
                    max_c = max(r, g, b)
                    min_c = min(r, g, b)
                    sats.append((max_c - min_c) / max_c if max_c > 0 else 0)
                except (IndexError, TypeError):
                    pass
        return sum(sats) / len(sats) if sats else 0

    def _region_warm_ratio(self, pix, x1: int, y1: int, x2: int, y2: int,
                            tw: int, th: int) -> float:
        """Ratio of warm-colored (gold/brown/orange) pixels."""
        x1, x2 = max(0, x1), min(tw - 1, x2)
        y1, y2 = max(0, y1), min(th - 1, y2)
        total = 0
        warm = 0
        for y in range(y1, y2, 3):
            for x in range(x1, x2, 3):
                try:
                    r, g, b = pix[x, y][:3]
                    total += 1
                    if r > 100 and g > 60 and b < g and r > b * 1.3:
                        warm += 1
                except (IndexError, TypeError):
                    pass
        return warm / total if total else 0

    def _region_color_ratio(self, pix, x1: int, y1: int, x2: int, y2: int,
                             tw: int, th: int, color: str) -> float:
        """Ratio of pixels matching a named color."""
        x1, x2 = max(0, x1), min(tw - 1, x2)
        y1, y2 = max(0, y1), min(th - 1, y2)
        total = 0
        matched = 0
        for y in range(y1, y2, 3):
            for x in range(x1, x2, 3):
                try:
                    r, g, b = pix[x, y][:3]
                    total += 1
                    if color == "green" and g > 80 and g > r * 1.2 and g > b * 1.2:
                        matched += 1
                    elif color == "yellow" and r > 150 and g > 130 and b < 80:
                        matched += 1
                    elif color == "red" and r > 120 and r > g * 1.5 and r > b * 1.5:
                        matched += 1
                    elif color == "blue" and b > 120 and b > r * 1.3 and b > g * 1.1:
                        matched += 1
                except (IndexError, TypeError):
                    pass
        return matched / total if total else 0

    def _check_horizontal_banding(self, pix, tw: int, th: int,
                                    y_start: int, y_end: int,
                                    expected_bands: int) -> float:
        """Check for horizontal brightness banding (scoreboard rows)."""
        row_brightnesses = []
        for y in range(y_start, y_end, 2):
            row_vals = []
            for x in range(int(tw * 0.15), int(tw * 0.85), 4):
                try:
                    r, g, b = pix[x, y][:3]
                    row_vals.append((r + g + b) / 3)
                except (IndexError, TypeError):
                    pass
            if row_vals:
                row_brightnesses.append(sum(row_vals) / len(row_vals))

        if len(row_brightnesses) < 10:
            return 0.0

        # Count transitions (bright ↔ dark) — scoreboard has alternating rows
        transitions = 0
        threshold = 15  # brightness change to count as transition
        for i in range(1, len(row_brightnesses)):
            if abs(row_brightnesses[i] - row_brightnesses[i - 1]) > threshold:
                transitions += 1

        # Expect roughly expected_bands * 2 transitions (top + bottom of each row)
        expected_transitions = expected_bands * 1.5
        return min(transitions / expected_transitions, 1.0)

    def _estimate_game_phase(self) -> GamePhase:
        """Estimate game phase from temporal context."""
        if self._game_start_time is None:
            # First in-game detection — set game start
            self._game_start_time = time.time()
            return GamePhase.EARLY_LANING

        elapsed_minutes = (time.time() - self._game_start_time) / 60

        if elapsed_minutes < 8:
            return GamePhase.EARLY_LANING
        elif elapsed_minutes < 14:
            return GamePhase.MID_LANING
        elif elapsed_minutes < 25:
            return GamePhase.MID_GAME
        else:
            return GamePhase.LATE_GAME

    def _apply_temporal_context(self, result: GameStateResult, now: float) -> GameStateResult:
        """Refine detection using temporal context (state transitions)."""
        # If we just detected loading screen and now see in-game → game started
        if (self._current_state == GameState.LOADING_SCREEN and
                result.state == GameState.IN_GAME_LANING):
            self._game_start_time = now
            result.phase = GamePhase.EARLY_LANING

        # Track state duration
        last_change = self._state_history[-1][0] if self._state_history else now
        if self._state_history and self._state_history[-1][1] == result.state:
            result.state_duration_seconds = now - last_change

        return result

    def _determine_coaching_action(self, result: GameStateResult) -> str:
        """Determine what coaching to provide based on detected state."""
        actions = {
            GameState.LOADING_SCREEN: "full_pregame_plan",
            GameState.TAB_SCOREBOARD: "item_check_and_build_adjust",
            GameState.SHOP_OPEN: "buy_recommendation",
            GameState.DEATH_SCREEN: "death_review_and_recovery",
            GameState.POST_GAME_STATS: "game_review",
            GameState.IN_GAME_LANING: "lane_coaching",
            GameState.IN_GAME_TEAMFIGHT: "teamfight_coaching",
            GameState.IN_GAME_OBJECTIVES: "objective_coaching",
            GameState.CHAMPION_SELECT: "draft_advice",
            GameState.NOT_LOL: "none",
        }
        return actions.get(result.state, "none")


# =============================================================================
# GAME SESSION — Accumulated knowledge from this game
# =============================================================================

class GameSession:
    """
    Tracks accumulated knowledge across multiple screenshots in a single game.

    As the player takes screenshots throughout the game, we build up a picture of:
    - Both team compositions (from loading screen)
    - Item builds over time (from tab/shop screenshots)
    - KDA progression (from tab screenshots)
    - Deaths and circumstances (from death screens)
    - Game phase transitions
    - Dragon/Baron takes
    """

    def __init__(self):
        self.game_id: Optional[str] = None
        self.start_time: Optional[float] = None

        # Set during loading screen
        self.blue_team: List[str] = []
        self.red_team: List[str] = []
        self.user_champion: str = ""
        self.user_role: str = ""
        self.user_team: str = ""  # "blue" or "red"
        self.lane_opponent: str = ""
        self.role_assignments: Dict[str, Dict[str, str]] = {}

        # Updated throughout the game
        self.user_items: List[str] = []             # Current items
        self.user_items_history: List[Dict] = []    # Timestamped item snapshots
        self.user_gold: int = 0
        self.user_cs: int = 0
        self.user_level: int = 1
        self.user_kda: Tuple[int, int, int] = (0, 0, 0)

        # Enemy tracking
        self.enemy_items: Dict[str, List[str]] = {}     # champion → items
        self.enemy_levels: Dict[str, int] = {}
        self.enemy_kda: Dict[str, Tuple[int, int, int]] = {}

        # Events
        self.deaths: List[Dict] = []                    # Each death with timestamp + context
        self.objectives_taken: List[Dict] = []          # Dragon, Baron, Herald
        self.screenshots_analyzed: int = 0
        self.coaching_advice_given: List[Dict] = []     # History of advice

        # Build plan (set during loading, can be adjusted)
        self.original_build_plan: Dict = {}
        self.adjusted_build_plan: Dict = {}
        self.build_adjustments: List[Dict] = []         # Why we changed the plan

    def update_from_loading(self, coaching_package: Dict):
        """Initialize session from the loading screen coaching package."""
        import time as _time
        self.start_time = _time.time()
        self.game_id = f"game_{int(self.start_time)}"

        teams = coaching_package.get("teams", {})
        self.blue_team = teams.get("blue", [])
        self.red_team = teams.get("red", [])
        self.role_assignments = teams.get("role_inference", {})

        user = coaching_package.get("user", {})
        self.user_champion = user.get("champion", "")
        self.user_role = user.get("role", "")
        self.lane_opponent = user.get("lane_opponent", "")
        self.user_team = "blue" if self.user_champion in self.blue_team else "red"

        self.original_build_plan = coaching_package.get("build", {})
        self.adjusted_build_plan = dict(self.original_build_plan)

    def update_from_tab(self, tab_analysis: Dict):
        """Update session with data extracted from TAB scoreboard."""
        if "user_items" in tab_analysis:
            self.user_items = tab_analysis["user_items"]
            self.user_items_history.append({
                "time": time.time(),
                "items": list(self.user_items),
            })
        if "user_cs" in tab_analysis:
            self.user_cs = tab_analysis["user_cs"]
        if "user_kda" in tab_analysis:
            self.user_kda = tab_analysis["user_kda"]
        if "enemy_items" in tab_analysis:
            self.enemy_items.update(tab_analysis["enemy_items"])

    def update_from_death(self, death_analysis: Dict):
        """Record a death event."""
        self.deaths.append({
            "time": time.time(),
            "game_time": death_analysis.get("game_time"),
            "killed_by": death_analysis.get("killed_by"),
            "damage_breakdown": death_analysis.get("damage_breakdown"),
            "advice": death_analysis.get("advice"),
        })

    def get_context_for_coaching(self) -> Dict:
        """Package current session knowledge for coaching agents."""
        return {
            "game_id": self.game_id,
            "elapsed_minutes": (time.time() - self.start_time) / 60 if self.start_time else 0,
            "user": {
                "champion": self.user_champion,
                "role": self.user_role,
                "team": self.user_team,
                "lane_opponent": self.lane_opponent,
                "current_items": self.user_items,
                "cs": self.user_cs,
                "kda": self.user_kda,
                "level": self.user_level,
                "deaths_this_game": len(self.deaths),
            },
            "teams": {
                "blue": self.blue_team,
                "red": self.red_team,
                "roles": self.role_assignments,
            },
            "enemy": {
                "items": self.enemy_items,
                "levels": self.enemy_levels,
            },
            "build_plan": self.adjusted_build_plan,
            "death_history": self.deaths[-3:],  # Last 3 deaths for context
        }

    def should_adjust_build(self) -> Tuple[bool, str]:
        """
        Check if the build plan should be adjusted based on game state.

        Triggers:
        - Enemy laner building armor → switch to armor pen
        - Team is behind → build defensive
        - Specific enemy is fed → build counter items
        """
        reasons = []

        # Check if enemy laner is building specific counters
        if self.lane_opponent and self.lane_opponent in self.enemy_items:
            enemy_items = self.enemy_items[self.lane_opponent]
            enemy_items_lower = [i.lower() for i in enemy_items]

            # Enemy building armor
            armor_items = ["plated steelcaps", "warden's mail", "bramble vest",
                          "frozen heart", "thornmail", "randuin's omen"]
            if any(item in enemy_items_lower for item in armor_items):
                reasons.append("enemy_building_armor")

            # Enemy building MR
            mr_items = ["mercury's treads", "spectre's cowl", "hexdrinker",
                       "maw of malmortius", "spirit visage", "force of nature"]
            if any(item in enemy_items_lower for item in mr_items):
                reasons.append("enemy_building_mr")

        # Check KDA — if dying a lot, suggest defensive
        kills, deaths, assists = self.user_kda
        if deaths >= 3 and deaths > kills + assists:
            reasons.append("dying_frequently")

        return (len(reasons) > 0, ", ".join(reasons))
