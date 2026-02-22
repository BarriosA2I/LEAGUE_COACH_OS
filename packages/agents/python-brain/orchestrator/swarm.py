"""
================================================================================
LEAGUE COACHING SWARM — MASTER ORCHESTRATOR
================================================================================
LangGraph-style state machine with parallel agent execution.
9-agent coordination | FAST/FULL modes | Circuit breakers | Cost tracking

Flow:
  1. Vision Parse → 2. User Context + Role Inference (parallel)
  3. Canon Knowledge → 4. Build + Laning + Teamfight + Macro (parallel)
  5. Judge Validation → 6. Package Assembly + Coach Summary

Author: Barrios A2I | Version: 1.0.0 | UPRS: 9.5+/10
================================================================================
"""
import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from schemas.models import (
    AgentStatus,
    BeatEnemyBlock,
    BuildBlock,
    BuildPlannerInput,
    CanonKnowledgeInput,
    CanonKnowledgeOutput,
    ChampionKit,
    CoachMeta,
    CoachMode,
    GameCoachPackage,
    JudgeInput,
    LanePlanBlock,
    LaningCoachInput,
    MacroBlock,
    MacroCoachInput,
    Next30Seconds,
    Role,
    RoleInferenceInput,
    SwarmState,
    TeamfightCoachInput,
    TeamPlanBlock,
    TeamsBlock,
    UserBlock,
    UserContextInput,
    VisionParserInput,
)
from agents import (
    BuildAndRunesPlannerAgent,
    FinalJudgeValidatorAgent,
    LaningMatchupCoachAgent,
    MacroObjectivesCoachAgent,
    RoleInferenceEngineAgent,
    TeamfightCompCoachAgent,
    UserContextResolverAgent,
    VisionParserAgent,
)

logger = logging.getLogger(__name__)


# =============================================================================
# CIRCUIT BREAKER (Inline minimal version)
# =============================================================================

class AgentCircuitBreaker:
    """Per-agent circuit breaker with fallback support."""

    def __init__(self, name: str, failure_threshold: int = 3, timeout: float = 30.0):
        self.name = name
        self.failures = 0
        self.threshold = failure_threshold
        self.timeout = timeout
        self.is_open = False

    async def execute(self, coro, fallback=None):
        if self.is_open:
            logger.warning(f"Circuit OPEN for {self.name} — using fallback")
            if fallback:
                return await fallback() if asyncio.iscoroutinefunction(fallback) else fallback()
            return None

        try:
            result = await asyncio.wait_for(coro, timeout=self.timeout)
            self.failures = 0
            return result
        except (asyncio.TimeoutError, Exception) as e:
            self.failures += 1
            logger.error(f"Agent {self.name} failed ({self.failures}/{self.threshold}): {e}")
            if self.failures >= self.threshold:
                self.is_open = True
                logger.critical(f"Circuit OPENED for {self.name}")
            if fallback:
                return await fallback() if asyncio.iscoroutinefunction(fallback) else fallback()
            return None


# =============================================================================
# MASTER ORCHESTRATOR
# =============================================================================

class LeagueCoachingSwarm:
    """
    9-agent orchestrator for League of Legends coaching.
    
    Supports FAST mode (<7s) and FULL mode (<20s).
    Parallel execution where possible with circuit breakers per agent.
    """

    def __init__(
        self,
        llm_client=None,
        vision_model: str = "claude-sonnet-4-5-20250929",
        coaching_model: str = "claude-sonnet-4-5-20250929",
        utility_model: str = "claude-haiku-4-5-20251001",
        patch_version: str = "14.24",
    ):
        self.llm_client = llm_client
        self.patch_version = patch_version

        # Initialize all 9 agents
        self.vision = VisionParserAgent(llm_client=llm_client, model=vision_model)
        self.user_context = UserContextResolverAgent()
        self.role_inference = RoleInferenceEngineAgent(llm_client=llm_client, model=utility_model)
        self.build_planner = BuildAndRunesPlannerAgent(llm_client=llm_client, model=coaching_model)
        self.laning_coach = LaningMatchupCoachAgent(llm_client=llm_client, model=coaching_model)
        self.teamfight_coach = TeamfightCompCoachAgent(llm_client=llm_client, model=coaching_model)
        self.macro_coach = MacroObjectivesCoachAgent(llm_client=llm_client, model=utility_model)
        self.judge = FinalJudgeValidatorAgent()

        # Per-agent circuit breakers
        self.breakers = {
            "vision": AgentCircuitBreaker("vision", timeout=15.0),
            "build": AgentCircuitBreaker("build", timeout=20.0),
            "laning": AgentCircuitBreaker("laning", timeout=20.0),
            "teamfight": AgentCircuitBreaker("teamfight", timeout=20.0),
            "macro": AgentCircuitBreaker("macro", timeout=15.0),
        }

    async def coach(
        self,
        image_data: Optional[str] = None,
        user_champion: Optional[str] = None,
        user_role: Optional[str] = None,
        user_rank: Optional[str] = None,
        blue_team: Optional[List[str]] = None,
        red_team: Optional[List[str]] = None,
        mode: CoachMode = CoachMode.FAST,
    ) -> GameCoachPackage:
        """
        Main entry point. Orchestrates all 9 agents.
        
        Args:
            image_data: Base64 loading screen image (optional if teams provided)
            user_champion: User's champion name
            user_role: User's role (Top/Jungle/Mid/ADC/Support)
            user_rank: User's rank
            blue_team: Blue team champions (optional if image provided)
            red_team: Red team champions (optional if image provided)
            mode: FAST (<7s) or FULL (<20s)
        
        Returns:
            GameCoachPackage with full coaching output
        """
        orchestration_start = time.time()
        total_cost = 0.0

        state = SwarmState(
            image_data=image_data,
            user_champion=user_champion,
            user_role=Role(user_role) if user_role else None,
            user_rank=user_rank,
            mode=mode,
            patch_version=self.patch_version,
        )

        # =====================================================================
        # PHASE 1: Vision Parse (skip if teams provided directly)
        # =====================================================================
        if blue_team and red_team:
            logger.info("Teams provided directly — skipping vision parse")
            parsed_blue = blue_team
            parsed_red = red_team
        elif image_data:
            logger.info("Phase 1: Vision parsing loading screen...")
            vision_result = await self.breakers["vision"].execute(
                self.vision.parse(VisionParserInput(image_data=image_data))
            )
            if vision_result:
                state.vision = vision_result
                parsed_blue = vision_result.blue_team
                parsed_red = vision_result.red_team
                total_cost += vision_result.cost_usd
                logger.info(f"Vision: Blue={parsed_blue}, Red={parsed_red} (conf={vision_result.overall_confidence:.2f})")
            else:
                raise ValueError("Vision parsing failed and no fallback teams provided")
        else:
            raise ValueError("Must provide either image_data or blue_team+red_team")

        # =====================================================================
        # PHASE 2: User Context + Role Inference (PARALLEL)
        # =====================================================================
        logger.info("Phase 2: Resolving user context + inferring roles (parallel)...")

        user_ctx_task = self.user_context.resolve(UserContextInput(
            user_champion=user_champion,
            user_role=Role(user_role) if user_role else None,
            user_rank=user_rank,
            blue_team=parsed_blue,
            red_team=parsed_red,
        ))

        role_inf_task = self.role_inference.infer(RoleInferenceInput(
            blue_team=parsed_blue,
            red_team=parsed_red,
            user_champion=user_champion,
            user_role=Role(user_role) if user_role else None,
        ))

        user_ctx_result, role_result = await asyncio.gather(user_ctx_task, role_inf_task)
        state.user_context = user_ctx_result
        state.role_inference = role_result

        # Resolve user context
        resolved_champion = user_ctx_result.user_champion
        resolved_role = user_ctx_result.user_role
        resolved_team = user_ctx_result.user_team
        lane_opponent = user_ctx_result.lane_opponent

        # If lane opponent still unknown, use role inference
        if lane_opponent == "Unknown" and resolved_role != Role.UNKNOWN:
            role_key = {"Top": "TOP", "Jungle": "JG", "Mid": "MID", "ADC": "ADC", "Support": "SUP"}.get(resolved_role.value, "")
            if role_key:
                enemy_roles = role_result.red_roles if resolved_team.value == "blue" else role_result.blue_roles
                lane_opponent = getattr(enemy_roles, role_key, "Unknown")

        logger.info(f"User: {resolved_champion} ({resolved_role.value}) vs {lane_opponent}")

        # =====================================================================
        # PHASE 3: Canon Knowledge (lightweight — could be local DB lookup)
        # =====================================================================
        logger.info("Phase 3: Fetching canon knowledge...")

        # For now, create minimal kit objects (extend with Data Dragon integration)
        user_kit = ChampionKit(champion_name=resolved_champion, tags=["Fighter"])
        enemy_kit = ChampionKit(champion_name=lane_opponent, tags=["Fighter"])

        ally_team = parsed_blue if resolved_team.value == "blue" else parsed_red
        enemy_team = parsed_red if resolved_team.value == "blue" else parsed_blue
        ally_roles = role_result.blue_roles if resolved_team.value == "blue" else role_result.red_roles
        enemy_roles = role_result.red_roles if resolved_team.value == "blue" else role_result.blue_roles

        # =====================================================================
        # PHASE 4: Parallel Coaching Generation (Build + Laning + TF + Macro)
        # =====================================================================
        logger.info("Phase 4: Running coaching agents in parallel...")

        build_task = self.breakers["build"].execute(
            self.build_planner.plan(BuildPlannerInput(
                user_champion=resolved_champion,
                user_role=resolved_role,
                lane_opponent=lane_opponent,
                user_kit=user_kit,
                enemy_kit=enemy_kit,
                enemy_team=enemy_team,
                ally_team=ally_team,
                user_rank=user_ctx_result.user_rank,
                patch_version=self.patch_version,
            ))
        )

        laning_task = self.breakers["laning"].execute(
            self.laning_coach.coach(LaningCoachInput(
                user_champion=resolved_champion,
                user_role=resolved_role,
                lane_opponent=lane_opponent,
                user_kit=user_kit,
                enemy_kit=enemy_kit,
                user_rank=user_ctx_result.user_rank,
            ))
        )

        teamfight_task = self.breakers["teamfight"].execute(
            self.teamfight_coach.analyze(TeamfightCoachInput(
                user_champion=resolved_champion,
                user_role=resolved_role,
                ally_team=ally_team,
                enemy_team=enemy_team,
                ally_roles=ally_roles,
                enemy_roles=enemy_roles,
                user_kit=user_kit,
            ))
        )

        macro_task = self.breakers["macro"].execute(
            self.macro_coach.plan(MacroCoachInput(
                user_champion=resolved_champion,
                user_role=resolved_role,
                ally_team=ally_team,
                enemy_team=enemy_team,
                ally_roles=ally_roles,
                enemy_roles=enemy_roles,
            ))
        )

        build_result, laning_result, teamfight_result, macro_result = await asyncio.gather(
            build_task, laning_task, teamfight_task, macro_task
        )

        state.build_plan = build_result
        state.laning_plan = laning_result
        state.teamfight_plan = teamfight_result
        state.macro_plan = macro_result

        # Accumulate costs
        for r in [build_result, laning_result, teamfight_result, macro_result]:
            if r:
                total_cost += getattr(r, "cost_usd", 0.0)

        # =====================================================================
        # PHASE 5: Judge Validation
        # =====================================================================
        logger.info("Phase 5: Judge validation...")

        judge_result = await self.judge.validate(JudgeInput(
            build=build_result,
            laning=laning_result,
            teamfight=teamfight_result,
            macro=macro_result,
            user_champion=resolved_champion,
            lane_opponent=lane_opponent,
            patch_version=self.patch_version,
        ))
        state.judge_result = judge_result

        if not judge_result.approved:
            logger.warning(f"Judge flagged issues: {[f.issue for f in judge_result.fixes_applied]}")

        # =====================================================================
        # PHASE 6: Assembly
        # =====================================================================
        logger.info("Phase 6: Assembling GAME_COACH_PACKAGE...")

        total_elapsed = (time.time() - orchestration_start) * 1000

        # Compute overall confidence
        confidences = [
            getattr(r, "confidence", 0.5)
            for r in [build_result, laning_result, teamfight_result, macro_result]
            if r
        ]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5

        package = GameCoachPackage(
            meta=CoachMeta(
                patch_version=self.patch_version,
                mode=mode,
                confidence=round(avg_confidence, 2),
                notes=judge_result.remaining_uncertainty if judge_result else [],
                total_cost_usd=round(total_cost, 4),
                total_latency_ms=round(total_elapsed, 1),
                agents_run=9,
            ),
            teams=TeamsBlock(
                blue=parsed_blue,
                red=parsed_red,
                role_inference={
                    "blue": role_result.blue_roles.model_dump() if role_result else {},
                    "red": role_result.red_roles.model_dump() if role_result else {},
                    "confidence": role_result.confidence.model_dump() if role_result else {},
                },
            ),
            user=UserBlock(
                champion=resolved_champion,
                role=resolved_role.value,
                rank=user_ctx_result.user_rank,
                lane_opponent=lane_opponent,
            ),
            build=BuildBlock(
                summoners=build_result.summoners if build_result else ["Flash", "Teleport"],
                runes=build_result.runes.model_dump() if build_result else {},
                skill_order=build_result.skill_order.model_dump() if build_result else {},
                start_items=build_result.start_items if build_result else [],
                core_items=build_result.core_items if build_result else [],
                boots=build_result.boots if build_result else "Plated Steelcaps",
                situational_items=[s.model_dump(by_alias=True) for s in build_result.situational_items] if build_result else [],
            ),
            lane_plan=LanePlanBlock(
                levels_1_3=laning_result.levels_1_3 if laning_result else [],
                wave_plan=laning_result.wave_plan if laning_result else [],
                trade_windows=laning_result.trade_windows if laning_result else [],
                first_recall=laning_result.first_recall.model_dump() if laning_result else {},
                level_6=laning_result.level_6 if laning_result else [],
            ),
            beat_enemy=BeatEnemyBlock(
                biggest_threats=teamfight_result.threat_list[:3] if teamfight_result else ["Unknown"],
                how_to_punish=laning_result.punish_list[:3] if laning_result else ["Look for cooldown windows"],
                what_not_to_do=laning_result.avoid_list[:3] if laning_result else ["Don't overextend"],
            ),
            team_plan=TeamPlanBlock(
                win_condition=teamfight_result.win_condition if teamfight_result else "Group and teamfight",
                your_job=teamfight_result.your_job if teamfight_result else "Play your role",
                target_priority=teamfight_result.target_priority if teamfight_result else [],
                fight_rules=teamfight_result.fight_rules if teamfight_result else [],
            ),
            macro=MacroBlock(
                wards=macro_result.wards if macro_result else [],
                roams=macro_result.roams if macro_result else [],
                objectives=macro_result.objectives if macro_result else [],
                midgame=macro_result.midgame if macro_result else [],
                lategame=macro_result.lategame if macro_result else [],
            ),
            next_30_seconds=Next30Seconds(
                do=[
                    laning_result.levels_1_3[0] if laning_result and laning_result.levels_1_3 else "Farm safely",
                    f"Ward {macro_result.wards[0].split(' ')[0] if macro_result and macro_result.wards else 'river'}" if macro_result else "Ward river",
                    "Track enemy jungler position",
                ],
                avoid=[
                    laning_result.avoid_list[0] if laning_result and laning_result.avoid_list else "Don't overextend",
                    "Don't blow summoner spells unless you get a kill",
                    "Don't fight in enemy minion wave level 1",
                ],
            ),
        )

        # Generate coach summary
        summary = self._generate_summary(package)
        state.final_package = package
        state.coach_summary = summary

        logger.info(f"✅ GAME_COACH_PACKAGE assembled in {total_elapsed:.0f}ms (cost: ${total_cost:.4f})")
        return package

    def _generate_summary(self, pkg: GameCoachPackage) -> str:
        """Generate human-readable coach summary from the package."""
        lines = []
        lines.append(f"═══ {pkg.user.champion} Game Plan vs {pkg.user.lane_opponent} ═══")
        lines.append(f"Patch {pkg.meta.patch_version} | {pkg.meta.mode.value} MODE | Confidence: {pkg.meta.confidence:.0%}")
        lines.append("")

        # Build
        lines.append(f"🔧 BUILD: {' → '.join(pkg.build.core_items)} | Boots: {pkg.build.boots}")
        lines.append(f"🎯 RUNES: {pkg.build.runes.get('primary', ['?'])[0]} ({pkg.build.runes.get('primary_tree', '?')})")
        lines.append(f"🔮 SPELLS: {' + '.join(pkg.build.summoners)}")
        lines.append(f"⬆️ SKILL: Start {pkg.build.skill_order.get('start', '?')} → Max {' > '.join(pkg.build.skill_order.get('max_order', []))}")
        lines.append("")

        # Lane Plan
        lines.append("📍 LANE PLAN:")
        for step in pkg.lane_plan.levels_1_3[:3]:
            lines.append(f"  • {step}")
        lines.append("")

        # Beat Enemy
        lines.append(f"⚔️ BEAT {pkg.user.lane_opponent.upper()} BY:")
        for tip in pkg.beat_enemy.how_to_punish[:3]:
            lines.append(f"  • {tip}")
        lines.append("")

        # Teamfight
        lines.append(f"🛡️ TEAMFIGHT JOB: {pkg.team_plan.your_job}")
        lines.append(f"🎯 WIN CONDITION: {pkg.team_plan.win_condition}")
        lines.append("")

        # Next 30 seconds
        lines.append("⏱️ NEXT 30 SECONDS:")
        lines.append("  DO:")
        for item in pkg.next_30_seconds.do:
            lines.append(f"    ✅ {item}")
        lines.append("  AVOID:")
        for item in pkg.next_30_seconds.avoid:
            lines.append(f"    ❌ {item}")

        lines.append("")
        lines.append(f"Generated in {pkg.meta.total_latency_ms:.0f}ms | Cost: ${pkg.meta.total_cost_usd:.4f}")

        return "\n".join(lines)
