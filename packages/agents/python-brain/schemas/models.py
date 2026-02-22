"""
================================================================================
LEAGUE COACHING SWARM — PYDANTIC SCHEMAS
================================================================================
Full typed IO contracts for all 9 agents + GAME_COACH_PACKAGE output schema.
Strict validation, immutable state updates, production-grade.

Author: Barrios A2I | Version: 1.0.0
================================================================================
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# ENUMS
# =============================================================================

class CoachMode(str, Enum):
    FAST = "FAST"
    FULL = "FULL"

class Role(str, Enum):
    TOP = "Top"
    JUNGLE = "Jungle"
    MID = "Mid"
    ADC = "ADC"
    SUPPORT = "Support"
    UNKNOWN = "Unknown"

class TeamSide(str, Enum):
    BLUE = "blue"
    RED = "red"

class CRAGAction(str, Enum):
    GENERATE = "generate"
    DECOMPOSE = "decompose"
    WEB_SEARCH = "web_search"

class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# =============================================================================
# AGENT 1: VISION_PARSER — IO
# =============================================================================

class VisionParserInput(BaseModel):
    image_data: str = Field(..., description="Base64-encoded loading screen image or file path")
    image_format: str = Field(default="png", description="Image format: png, jpg, webp")

class ChampionSlot(BaseModel):
    champion_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    skin_detected: Optional[str] = None
    position_index: int = Field(ge=0, le=9)

class VisionParserOutput(BaseModel):
    blue_team: List[str] = Field(min_length=5, max_length=5)
    red_team: List[str] = Field(min_length=5, max_length=5)
    blue_team_details: List[ChampionSlot] = Field(default_factory=list)
    red_team_details: List[ChampionSlot] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0.0, le=1.0)
    unknown_slots: List[int] = Field(default_factory=list)
    processing_time_ms: float = 0.0
    cost_usd: float = 0.0


# =============================================================================
# AGENT 2: USER_CONTEXT_RESOLVER — IO
# =============================================================================

class UserContextInput(BaseModel):
    user_champion: Optional[str] = None
    user_role: Optional[Role] = None
    user_rank: Optional[str] = None
    blue_team: List[str] = Field(min_length=5, max_length=5)
    red_team: List[str] = Field(min_length=5, max_length=5)

class UserContextOutput(BaseModel):
    user_champion: str
    user_role: Role
    user_rank: str = "Unknown"
    user_team: TeamSide
    lane_opponent: str = "Unknown"
    needs_clarification: bool = False
    clarification_prompt: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.9)


# =============================================================================
# AGENT 3: ROLE_INFERENCE_ENGINE — IO
# =============================================================================

class RoleInferenceInput(BaseModel):
    blue_team: List[str] = Field(min_length=5, max_length=5)
    red_team: List[str] = Field(min_length=5, max_length=5)
    user_champion: Optional[str] = None
    user_role: Optional[Role] = None

class RoleAssignment(BaseModel):
    TOP: str
    JG: str
    MID: str
    ADC: str
    SUP: str

class RoleConfidence(BaseModel):
    TOP: float = Field(ge=0.0, le=1.0)
    JG: float = Field(ge=0.0, le=1.0)
    MID: float = Field(ge=0.0, le=1.0)
    ADC: float = Field(ge=0.0, le=1.0)
    SUP: float = Field(ge=0.0, le=1.0)

class RoleInferenceOutput(BaseModel):
    blue_roles: RoleAssignment
    red_roles: RoleAssignment
    confidence: RoleConfidence
    notes: List[str] = Field(default_factory=list)
    ambiguous_assignments: List[str] = Field(default_factory=list)
    processing_time_ms: float = 0.0


# =============================================================================
# AGENT 4: CANON_KNOWLEDGE_FETCHER — IO
# =============================================================================

class CanonKnowledgeInput(BaseModel):
    user_champion: str
    lane_opponent: str
    all_champions: List[str]
    patch_version: Optional[str] = None

class AbilityInfo(BaseModel):
    name: str
    key: str  # Q, W, E, R, Passive
    description: str
    cooldown: Optional[str] = None
    cost: Optional[str] = None
    damage_type: Optional[str] = None

class ChampionKit(BaseModel):
    champion_name: str
    title: str = ""
    tags: List[str] = Field(default_factory=list)  # Fighter, Mage, etc.
    abilities: List[AbilityInfo] = Field(default_factory=list)
    base_stats: Dict[str, Any] = Field(default_factory=dict)

class CanonKnowledgeOutput(BaseModel):
    user_kit: ChampionKit
    enemy_kit: ChampionKit
    all_kits: Dict[str, ChampionKit] = Field(default_factory=dict)
    patch_version: str
    patch_is_current: bool = True
    available_items: Dict[str, Any] = Field(default_factory=dict)
    available_runes: Dict[str, Any] = Field(default_factory=dict)
    processing_time_ms: float = 0.0
    cost_usd: float = 0.0


# =============================================================================
# AGENT 5: BUILD_AND_RUNES_PLANNER — IO
# =============================================================================

class BuildPlannerInput(BaseModel):
    user_champion: str
    user_role: Role
    lane_opponent: str
    user_kit: ChampionKit
    enemy_kit: ChampionKit
    enemy_team: List[str]
    ally_team: List[str]
    user_rank: str = "Unknown"
    patch_version: str = ""

class RuneConfig(BaseModel):
    primary_tree: str
    primary: List[str] = Field(min_length=4, max_length=4)
    secondary_tree: str
    secondary: List[str] = Field(min_length=2, max_length=2)
    shards: List[str] = Field(min_length=3, max_length=3)

class SkillOrder(BaseModel):
    start: str = Field(pattern=r"^[QWE]$")
    max_order: List[str] = Field(min_length=3, max_length=3)
    levels_1_6: List[str] = Field(min_length=6, max_length=6)

class SituationalItem(BaseModel):
    condition: str = Field(alias="if")
    buy: List[str] = Field(min_length=1, max_length=3)

    class Config:
        populate_by_name = True

class BuildPlannerOutput(BaseModel):
    summoners: List[str] = Field(min_length=2, max_length=2)
    runes: RuneConfig
    skill_order: SkillOrder
    start_items: List[str] = Field(min_length=1, max_length=3)
    core_items: List[str] = Field(min_length=2, max_length=4)
    boots: str
    situational_items: List[SituationalItem] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.9)
    processing_time_ms: float = 0.0
    cost_usd: float = 0.0


# =============================================================================
# AGENT 6: LANING_MATCHUP_COACH — IO
# =============================================================================

class LaningCoachInput(BaseModel):
    user_champion: str
    user_role: Role
    lane_opponent: str
    user_kit: ChampionKit
    enemy_kit: ChampionKit
    user_rank: str = "Unknown"

class FirstRecall(BaseModel):
    goal_gold: str
    timing_rule: str
    buy: List[str]

class LaningCoachOutput(BaseModel):
    levels_1_3: List[str] = Field(min_length=2, max_length=5)
    wave_plan: List[str] = Field(min_length=2, max_length=5)
    trade_windows: List[str] = Field(min_length=2, max_length=5)
    first_recall: FirstRecall
    level_6: List[str] = Field(min_length=2, max_length=5)
    avoid_list: List[str] = Field(min_length=1, max_length=5)
    punish_list: List[str] = Field(min_length=1, max_length=5)
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)
    processing_time_ms: float = 0.0
    cost_usd: float = 0.0


# =============================================================================
# AGENT 7: TEAMFIGHT_COMP_COACH — IO
# =============================================================================

class TeamfightCoachInput(BaseModel):
    user_champion: str
    user_role: Role
    ally_team: List[str]
    enemy_team: List[str]
    ally_roles: RoleAssignment
    enemy_roles: RoleAssignment
    user_kit: ChampionKit

class TeamfightCoachOutput(BaseModel):
    win_condition: str
    your_job: str
    target_priority: List[str] = Field(min_length=2, max_length=5)
    threat_list: List[str] = Field(min_length=1, max_length=5)
    fight_rules: List[str] = Field(min_length=2, max_length=5)
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)
    processing_time_ms: float = 0.0
    cost_usd: float = 0.0


# =============================================================================
# AGENT 8: MACRO_OBJECTIVES_COACH — IO
# =============================================================================

class MacroCoachInput(BaseModel):
    user_champion: str
    user_role: Role
    ally_team: List[str]
    enemy_team: List[str]
    ally_roles: RoleAssignment
    enemy_roles: RoleAssignment

class MacroCoachOutput(BaseModel):
    wards: List[str] = Field(min_length=2, max_length=5)
    roams: List[str] = Field(min_length=1, max_length=4)
    objectives: List[str] = Field(min_length=2, max_length=5)
    midgame: List[str] = Field(min_length=1, max_length=4)
    lategame: List[str] = Field(min_length=1, max_length=4)
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)
    processing_time_ms: float = 0.0
    cost_usd: float = 0.0


# =============================================================================
# AGENT 9: FINAL_JUDGE_VALIDATOR — IO
# =============================================================================

class JudgeInput(BaseModel):
    build: BuildPlannerOutput
    laning: LaningCoachOutput
    teamfight: TeamfightCoachOutput
    macro: MacroCoachOutput
    user_champion: str
    lane_opponent: str
    patch_version: str

class ValidationFix(BaseModel):
    field: str
    issue: str
    fix_applied: str

class JudgeOutput(BaseModel):
    approved: bool
    fixes_applied: List[ValidationFix] = Field(default_factory=list)
    remaining_uncertainty: List[str] = Field(default_factory=list)
    schema_valid: bool = True
    cross_agent_consistent: bool = True
    processing_time_ms: float = 0.0


# =============================================================================
# FINAL OUTPUT: GAME_COACH_PACKAGE
# =============================================================================

class CoachMeta(BaseModel):
    patch_version: str
    mode: CoachMode
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    confidence: float = Field(ge=0.0, le=1.0)
    notes: List[str] = Field(default_factory=list)
    total_cost_usd: float = 0.0
    total_latency_ms: float = 0.0
    agents_run: int = 9

class TeamsBlock(BaseModel):
    blue: List[str]
    red: List[str]
    role_inference: Dict[str, Any]

class UserBlock(BaseModel):
    champion: str
    role: str
    rank: str
    lane_opponent: str

class BuildBlock(BaseModel):
    summoners: List[str]
    runes: Dict[str, Any]
    skill_order: Dict[str, Any]
    start_items: List[str]
    core_items: List[str]
    boots: str
    situational_items: List[Dict[str, Any]]

class LanePlanBlock(BaseModel):
    levels_1_3: List[str]
    wave_plan: List[str]
    trade_windows: List[str]
    first_recall: Dict[str, Any]
    level_6: List[str]

class BeatEnemyBlock(BaseModel):
    biggest_threats: List[str]
    how_to_punish: List[str]
    what_not_to_do: List[str]

class TeamPlanBlock(BaseModel):
    win_condition: str
    your_job: str
    target_priority: List[str]
    fight_rules: List[str]

class MacroBlock(BaseModel):
    wards: List[str]
    roams: List[str]
    objectives: List[str]
    midgame: List[str]
    lategame: List[str]

class Next30Seconds(BaseModel):
    do: List[str] = Field(min_length=3, max_length=3)
    avoid: List[str] = Field(min_length=3, max_length=3)

class GameCoachPackage(BaseModel):
    """The full GAME_COACH_PACKAGE output schema — strict compliance required."""
    meta: CoachMeta
    teams: TeamsBlock
    user: UserBlock
    build: BuildBlock
    lane_plan: LanePlanBlock
    beat_enemy: BeatEnemyBlock
    team_plan: TeamPlanBlock
    macro: MacroBlock
    next_30_seconds: Next30Seconds


# =============================================================================
# ORCHESTRATOR STATE (LangGraph TypedDict equivalent)
# =============================================================================

class SwarmState(BaseModel):
    """Immutable state for LangGraph orchestrator. Updated via dict merge."""
    # Inputs
    image_data: Optional[str] = None
    user_champion: Optional[str] = None
    user_role: Optional[Role] = None
    user_rank: Optional[str] = None
    patch_version: Optional[str] = None
    mode: CoachMode = CoachMode.FAST

    # Agent outputs (populated during execution)
    vision: Optional[VisionParserOutput] = None
    user_context: Optional[UserContextOutput] = None
    role_inference: Optional[RoleInferenceOutput] = None
    canon_knowledge: Optional[CanonKnowledgeOutput] = None
    build_plan: Optional[BuildPlannerOutput] = None
    laning_plan: Optional[LaningCoachOutput] = None
    teamfight_plan: Optional[TeamfightCoachOutput] = None
    macro_plan: Optional[MacroCoachOutput] = None
    judge_result: Optional[JudgeOutput] = None

    # Tracking
    agent_statuses: Dict[str, AgentStatus] = Field(default_factory=dict)
    errors: List[Dict[str, str]] = Field(default_factory=list)
    total_cost_usd: float = 0.0
    total_latency_ms: float = 0.0

    # Final output
    final_package: Optional[GameCoachPackage] = None
    coach_summary: Optional[str] = None


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "CoachMode", "Role", "TeamSide", "CRAGAction", "AgentStatus",
    "VisionParserInput", "VisionParserOutput", "ChampionSlot",
    "UserContextInput", "UserContextOutput",
    "RoleInferenceInput", "RoleInferenceOutput", "RoleAssignment", "RoleConfidence",
    "CanonKnowledgeInput", "CanonKnowledgeOutput", "ChampionKit", "AbilityInfo",
    "BuildPlannerInput", "BuildPlannerOutput", "RuneConfig", "SkillOrder", "SituationalItem",
    "LaningCoachInput", "LaningCoachOutput", "FirstRecall",
    "TeamfightCoachInput", "TeamfightCoachOutput",
    "MacroCoachInput", "MacroCoachOutput",
    "JudgeInput", "JudgeOutput", "ValidationFix",
    "GameCoachPackage", "CoachMeta", "TeamsBlock", "UserBlock",
    "BuildBlock", "LanePlanBlock", "BeatEnemyBlock", "TeamPlanBlock",
    "MacroBlock", "Next30Seconds", "SwarmState",
]
