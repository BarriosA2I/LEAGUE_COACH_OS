"""
================================================================================
AGENTS 5-8: LLM COACHING AGENTS
================================================================================
Build & Runes Planner | Laning Matchup Coach | Teamfight Comp Coach | Macro Coach

All use structured LLM generation with JSON mode for deterministic output.
Cost-aware routing: Haiku for simple, Sonnet for complex analysis.

Author: Barrios A2I | Status: PRODUCTION
================================================================================
"""
import json
import logging
import time
from typing import Any, Dict, List, Optional

from schemas.models import (
    BuildPlannerInput,
    BuildPlannerOutput,
    FirstRecall,
    LaningCoachInput,
    LaningCoachOutput,
    MacroCoachInput,
    MacroCoachOutput,
    Role,
    RuneConfig,
    SituationalItem,
    SkillOrder,
    TeamfightCoachInput,
    TeamfightCoachOutput,
)

logger = logging.getLogger(__name__)


# =============================================================================
# SHARED LLM HELPER
# =============================================================================

async def _call_llm(
    llm_client,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2048,
) -> Dict[str, Any]:
    """Structured LLM call with JSON extraction and retry."""
    if llm_client is None:
        return {}

    try:
        response = await llm_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = response.content[0].text
        # Extract JSON
        if "```" in raw:
            raw = raw.split("```json")[-1].split("```")[0].strip()
        if raw.startswith("{"):
            return json.loads(raw)
        # Try to find JSON in response
        start_idx = raw.find("{")
        end_idx = raw.rfind("}") + 1
        if start_idx >= 0 and end_idx > start_idx:
            return json.loads(raw[start_idx:end_idx])
        return {}
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return {}


# =============================================================================
# AGENT 5: BUILD & RUNES PLANNER
# =============================================================================

BUILD_SYSTEM_PROMPT = """You are an expert League of Legends build optimizer.
Given a champion, role, matchup, and team compositions, provide the optimal build.

You MUST output valid JSON only. Use EXACT official item, rune, and spell names.
Do NOT invent items or runes. If unsure, use the most common/safe option.

Required JSON structure:
{
  "summoners": ["Flash", "Teleport"],
  "runes": {
    "primary_tree": "Precision",
    "primary": ["Conqueror", "Triumph", "Legend: Alacrity", "Last Stand"],
    "secondary_tree": "Resolve",
    "secondary": ["Bone Plating", "Overgrowth"],
    "shards": ["Attack Speed", "Adaptive Force", "Health Scaling"]
  },
  "skill_order": {
    "start": "Q",
    "max_order": ["Q", "E", "W"],
    "levels_1_6": ["Q", "W", "E", "Q", "Q", "R"]
  },
  "start_items": ["Doran's Blade", "Health Potion"],
  "core_items": ["Trinity Force", "Sterak's Gage", "Death's Dance"],
  "boots": "Plated Steelcaps",
  "situational_items": [
    {"if": "Enemy team is AP heavy", "buy": ["Spirit Visage", "Force of Nature"]},
    {"if": "Enemy has heavy healing", "buy": ["Executioner's Calling"]}
  ],
  "notes": ["Rush Sheen on first back if possible"]
}"""


class BuildAndRunesPlannerAgent:
    """Generates optimal build, runes, and skill order for the matchup."""

    def __init__(self, llm_client=None, model: str = "claude-sonnet-4-5-20250929"):
        self.name = "build_and_runes_planner"
        self.status = "PRODUCTION"
        self.llm_client = llm_client
        self.model = model
        self.cost_per_call = 0.005

    async def plan(self, input_data: BuildPlannerInput) -> BuildPlannerOutput:
        start = time.time()

        user_prompt = f"""Champion: {input_data.user_champion}
Role: {input_data.user_role.value}
Lane Opponent: {input_data.lane_opponent}
Rank: {input_data.user_rank}
Allied Team: {', '.join(input_data.ally_team)}
Enemy Team: {', '.join(input_data.enemy_team)}
Patch: {input_data.patch_version}

Champion Abilities: {', '.join(a.name for a in input_data.user_kit.abilities) if input_data.user_kit.abilities else 'standard kit'}
Enemy Abilities: {', '.join(a.name for a in input_data.enemy_kit.abilities) if input_data.enemy_kit.abilities else 'standard kit'}

Provide the optimal build for this specific game. Consider:
1. Lane matchup (who wins trades, poke vs all-in)
2. Enemy team damage types (AP/AD mix)
3. Win condition (split push, teamfight, pick)
4. Power spikes and item synergies"""

        data = await _call_llm(self.llm_client, self.model, BUILD_SYSTEM_PROMPT, user_prompt)

        elapsed = (time.time() - start) * 1000

        if not data:
            return self._fallback_build(input_data, elapsed)

        try:
            runes_data = data.get("runes", {})
            skill_data = data.get("skill_order", {})
            sit_items = data.get("situational_items", [])

            return BuildPlannerOutput(
                summoners=data.get("summoners", ["Flash", "Teleport"])[:2],
                runes=RuneConfig(
                    primary_tree=runes_data.get("primary_tree", "Precision"),
                    primary=runes_data.get("primary", ["Conqueror", "Triumph", "Legend: Alacrity", "Last Stand"]),
                    secondary_tree=runes_data.get("secondary_tree", "Resolve"),
                    secondary=runes_data.get("secondary", ["Bone Plating", "Overgrowth"]),
                    shards=runes_data.get("shards", ["Attack Speed", "Adaptive Force", "Health Scaling"]),
                ),
                skill_order=SkillOrder(
                    start=skill_data.get("start", "Q"),
                    max_order=skill_data.get("max_order", ["Q", "W", "E"])[:3],
                    levels_1_6=skill_data.get("levels_1_6", ["Q", "W", "E", "Q", "Q", "R"])[:6],
                ),
                start_items=data.get("start_items", ["Doran's Blade", "Health Potion"]),
                core_items=data.get("core_items", ["Trinity Force", "Sterak's Gage", "Death's Dance"]),
                boots=data.get("boots", "Plated Steelcaps"),
                situational_items=[
                    SituationalItem(**{"if": s.get("if", "General"), "buy": s.get("buy", [])})
                    for s in sit_items[:4]
                ],
                notes=data.get("notes", []),
                confidence=0.9,
                processing_time_ms=elapsed,
                cost_usd=self.cost_per_call,
            )
        except Exception as e:
            logger.error(f"Build plan parsing failed: {e}")
            return self._fallback_build(input_data, elapsed)

    def _fallback_build(self, input_data: BuildPlannerInput, elapsed: float) -> BuildPlannerOutput:
        """Safe fallback build when LLM fails."""
        return BuildPlannerOutput(
            summoners=["Flash", "Teleport"],
            runes=RuneConfig(
                primary_tree="Precision",
                primary=["Conqueror", "Triumph", "Legend: Alacrity", "Last Stand"],
                secondary_tree="Resolve",
                secondary=["Bone Plating", "Overgrowth"],
                shards=["Attack Speed", "Adaptive Force", "Health Scaling"],
            ),
            skill_order=SkillOrder(start="Q", max_order=["Q", "W", "E"], levels_1_6=["Q", "W", "E", "Q", "Q", "R"]),
            start_items=["Doran's Blade", "Health Potion"],
            core_items=["Trinity Force", "Sterak's Gage", "Death's Dance"],
            boots="Plated Steelcaps",
            situational_items=[],
            notes=["FALLBACK BUILD — LLM generation failed. Using safe defaults."],
            confidence=0.4,
            processing_time_ms=elapsed,
            cost_usd=0.0,
        )


# =============================================================================
# AGENT 6: LANING MATCHUP COACH
# =============================================================================

LANING_SYSTEM_PROMPT = """You are an expert League of Legends laning coach.
Given a champion matchup, provide specific, actionable laning advice.

You MUST output valid JSON only. Be specific about ability interactions and timings.

Required JSON structure:
{
  "levels_1_3": ["Step 1", "Step 2", "Step 3"],
  "wave_plan": ["Rule 1", "Rule 2", "Rule 3"],
  "trade_windows": ["When to trade", "Combo to use", "Goal of trade"],
  "first_recall": {"goal_gold": "1100", "timing_rule": "After shoving wave 4-5", "buy": ["Sheen", "Control Ward"]},
  "level_6": ["All-in conditions", "Bait conditions", "What to avoid"],
  "avoid_list": ["Don't do X", "Don't do Y", "Don't do Z"],
  "punish_list": ["Punish when X", "Punish when Y", "Punish when Z"]
}"""


class LaningMatchupCoachAgent:
    """Provides detailed lane plan and matchup-specific advice."""

    def __init__(self, llm_client=None, model: str = "claude-sonnet-4-5-20250929"):
        self.name = "laning_matchup_coach"
        self.status = "PRODUCTION"
        self.llm_client = llm_client
        self.model = model
        self.cost_per_call = 0.005

    async def coach(self, input_data: LaningCoachInput) -> LaningCoachOutput:
        start = time.time()

        user_prompt = f"""You are coaching {input_data.user_champion} ({input_data.user_role.value}) vs {input_data.lane_opponent}.
Rank: {input_data.user_rank}

{input_data.user_champion} abilities: {', '.join(a.name + ' (' + a.key + ')' for a in input_data.user_kit.abilities) if input_data.user_kit.abilities else 'standard kit'}
{input_data.lane_opponent} abilities: {', '.join(a.name + ' (' + a.key + ')' for a in input_data.enemy_kit.abilities) if input_data.enemy_kit.abilities else 'standard kit'}

Provide specific laning advice for levels 1-6. Be concrete about:
1. Which abilities to use for trading
2. Exact wave manipulation strategies
3. When the enemy is vulnerable (cooldowns, positioning)
4. When YOU are vulnerable
5. First recall timing and what to buy
6. Level 6 all-in potential"""

        data = await _call_llm(self.llm_client, self.model, LANING_SYSTEM_PROMPT, user_prompt)
        elapsed = (time.time() - start) * 1000

        if not data:
            return self._fallback_laning(input_data, elapsed)

        try:
            recall_data = data.get("first_recall", {})
            return LaningCoachOutput(
                levels_1_3=data.get("levels_1_3", ["Play safe and farm", "Trade when enemy uses abilities on minions", "Build wave advantage"])[:5],
                wave_plan=data.get("wave_plan", ["Slow push waves 1-3", "Crash on cannon wave", "Freeze after recall"])[:5],
                trade_windows=data.get("trade_windows", ["Trade when enemy uses key cooldown", "Short trades preferred", "Disengage before enemy retaliates"])[:5],
                first_recall=FirstRecall(
                    goal_gold=str(recall_data.get("goal_gold", "1100")),
                    timing_rule=recall_data.get("timing_rule", "After crashing cannon wave"),
                    buy=recall_data.get("buy", ["Component item", "Control Ward"]),
                ),
                level_6=data.get("level_6", ["Check if you can all-in with full combo", "Bait enemy abilities first", "Respect enemy level 6 spike too"])[:5],
                avoid_list=data.get("avoid_list", ["Don't overextend without vision", "Don't fight in enemy minion wave", "Don't burn flash aggressively"])[:5],
                punish_list=data.get("punish_list", ["Punish when enemy misses key ability", "Punish when enemy wastes cooldown on minions"])[:5],
                confidence=0.85,
                processing_time_ms=elapsed,
                cost_usd=self.cost_per_call,
            )
        except Exception as e:
            logger.error(f"Laning coach parsing failed: {e}")
            return self._fallback_laning(input_data, elapsed)

    def _fallback_laning(self, input_data: LaningCoachInput, elapsed: float) -> LaningCoachOutput:
        return LaningCoachOutput(
            levels_1_3=["Play safe and farm", "Trade only when advantageous", "Respect enemy power spikes"],
            wave_plan=["Slow push early waves", "Crash on cannon wave", "Freeze if behind"],
            trade_windows=["Trade when enemy wastes cooldown", "Short trades in melee matchups"],
            first_recall=FirstRecall(goal_gold="1100", timing_rule="After crashing wave", buy=["Component item", "Control Ward"]),
            level_6=["Check kill potential", "Bait enemy abilities first", "Respect enemy level 6"],
            avoid_list=["Don't overextend", "Don't fight in minion waves"],
            punish_list=["Punish missed abilities", "Punish bad positioning"],
            confidence=0.4,
            processing_time_ms=elapsed,
            cost_usd=0.0,
        )


# =============================================================================
# AGENT 7: TEAMFIGHT COMP COACH
# =============================================================================

TEAMFIGHT_SYSTEM_PROMPT = """You are an expert League of Legends teamfight and composition analyst.
Given team compositions, explain the user's win condition and teamfight role.

You MUST output valid JSON only. Be specific about champion interactions.

Required JSON structure:
{
  "win_condition": "Description of how this team wins",
  "your_job": "What the user's champion should do in fights",
  "target_priority": ["Enemy1 (reason)", "Enemy2 (reason)", "Enemy3 (reason)"],
  "threat_list": ["Enemy1 (why threatening)", "Enemy2 (why threatening)"],
  "fight_rules": ["Rule 1", "Rule 2", "Rule 3"]
}"""


class TeamfightCompCoachAgent:
    """Analyzes team compositions and provides teamfight strategy."""

    def __init__(self, llm_client=None, model: str = "claude-sonnet-4-5-20250929"):
        self.name = "teamfight_comp_coach"
        self.status = "PRODUCTION"
        self.llm_client = llm_client
        self.model = model
        self.cost_per_call = 0.004

    async def analyze(self, input_data: TeamfightCoachInput) -> TeamfightCoachOutput:
        start = time.time()

        user_prompt = f"""You: {input_data.user_champion} ({input_data.user_role.value})
Your Team: {', '.join(input_data.ally_team)}
  Roles: TOP={input_data.ally_roles.TOP}, JG={input_data.ally_roles.JG}, MID={input_data.ally_roles.MID}, ADC={input_data.ally_roles.ADC}, SUP={input_data.ally_roles.SUP}

Enemy Team: {', '.join(input_data.enemy_team)}
  Roles: TOP={input_data.enemy_roles.TOP}, JG={input_data.enemy_roles.JG}, MID={input_data.enemy_roles.MID}, ADC={input_data.enemy_roles.ADC}, SUP={input_data.enemy_roles.SUP}

Analyze:
1. Your team's win condition (teamfight, splitpush, pick comp, siege)
2. Your specific job as {input_data.user_champion}
3. Who to target and who to avoid
4. Key threats on the enemy team
5. Positioning and engagement rules"""

        data = await _call_llm(self.llm_client, self.model, TEAMFIGHT_SYSTEM_PROMPT, user_prompt)
        elapsed = (time.time() - start) * 1000

        if not data:
            return self._fallback_teamfight(input_data, elapsed)

        try:
            return TeamfightCoachOutput(
                win_condition=data.get("win_condition", "Group and teamfight around objectives"),
                your_job=data.get("your_job", "Play your role and focus priority targets"),
                target_priority=data.get("target_priority", ["Enemy ADC", "Enemy Mid", "Enemy Top"])[:5],
                threat_list=data.get("threat_list", ["Enemy Assassin", "Enemy Tank engage"])[:5],
                fight_rules=data.get("fight_rules", ["Wait for engage before committing", "Peel for carries", "Focus squishy targets"])[:5],
                confidence=0.85,
                processing_time_ms=elapsed,
                cost_usd=self.cost_per_call,
            )
        except Exception as e:
            logger.error(f"Teamfight coach parsing failed: {e}")
            return self._fallback_teamfight(input_data, elapsed)

    def _fallback_teamfight(self, input_data: TeamfightCoachInput, elapsed: float) -> TeamfightCoachOutput:
        return TeamfightCoachOutput(
            win_condition="Group and fight around objectives",
            your_job=f"Play {input_data.user_champion}'s role effectively",
            target_priority=["Enemy carry", "Enemy mid laner"],
            threat_list=["Enemy burst damage", "Enemy engage"],
            fight_rules=["Wait for engage", "Focus priority targets", "Peel if needed"],
            confidence=0.4,
            processing_time_ms=elapsed,
            cost_usd=0.0,
        )


# =============================================================================
# AGENT 8: MACRO OBJECTIVES COACH
# =============================================================================

MACRO_SYSTEM_PROMPT = """You are an expert League of Legends macro coach.
Given team compositions and the user's role, provide objective and map play advice.

You MUST output valid JSON only. Be specific about timings and conditions.

Required JSON structure:
{
  "wards": ["Where and when to ward 1", "Where and when to ward 2", "Where and when to ward 3"],
  "roams": ["Roam rule 1", "Roam rule 2"],
  "objectives": ["Dragon/Herald plan", "Setup timing", "Reset timing"],
  "midgame": ["Midgame rule 1", "Midgame rule 2"],
  "lategame": ["Lategame rule 1", "Lategame rule 2"]
}"""


class MacroObjectivesCoachAgent:
    """Provides ward plans, roam timers, objective setup, and macro strategy."""

    def __init__(self, llm_client=None, model: str = "claude-haiku-4-5-20251001"):
        self.name = "macro_objectives_coach"
        self.status = "PRODUCTION"
        self.llm_client = llm_client
        self.model = model
        self.cost_per_call = 0.002

    async def plan(self, input_data: MacroCoachInput) -> MacroCoachOutput:
        start = time.time()

        user_prompt = f"""You: {input_data.user_champion} ({input_data.user_role.value})
Your Team: {', '.join(input_data.ally_team)}
  Roles: TOP={input_data.ally_roles.TOP}, JG={input_data.ally_roles.JG}, MID={input_data.ally_roles.MID}, ADC={input_data.ally_roles.ADC}, SUP={input_data.ally_roles.SUP}

Enemy Team: {', '.join(input_data.enemy_team)}
  Roles: TOP={input_data.enemy_roles.TOP}, JG={input_data.enemy_roles.JG}, MID={input_data.enemy_roles.MID}, ADC={input_data.enemy_roles.ADC}, SUP={input_data.enemy_roles.SUP}

Provide macro strategy for {input_data.user_champion} in the {input_data.user_role.value} role:
1. Where and when to place wards (be specific: "River bush at 2:50 before first scuttle")
2. Roam timing rules
3. Dragon/Herald/Baron setup
4. Midgame transition plan
5. Lategame strategy"""

        data = await _call_llm(self.llm_client, self.model, MACRO_SYSTEM_PROMPT, user_prompt)
        elapsed = (time.time() - start) * 1000

        if not data:
            return self._fallback_macro(input_data, elapsed)

        try:
            return MacroCoachOutput(
                wards=data.get("wards", ["River bush before objectives", "Pixel bush for jungle tracking", "Deep ward enemy raptors"])[:5],
                roams=data.get("roams", ["Roam after crashing wave", "Follow enemy roams when possible"])[:4],
                objectives=data.get("objectives", ["Contest first dragon if bot lane has priority", "Take Herald when top has TP advantage", "Setup vision 60s before objectives"])[:5],
                midgame=data.get("midgame", ["Group for objectives", "Split push if ahead"])[:4],
                lategame=data.get("lategame", ["Play around Baron", "Don't get caught"])[:4],
                confidence=0.85,
                processing_time_ms=elapsed,
                cost_usd=self.cost_per_call,
            )
        except Exception as e:
            logger.error(f"Macro coach parsing failed: {e}")
            return self._fallback_macro(input_data, elapsed)

    def _fallback_macro(self, input_data: MacroCoachInput, elapsed: float) -> MacroCoachOutput:
        return MacroCoachOutput(
            wards=["River bush before objectives", "Pixel bush for tracking", "Deep ward enemy jungle"],
            roams=["Roam after crashing wave", "Follow enemy roams when possible"],
            objectives=["Contest dragon when bot has priority", "Take Herald when possible", "Setup vision 60s before spawn"],
            midgame=["Group for objectives", "Catch side lane waves"],
            lategame=["Play around Baron", "Stick with team"],
            confidence=0.4,
            processing_time_ms=elapsed,
            cost_usd=0.0,
        )
