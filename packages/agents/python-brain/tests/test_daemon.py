"""
================================================================================
LEAGUE COACH OS — DAEMON INTEGRATION TESTS
================================================================================
Tests for:
- Loading screen detection (heuristic classifier)
- Overlay rendering (console mode)
- Pipeline end-to-end (mock mode)
- Hotkey configuration

Author: Barrios A2I | Version: 1.0.0
================================================================================
"""
import asyncio
import sys
import os
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image, ImageDraw
import json

# =============================================================================
# TEST UTILITIES
# =============================================================================

def create_mock_loading_screen(width=1920, height=1080) -> Image.Image:
    """
    Create a synthetic LoL loading screen image for testing.

    Simulates the 5+5 champion splash layout with:
    - Dark background
    - Two rows of 5 colored rectangles (champion splashes)
    - Blue/red team indicators
    """
    img = Image.new("RGB", (width, height), (15, 15, 25))  # Dark background
    draw = ImageDraw.Draw(img)

    # Blue team — top row: 5 champion "splashes"
    blue_colors = [
        (60, 90, 140),   # Darius-ish
        (80, 120, 60),   # Lee Sin-ish
        (140, 80, 150),  # Ahri-ish
        (100, 140, 180), # Jinx-ish
        (50, 100, 90),   # Thresh-ish
    ]

    for i, color in enumerate(blue_colors):
        x1 = int(width * (0.01 + i * 0.195))
        x2 = int(width * (0.01 + i * 0.195 + 0.17))
        y1 = int(height * 0.08)
        y2 = int(height * 0.45)

        # Draw "splash art" rectangle with some variation
        draw.rectangle([x1, y1, x2, y2], fill=color)
        # Add some noise/detail to simulate splash art texture
        for px in range(x1, x2, 4):
            for py in range(y1, y2, 4):
                r, g, b = color
                import random
                noise = random.randint(-20, 20)
                draw.point((px, py), fill=(
                    max(0, min(255, r + noise)),
                    max(0, min(255, g + noise)),
                    max(0, min(255, b + noise))
                ))

        # Add blue team indicator
        draw.rectangle([x1, y1, x1 + 3, y2], fill=(50, 100, 200))

    # Red team — bottom row: 5 champion "splashes"
    red_colors = [
        (140, 80, 60),   # Garen-ish
        (100, 60, 100),  # Vi-ish
        (100, 60, 140),  # Syndra-ish
        (120, 100, 80),  # Caitlyn-ish
        (140, 100, 50),  # Leona-ish
    ]

    for i, color in enumerate(red_colors):
        x1 = int(width * (0.01 + i * 0.195))
        x2 = int(width * (0.01 + i * 0.195 + 0.17))
        y1 = int(height * 0.55)
        y2 = int(height * 0.92)

        draw.rectangle([x1, y1, x2, y2], fill=color)
        for px in range(x1, x2, 4):
            for py in range(y1, y2, 4):
                r, g, b = color
                noise = random.randint(-20, 20)
                draw.point((px, py), fill=(
                    max(0, min(255, r + noise)),
                    max(0, min(255, g + noise)),
                    max(0, min(255, b + noise))
                ))

        # Red team indicator
        draw.rectangle([x1, y1, x1 + 3, y2], fill=(200, 50, 50))

    return img


def create_non_lol_image(width=1920, height=1080) -> Image.Image:
    """Create a generic non-LoL screenshot for negative testing."""
    img = Image.new("RGB", (width, height), (200, 200, 200))
    draw = ImageDraw.Draw(img)
    # Draw some random colored rectangles (desktop-like)
    draw.rectangle([100, 50, 800, 600], fill=(255, 255, 255))
    draw.rectangle([0, height - 48, width, height], fill=(0, 120, 212))
    return img


# =============================================================================
# TESTS
# =============================================================================

import random
random.seed(42)  # Deterministic tests


def test_loading_screen_detection_positive():
    """Test that a simulated loading screen is detected."""
    from daemon.screenshot_watcher import LoadingScreenDetector

    detector = LoadingScreenDetector()
    mock_img = create_mock_loading_screen()

    result = detector.detect(mock_img)

    assert result["is_loading_screen"], (
        f"Should detect loading screen. "
        f"Confidence: {result['confidence']:.3f}, "
        f"Signals: {result['signals']}"
    )
    assert result["confidence"] >= 0.60, f"Confidence too low: {result['confidence']}"
    assert len(result["detected_regions"].get("champion_slots", [])) == 10

    print(f"  ✅ Loading screen detection: confidence={result['confidence']:.3f}")
    return True


def test_loading_screen_detection_negative():
    """Test that a non-LoL image is NOT detected as a loading screen."""
    from daemon.screenshot_watcher import LoadingScreenDetector

    detector = LoadingScreenDetector()
    desktop_img = create_non_lol_image()

    result = detector.detect(desktop_img)

    assert not result["is_loading_screen"], (
        f"Should NOT detect desktop as loading screen. "
        f"Confidence: {result['confidence']:.3f}"
    )

    print(f"  ✅ Negative detection: confidence={result['confidence']:.3f} (correctly rejected)")
    return True


def test_champion_region_extraction():
    """Test that champion crop regions are correctly computed."""
    from daemon.screenshot_watcher import LoadingScreenDetector

    detector = LoadingScreenDetector()
    regions = detector._compute_regions(1920, 1080)

    slots = regions["champion_slots"]
    assert len(slots) == 10, f"Expected 10 slots, got {len(slots)}"

    blue_slots = [s for s in slots if s["team"] == "blue"]
    red_slots = [s for s in slots if s["team"] == "red"]
    assert len(blue_slots) == 5, f"Expected 5 blue slots, got {len(blue_slots)}"
    assert len(red_slots) == 5, f"Expected 5 red slots, got {len(red_slots)}"

    # Check bounding boxes are valid
    for slot in slots:
        x1, y1, x2, y2 = slot["bbox"]
        assert x2 > x1, f"Invalid bbox width: {slot}"
        assert y2 > y1, f"Invalid bbox height: {slot}"
        assert x1 >= 0 and y1 >= 0, f"Negative coordinates: {slot}"
        assert x2 <= 1920 and y2 <= 1080, f"Out of bounds: {slot}"

    print(f"  ✅ Champion region extraction: {len(slots)} slots validated")
    return True


def test_console_overlay():
    """Test that console overlay renders without errors."""
    from daemon.overlay import ConsoleOverlay

    overlay = ConsoleOverlay()

    sample = {
        "user": {"champion": "Darius", "role": "Top", "lane_opponent": "Garen"},
        "teams": {
            "blue": ["Darius", "Lee Sin", "Ahri", "Jinx", "Thresh"],
            "red": ["Garen", "Vi", "Syndra", "Caitlyn", "Leona"]
        },
        "build": {
            "runes": {"primary": ["Conqueror"], "primary_tree": "Precision", "secondary_tree": "Resolve"},
            "core_items": ["Trinity Force", "Sterak's Gage"],
            "skill_order": {"max_order": ["Q", "E", "W"]},
        },
        "lane_plan": {
            "levels_1_3": "Short trades with auto-W-auto",
            "first_recall": {"goal_gold": 1050, "buy": "Phage + Boots"},
        },
        "beat_enemy": {
            "biggest_threats": ["Garen silence"],
            "how_to_punish": ["Trade after Q cooldown"],
            "what_not_to_do": ["Fight in his E"],
        },
        "team_plan": {"win_condition": "Win lane, TP for dragons"},
        "next_30_seconds": {
            "do": ["Doran's Blade start", "Walk through tri-brush"],
            "avoid": ["Don't push wave", "Don't waste mana Q poke"],
        },
        "meta": {"total_latency_ms": 3500, "total_cost_usd": 0.015, "mode": "FAST"},
    }

    # Should not throw
    overlay.show(sample)
    print(f"  ✅ Console overlay rendered successfully")
    return True


def test_pipeline_flow():
    """Test the coaching pipeline processes a mock screenshot without crashing."""
    from daemon.screenshot_watcher import CoachingPipeline, DaemonConfig

    config = DaemonConfig()
    pipeline = CoachingPipeline(config=config)

    mock_img = create_mock_loading_screen()

    # This should detect the loading screen and try to run the swarm
    # In mock mode (no API key), it will use the fallback behavior
    detection = pipeline.detector.detect(mock_img)
    assert detection["is_loading_screen"], "Mock image should be detected as loading screen"

    # Test image encoding
    b64 = pipeline._image_to_base64(mock_img)
    assert len(b64) > 100, "Base64 encoding failed"

    # Test crop extraction
    crops = pipeline._extract_champion_crops(mock_img, detection["detected_regions"])
    assert len(crops) == 10, f"Expected 10 crops, got {len(crops)}"

    print(f"  ✅ Pipeline flow: detection + encoding + cropping validated")
    return True


def test_resolution_support():
    """Test detection works across common gaming resolutions."""
    from daemon.screenshot_watcher import LoadingScreenDetector

    detector = LoadingScreenDetector()

    resolutions = [
        (1920, 1080),  # 1080p
        (2560, 1440),  # 1440p
        (3840, 2160),  # 4K
        (1280, 720),   # 720p
        (2560, 1080),  # Ultrawide
    ]

    results = []
    for w, h in resolutions:
        mock = create_mock_loading_screen(w, h)
        result = detector.detect(mock)
        results.append((w, h, result["is_loading_screen"], result["confidence"]))
        status = "✅" if result["is_loading_screen"] else "❌"
        print(f"    {status} {w}x{h}: confidence={result['confidence']:.3f}")

    # At least standard resolutions should work
    standard_pass = sum(1 for w, h, detected, _ in results if detected and w in [1920, 2560, 3840])
    assert standard_pass >= 2, f"Standard resolutions failed: only {standard_pass}/3 detected"

    print(f"  ✅ Resolution support: {sum(1 for _, _, d, _ in results if d)}/{len(resolutions)} passed")
    return True


# =============================================================================
# RUNNER
# =============================================================================

def run_all_tests():
    """Run all daemon integration tests."""
    print("\n" + "=" * 60)
    print("  LEAGUE COACH OS — Daemon Integration Tests")
    print("=" * 60 + "\n")

    tests = [
        ("Loading Screen Detection (positive)", test_loading_screen_detection_positive),
        ("Loading Screen Detection (negative)", test_loading_screen_detection_negative),
        ("Champion Region Extraction", test_champion_region_extraction),
        ("Console Overlay Rendering", test_console_overlay),
        ("Pipeline Flow (mock)", test_pipeline_flow),
        ("Resolution Support", test_resolution_support),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        print(f"\n  📋 {name}")
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"  Results: {passed} passed, {failed} failed, {len(tests)} total")
    print(f"{'=' * 60}\n")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
