"""
================================================================================
LEAGUE COACH OS — LIVE COACHING AGENTS
================================================================================
Mid-game coaching that fires on EVERY PrintScreen throughout the game.

Screenshot at ANY point → you get:
  • What to buy RIGHT NOW (adaptive to enemy builds + gold + game phase)
  • How to beat your laner (trades, cooldowns, power spikes, kill windows)
  • Bot lane: how to beat BOTH enemy ADC + Support
  • After death: what went wrong + what to change
  • At shop: exact purchase order for your gold

Each agent uses Claude Vision to read the screenshot directly —
no OCR, no pixel scraping. Just "look at this and tell me what's happening."

Author: Barrios A2I | Version: 2.0.0
================================================================================
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger("league_coach.live")


# =============================================================================
# LIVE COACHING SCHEMAS
# =============================================================================

class LiveCoachingMode(str, Enum):
    """What type of coaching to deliver based on game state."""
    PREGAME_PLAN = "pregame_plan"           # Loading screen → full plan
    LANE_COACHING = "lane_coaching"          # In-game → how to beat laner
    BUILD_ADVICE = "build_advice"            # Tab/Shop → what to buy
    DEATH_REVIEW = "death_review"            # Death screen → what went wrong
    TEAMFIGHT_PREP = "teamfight_prep"        # Mid/late game → team priorities
    OBJECTIVE_CALL = "objective_call"         # Near objective → setup advice
    GAME_REVIEW = "game_review"              # Post-game → improvement tips


class ItemRecommendation(BaseModel):
    """A single item purchase recommendation."""
    item_name: str = Field(description="Item to buy")
    gold_cost: int = Field(default=0, description="Gold cost")
    reason: str = Field(description="Why this item right now")
    priority: int = Field(default=1, description="Buy order priority (1=first)")
    situational: bool = Field(default=False, description="Is this a situational swap")
    replaces: Optional[str] = Field(default=None, description="What planned item this replaces")


class LanerThreat(BaseModel):
    """Analysis of how to beat a specific enemy laner."""
    champion: str = Field(description="Enemy champion name")
    role: str = Field(default="", description="Their role")
    threat_level: str = Field(default="medium", description="low/medium/high/extreme")

    # How to fight them
    trade_pattern: str = Field(default="", description="Best trade combo/pattern")
    avoid_when: str = Field(default="", description="When NOT to fight them")
    punish_when: str = Field(default="", description="When to go aggressive")
    key_cooldowns: List[str] = Field(default_factory=list, description="Abilities to track")
    kill_window: str = Field(default="", description="When you can all-in for kill")

    # Current state adjustments
    ahead_strategy: str = Field(default="", description="What to do if you're ahead")
    behind_strategy: str = Field(default="", description="What to do if you're behind")
    even_strategy: str = Field(default="", description="What to do if even")

    # Items they might build and how to counter
    likely_items: List[str] = Field(default_factory=list)
    counter_items: List[str] = Field(default_factory=list)


class BotLaneMatchup(BaseModel):
    """Dual-threat analysis for bot lane (enemy ADC + Support)."""
    enemy_adc: LanerThreat = Field(description="Enemy ADC analysis")
    enemy_support: LanerThreat = Field(description="Enemy Support analysis")

    # Combined bot lane advice
    lane_dynamic: str = Field(default="", description="How their duo plays together")
    their_kill_combo: str = Field(default="", description="How they try to kill you")
    your_win_condition: str = Field(default="", description="How YOU win this lane")
    level_2_plan: str = Field(default="", description="Level 2 race strategy")
    level_6_plan: str = Field(default="", description="Level 6 power shift")
    bush_control: str = Field(default="", description="Ward/bush priority")
    gank_setup: str = Field(default="", description="How to set up ganks")


class DeathReview(BaseModel):
    """Analysis of what went wrong when you died."""
    killed_by: str = Field(default="Unknown", description="Who killed you")
    death_reason: str = Field(default="", description="Why you died (1 sentence)")
    what_to_change: str = Field(default="", description="Specific adjustment")
    positioning_fix: str = Field(default="", description="Where to stand instead")
    was_avoidable: bool = Field(default=True)
    tip: str = Field(default="", description="Quick recovery tip")


class LiveCoachingPackage(BaseModel):
    """Complete coaching output for any mid-game screenshot."""
    mode: LiveCoachingMode
    timestamp: float = Field(default_factory=time.time)
    game_time_estimate: str = Field(default="unknown", description="Estimated game time")
    game_phase: str = Field(default="", description="early/mid/late")

    # Always present
    headline: str = Field(default="", description="1-line summary of what to do RIGHT NOW")
    next_30_seconds: List[str] = Field(default_factory=list, description="Top 3 things to do")

    # Build advice (present in most modes)
    buy_now: List[ItemRecommendation] = Field(default_factory=list)
    full_build_path: List[str] = Field(default_factory=list, description="Updated full build order")
    build_adjustment_reason: str = Field(default="", description="Why build changed from original")

    # Laner advice (present in lane_coaching mode)
    laner_matchup: Optional[LanerThreat] = None
    bot_lane_matchup: Optional[BotLaneMatchup] = None

    # Death review (present in death_review mode)
    death_review: Optional[DeathReview] = None

    # Teamfight (present in teamfight/late game)
    teamfight_priority: str = Field(default="", description="Who to focus in fights")
    positioning: str = Field(default="", description="Where to stand in fights")

    # Warnings
    warnings: List[str] = Field(default_factory=list, description="Danger alerts")


# =============================================================================
# VISION PROMPTS — What we ask Claude to see in each screenshot
# =============================================================================

VISION_PROMPTS = {
    "tab_scoreboard": """You are analyzing a League of Legends TAB scoreboard screenshot.

Extract ALL of the following information you can see:

1. **All 10 players**: Champion name, KDA (kills/deaths/assists), CS count, items they have
2. **My champion**: Identify which champion the user is playing (highlighted row or summoner name)
3. **Gold difference**: Who appears to be ahead/behind
4. **Game time**: If visible in the top center
5. **Turret plates/towers**: Any visible objective info

Format your response as JSON:
{{
  "game_time": "MM:SS or estimate",
  "user_champion": "name",
  "user_kda": [kills, deaths, assists],
  "user_cs": number,
  "user_items": ["item1", "item2", ...],
  "user_gold": number_if_visible,
  "lane_opponent": "champion name",
  "lane_opponent_items": ["item1", "item2", ...],
  "lane_opponent_kda": [k, d, a],
  "all_players": [
    {{"champion": "name", "team": "blue/red", "kda": [k,d,a], "cs": n, "items": [...]}}
  ],
  "who_is_fed": "champion name or none",
  "gold_state": "ahead/behind/even"
}}""",

    "shop_open": """You are analyzing a League of Legends shop screenshot.

Extract:
1. **Current gold**: How much gold the player has (shown in gold text)
2. **Items already purchased**: What's in the player's inventory (bottom center)
3. **What they're browsing**: What category or item they're looking at
4. **Champion being played**: If identifiable from abilities/portrait

Format as JSON:
{{
  "current_gold": number,
  "current_items": ["item1", "item2", ...],
  "browsing": "item or category name",
  "champion": "name if identifiable"
}}""",

    "in_game": """You are analyzing a League of Legends in-game screenshot (active gameplay).

Look at the screen and extract:
1. **Champion being played**: Identify from abilities on HUD or character model
2. **Health/Mana status**: Approximate percentage
3. **Lane state**: Where are minions? Is the wave pushing toward us or enemy?
4. **Enemy laner visible?**: Who are they, approximate health
5. **Minimap state**: Where are enemy champions visible? Any missing?
6. **Level**: Player's current level if visible
7. **Items**: What's in the inventory slots (bottom center HUD)
8. **Summoner spells**: Which ones and are they on cooldown
9. **Danger level**: Is the player in a safe or dangerous position?

Format as JSON:
{{
  "champion": "name",
  "health_pct": 0-100,
  "mana_pct": 0-100,
  "level": number,
  "current_items": ["item1", ...],
  "wave_state": "pushing_to_us / pushing_to_them / frozen / crashing / no_wave",
  "enemy_visible": {{"champion": "name", "health_pct": 0-100}} or null,
  "enemies_on_minimap": number_visible,
  "enemies_missing": number_missing,
  "position_safety": "safe / risky / danger",
  "game_time_estimate": "early / mid / late",
  "lane": "top / mid / bot / jungle / river"
}}""",

    "death_screen": """You are analyzing a League of Legends death/gray screen.

The screen is desaturated (gray overlay) because the player just died.
Look for:
1. **Death timer**: Countdown number in the center
2. **Death recap**: If visible, who dealt damage and how much
3. **Killer**: Who killed the player
4. **Location**: Where on the map did they die (check minimap)
5. **Game state**: What was happening when they died

Format as JSON:
{{
  "respawn_timer": seconds_if_visible,
  "killed_by": "champion name",
  "death_location": "lane / river / jungle / tower",
  "damage_sources": [{{"champion": "name", "damage_type": "physical/magic/true", "amount": n}}],
  "game_time_estimate": "early / mid / late"
}}""",

    "post_game": """You are analyzing a League of Legends post-game stats screen.

Extract:
1. **Result**: Victory or Defeat
2. **Player's champion and stats**: KDA, CS, damage dealt, gold earned
3. **Notable performances**: Who carried, who fed
4. **Game duration**
5. **Items built**

Format as JSON:
{{
  "result": "victory / defeat",
  "game_duration": "MM:SS",
  "user_champion": "name",
  "user_kda": [k, d, a],
  "user_cs": number,
  "user_damage": number,
  "user_gold": number,
  "user_items": ["item1", ...],
  "mvp": "champion name",
  "key_takeaway": "one sentence"
}}"""
}


# =============================================================================
# COACHING PROMPT TEMPLATES — What advice to generate per state
# =============================================================================

COACHING_PROMPTS = {
    "build_advice": """You are an expert League of Legends coach analyzing a mid-game state.

**Context from this game session:**
{session_context}

**What was just extracted from the screenshot:**
{extracted_data}

**Original pre-game build plan:**
{original_build}

Based on the CURRENT game state, give build advice:

1. **BUY NOW**: What should the player buy with their current gold? List items in priority order.
   - Consider what enemies are building (armor? MR? health?)
   - Consider if the player is ahead, behind, or even
   - Consider game phase (early = components, mid = complete items, late = situational)

2. **BUILD ADJUSTMENT**: Should the original build plan change?
   - Enemy stacking armor → build armor penetration (Last Whisper, Serylda's, Black Cleaver)
   - Enemy stacking MR → build magic penetration (Void Staff, Shadowflame)
   - Enemy has healing → build anti-heal (Executioner's, Oblivion Orb)
   - Getting bursted → build defensive (Zhonya's, Guardian Angel, Death's Dance)
   - Enemy assassin fed → build survival (Maw, Sterak's, GA)
   - Team needs waveclear → build Hydra/Statikk

3. **COMPONENT PRIORITY**: If they can't afford a full item, what component to buy first and why.

Respond in this JSON format:
{{
  "buy_now": [
    {{"item": "name", "gold": cost, "reason": "why", "priority": 1}},
    ...
  ],
  "full_build_update": ["item1", "item2", "item3", "item4", "item5", "item6", "boots"],
  "build_changed": true/false,
  "change_reason": "why the build changed from original plan",
  "dont_buy": ["item to avoid and why"],
  "power_spike": "what completing your next item unlocks"
}}""",

    "lane_coaching_solo": """You are an expert League of Legends coach giving LIVE lane advice.

**Your champion:** {user_champion} ({user_role})
**Enemy laner:** {enemy_laner}
**Game phase:** {game_phase}
**Current game state from screenshot:** {extracted_data}
**Session context:** {session_context}

Give SPECIFIC, ACTIONABLE lane coaching:

1. **RIGHT NOW** (next 30 seconds): What should they do immediately?
2. **TRADING PATTERN**: Exact combo to trade with the enemy
   - What ability to start with
   - When to disengage
   - What to avoid getting hit by
3. **COOLDOWN WINDOWS**: Which enemy abilities to wait for before trading
4. **WAVE MANAGEMENT**: Should they push, freeze, or slow push right now?
5. **KILL WINDOW**: Can they kill the enemy? What needs to happen?
6. **DANGER CHECK**: Is a gank likely? Should they play safe?
7. **POWER SPIKES**: Any upcoming level or item advantage?

If the player is BEHIND: Focus on safe farming, avoiding deaths, what to give up and what NOT to give up.
If the player is AHEAD: How to press the advantage, when to dive, when to roam.

Respond in JSON:
{{
  "headline": "One sentence — what to do RIGHT NOW",
  "next_30_seconds": ["tip1", "tip2", "tip3"],
  "trade_pattern": "exact combo description",
  "avoid": "what NOT to do",
  "punish_when": "enemy does X → you do Y",
  "key_cooldowns": ["ability1 (Xs)", "ability2 (Xs)"],
  "kill_window": "can you kill? how?",
  "wave_management": "push / freeze / slow push and why",
  "gank_danger": "low / medium / high + why",
  "power_spike_incoming": "next spike and when",
  "state": "ahead / behind / even",
  "if_ahead": "how to press advantage",
  "if_behind": "how to safely farm and recover"
}}""",

    "lane_coaching_botlane": """You are an expert League of Legends coach giving LIVE bot lane advice.

**Your champion:** {user_champion} ({user_role})
**Your support/ADC partner:** {lane_partner}
**Enemy ADC:** {enemy_adc}
**Enemy Support:** {enemy_support}
**Game phase:** {game_phase}
**Current game state from screenshot:** {extracted_data}
**Session context:** {session_context}

Bot lane is a 2v2 — coaching must address BOTH enemies:

1. **RIGHT NOW**: What should they do in the next 30 seconds?

2. **ENEMY ADC ({enemy_adc}) MATCHUP**:
   - Their trading pattern and how to dodge/counter it
   - Their power spikes (BF Sword, level 6, etc.)
   - When they're vulnerable

3. **ENEMY SUPPORT ({enemy_support}) MATCHUP**:
   - Their engage/poke/catch pattern
   - What ability is the biggest threat
   - How to position against them
   - Bush control priority

4. **THEIR KILL COMBO**: How do they try to kill you as a duo?
   - Support engages with X → ADC follows with Y → you die if Z
   - How to survive their all-in

5. **YOUR WIN CONDITION**: How does your bot lane duo beat theirs?
   - Level 2 race (who hits 2 first matters — first wave + 3 melee of second)
   - Trade windows when support abilities are down
   - All-in vs poke vs sustain dynamic

6. **WAVE MANAGEMENT**: Push for level 2? Freeze? Let them push for gank setup?

7. **GANK SETUP**: How to set up for your jungler. What CC chain to use.

Respond in JSON:
{{
  "headline": "One sentence — what to do RIGHT NOW",
  "next_30_seconds": ["tip1", "tip2", "tip3"],
  "enemy_adc": {{
    "champion": "{enemy_adc}",
    "trade_pattern": "how they trade",
    "dodge_this": "key ability to avoid",
    "punish_when": "when they're vulnerable",
    "threat_level": "low/medium/high"
  }},
  "enemy_support": {{
    "champion": "{enemy_support}",
    "engage_pattern": "how they engage/poke",
    "dodge_this": "key ability to avoid",
    "punish_when": "when they're vulnerable",
    "threat_level": "low/medium/high",
    "bush_control": "who should control bushes and why"
  }},
  "their_kill_combo": "step by step how they kill you",
  "your_win_condition": "how your duo wins this lane",
  "level_2_plan": "level 2 race strategy",
  "level_6_shift": "how level 6 changes the lane",
  "wave_management": "push / freeze / slow push and why",
  "gank_setup": "how to set up ganks for your jungler",
  "positioning": "where to stand relative to minions and support"
}}""",

    "death_review": """You are an expert League of Legends coach reviewing a death.

**Your champion:** {user_champion} ({user_role})
**What we can see:** {extracted_data}
**Session context (including previous deaths):** {session_context}

This is the player's death #{death_count} this game.

Give a QUICK, NON-TILTING death review:

1. **What happened**: 1 sentence — why they died
2. **Was it avoidable?**: Yes/No and how
3. **What to change**: ONE specific thing to do differently
4. **Recovery plan**: What to do when they respawn
5. **Positioning fix**: Where they should have been standing
6. **Mental reset**: Quick encouragement (not toxic positivity — real talk)

{"If this is death #3+, also address the PATTERN — are they dying the same way repeatedly? What's the common thread?" if death_count >= 3 else ""}

Respond in JSON:
{{
  "headline": "You died because X — here's the fix",
  "death_reason": "1 sentence",
  "avoidable": true/false,
  "what_to_change": "specific adjustment",
  "positioning_fix": "where to stand instead",
  "on_respawn": "first thing to do when alive",
  "mental_note": "quick real talk encouragement",
  "pattern_warning": "if dying repeatedly to same thing, call it out"
}}""",

    "teamfight_prep": """You are an expert League of Legends coach preparing the player for teamfights.

**Your champion:** {user_champion} ({user_role})
**Full team comps:**
  Blue: {blue_team}
  Red: {red_team}
**Current items/state:** {extracted_data}
**Session context:** {session_context}

Give teamfight coaching:

1. **YOUR JOB**: What is your specific role in teamfights with this champion?
2. **FOCUS TARGET**: Who should you prioritize attacking and why?
3. **THREATS**: Who is the biggest threat to you? How to avoid them?
4. **POSITIONING**: Front/back/flank? Where to stand before fight starts?
5. **COMBO**: What's your teamfight combo/rotation?
6. **WIN CONDITION**: What needs to happen for your team to win the fight?
7. **DO NOT**: Critical mistakes to avoid

Respond in JSON:
{{
  "headline": "Your job in teamfights: X",
  "your_role": "frontline / backline / assassin / peel / engage",
  "focus_target": "champion + why",
  "biggest_threat": "champion + how to avoid",
  "positioning": "where to stand",
  "combo": "teamfight ability rotation",
  "win_condition": "what has to happen",
  "do_not": ["mistake1", "mistake2"],
  "if_behind": "how to teamfight from behind"
}}"""
}


# =============================================================================
# LIVE COACHING ENGINE
# =============================================================================

class LiveCoachingEngine:
    """
    The brain that processes every PrintScreen and delivers context-aware coaching.

    Workflow:
    1. GameStateDetector identifies what the player is looking at
    2. Claude Vision extracts data from the screenshot
    3. This engine combines extracted data + session history + matchup knowledge
    4. Delivers a LiveCoachingPackage with exactly what the player needs

    The engine maintains a GameSession that accumulates knowledge:
    - Loading screen → sets team comps, matchups, initial build plan
    - Each subsequent screenshot → updates items, KDA, game phase
    - Build advice adapts: "enemy building armor? switch to penetration"
    - Lane advice adapts: "you're 0/2 now — here's how to play safe and recover"
    """

    def __init__(self, anthropic_client=None, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic_client
        self.model = model

        # Import GameSession from game_state_detector
        from .game_state_detector import GameSession, GameState, GamePhase
        self.session = GameSession()
        self._GameState = GameState
        self._GamePhase = GamePhase

    async def coach_from_screenshot(
        self,
        image_b64: str,
        game_state: str,
        game_phase: str = "",
        session_context: Optional[Dict] = None,
    ) -> LiveCoachingPackage:
        """
        Main entry point — takes a screenshot and game state, returns coaching.

        Args:
            image_b64: Base64 encoded screenshot
            game_state: Detected game state (from GameStateDetector)
            game_phase: early_laning / mid_laning / mid_game / late_game
            session_context: Accumulated game session data
        """
        GS = self._GameState

        # Step 1: Extract data from the screenshot using Vision
        extracted = await self._extract_from_screenshot(image_b64, game_state)

        # Step 2: Update session with new data
        self._update_session(game_state, extracted)

        # Step 3: Generate coaching based on state
        ctx = session_context or self.session.get_context_for_coaching()

        if game_state == GS.LOADING_SCREEN.value:
            # Existing pre-game flow handles this
            return LiveCoachingPackage(
                mode=LiveCoachingMode.PREGAME_PLAN,
                headline="Loading screen detected — running full pre-game plan",
                game_phase="pre_game",
            )

        elif game_state == GS.TAB_SCOREBOARD.value:
            return await self._coach_from_tab(extracted, ctx)

        elif game_state == GS.SHOP_OPEN.value:
            return await self._coach_from_shop(extracted, ctx)

        elif game_state == GS.DEATH_SCREEN.value:
            return await self._coach_from_death(extracted, ctx)

        elif game_state in (GS.IN_GAME_LANING.value,
                            GS.IN_GAME_TEAMFIGHT.value,
                            GS.IN_GAME_OBJECTIVES.value):
            return await self._coach_from_ingame(extracted, ctx, game_phase)

        elif game_state == GS.POST_GAME_STATS.value:
            return await self._coach_from_postgame(extracted, ctx)

        else:
            return LiveCoachingPackage(
                mode=LiveCoachingMode.LANE_COACHING,
                headline="Screenshot captured — couldn't determine game state",
                warnings=["Try pressing TAB then PrintScreen for best analysis"],
            )

    # =========================================================================
    # VISION EXTRACTION
    # =========================================================================

    async def _extract_from_screenshot(self, image_b64: str, game_state: str) -> Dict:
        """Use Claude Vision to extract structured data from the screenshot."""
        GS = self._GameState

        # Pick the right vision prompt
        prompt_key = {
            GS.TAB_SCOREBOARD.value: "tab_scoreboard",
            GS.SHOP_OPEN.value: "shop_open",
            GS.DEATH_SCREEN.value: "death_screen",
            GS.POST_GAME_STATS.value: "post_game",
        }.get(game_state, "in_game")

        vision_prompt = VISION_PROMPTS[prompt_key]

        if not self.client:
            logger.warning("No Anthropic client — returning mock extraction")
            return {"mock": True, "game_state": game_state}

        try:
            response = await asyncio.wait_for(
                self._call_vision(image_b64, vision_prompt),
                timeout=10.0
            )
            # Parse JSON from response
            return self._parse_json_response(response)
        except asyncio.TimeoutError:
            logger.error("Vision extraction timed out (10s)")
            return {"error": "timeout", "game_state": game_state}
        except Exception as e:
            logger.error(f"Vision extraction failed: {e}")
            return {"error": str(e), "game_state": game_state}

    async def _call_vision(self, image_b64: str, prompt: str) -> str:
        """Call Claude Vision API with the screenshot."""
        # Handle both sync and async clients
        import anthropic

        messages = [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_b64,
                    }
                },
                {
                    "type": "text",
                    "text": prompt,
                }
            ]
        }]

        if hasattr(self.client, 'messages') and hasattr(self.client.messages, 'create'):
            # Sync client
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=messages,
            )
        else:
            # Async client
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=messages,
            )

        return response.content[0].text

    def _parse_json_response(self, text: str) -> Dict:
        """Extract JSON from Claude's response (handles markdown code blocks)."""
        import re

        # Try to find JSON in code blocks
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try raw JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in text
        brace_start = text.find('{')
        brace_end = text.rfind('}')
        if brace_start >= 0 and brace_end > brace_start:
            try:
                return json.loads(text[brace_start:brace_end + 1])
            except json.JSONDecodeError:
                pass

        logger.warning(f"Could not parse JSON from response: {text[:200]}")
        return {"raw_text": text}

    # =========================================================================
    # SESSION UPDATES
    # =========================================================================

    def _update_session(self, game_state: str, extracted: Dict):
        """Update the game session with newly extracted data."""
        GS = self._GameState

        if extracted.get("error") or extracted.get("mock"):
            return

        if game_state == GS.TAB_SCOREBOARD.value:
            self.session.update_from_tab(extracted)

        elif game_state == GS.SHOP_OPEN.value:
            if "current_items" in extracted:
                self.session.user_items = extracted["current_items"]
            if "current_gold" in extracted:
                self.session.user_gold = extracted["current_gold"]

        elif game_state == GS.DEATH_SCREEN.value:
            self.session.update_from_death(extracted)

        elif game_state in (GS.IN_GAME_LANING.value,):
            if "level" in extracted:
                self.session.user_level = extracted["level"]
            if "current_items" in extracted:
                self.session.user_items = extracted["current_items"]

        self.session.screenshots_analyzed += 1

    # =========================================================================
    # COACHING GENERATORS
    # =========================================================================

    async def _coach_from_tab(self, extracted: Dict, ctx: Dict) -> LiveCoachingPackage:
        """Generate coaching from TAB scoreboard — build advice + enemy tracking."""
        coaching_prompt = COACHING_PROMPTS["build_advice"].format(
            session_context=json.dumps(ctx, indent=2),
            extracted_data=json.dumps(extracted, indent=2),
            original_build=json.dumps(ctx.get("build_plan", {}), indent=2),
        )

        advice = await self._generate_coaching(coaching_prompt)

        buy_now = []
        for item in advice.get("buy_now", []):
            buy_now.append(ItemRecommendation(
                item_name=item.get("item", ""),
                gold_cost=item.get("gold", 0),
                reason=item.get("reason", ""),
                priority=item.get("priority", 1),
            ))

        # Also generate lane advice if we know the matchup
        laner_matchup = None
        bot_matchup = None
        if ctx.get("user", {}).get("role") in ("ADC", "Support"):
            bot_matchup = await self._generate_botlane_coaching(extracted, ctx)
        elif ctx.get("user", {}).get("lane_opponent"):
            laner_matchup = await self._generate_laner_coaching(extracted, ctx)

        return LiveCoachingPackage(
            mode=LiveCoachingMode.BUILD_ADVICE,
            headline=f"Build update: {advice.get('buy_now', [{}])[0].get('item', 'check items')} → {advice.get('buy_now', [{}])[0].get('reason', '')}",
            game_phase=ctx.get("elapsed_minutes", 0) and (
                "early" if ctx["elapsed_minutes"] < 14 else
                "mid" if ctx["elapsed_minutes"] < 25 else "late"
            ),
            buy_now=buy_now,
            full_build_path=advice.get("full_build_update", []),
            build_adjustment_reason=advice.get("change_reason", ""),
            laner_matchup=laner_matchup,
            bot_lane_matchup=bot_matchup,
            next_30_seconds=advice.get("next_30_seconds", [
                f"Buy {advice.get('buy_now', [{}])[0].get('item', 'components')}" if advice.get("buy_now") else "Check shop",
                "Ward river before returning to lane",
                "Look for TP play if available",
            ]),
            warnings=advice.get("dont_buy", []),
        )

    async def _coach_from_shop(self, extracted: Dict, ctx: Dict) -> LiveCoachingPackage:
        """Generate coaching when shop is open — exact purchase recommendations."""
        gold = extracted.get("current_gold", 0)
        current_items = extracted.get("current_items", ctx.get("user", {}).get("current_items", []))

        coaching_prompt = COACHING_PROMPTS["build_advice"].format(
            session_context=json.dumps(ctx, indent=2),
            extracted_data=json.dumps(extracted, indent=2),
            original_build=json.dumps(ctx.get("build_plan", {}), indent=2),
        )

        advice = await self._generate_coaching(coaching_prompt)

        buy_now = []
        for item in advice.get("buy_now", []):
            buy_now.append(ItemRecommendation(
                item_name=item.get("item", ""),
                gold_cost=item.get("gold", 0),
                reason=item.get("reason", ""),
                priority=item.get("priority", 1),
            ))

        headline = f"You have {gold}g — buy: {', '.join(i.item_name for i in buy_now[:3])}" if buy_now else "Buy components toward your next item"

        return LiveCoachingPackage(
            mode=LiveCoachingMode.BUILD_ADVICE,
            headline=headline,
            buy_now=buy_now,
            full_build_path=advice.get("full_build_update", []),
            build_adjustment_reason=advice.get("change_reason", ""),
            next_30_seconds=[
                f"Buy {buy_now[0].item_name}" if buy_now else "Build toward core item",
                "Don't forget Control Ward (75g)" if gold > 200 else "Save for next back",
                advice.get("power_spike", "Complete your item for a power spike"),
            ],
        )

    async def _coach_from_death(self, extracted: Dict, ctx: Dict) -> LiveCoachingPackage:
        """Generate coaching after dying — quick review + recovery plan."""
        death_count = len(self.session.deaths)

        coaching_prompt = COACHING_PROMPTS["death_review"].format(
            user_champion=ctx.get("user", {}).get("champion", "Unknown"),
            user_role=ctx.get("user", {}).get("role", "Unknown"),
            extracted_data=json.dumps(extracted, indent=2),
            session_context=json.dumps(ctx, indent=2),
            death_count=death_count,
        )

        advice = await self._generate_coaching(coaching_prompt)

        death_review = DeathReview(
            killed_by=advice.get("killed_by", extracted.get("killed_by", "Unknown")),
            death_reason=advice.get("death_reason", ""),
            what_to_change=advice.get("what_to_change", ""),
            positioning_fix=advice.get("positioning_fix", ""),
            was_avoidable=advice.get("avoidable", True),
            tip=advice.get("mental_note", ""),
        )

        warnings = []
        if death_count >= 3:
            pattern = advice.get("pattern_warning", "")
            if pattern:
                warnings.append(f"⚠️ Death pattern: {pattern}")

        return LiveCoachingPackage(
            mode=LiveCoachingMode.DEATH_REVIEW,
            headline=advice.get("headline", f"Death #{death_count} — {advice.get('death_reason', 'reviewing')}"),
            death_review=death_review,
            next_30_seconds=[
                advice.get("on_respawn", "Farm safely when you respawn"),
                advice.get("what_to_change", "Adjust positioning"),
                "Buy items if you have gold",
            ],
            warnings=warnings,
        )

    async def _coach_from_ingame(self, extracted: Dict, ctx: Dict,
                                   game_phase: str) -> LiveCoachingPackage:
        """Generate coaching from active in-game screenshot."""
        user_role = ctx.get("user", {}).get("role", "")

        # Determine if bot lane or solo lane
        if user_role in ("ADC", "Support"):
            return await self._coach_botlane_ingame(extracted, ctx, game_phase)
        else:
            return await self._coach_solo_ingame(extracted, ctx, game_phase)

    async def _coach_solo_ingame(self, extracted: Dict, ctx: Dict,
                                   game_phase: str) -> LiveCoachingPackage:
        """Lane coaching for solo laners (Top/Mid/Jungle)."""
        user_champ = ctx.get("user", {}).get("champion", "Unknown")
        user_role = ctx.get("user", {}).get("role", "Unknown")
        enemy = ctx.get("user", {}).get("lane_opponent", "Unknown")

        # Late game → teamfight coaching instead
        elapsed = ctx.get("elapsed_minutes", 0)
        if elapsed > 20 or game_phase in ("mid_game", "late_game"):
            return await self._coach_teamfight(extracted, ctx)

        coaching_prompt = COACHING_PROMPTS["lane_coaching_solo"].format(
            user_champion=user_champ,
            user_role=user_role,
            enemy_laner=enemy,
            game_phase=game_phase or "laning",
            extracted_data=json.dumps(extracted, indent=2),
            session_context=json.dumps(ctx, indent=2),
        )

        advice = await self._generate_coaching(coaching_prompt)

        laner = LanerThreat(
            champion=enemy,
            role=user_role,
            threat_level=advice.get("state", "medium"),
            trade_pattern=advice.get("trade_pattern", ""),
            avoid_when=advice.get("avoid", ""),
            punish_when=advice.get("punish_when", ""),
            key_cooldowns=advice.get("key_cooldowns", []),
            kill_window=advice.get("kill_window", ""),
            ahead_strategy=advice.get("if_ahead", ""),
            behind_strategy=advice.get("if_behind", ""),
            even_strategy="",
        )

        return LiveCoachingPackage(
            mode=LiveCoachingMode.LANE_COACHING,
            headline=advice.get("headline", f"vs {enemy}: {advice.get('trade_pattern', 'trade smart')}"),
            game_phase=game_phase,
            next_30_seconds=advice.get("next_30_seconds", []),
            laner_matchup=laner,
            warnings=[
                f"Gank danger: {advice.get('gank_danger', 'unknown')}"
            ] if advice.get("gank_danger", "").lower() in ("medium", "high") else [],
        )

    async def _coach_botlane_ingame(self, extracted: Dict, ctx: Dict,
                                      game_phase: str) -> LiveCoachingPackage:
        """Lane coaching for bot lane — analyzes BOTH enemy ADC + Support."""
        user_champ = ctx.get("user", {}).get("champion", "Unknown")
        user_role = ctx.get("user", {}).get("role", "Unknown")

        # Determine lane partner and enemies
        roles = ctx.get("teams", {}).get("roles", {})
        user_team = ctx.get("user", {}).get("team", "blue")
        enemy_team = "red" if user_team == "blue" else "blue"

        # Find bot lane players
        team_roles = roles.get(user_team, {})
        enemy_roles = roles.get(enemy_team, {})

        lane_partner = ""
        enemy_adc = ""
        enemy_support = ""

        for champ, role in team_roles.items():
            if champ != user_champ and role in ("ADC", "Support"):
                lane_partner = champ
                break

        for champ, role in enemy_roles.items():
            if role == "ADC":
                enemy_adc = champ
            elif role == "Support":
                enemy_support = champ

        # Fallback to lane opponent if roles not fully resolved
        if not enemy_adc:
            enemy_adc = ctx.get("user", {}).get("lane_opponent", "Unknown")
        if not enemy_support:
            enemy_support = "Unknown"

        # Late game → teamfight
        elapsed = ctx.get("elapsed_minutes", 0)
        if elapsed > 20 or game_phase in ("mid_game", "late_game"):
            return await self._coach_teamfight(extracted, ctx)

        coaching_prompt = COACHING_PROMPTS["lane_coaching_botlane"].format(
            user_champion=user_champ,
            user_role=user_role,
            lane_partner=lane_partner or "Unknown",
            enemy_adc=enemy_adc,
            enemy_support=enemy_support,
            game_phase=game_phase or "laning",
            extracted_data=json.dumps(extracted, indent=2),
            session_context=json.dumps(ctx, indent=2),
        )

        advice = await self._generate_coaching(coaching_prompt)

        # Build dual-threat analysis
        adc_threat = LanerThreat(
            champion=enemy_adc,
            role="ADC",
            threat_level=advice.get("enemy_adc", {}).get("threat_level", "medium"),
            trade_pattern=advice.get("enemy_adc", {}).get("trade_pattern", ""),
            avoid_when=advice.get("enemy_adc", {}).get("dodge_this", ""),
            punish_when=advice.get("enemy_adc", {}).get("punish_when", ""),
        )

        sup_threat = LanerThreat(
            champion=enemy_support,
            role="Support",
            threat_level=advice.get("enemy_support", {}).get("threat_level", "medium"),
            trade_pattern=advice.get("enemy_support", {}).get("engage_pattern", ""),
            avoid_when=advice.get("enemy_support", {}).get("dodge_this", ""),
            punish_when=advice.get("enemy_support", {}).get("punish_when", ""),
        )

        bot_matchup = BotLaneMatchup(
            enemy_adc=adc_threat,
            enemy_support=sup_threat,
            lane_dynamic=advice.get("your_win_condition", ""),
            their_kill_combo=advice.get("their_kill_combo", ""),
            your_win_condition=advice.get("your_win_condition", ""),
            level_2_plan=advice.get("level_2_plan", ""),
            level_6_plan=advice.get("level_6_shift", ""),
            bush_control=advice.get("enemy_support", {}).get("bush_control", ""),
            gank_setup=advice.get("gank_setup", ""),
        )

        return LiveCoachingPackage(
            mode=LiveCoachingMode.LANE_COACHING,
            headline=advice.get("headline", f"vs {enemy_adc}/{enemy_support}: {advice.get('your_win_condition', 'play safe')}"),
            game_phase=game_phase,
            next_30_seconds=advice.get("next_30_seconds", []),
            bot_lane_matchup=bot_matchup,
            warnings=[
                f"Watch for: {advice.get('their_kill_combo', 'enemy all-in')}"
            ],
        )

    async def _coach_teamfight(self, extracted: Dict, ctx: Dict) -> LiveCoachingPackage:
        """Teamfight coaching for mid/late game."""
        user_champ = ctx.get("user", {}).get("champion", "Unknown")
        user_role = ctx.get("user", {}).get("role", "Unknown")
        blue = ctx.get("teams", {}).get("blue", [])
        red = ctx.get("teams", {}).get("red", [])

        coaching_prompt = COACHING_PROMPTS["teamfight_prep"].format(
            user_champion=user_champ,
            user_role=user_role,
            blue_team=", ".join(blue) if blue else "Unknown",
            red_team=", ".join(red) if red else "Unknown",
            extracted_data=json.dumps(extracted, indent=2),
            session_context=json.dumps(ctx, indent=2),
        )

        advice = await self._generate_coaching(coaching_prompt)

        return LiveCoachingPackage(
            mode=LiveCoachingMode.TEAMFIGHT_PREP,
            headline=advice.get("headline", f"Teamfight: {advice.get('your_role', 'play your role')}"),
            game_phase="mid" if ctx.get("elapsed_minutes", 0) < 25 else "late",
            teamfight_priority=advice.get("focus_target", ""),
            positioning=advice.get("positioning", ""),
            next_30_seconds=[
                f"Focus: {advice.get('focus_target', 'carries')}",
                f"Avoid: {advice.get('biggest_threat', 'assassins')}",
                advice.get("win_condition", "Group and fight together"),
            ],
            warnings=advice.get("do_not", []),
        )

    async def _coach_from_postgame(self, extracted: Dict, ctx: Dict) -> LiveCoachingPackage:
        """Post-game review — what to improve."""
        result = extracted.get("result", "unknown")
        kda = extracted.get("user_kda", [0, 0, 0])

        return LiveCoachingPackage(
            mode=LiveCoachingMode.GAME_REVIEW,
            headline=f"{'GG WP!' if result == 'victory' else 'Tough game.'} KDA: {kda[0]}/{kda[1]}/{kda[2]}",
            game_phase="post_game",
            next_30_seconds=[
                extracted.get("key_takeaway", "Review your deaths and positioning"),
                f"Deaths: {kda[1]} — {'good survival' if kda[1] <= 3 else 'work on dying less'}",
                "Queue up and apply what you learned",
            ],
        )

    # =========================================================================
    # HELPER: Generate lane/bot coaching (reusable from tab state)
    # =========================================================================

    async def _generate_laner_coaching(self, extracted: Dict, ctx: Dict) -> Optional[LanerThreat]:
        """Generate laner matchup advice (called from tab/build contexts too)."""
        enemy = ctx.get("user", {}).get("lane_opponent", "")
        if not enemy:
            return None

        coaching_prompt = COACHING_PROMPTS["lane_coaching_solo"].format(
            user_champion=ctx.get("user", {}).get("champion", "Unknown"),
            user_role=ctx.get("user", {}).get("role", "Unknown"),
            enemy_laner=enemy,
            game_phase="laning",
            extracted_data=json.dumps(extracted, indent=2),
            session_context=json.dumps(ctx, indent=2),
        )

        advice = await self._generate_coaching(coaching_prompt)

        return LanerThreat(
            champion=enemy,
            trade_pattern=advice.get("trade_pattern", ""),
            avoid_when=advice.get("avoid", ""),
            punish_when=advice.get("punish_when", ""),
            key_cooldowns=advice.get("key_cooldowns", []),
            kill_window=advice.get("kill_window", ""),
            ahead_strategy=advice.get("if_ahead", ""),
            behind_strategy=advice.get("if_behind", ""),
        )

    async def _generate_botlane_coaching(self, extracted: Dict, ctx: Dict) -> Optional[BotLaneMatchup]:
        """Generate bot lane matchup advice (called from tab/build contexts too)."""
        roles = ctx.get("teams", {}).get("roles", {})
        enemy_team = "red" if ctx.get("user", {}).get("team") == "blue" else "blue"
        enemy_roles = roles.get(enemy_team, {})

        enemy_adc = ""
        enemy_support = ""
        for champ, role in enemy_roles.items():
            if role == "ADC":
                enemy_adc = champ
            elif role == "Support":
                enemy_support = champ

        if not enemy_adc and not enemy_support:
            return None

        # Quick version — just the key points
        prompt = f"""Quick bot lane matchup analysis:
Your champion: {ctx.get('user', {}).get('champion', 'Unknown')}
Enemy ADC: {enemy_adc or 'Unknown'}
Enemy Support: {enemy_support or 'Unknown'}
Current items: {json.dumps(extracted.get('user_items', []))}
Enemy items: {json.dumps(extracted.get('lane_opponent_items', []))}

Respond in JSON with: enemy_adc_threat, enemy_support_threat, their_kill_combo, your_win_condition, positioning"""

        advice = await self._generate_coaching(prompt)

        return BotLaneMatchup(
            enemy_adc=LanerThreat(champion=enemy_adc or "Unknown"),
            enemy_support=LanerThreat(champion=enemy_support or "Unknown"),
            their_kill_combo=advice.get("their_kill_combo", ""),
            your_win_condition=advice.get("your_win_condition", ""),
        )

    # =========================================================================
    # LLM CALL
    # =========================================================================

    async def _generate_coaching(self, prompt: str) -> Dict:
        """Generate coaching advice from a prompt. Returns parsed JSON dict."""
        if not self.client:
            logger.warning("No Anthropic client — returning mock coaching")
            return {"mock": True, "headline": "Mock coaching (no API key)"}

        try:
            import anthropic

            messages = [{"role": "user", "content": prompt}]
            system = (
                "You are an expert League of Legends coach. "
                "Give specific, actionable advice. No fluff. "
                "Always respond in valid JSON format. "
                "Be encouraging but direct — like a good coach, not a cheerleader."
            )

            if hasattr(self.client, 'messages') and hasattr(self.client.messages, 'create'):
                response = self.client.messages.create(
                    model="claude-haiku-4-5-20251001",  # Fast model for live coaching
                    max_tokens=1500,
                    system=system,
                    messages=messages,
                )
            else:
                response = await self.client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=1500,
                    system=system,
                    messages=messages,
                )

            return self._parse_json_response(response.content[0].text)

        except Exception as e:
            logger.error(f"Coaching generation failed: {e}")
            return {"error": str(e)}
