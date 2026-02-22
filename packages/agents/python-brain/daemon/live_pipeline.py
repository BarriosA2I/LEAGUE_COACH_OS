"""
================================================================================
LEAGUE COACH OS — LIVE COACHING PIPELINE
================================================================================
The master pipeline that handles PrintScreen at ANY point in the game.

Every screenshot flows through:
  1. GameStateDetector → what are we looking at?
  2. LiveCoachingEngine → extract data + generate advice
  3. Session tracking → accumulate knowledge across screenshots
  4. Overlay rendering → show coaching in-game

Game Flow:
  Loading Screen → full pregame plan (existing 9-agent swarm)
  TAB pressed → "enemy building armor, switch to penetration"
  Shop open → "buy Serrated Dirk (1100g) → you have 1250g"
  In-lane → "Darius Q is down (9s CD) → go in NOW with your E"
  You die → "You got hooked under tower. Stay behind minions vs Blitz"
  Teamfight → "Focus Jinx, avoid Leona ult, flash her Zenith Blade"
  Post-game → "3 deaths to ganks — ward more, play safer when jungler MIA"

Author: Barrios A2I | Version: 2.0.0
================================================================================
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("league_coach.pipeline")

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# =============================================================================
# PIPELINE CONFIGURATION
# =============================================================================

@dataclass
class LivePipelineConfig:
    """Configuration for the live coaching pipeline."""
    # API
    anthropic_api_key: str = ""
    vision_model: str = "claude-sonnet-4-20250514"      # Vision extraction
    coaching_model: str = "claude-haiku-4-5-20251001"    # Fast coaching advice

    # Detection thresholds
    game_state_confidence: float = 0.65
    loading_screen_confidence: float = 0.70

    # Performance
    max_coaching_time: float = 8.0       # Max seconds for full coaching response
    vision_timeout: float = 10.0          # Max seconds for vision extraction
    cooldown_between_shots: float = 3.0   # Min seconds between processing

    # Session
    save_screenshots: bool = True
    save_coaching: bool = True
    output_dir: str = "fixtures/coaching_outputs"
    screenshot_dir: str = "fixtures/screenshots"

    # Overlay
    overlay_duration: float = 20.0        # How long overlay stays (seconds)
    overlay_opacity: float = 0.92

    @classmethod
    def from_env(cls) -> "LivePipelineConfig":
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            vision_model=os.getenv("VISION_MODEL", "claude-sonnet-4-20250514"),
            coaching_model=os.getenv("COACHING_MODEL", "claude-haiku-4-5-20251001"),
            overlay_duration=float(os.getenv("OVERLAY_DURATION", "20")),
            overlay_opacity=float(os.getenv("OVERLAY_OPACITY", "0.92")),
        )


# =============================================================================
# COACHING RESULT — unified output for the overlay
# =============================================================================

@dataclass
class CoachingResult:
    """Unified coaching result that the overlay can render."""
    # Metadata
    game_state: str = "unknown"
    game_phase: str = ""
    timestamp: float = 0.0
    processing_time: float = 0.0

    # Core coaching (always present)
    headline: str = ""                          # Big text at top
    next_30_seconds: List[str] = field(default_factory=list)  # Top 3 actions

    # Build advice (present when relevant)
    buy_now: List[Dict] = field(default_factory=list)        # [{item, gold, reason, priority}]
    full_build: List[str] = field(default_factory=list)       # Full build path
    build_changed: bool = False
    build_change_reason: str = ""

    # Laner advice — solo lane
    laner_name: str = ""
    trade_pattern: str = ""
    avoid: str = ""
    punish_when: str = ""
    key_cooldowns: List[str] = field(default_factory=list)
    kill_window: str = ""
    wave_management: str = ""

    # Laner advice — bot lane (2 enemies)
    is_botlane: bool = False
    enemy_adc: str = ""
    enemy_adc_threat: str = ""
    enemy_adc_dodge: str = ""
    enemy_adc_punish: str = ""
    enemy_support: str = ""
    enemy_support_threat: str = ""
    enemy_support_dodge: str = ""
    enemy_support_punish: str = ""
    their_kill_combo: str = ""
    your_win_condition: str = ""
    level_2_plan: str = ""
    bush_control: str = ""
    gank_setup: str = ""

    # Death review
    death_reason: str = ""
    death_fix: str = ""
    death_positioning: str = ""
    death_recovery: str = ""
    death_count: int = 0

    # Teamfight
    teamfight_role: str = ""
    focus_target: str = ""
    biggest_threat: str = ""
    positioning: str = ""

    # Warnings
    warnings: List[str] = field(default_factory=list)

    # Raw data for debugging
    raw_extracted: Dict = field(default_factory=dict)
    raw_coaching: Dict = field(default_factory=dict)


# =============================================================================
# LIVE COACHING PIPELINE
# =============================================================================

class LiveCoachingPipeline:
    """
    Master pipeline that processes every PrintScreen throughout the entire game.

    Usage:
        pipeline = LiveCoachingPipeline(config)
        await pipeline.initialize()

        # Called by ClipboardWatcher or HotkeyListener on every PrintScreen
        result = await pipeline.process_screenshot(pil_image, mode="FAST")

        # Result is a CoachingResult ready for the overlay
        overlay.show(result)

    The pipeline maintains a GameSession that tracks:
    - Team compositions (from loading screen)
    - Item builds over time (from tab screenshots)
    - Deaths and patterns
    - Game phase progression
    - Build adjustments
    """

    def __init__(self, config: Optional[LivePipelineConfig] = None):
        self.config = config or LivePipelineConfig.from_env()
        self._last_process_time = 0.0
        self._initialized = False

        # Components (initialized in initialize())
        self.state_detector = None
        self.coaching_engine = None
        self.swarm = None  # Existing 9-agent swarm for loading screen

        # Callbacks
        self._on_coaching_ready: Optional[Callable] = None
        self._on_state_change: Optional[Callable] = None

    async def initialize(self):
        """Initialize all pipeline components."""
        # Game state detector
        from daemon.game_state_detector import GameStateDetector
        self.state_detector = GameStateDetector()

        # Live coaching engine
        from agents.live_coaching_agents import LiveCoachingEngine
        client = None
        if self.config.anthropic_api_key:
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=self.config.anthropic_api_key)
            except ImportError:
                logger.warning("anthropic package not installed")

        self.coaching_engine = LiveCoachingEngine(
            anthropic_client=client,
            model=self.config.vision_model,
        )

        # Existing swarm for loading screen (optional)
        try:
            from orchestrator.swarm import LeagueCoachingSwarm
            self.swarm = LeagueCoachingSwarm()
        except Exception as e:
            logger.warning(f"Could not load coaching swarm: {e}")

        # Create output directories
        Path(self.config.output_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.screenshot_dir).mkdir(parents=True, exist_ok=True)

        self._initialized = True
        logger.info("✅ Live coaching pipeline initialized")

    def on_coaching_ready(self, callback: Callable):
        """Register callback for when coaching is ready."""
        self._on_coaching_ready = callback

    def on_state_change(self, callback: Callable):
        """Register callback for game state changes."""
        self._on_state_change = callback

    async def process_screenshot(self, image: Image.Image,
                                   mode: str = "FAST") -> CoachingResult:
        """
        Process a screenshot and return coaching advice.

        This is the main entry point called on every PrintScreen.
        The pipeline:
        1. Detects game state (loading screen? tab? shop? in-game? death?)
        2. Routes to the appropriate coaching engine
        3. Returns a unified CoachingResult for the overlay

        Args:
            image: PIL Image from clipboard
            mode: "FAST" (<8s) or "FULL" (<20s, more detailed)

        Returns:
            CoachingResult ready for overlay rendering
        """
        if not self._initialized:
            await self.initialize()

        start = time.time()

        # Cooldown check
        elapsed_since_last = start - self._last_process_time
        if elapsed_since_last < self.config.cooldown_between_shots:
            logger.info(f"Cooldown: {elapsed_since_last:.1f}s < {self.config.cooldown_between_shots}s")
            return CoachingResult(
                headline="⏳ Processing previous screenshot — wait a moment",
                game_state="cooldown",
            )

        self._last_process_time = start

        try:
            # Step 1: Detect game state
            from daemon.game_state_detector import GameState
            state_result = self.state_detector.detect(image)

            logger.info(
                f"📸 Detected: {state_result.state.value} "
                f"(confidence: {state_result.confidence:.2f})"
            )

            # Notify state change
            if (self._on_state_change and
                    state_result.previous_state != state_result.state):
                self._on_state_change(state_result)

            # Reject non-LoL screenshots
            if (state_result.state == GameState.NOT_LOL or
                    state_result.confidence < self.config.game_state_confidence):
                return CoachingResult(
                    headline="Not a League screenshot — take a screenshot in-game!",
                    game_state="not_lol",
                    warnings=["Tip: Press TAB then PrintScreen for best item/build analysis"],
                )

            # Step 2: Encode image for Vision API
            image_b64 = self._encode_image(image)

            # Step 3: Save screenshot
            if self.config.save_screenshots:
                self._save_screenshot(image, state_result.state.value)

            # Step 4: Route to coaching
            if state_result.state == GameState.LOADING_SCREEN:
                result = await self._handle_loading_screen(image, image_b64, mode)
            else:
                result = await self._handle_live_coaching(
                    image_b64, state_result, mode
                )

            result.processing_time = time.time() - start
            result.timestamp = start

            # Step 5: Save coaching output
            if self.config.save_coaching:
                self._save_coaching(result)

            # Step 6: Notify
            if self._on_coaching_ready:
                self._on_coaching_ready(result)

            logger.info(
                f"✅ Coaching delivered in {result.processing_time:.1f}s | "
                f"State: {result.game_state} | Headline: {result.headline[:60]}"
            )

            return result

        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            return CoachingResult(
                headline=f"Error processing screenshot: {str(e)[:80]}",
                game_state="error",
                processing_time=time.time() - start,
            )

    # =========================================================================
    # ROUTING HANDLERS
    # =========================================================================

    async def _handle_loading_screen(self, image: Image.Image,
                                       image_b64: str,
                                       mode: str) -> CoachingResult:
        """
        Handle loading screen → run full 9-agent pre-game coaching swarm.

        This is the existing flow that produces the complete GameCoachPackage
        with build, runes, lane plan, teamfight plan, etc.
        """
        logger.info("🏁 Loading screen detected — running full pre-game plan")

        result = CoachingResult(game_state="loading_screen", game_phase="pre_game")

        if self.swarm:
            try:
                # Run existing swarm
                package = await asyncio.wait_for(
                    self.swarm.run(image_b64=image_b64, mode=mode),
                    timeout=30.0
                )

                # Initialize game session from the full coaching package
                if hasattr(package, 'dict'):
                    pkg_dict = package.dict()
                else:
                    pkg_dict = package if isinstance(package, dict) else {}

                self.coaching_engine.session.update_from_loading(pkg_dict)

                # Convert to CoachingResult
                result.headline = f"Pre-game plan ready! Playing {pkg_dict.get('user', {}).get('champion', '?')} {pkg_dict.get('user', {}).get('role', '?')}"

                build = pkg_dict.get("build", {})
                result.full_build = build.get("items", [])

                laner = pkg_dict.get("user", {}).get("lane_opponent", "")
                if laner:
                    result.laner_name = laner

                result.next_30_seconds = [
                    f"Lane vs {laner}" if laner else "Prepare for lane",
                    f"First item: {result.full_build[0]}" if result.full_build else "Follow build path",
                    "GL HF!",
                ]

                result.raw_coaching = pkg_dict

            except asyncio.TimeoutError:
                result.headline = "Pre-game plan timed out — using quick analysis"
                result.warnings.append("Full analysis took too long, using simplified plan")
            except Exception as e:
                logger.error(f"Swarm failed: {e}")
                result.headline = "Pre-game analysis error — check API key"
                result.warnings.append(str(e))
        else:
            # No swarm available — use live coaching engine for basic extraction
            coaching_pkg = await self.coaching_engine.coach_from_screenshot(
                image_b64=image_b64,
                game_state="loading_screen",
            )
            result.headline = coaching_pkg.headline
            result.next_30_seconds = coaching_pkg.next_30_seconds

        return result

    async def _handle_live_coaching(self, image_b64: str,
                                      state_result: Any,
                                      mode: str) -> CoachingResult:
        """
        Handle any mid-game screenshot — route to appropriate coaching agent.
        """
        coaching_pkg = await asyncio.wait_for(
            self.coaching_engine.coach_from_screenshot(
                image_b64=image_b64,
                game_state=state_result.state.value,
                game_phase=state_result.phase.value if state_result.phase else "",
                session_context=self.coaching_engine.session.get_context_for_coaching(),
            ),
            timeout=self.config.max_coaching_time,
        )

        # Convert LiveCoachingPackage → CoachingResult
        result = CoachingResult(
            game_state=state_result.state.value,
            game_phase=coaching_pkg.game_phase,
            headline=coaching_pkg.headline,
            next_30_seconds=coaching_pkg.next_30_seconds,
            warnings=coaching_pkg.warnings,
        )

        # Build advice
        if coaching_pkg.buy_now:
            result.buy_now = [
                {
                    "item": item.item_name,
                    "gold": item.gold_cost,
                    "reason": item.reason,
                    "priority": item.priority,
                }
                for item in coaching_pkg.buy_now
            ]
        result.full_build = coaching_pkg.full_build_path
        result.build_changed = bool(coaching_pkg.build_adjustment_reason)
        result.build_change_reason = coaching_pkg.build_adjustment_reason

        # Solo lane matchup
        if coaching_pkg.laner_matchup:
            lm = coaching_pkg.laner_matchup
            result.laner_name = lm.champion
            result.trade_pattern = lm.trade_pattern
            result.avoid = lm.avoid_when
            result.punish_when = lm.punish_when
            result.key_cooldowns = lm.key_cooldowns
            result.kill_window = lm.kill_window
            result.wave_management = getattr(coaching_pkg, '_wave_management', '')

        # Bot lane matchup
        if coaching_pkg.bot_lane_matchup:
            bm = coaching_pkg.bot_lane_matchup
            result.is_botlane = True
            result.enemy_adc = bm.enemy_adc.champion
            result.enemy_adc_threat = bm.enemy_adc.threat_level
            result.enemy_adc_dodge = bm.enemy_adc.avoid_when
            result.enemy_adc_punish = bm.enemy_adc.punish_when
            result.enemy_support = bm.enemy_support.champion
            result.enemy_support_threat = bm.enemy_support.threat_level
            result.enemy_support_dodge = bm.enemy_support.avoid_when
            result.enemy_support_punish = bm.enemy_support.punish_when
            result.their_kill_combo = bm.their_kill_combo
            result.your_win_condition = bm.your_win_condition
            result.level_2_plan = bm.level_2_plan
            result.bush_control = bm.bush_control
            result.gank_setup = bm.gank_setup

        # Death review
        if coaching_pkg.death_review:
            dr = coaching_pkg.death_review
            result.death_reason = dr.death_reason
            result.death_fix = dr.what_to_change
            result.death_positioning = dr.positioning_fix
            result.death_recovery = dr.tip
            result.death_count = len(self.coaching_engine.session.deaths)

        # Teamfight
        result.teamfight_role = coaching_pkg.teamfight_priority
        result.focus_target = coaching_pkg.teamfight_priority
        result.positioning = coaching_pkg.positioning

        return result

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def _encode_image(self, image: Image.Image) -> str:
        """Encode PIL image to base64."""
        buf = io.BytesIO()
        image.save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _save_screenshot(self, image: Image.Image, state: str):
        """Save screenshot to disk."""
        try:
            ts = int(time.time())
            path = Path(self.config.screenshot_dir) / f"{state}_{ts}.png"
            image.save(str(path))
            logger.debug(f"Saved screenshot: {path}")
        except Exception as e:
            logger.warning(f"Failed to save screenshot: {e}")

    def _save_coaching(self, result: CoachingResult):
        """Save coaching result to JSON."""
        try:
            ts = int(time.time())
            path = Path(self.config.output_dir) / f"{result.game_state}_{ts}.json"
            # Convert dataclass to dict
            import dataclasses
            data = dataclasses.asdict(result)
            with open(str(path), "w") as f:
                json.dump(data, f, indent=2, default=str)
            logger.debug(f"Saved coaching: {path}")
        except Exception as e:
            logger.warning(f"Failed to save coaching: {e}")

    def get_session_summary(self) -> Dict:
        """Get a summary of the current game session."""
        if not self.coaching_engine:
            return {"status": "not_initialized"}

        s = self.coaching_engine.session
        return {
            "game_id": s.game_id,
            "user_champion": s.user_champion,
            "user_role": s.user_role,
            "lane_opponent": s.lane_opponent,
            "blue_team": s.blue_team,
            "red_team": s.red_team,
            "current_items": s.user_items,
            "kda": s.user_kda,
            "cs": s.user_cs,
            "deaths": len(s.deaths),
            "screenshots_analyzed": s.screenshots_analyzed,
            "build_adjustments": len(s.build_adjustments),
        }
