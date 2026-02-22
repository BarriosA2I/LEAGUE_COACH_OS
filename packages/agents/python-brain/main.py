"""
================================================================================
LEAGUE COACHING SWARM — API SERVER + CLI
================================================================================
FastAPI server for the coaching swarm with WebSocket support.
Also runnable as CLI for local testing.

Usage:
  Server: python main.py serve
  CLI:    python main.py coach --champion "Darius" --role "Top" --blue "Darius,Lee Sin,Ahri,Jinx,Thresh" --red "Garen,Vi,Syndra,Caitlyn,Leona"
  Test:   python main.py test

Author: Barrios A2I | Version: 1.0.0
================================================================================
"""
import argparse
import asyncio
import json
import logging
import sys
import time
from typing import List, Optional

# Setup path
sys.path.insert(0, ".")

from schemas.models import CoachMode, GameCoachPackage
from orchestrator.swarm import LeagueCoachingSwarm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("league_swarm")


# =============================================================================
# CLI RUNNER
# =============================================================================

async def run_cli(args):
    """Run coaching from command line arguments."""
    blue_team = args.blue.split(",") if args.blue else None
    red_team = args.red.split(",") if args.red else None

    # Try to initialize with real Anthropic client
    llm_client = None
    try:
        import anthropic
        llm_client = anthropic.AsyncAnthropic()
        logger.info("✅ Anthropic client initialized")
    except Exception as e:
        logger.warning(f"No Anthropic client — running in MOCK mode: {e}")

    swarm = LeagueCoachingSwarm(
        llm_client=llm_client,
        patch_version=args.patch or "14.24",
    )

    mode = CoachMode.FULL if args.full else CoachMode.FAST

    logger.info(f"🚀 Running {mode.value} MODE coaching for {args.champion}...")
    start = time.time()

    package = await swarm.coach(
        image_data=args.image,
        user_champion=args.champion,
        user_role=args.role,
        user_rank=args.rank,
        blue_team=blue_team,
        red_team=red_team,
        mode=mode,
    )

    elapsed = time.time() - start
    logger.info(f"✅ Coaching complete in {elapsed:.2f}s")

    # Print JSON package
    if args.json:
        print("\n" + "=" * 60)
        print("GAME_COACH_PACKAGE (JSON)")
        print("=" * 60)
        print(json.dumps(package.model_dump(), indent=2))

    # Print coach summary
    print("\n" + "=" * 60)
    summary = swarm._generate_summary(package)
    print(summary)
    print("=" * 60)

    return package


# =============================================================================
# TEST RUNNER
# =============================================================================

async def run_tests():
    """Run integration tests with mock data."""
    logger.info("🧪 Running League Coaching Swarm tests...")
    passed = 0
    failed = 0

    # Test 1: Mock coaching run
    logger.info("\n--- Test 1: Full coaching pipeline (mock) ---")
    try:
        swarm = LeagueCoachingSwarm(llm_client=None, patch_version="14.24")
        package = await swarm.coach(
            user_champion="Darius",
            user_role="Top",
            user_rank="Gold",
            blue_team=["Darius", "Lee Sin", "Ahri", "Jinx", "Thresh"],
            red_team=["Garen", "Vi", "Syndra", "Caitlyn", "Leona"],
            mode=CoachMode.FAST,
        )

        assert package is not None, "Package is None"
        assert package.user.champion == "Darius", f"Expected Darius, got {package.user.champion}"
        assert package.user.role == "Top", f"Expected Top, got {package.user.role}"
        assert package.user.lane_opponent == "Garen", f"Expected Garen, got {package.user.lane_opponent}"
        assert len(package.teams.blue) == 5, "Blue team should have 5 champions"
        assert len(package.teams.red) == 5, "Red team should have 5 champions"
        assert package.build.summoners is not None, "Summoners missing"
        assert len(package.build.summoners) == 2, "Should have 2 summoners"
        assert len(package.next_30_seconds.do) == 3, "Should have 3 'do' items"
        assert len(package.next_30_seconds.avoid) == 3, "Should have 3 'avoid' items"
        assert package.meta.mode == CoachMode.FAST, "Should be FAST mode"
        assert package.meta.patch_version == "14.24", "Wrong patch"

        logger.info("  ✅ Full pipeline test PASSED")
        passed += 1
    except Exception as e:
        logger.error(f"  ❌ Full pipeline test FAILED: {e}")
        failed += 1

    # Test 2: Schema validation
    logger.info("\n--- Test 2: Schema validation ---")
    try:
        pkg_dict = package.model_dump()
        reconstructed = GameCoachPackage.model_validate(pkg_dict)
        assert reconstructed.user.champion == "Darius"
        logger.info("  ✅ Schema validation PASSED")
        passed += 1
    except Exception as e:
        logger.error(f"  ❌ Schema validation FAILED: {e}")
        failed += 1

    # Test 3: Role inference accuracy
    logger.info("\n--- Test 3: Role inference ---")
    try:
        from agents.role_inference import RoleInferenceEngineAgent
        from schemas.models import RoleInferenceInput

        engine = RoleInferenceEngineAgent()
        result = await engine.infer(RoleInferenceInput(
            blue_team=["Darius", "Lee Sin", "Ahri", "Jinx", "Thresh"],
            red_team=["Garen", "Vi", "Syndra", "Caitlyn", "Leona"],
        ))

        assert result.blue_roles.TOP == "Darius", f"Expected Darius TOP, got {result.blue_roles.TOP}"
        assert result.blue_roles.JG == "Lee Sin", f"Expected Lee Sin JG, got {result.blue_roles.JG}"
        assert result.blue_roles.MID == "Ahri", f"Expected Ahri MID, got {result.blue_roles.MID}"
        assert result.blue_roles.ADC == "Jinx", f"Expected Jinx ADC, got {result.blue_roles.ADC}"
        assert result.blue_roles.SUP == "Thresh", f"Expected Thresh SUP, got {result.blue_roles.SUP}"

        assert result.red_roles.TOP == "Garen", f"Expected Garen TOP, got {result.red_roles.TOP}"
        assert result.red_roles.JG == "Vi", f"Expected Vi JG, got {result.red_roles.JG}"
        assert result.red_roles.MID == "Syndra", f"Expected Syndra MID, got {result.red_roles.MID}"
        assert result.red_roles.ADC == "Caitlyn", f"Expected Caitlyn ADC, got {result.red_roles.ADC}"
        assert result.red_roles.SUP == "Leona", f"Expected Leona SUP, got {result.red_roles.SUP}"

        logger.info("  ✅ Role inference PASSED")
        passed += 1
    except Exception as e:
        logger.error(f"  ❌ Role inference FAILED: {e}")
        failed += 1

    # Test 4: Edge case — flex picks
    logger.info("\n--- Test 4: Flex pick role inference ---")
    try:
        result2 = await engine.infer(RoleInferenceInput(
            blue_team=["Yasuo", "Viego", "Irelia", "Vayne", "Sett"],
            red_team=["Yone", "Lee Sin", "Akali", "Lucian", "Nautilus"],
        ))

        # These are all flex picks — just verify no crashes and all roles filled
        all_blue = [result2.blue_roles.TOP, result2.blue_roles.JG, result2.blue_roles.MID,
                    result2.blue_roles.ADC, result2.blue_roles.SUP]
        assert len(set(all_blue)) == 5, f"Duplicate role assignments: {all_blue}"

        all_red = [result2.red_roles.TOP, result2.red_roles.JG, result2.red_roles.MID,
                   result2.red_roles.ADC, result2.red_roles.SUP]
        assert len(set(all_red)) == 5, f"Duplicate role assignments: {all_red}"

        logger.info(f"  Blue: TOP={result2.blue_roles.TOP} JG={result2.blue_roles.JG} MID={result2.blue_roles.MID} ADC={result2.blue_roles.ADC} SUP={result2.blue_roles.SUP}")
        logger.info(f"  Red:  TOP={result2.red_roles.TOP} JG={result2.red_roles.JG} MID={result2.red_roles.MID} ADC={result2.red_roles.ADC} SUP={result2.red_roles.SUP}")
        logger.info("  ✅ Flex pick inference PASSED")
        passed += 1
    except Exception as e:
        logger.error(f"  ❌ Flex pick inference FAILED: {e}")
        failed += 1

    # Test 5: Judge validation
    logger.info("\n--- Test 5: Judge validation ---")
    try:
        from agents.judge import FinalJudgeValidatorAgent
        from schemas.models import (
            JudgeInput, BuildPlannerOutput, LaningCoachOutput,
            TeamfightCoachOutput, MacroCoachOutput, RuneConfig, SkillOrder, FirstRecall,
        )

        judge = FinalJudgeValidatorAgent()
        judge_result = await judge.validate(JudgeInput(
            build=BuildPlannerOutput(
                summoners=["Flash", "Teleport"],
                runes=RuneConfig(
                    primary_tree="Precision",
                    primary=["Conqueror", "Triumph", "Legend: Alacrity", "Last Stand"],
                    secondary_tree="Resolve",
                    secondary=["Bone Plating", "Overgrowth"],
                    shards=["Attack Speed", "Adaptive Force", "Health Scaling"],
                ),
                skill_order=SkillOrder(start="Q", max_order=["Q", "E", "W"], levels_1_6=["Q", "W", "E", "Q", "Q", "R"]),
                start_items=["Doran's Blade", "Health Potion"],
                core_items=["Trinity Force", "Sterak's Gage", "Death's Dance"],
                boots="Plated Steelcaps",
                confidence=0.9,
                processing_time_ms=100.0,
                cost_usd=0.005,
            ),
            laning=LaningCoachOutput(
                levels_1_3=["Play aggressive level 1 with Q", "Zone off CS at level 2", "All-in at level 3 with full combo"],
                wave_plan=["Slow push first 3 waves", "Crash on cannon wave"],
                trade_windows=["Trade when Garen Q is on cooldown", "Short trades with W reset"],
                first_recall=FirstRecall(goal_gold="1100", timing_rule="After crashing wave 4", buy=["Sheen", "Control Ward"]),
                level_6=["All-in with R at 5 stacks", "Bait Garen W first"],
                avoid_list=["Don't extended trade into Garen W", "Don't chase into brush"],
                punish_list=["Punish Garen Q whiff", "Punish when Garen wastes W"],
                confidence=0.85,
                processing_time_ms=200.0,
                cost_usd=0.005,
            ),
            teamfight=TeamfightCoachOutput(
                win_condition="5v5 teamfight with Darius resets",
                your_job="Frontline, get 5 stacks, dunk backline",
                target_priority=["Caitlyn (squishy)", "Syndra (burst)", "Vi (if isolated)"],
                threat_list=["Syndra R burst", "Vi ult lockdown"],
                fight_rules=["Flash onto backline when team engages", "Don't go in alone", "Wait for Thresh hook"],
                confidence=0.85,
                processing_time_ms=150.0,
                cost_usd=0.004,
            ),
            macro=MacroCoachOutput(
                wards=["Tri-bush at 2:50", "River bush before dragon", "Deep ward enemy raptors when shoving"],
                roams=["Roam mid after crashing wave", "TP bot for dragon fights"],
                objectives=["Contest Herald at 14:00", "Setup dragon with vision 60s before", "Take tower plates when enemy backs"],
                midgame=["Split push top with TP", "Group for Herald/Dragon"],
                lategame=["Flank in teamfights", "Catch side waves then group"],
                confidence=0.85,
                processing_time_ms=100.0,
                cost_usd=0.002,
            ),
            user_champion="Darius",
            lane_opponent="Garen",
            patch_version="14.24",
        ))

        assert judge_result.approved, f"Judge rejected: {[f.issue for f in judge_result.fixes_applied]}"
        assert judge_result.schema_valid, "Schema invalid"
        logger.info(f"  Judge: approved={judge_result.approved}, fixes={len(judge_result.fixes_applied)}, uncertainties={len(judge_result.remaining_uncertainty)}")
        logger.info("  ✅ Judge validation PASSED")
        passed += 1
    except Exception as e:
        logger.error(f"  ❌ Judge validation FAILED: {e}")
        failed += 1

    # Summary
    total = passed + failed
    logger.info(f"\n{'='*60}")
    logger.info(f"🧪 Test Results: {passed}/{total} passed, {failed} failed")
    logger.info(f"{'='*60}")

    return failed == 0


# =============================================================================
# FASTAPI SERVER
# =============================================================================

def create_app():
    """Create FastAPI app for the coaching swarm."""
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.middleware.cors import CORSMiddleware
        from pydantic import BaseModel as PydanticBaseModel
    except ImportError:
        logger.error("FastAPI not installed. Run: pip install fastapi uvicorn")
        return None

    app = FastAPI(
        title="League Coaching Swarm",
        description="9-agent autonomous coaching system for League of Legends",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize swarm
    llm_client = None
    try:
        import anthropic
        llm_client = anthropic.AsyncAnthropic()
    except Exception:
        pass

    swarm = LeagueCoachingSwarm(llm_client=llm_client)

    class CoachRequest(PydanticBaseModel):
        image_data: Optional[str] = None
        user_champion: Optional[str] = None
        user_role: Optional[str] = None
        user_rank: Optional[str] = None
        blue_team: Optional[List[str]] = None
        red_team: Optional[List[str]] = None
        mode: str = "FAST"

    @app.post("/api/coach", response_model=dict)
    async def coach_endpoint(request: CoachRequest):
        try:
            mode = CoachMode.FULL if request.mode == "FULL" else CoachMode.FAST
            package = await swarm.coach(
                image_data=request.image_data,
                user_champion=request.user_champion,
                user_role=request.user_role,
                user_rank=request.user_rank,
                blue_team=request.blue_team,
                red_team=request.red_team,
                mode=mode,
            )
            summary = swarm._generate_summary(package)
            return {
                "package": package.model_dump(),
                "summary": summary,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "agents": 9,
            "version": "1.0.0",
        }

    return app


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="League Coaching Swarm")
    subparsers = parser.add_subparsers(dest="command")

    # Coach command
    coach_parser = subparsers.add_parser("coach", help="Run coaching from CLI")
    coach_parser.add_argument("--champion", "-c", required=True, help="Your champion")
    coach_parser.add_argument("--role", "-r", help="Your role (Top/Jungle/Mid/ADC/Support)")
    coach_parser.add_argument("--rank", help="Your rank")
    coach_parser.add_argument("--blue", "-b", help="Blue team (comma-separated)")
    coach_parser.add_argument("--red", help="Red team (comma-separated)")
    coach_parser.add_argument("--image", "-i", help="Loading screen image path")
    coach_parser.add_argument("--patch", "-p", help="Patch version")
    coach_parser.add_argument("--full", action="store_true", help="Use FULL mode")
    coach_parser.add_argument("--json", action="store_true", help="Output JSON package")

    # Test command
    subparsers.add_parser("test", help="Run integration tests")

    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Start API server")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8080)

    args = parser.parse_args()

    if args.command == "coach":
        asyncio.run(run_cli(args))
    elif args.command == "test":
        success = asyncio.run(run_tests())
        sys.exit(0 if success else 1)
    elif args.command == "serve":
        app = create_app()
        if app:
            import uvicorn
            uvicorn.run(app, host=args.host, port=args.port)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
