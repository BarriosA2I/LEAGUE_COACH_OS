"""
================================================================================
LEAGUE COACH OS — LIVE COACHING TESTS
================================================================================
Tests the complete live coaching pipeline:
  • Game state detection (all states)
  • Session tracking across screenshots
  • Coaching output generation per state
  • Build adjustment triggers
  • Bot lane dual-threat detection
  • Overlay rendering (console)

Run: python tests/test_live_coaching.py
================================================================================
"""
import asyncio
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image
import numpy as np


def create_test_image(width: int, height: int, pattern: str = "loading") -> Image.Image:
    """Create synthetic test images for each game state."""
    arr = np.zeros((height, width, 3), dtype=np.uint8)

    if pattern == "loading":
        # Loading screen: dark background + 10 bright champion rectangles
        arr[:, :] = [20, 20, 30]  # Dark bg
        for i in range(5):
            x1 = int(width * (0.02 + i * 0.195))
            x2 = int(width * (0.02 + i * 0.195 + 0.17))
            # Blue team (top row)
            arr[int(height * 0.08):int(height * 0.45), x1:x2] = [
                80 + i * 20, 60 + i * 15, 100 + i * 10
            ]
            # Red team (bottom row)
            arr[int(height * 0.55):int(height * 0.92), x1:x2] = [
                100 + i * 15, 50 + i * 10, 60 + i * 20
            ]

    elif pattern == "in_game":
        # In-game: colorful terrain + minimap (bottom-right) + HUD (bottom-center)
        arr[:, :] = [40, 60, 30]  # Green-ish terrain

        # Minimap (bottom-right, bright)
        mm_x1 = int(width * 0.78)
        mm_y1 = int(height * 0.74)
        arr[mm_y1:, mm_x1:] = [60, 90, 50]  # Minimap green
        # Add blue/red dots on minimap
        arr[mm_y1 + 10:mm_y1 + 15, mm_x1 + 20:mm_x1 + 25] = [50, 50, 200]
        arr[mm_y1 + 30:mm_y1 + 35, mm_x1 + 40:mm_x1 + 45] = [200, 50, 50]

        # HUD bar (bottom-center)
        hud_y = int(height * 0.88)
        arr[hud_y:, int(width * 0.30):int(width * 0.70)] = [50, 50, 70]

        # Health bar (green)
        hp_y = int(height * 0.90)
        arr[hp_y:hp_y + 8, int(width * 0.38):int(width * 0.55)] = [30, 180, 50]

    elif pattern == "tab_scoreboard":
        # Tab: dark overlay with horizontal banding rows
        arr[:, :] = [25, 25, 35]  # Dark overlay

        # Minimap still visible
        mm_x1 = int(width * 0.78)
        mm_y1 = int(height * 0.74)
        arr[mm_y1:, mm_x1:] = [60, 90, 50]

        # 10 player rows (alternating brightness)
        for row in range(10):
            y1 = int(height * (0.12 + row * 0.065))
            y2 = y1 + int(height * 0.05)
            brightness = 60 if row % 2 == 0 else 40
            arr[y1:y2, int(width * 0.12):int(width * 0.88)] = [brightness, brightness, brightness + 10]

    elif pattern == "shop":
        # Shop: warm-colored panel on right side + minimap
        arr[:, :] = [30, 35, 25]  # Game background

        # Shop panel (warm colors)
        arr[int(height * 0.05):int(height * 0.90),
            int(width * 0.20):int(width * 0.85)] = [80, 65, 40]  # Warm brown

        # Gold display (yellow)
        arr[int(height * 0.06):int(height * 0.10),
            int(width * 0.72):int(width * 0.82)] = [200, 180, 40]

        # Minimap
        mm_x1 = int(width * 0.78)
        mm_y1 = int(height * 0.74)
        arr[mm_y1:, mm_x1:] = [60, 90, 50]

    elif pattern == "death":
        # Death screen: desaturated gray overlay
        arr[:, :] = [70, 70, 72]  # Gray (low saturation)

        # Some structure (game terrain underneath but grayed out)
        for y in range(0, height, 20):
            brightness = 60 + (y % 40)
            arr[y:y + 10, :] = [brightness, brightness, brightness + 2]

    elif pattern == "desktop":
        # Desktop (NOT LoL) — uniform light colors, no minimap/HUD patterns
        arr[:, :] = [200, 200, 210]  # Light gray desktop
        arr[int(height * 0.95):, :] = [40, 40, 50]  # Dark taskbar
        # White window covering most of screen (breaks minimap/HUD detection)
        arr[30:int(height * 0.9), 50:width - 50] = [245, 245, 245]
        # Title bar
        arr[30:60, 50:width - 50] = [220, 220, 230]

    elif pattern == "post_game":
        # Post-game: dark bg + bright header + stats table
        arr[:, :] = [15, 15, 25]

        # Victory/Defeat banner (bright header)
        arr[0:int(height * 0.08), :] = [100, 140, 200]

        # Stats table rows
        for row in range(10):
            y1 = int(height * (0.15 + row * 0.065))
            y2 = y1 + int(height * 0.05)
            brightness = 55 if row % 2 == 0 else 35
            arr[y1:y2, int(width * 0.08):int(width * 0.92)] = [brightness, brightness, brightness]

    return Image.fromarray(arr)


# =============================================================================
# TESTS
# =============================================================================

def test_game_state_detection_all_states():
    """Test that the detector correctly identifies all game states."""
    from daemon.game_state_detector import GameStateDetector, GameState

    detector = GameStateDetector()

    test_cases = [
        ("loading", GameState.LOADING_SCREEN, 0.65),
        ("in_game", GameState.IN_GAME_LANING, 0.60),
        ("tab_scoreboard", GameState.TAB_SCOREBOARD, 0.50),
        ("death", GameState.DEATH_SCREEN, 0.50),
        ("desktop", GameState.NOT_LOL, 0.0),  # Should be low confidence for all LoL states
    ]

    passed = 0
    for pattern, expected_state, min_confidence in test_cases:
        img = create_test_image(1920, 1080, pattern)
        result = detector.detect(img)

        # For NOT_LOL, we check that no LoL state got high confidence
        if expected_state == GameState.NOT_LOL:
            is_correct = result.confidence < 0.65 or result.state == GameState.NOT_LOL
        else:
            is_correct = result.state == expected_state and result.confidence >= min_confidence

        status = "✅" if is_correct else "❌"
        print(
            f"  {status} {pattern}: detected={result.state.value} "
            f"(conf={result.confidence:.2f}) expected={expected_state.value}"
        )
        if is_correct:
            passed += 1

    return passed, len(test_cases)


def test_game_state_temporal_tracking():
    """Test that state transitions are tracked correctly."""
    from daemon.game_state_detector import GameStateDetector, GameState

    detector = GameStateDetector()

    # Simulate game flow: loading → in-game → tab → in-game → death
    flow = ["loading", "in_game", "tab_scoreboard", "in_game", "death"]
    states = []

    for pattern in flow:
        img = create_test_image(1920, 1080, pattern)
        result = detector.detect(img)
        states.append(result)

    # Check that previous_state tracking works
    if len(states) >= 2:
        has_prev = states[1].previous_state is not None
        print(f"  {'✅' if has_prev else '❌'} Previous state tracking: {states[1].previous_state}")
    else:
        has_prev = False

    # Check game phase estimation
    has_phase = any(s.phase is not None for s in states)
    print(f"  {'✅' if has_phase else '❌'} Game phase estimation present")

    return (1 if has_prev else 0) + (1 if has_phase else 0), 2


def test_game_session_tracking():
    """Test GameSession accumulates data across screenshots."""
    from daemon.game_state_detector import GameSession

    session = GameSession()

    # Initialize from loading screen
    session.update_from_loading({
        "teams": {
            "blue": ["Darius", "LeeSin", "Ahri", "Jinx", "Thresh"],
            "red": ["Garen", "Elise", "Zed", "Caitlyn", "Lulu"],
            "role_inference": {
                "blue": {"Darius": "Top", "LeeSin": "Jungle", "Ahri": "Mid",
                         "Jinx": "ADC", "Thresh": "Support"},
                "red": {"Garen": "Top", "Elise": "Jungle", "Zed": "Mid",
                        "Caitlyn": "ADC", "Lulu": "Support"},
            }
        },
        "user": {"champion": "Darius", "role": "Top", "lane_opponent": "Garen"},
        "build": {"items": ["Trinity Force", "Sterak's Gage", "Dead Man's Plate"]},
    })

    checks = [
        ("game_id set", session.game_id is not None),
        ("blue team", len(session.blue_team) == 5),
        ("red team", len(session.red_team) == 5),
        ("user champion", session.user_champion == "Darius"),
        ("user role", session.user_role == "Top"),
        ("lane opponent", session.lane_opponent == "Garen"),
        ("original build", len(session.original_build_plan) > 0),
    ]

    # Update from tab screenshot
    session.update_from_tab({
        "user_items": ["Phage", "Long Sword"],
        "user_cs": 85,
        "user_kda": (2, 1, 0),
        "enemy_items": {"Garen": ["Berserker's Greaves", "Dagger"]},
    })

    checks.append(("items tracked", session.user_items == ["Phage", "Long Sword"]))
    checks.append(("CS tracked", session.user_cs == 85))
    checks.append(("KDA tracked", session.user_kda == (2, 1, 0)))
    checks.append(("enemy items tracked", "Garen" in session.enemy_items))

    # Update from death
    session.update_from_death({"killed_by": "Elise", "advice": "Ward river"})
    checks.append(("death recorded", len(session.deaths) == 1))

    # Check context generation
    ctx = session.get_context_for_coaching()
    checks.append(("context has user", "user" in ctx))
    checks.append(("context has teams", "teams" in ctx))
    checks.append(("context has enemy", "enemy" in ctx))

    passed = 0
    for name, ok in checks:
        print(f"  {'✅' if ok else '❌'} {name}")
        if ok:
            passed += 1

    return passed, len(checks)


def test_build_adjustment_triggers():
    """Test that build adjustments trigger correctly."""
    from daemon.game_state_detector import GameSession

    session = GameSession()
    session.user_champion = "Darius"
    session.lane_opponent = "Garen"

    # Scenario 1: Enemy building armor → should trigger adjustment
    session.enemy_items = {"Garen": ["Plated Steelcaps", "Warden's Mail"]}
    session.user_kda = (3, 0, 1)
    should_adjust, reasons = session.should_adjust_build()
    check1 = should_adjust and "enemy_building_armor" in reasons
    print(f"  {'✅' if check1 else '❌'} Enemy armor → adjust build ({reasons})")

    # Scenario 2: Player dying a lot → defensive suggestion
    session.enemy_items = {"Garen": ["Dagger"]}
    session.user_kda = (0, 4, 0)
    should_adjust, reasons = session.should_adjust_build()
    check2 = should_adjust and "dying_frequently" in reasons
    print(f"  {'✅' if check2 else '❌'} Dying frequently → defensive ({reasons})")

    # Scenario 3: Normal state → no adjustment needed
    session.enemy_items = {"Garen": ["Dagger"]}
    session.user_kda = (2, 1, 3)
    should_adjust, reasons = session.should_adjust_build()
    check3 = not should_adjust
    print(f"  {'✅' if check3 else '❌'} Normal state → no adjustment needed")

    passed = sum([check1, check2, check3])
    return passed, 3


def test_coaching_result_structure():
    """Test that CoachingResult has all required fields for overlay rendering."""
    from daemon.live_pipeline import CoachingResult

    # Build advice result
    result = CoachingResult(
        game_state="tab_scoreboard",
        game_phase="early",
        headline="Buy Serrated Dirk → enemy has no armor yet",
        next_30_seconds=["Buy Dirk (1100g)", "Get Control Ward", "Return to lane"],
        buy_now=[{"item": "Serrated Dirk", "gold": 1100, "reason": "Lethality spike", "priority": 1}],
        full_build=["Eclipse", "Collector", "Infinity Edge"],
        build_changed=True,
        build_change_reason="Enemy building health, not armor — lethality still good",
    )

    checks = [
        ("has headline", bool(result.headline)),
        ("has tips", len(result.next_30_seconds) == 3),
        ("has buy_now", len(result.buy_now) == 1),
        ("has full_build", len(result.full_build) == 3),
        ("has build_changed", result.build_changed),
    ]

    # Bot lane result
    bot_result = CoachingResult(
        game_state="in_game_laning",
        is_botlane=True,
        enemy_adc="Caitlyn",
        enemy_adc_threat="high",
        enemy_adc_dodge="Q poke through minions",
        enemy_adc_punish="When she uses E (net) offensively — 16s CD",
        enemy_support="Lulu",
        enemy_support_threat="medium",
        enemy_support_dodge="Q (Glitterlance) slow",
        enemy_support_punish="When polymorph (W) is down — 15s CD",
        their_kill_combo="Lulu W polymorph → Cait trap → headshot → Q",
        your_win_condition="All-in when Lulu W is down, outscale after 2 items",
        level_2_plan="Let them push — their lvl 2 all-in is stronger",
        bush_control="Lulu wants bush control for surprise W — ward the bushes",
    )

    checks.extend([
        ("bot: has enemy_adc", bool(bot_result.enemy_adc)),
        ("bot: has enemy_support", bool(bot_result.enemy_support)),
        ("bot: has kill_combo", bool(bot_result.their_kill_combo)),
        ("bot: has win_con", bool(bot_result.your_win_condition)),
        ("bot: has bush_control", bool(bot_result.bush_control)),
    ])

    passed = 0
    for name, ok in checks:
        print(f"  {'✅' if ok else '❌'} {name}")
        if ok:
            passed += 1

    return passed, len(checks)


def test_console_overlay_rendering():
    """Test that the console overlay renders all game states without errors."""
    from daemon.live_overlay import ConsoleOverlay
    from daemon.live_pipeline import CoachingResult

    overlay = ConsoleOverlay()
    error_count = 0

    test_results = [
        # Build advice
        CoachingResult(
            game_state="tab_scoreboard", game_phase="early", processing_time=2.1,
            headline="Enemy Garen rushing armor — switch to Black Cleaver",
            next_30_seconds=["Buy Phage (1100g)", "Ward tri-bush", "Freeze wave"],
            buy_now=[{"item": "Phage", "gold": 1100, "reason": "Health + AD + MS", "priority": 1}],
            build_changed=True, build_change_reason="Garen has Plated Steelcaps + Warden's Mail",
            full_build=["Black Cleaver", "Sterak's Gage", "Dead Man's Plate"],
            laner_name="Garen",
            trade_pattern="E pull → W → auto → Q reset → disengage",
            avoid="Don't fight in his E spin — walk away",
            punish_when="After he uses Q to farm — 8s window",
            key_cooldowns=["Q (8s)", "W shield (23s)", "E (9s)"],
        ),
        # Bot lane
        CoachingResult(
            game_state="in_game_laning", game_phase="early", processing_time=3.5,
            headline="vs Caitlyn/Lulu: play safe until polymorph is down",
            is_botlane=True,
            enemy_adc="Caitlyn", enemy_adc_dodge="Q poke", enemy_adc_punish="After E (16s CD)",
            enemy_support="Lulu", enemy_support_dodge="W polymorph", enemy_support_punish="When W down (15s)",
            their_kill_combo="Lulu W → Cait trap → headshot → Q",
            your_win_condition="All-in when Lulu W is down",
            level_2_plan="Let them push, avoid trade at lvl 1",
            bush_control="Ward bushes — Lulu wants surprise polymorph",
        ),
        # Death
        CoachingResult(
            game_state="death_screen", processing_time=1.8,
            headline="Death #2 — ganked by Elise from river",
            death_reason="Pushed too far without river ward",
            death_fix="Ward river at 2:45 before pushing",
            death_positioning="Stay on your side of the wave when no wards",
            death_recovery="Farm under tower, don't force trades until even",
            death_count=2,
        ),
    ]

    for result in test_results:
        try:
            overlay.show(result)
            print(f"  ✅ Rendered: {result.game_state}")
        except Exception as e:
            print(f"  ❌ Failed {result.game_state}: {e}")
            error_count += 1

    return len(test_results) - error_count, len(test_results)


def test_multi_resolution_detection():
    """Test game state detection across common resolutions."""
    from daemon.game_state_detector import GameStateDetector, GameState

    detector = GameStateDetector()
    resolutions = [
        (1920, 1080, "1080p"),
        (2560, 1440, "1440p"),
        (3840, 2160, "4K"),
        (1280, 720, "720p"),
    ]

    passed = 0
    total = 0

    for w, h, name in resolutions:
        # Test in-game detection across resolutions
        img = create_test_image(w, h, "in_game")
        result = detector.detect(img)
        total += 1

        is_ingame = result.state in (GameState.IN_GAME_LANING,) and result.confidence >= 0.55
        status = "✅" if is_ingame else "❌"
        print(f"  {status} {name} ({w}x{h}): {result.state.value} conf={result.confidence:.2f}")
        if is_ingame:
            passed += 1

    return passed, total


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 60)
    print("  LEAGUE COACH OS — LIVE COACHING TESTS")
    print("=" * 60)

    total_passed = 0
    total_tests = 0

    tests = [
        ("Game State Detection (all states)", test_game_state_detection_all_states),
        ("Temporal State Tracking", test_game_state_temporal_tracking),
        ("Game Session Tracking", test_game_session_tracking),
        ("Build Adjustment Triggers", test_build_adjustment_triggers),
        ("Coaching Result Structure", test_coaching_result_structure),
        ("Console Overlay Rendering", test_console_overlay_rendering),
        ("Multi-Resolution Detection", test_multi_resolution_detection),
    ]

    for name, test_fn in tests:
        print(f"\n{'─' * 50}")
        print(f"  TEST: {name}")
        print(f"{'─' * 50}")
        try:
            passed, total = test_fn()
            total_passed += passed
            total_tests += total
            status = "✅" if passed == total else "⚠️"
            print(f"\n  {status} {passed}/{total} passed")
        except Exception as e:
            print(f"\n  ❌ FAILED with error: {e}")
            import traceback
            traceback.print_exc()
            total_tests += 1

    print(f"\n{'=' * 60}")
    print(f"  TOTAL: {total_passed}/{total_tests} passed")
    all_pass = total_passed == total_tests
    print(f"  {'✅ ALL TESTS PASSED' if all_pass else '⚠️ SOME TESTS FAILED'}")
    print(f"{'=' * 60}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
