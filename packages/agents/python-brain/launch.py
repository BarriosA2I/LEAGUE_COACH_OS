"""
================================================================================
LEAGUE COACH OS — UNIFIED LAUNCHER
================================================================================
Single entry point for all modes:

  python launch.py daemon          # 🎯 THE MAIN MODE: PrintScreen → auto coach
  python launch.py coach [args]    # Manual CLI coaching
  python launch.py serve           # FastAPI server
  python launch.py demo            # Demo overlay with sample data
  python launch.py test            # Run integration tests
  python launch.py status          # Show daemon status

Author: Barrios A2I | Version: 1.0.0
================================================================================
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env file if present (no external dependency needed)
_env_file = PROJECT_ROOT / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())


def setup_logging(level: str = "INFO"):
    """Configure structured logging."""
    log_dir = Path.home() / "BarriosA2I" / "LEAGUE_COACH_OS" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "coach.log", encoding="utf-8"),
        ]
    )


# =============================================================================
# DAEMON MODE — The Star
# =============================================================================

def cmd_daemon(args):
    """
    Start the autonomous coaching daemon.

    This is the main mode. Once running:
    1. Hit PrintScreen on your LoL loading screen
    2. 9 agents analyze your game in <7 seconds
    3. Coaching overlay appears on top of the game
    4. Play with full knowledge of your matchup, build, and game plan

    No clicks. No typing. Just play.
    """
    from daemon.screenshot_watcher import LeagueCoachDaemon, DaemonConfig

    config = DaemonConfig()

    # Override config from args
    if hasattr(args, "overlay_duration") and args.overlay_duration:
        config.OVERLAY_DURATION = args.overlay_duration
    if hasattr(args, "overlay_position") and args.overlay_position:
        config.OVERLAY_POSITION = args.overlay_position

    daemon = LeagueCoachDaemon(config=config)

    # Also start hotkey listener for direct PrintScreen capture
    try:
        from daemon.hotkey_listener import HotkeyListener
        hotkey = HotkeyListener(
            on_capture=daemon._on_screenshot,
            on_toggle=lambda: None,  # Will be wired to overlay
        )
        if hotkey.start():
            print("  ✅ Global hotkeys: ACTIVE (PrintScreen captures directly)")
        else:
            print("  ⚠️  Global hotkeys: DISABLED (using clipboard fallback)")
    except Exception as e:
        print(f"  ⚠️  Hotkey listener error: {e}")

    daemon.start()


# =============================================================================
# CLI COACH MODE
# =============================================================================

def cmd_coach(args):
    """Run coaching from CLI with explicit champion/team inputs."""
    from orchestrator.swarm import LeagueCoachingSwarm
    from schemas.models import CoachMode

    async def run():
        swarm = LeagueCoachingSwarm()

        # Build input from args
        kwargs = {"mode": "FULL" if args.full else "FAST"}

        if args.image:
            import base64
            with open(args.image, "rb") as f:
                kwargs["image_data"] = base64.b64encode(f.read()).decode()

        if args.champion:
            kwargs["user_champion"] = args.champion
        if args.role:
            kwargs["user_role"] = args.role

        if args.blue:
            kwargs["blue_team"] = [c.strip() for c in args.blue.split(",")]
        if args.red:
            kwargs["red_team"] = [c.strip() for c in args.red.split(",")]

        start = time.time()
        result = await swarm.run(**kwargs)
        elapsed = (time.time() - start) * 1000

        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            # Show console overlay
            from daemon.overlay import ConsoleOverlay
            overlay = ConsoleOverlay()
            overlay.show(result)
            print(f"\n⚡ Total: {elapsed:.0f}ms")

        if args.output:
            with open(args.output, "w") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"💾 Saved to {args.output}")

    asyncio.run(run())


# =============================================================================
# SERVER MODE
# =============================================================================

def cmd_serve(args):
    """Start FastAPI server for HTTP-based coaching."""
    try:
        import uvicorn
        from main import app  # Import the existing FastAPI app
        print(f"🌐 Starting League Coach API on port {args.port}...")
        uvicorn.run(app, host="0.0.0.0", port=args.port)
    except ImportError:
        print("❌ uvicorn not installed. Run: pip install uvicorn fastapi")
        sys.exit(1)


# =============================================================================
# DEMO MODE
# =============================================================================

def cmd_demo(args):
    """Show a demo overlay with sample Darius vs Garen data."""
    sample_data = {
        "user": {"champion": "Darius", "role": "Top", "rank": "Gold 2", "lane_opponent": "Garen"},
        "teams": {
            "blue": ["Darius", "Lee Sin", "Ahri", "Jinx", "Thresh"],
            "red": ["Garen", "Vi", "Syndra", "Caitlyn", "Leona"],
            "role_inference": {
                "blue": {"Top": "Darius", "Jungle": "Lee Sin", "Mid": "Ahri", "ADC": "Jinx", "Support": "Thresh"},
                "red": {"Top": "Garen", "Jungle": "Vi", "Mid": "Syndra", "ADC": "Caitlyn", "Support": "Leona"},
            }
        },
        "build": {
            "summoners": ["Flash", "Teleport"],
            "runes": {
                "primary_tree": "Precision",
                "primary": ["Conqueror", "Triumph", "Legend: Tenacity", "Last Stand"],
                "secondary_tree": "Resolve",
                "secondary": ["Bone Plating", "Unflinching"],
                "shards": ["Attack Speed", "Adaptive Force", "Health Scaling"]
            },
            "skill_order": {
                "start": "Q",
                "max_order": ["Q", "E", "W"],
                "levels_1_6": ["Q", "W", "E", "Q", "Q", "R"]
            },
            "start_items": ["Doran's Blade", "Health Potion"],
            "core_items": ["Trinity Force", "Sterak's Gage", "Dead Man's Plate"],
            "boots": "Plated Steelcaps",
            "situational_items": ["Spirit Visage", "Randuin's Omen", "Guardian Angel"],
        },
        "lane_plan": {
            "levels_1_3": "Auto-W-auto short trades. Darius passive stacks win extended fights. Don't all-in without E.",
            "wave_plan": "Freeze near your tower. Garen has no gap closer pre-6 so he's easy to freeze against.",
            "trade_windows": "Trade when Garen Q is on cooldown (8s). Pull him with E right after he wastes Q on a minion.",
            "first_recall": {"goal_gold": 1050, "timing_rule": "After killing or forcing enemy recall", "buy": "Phage + Boots"},
            "level_6": "All-in at 5 passive stacks. Noxian Guillotine (R) executes below 25% HP. Resets on kill.",
        },
        "beat_enemy": {
            "biggest_threats": [
                "Garen Q silence stops your combo for 1.5s",
                "Garen W gives him 60% tenacity — your E pull is shorter",
                "Garen R is true damage execute — respect at 30% HP"
            ],
            "how_to_punish": [
                "Auto-W when he walks up to CS — he has to choose between Q on you or CS",
                "E pull right after he wastes Q on a minion — 8 second window",
                "Stack passive to 5 before using R for maximum damage"
            ],
            "what_not_to_do": [
                "Don't fight inside his E spin — walk out and re-engage",
                "Don't ult without 5 Hemorrhage stacks — wasted damage",
                "Don't push without vision — Garen + Jungler runs you down"
            ],
        },
        "team_plan": {
            "win_condition": "Win lane hard, TP bot for dragon fights, become unkillable teamfight frontline",
            "your_job": "Frontline engage. Pull carries with E. Stack passive in teamfights. Dunk resets chain kills.",
            "target_priority": "Caitlyn > Syndra > Vi > Leona > Garen",
            "fight_rules": "Flash-E onto Caitlyn or Syndra. Don't waste R without 5 stacks of Noxian Might. Peel for Jinx if needed.",
        },
        "macro": {
            "wards": "River brush + tri-brush. Control ward in lane brush.",
            "roams": "TP bot on cannon wave timings for dragon fights.",
            "objectives": "Herald at 14 min if ahead. Dragon priority when TP is up.",
            "midgame": "Split top with TP available. Group when TP is down.",
            "lategame": "Frontline for team. Flash-E is your engage tool.",
        },
        "next_30_seconds": {
            "do": [
                "Take Doran's Blade + Health Potion",
                "Walk to lane through tri-brush for invade safety",
                "Auto-W Garen if he contests first 3 melee minions"
            ],
            "avoid": [
                "Don't waste mana on Q poke level 1 — save for trades",
                "Don't push the wave — let it slow push toward you",
                "Don't fight in Garen E spin range without 3+ passive stacks"
            ],
        },
        "meta": {
            "patch_version": "25.S1.3",
            "mode": "FAST",
            "generated_at": "2026-02-22T05:45:00Z",
            "confidence": 0.91,
            "notes": "Demo data — Darius vs Garen Top Lane",
            "total_cost_usd": 0.018,
            "total_latency_ms": 4200,
            "agents_run": ["vision_parser", "role_inference", "build_planner", "laning_coach", "teamfight_coach", "macro_coach", "judge"]
        }
    }

    if args.gui:
        from daemon.overlay import CoachOverlay
        print("🎨 Opening GUI overlay demo...")
        overlay = CoachOverlay(duration=60, position="top-right")
        overlay.show(sample_data)
    else:
        from daemon.overlay import ConsoleOverlay
        overlay = ConsoleOverlay()
        overlay.show(sample_data)


# =============================================================================
# TEST MODE
# =============================================================================

def cmd_test(args):
    """Run integration tests."""
    from main import run_tests
    asyncio.run(run_tests())


# =============================================================================
# STATUS MODE
# =============================================================================

def cmd_status(args):
    """Show system status and installed dependencies."""
    print("\n🔍 League Coach OS — System Status\n")

    # Check dependencies
    deps = {
        "Pillow (image handling)": "PIL",
        "anthropic (Claude API)": "anthropic",
        "keyboard (global hotkeys)": "keyboard",
        "pystray (system tray)": "pystray",
        "win10toast (notifications)": "win10toast_click",
        "plyer (cross-platform notif)": "plyer",
        "pydantic (schema validation)": "pydantic",
        "uvicorn (API server)": "uvicorn",
        "fastapi (API framework)": "fastapi",
    }

    for name, module in deps.items():
        try:
            __import__(module)
            print(f"  ✅ {name}")
        except ImportError:
            print(f"  ❌ {name}")

    # Check API key
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        print(f"\n  🔑 Anthropic API Key: {'*' * 8}...{api_key[-4:]}")
    else:
        print(f"\n  ❌ ANTHROPIC_API_KEY not set!")
        print(f"     Set it: $env:ANTHROPIC_API_KEY='sk-ant-...'")

    # Check vault
    vault = Path.home() / "BarriosA2I" / "LEAGUE_COACH_OS" / "vault"
    if vault.exists():
        print(f"\n  📚 Vault: {vault}")
        patches = list((vault / "patches").glob("*")) if (vault / "patches").exists() else []
        print(f"     Patches: {len(patches)}")
    else:
        print(f"\n  ⚠️  Vault not found at {vault}")

    print()


# =============================================================================
# CLI PARSER
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        prog="league-coach",
        description="League Coach OS — Autonomous LoL Coaching System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python launch.py daemon                         # Start the auto-coaching daemon
  python launch.py coach -c Darius -r Top         # Quick manual coaching
  python launch.py demo --gui                     # Show overlay demo
  python launch.py status                         # Check system dependencies
        """
    )

    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    sub = parser.add_subparsers(dest="command")

    # daemon
    p_daemon = sub.add_parser("daemon", help="Start autonomous coaching daemon (PrintScreen → coach)")
    p_daemon.add_argument("--overlay-duration", type=int, default=30, help="Overlay display duration (seconds)")
    p_daemon.add_argument("--overlay-position", default="top-right", choices=["top-right", "top-left", "center"])

    # coach
    p_coach = sub.add_parser("coach", help="Manual CLI coaching")
    p_coach.add_argument("-c", "--champion", help="Your champion name")
    p_coach.add_argument("-r", "--role", help="Your role (Top/Jungle/Mid/ADC/Support)")
    p_coach.add_argument("-i", "--image", help="Loading screen image path")
    p_coach.add_argument("--blue", help="Blue team champions (comma-separated)")
    p_coach.add_argument("--red", help="Red team champions (comma-separated)")
    p_coach.add_argument("--full", action="store_true", help="Use FULL mode (slower, more detailed)")
    p_coach.add_argument("--json", action="store_true", help="Output raw JSON")
    p_coach.add_argument("-o", "--output", help="Save output to file")

    # serve
    p_serve = sub.add_parser("serve", help="Start FastAPI coaching server")
    p_serve.add_argument("--port", type=int, default=8080, help="Server port")

    # demo
    p_demo = sub.add_parser("demo", help="Show demo overlay")
    p_demo.add_argument("--gui", action="store_true", help="Show GUI overlay (requires tkinter)")

    # test
    p_test = sub.add_parser("test", help="Run integration tests")

    # status
    p_status = sub.add_parser("status", help="Show system status")

    args = parser.parse_args()
    setup_logging(args.log_level)

    commands = {
        "daemon": cmd_daemon,
        "coach": cmd_coach,
        "serve": cmd_serve,
        "demo": cmd_demo,
        "test": cmd_test,
        "status": cmd_status,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        print("\n💡 Quick start: python launch.py daemon")


if __name__ == "__main__":
    main()
