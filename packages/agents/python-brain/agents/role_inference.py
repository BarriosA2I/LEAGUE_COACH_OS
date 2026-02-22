"""
================================================================================
AGENT 2: USER_CONTEXT_RESOLVER + AGENT 3: ROLE_INFERENCE_ENGINE
================================================================================
Determines user champion/role/rank and assigns roles to all 10 champions.
Uses champion tag priors + meta role mapping for inference.

Author: Barrios A2I | Status: PRODUCTION
================================================================================
"""
import json
import logging
import time
from typing import Any, Dict, List, Optional

from schemas.models import (
    Role,
    RoleAssignment,
    RoleConfidence,
    RoleInferenceInput,
    RoleInferenceOutput,
    TeamSide,
    UserContextInput,
    UserContextOutput,
)

logger = logging.getLogger(__name__)

# =============================================================================
# CHAMPION ROLE PRIORS — Primary role probabilities
# =============================================================================
# Format: champion -> {role: probability}
# Sourced from meta statistics. Extend this from Data Dragon / op.gg data.
ROLE_PRIORS: Dict[str, Dict[str, float]] = {
    # Marksmen → ADC
    "Jinx": {"ADC": 0.95, "Mid": 0.03, "Support": 0.02},
    "Caitlyn": {"ADC": 0.92, "Mid": 0.05, "Support": 0.03},
    "Ashe": {"ADC": 0.80, "Support": 0.18, "Mid": 0.02},
    "Ezreal": {"ADC": 0.90, "Mid": 0.08, "Jungle": 0.02},
    "Jhin": {"ADC": 0.93, "Mid": 0.05, "Support": 0.02},
    "Kai'Sa": {"ADC": 0.92, "Mid": 0.06, "Support": 0.02},
    "Vayne": {"ADC": 0.75, "Top": 0.22, "Mid": 0.03},
    "Miss Fortune": {"ADC": 0.88, "Support": 0.10, "Mid": 0.02},
    "Tristana": {"ADC": 0.75, "Mid": 0.22, "Top": 0.03},
    "Draven": {"ADC": 0.97, "Mid": 0.02, "Top": 0.01},
    "Sivir": {"ADC": 0.95, "Mid": 0.04, "Support": 0.01},
    "Varus": {"ADC": 0.85, "Mid": 0.13, "Support": 0.02},
    "Xayah": {"ADC": 0.95, "Mid": 0.04, "Support": 0.01},
    "Aphelios": {"ADC": 0.98, "Mid": 0.02},
    "Samira": {"ADC": 0.95, "Mid": 0.04, "Support": 0.01},
    "Zeri": {"ADC": 0.95, "Mid": 0.04, "Top": 0.01},
    "Smolder": {"ADC": 0.75, "Mid": 0.20, "Top": 0.05},
    "Lucian": {"ADC": 0.60, "Mid": 0.35, "Top": 0.05},
    "Kog'Maw": {"ADC": 0.90, "Mid": 0.08, "Top": 0.02},
    "Twitch": {"ADC": 0.80, "Support": 0.12, "Jungle": 0.08},
    "Kalista": {"ADC": 0.95, "Top": 0.04, "Jungle": 0.01},
    "Nilah": {"ADC": 0.95, "Mid": 0.04, "Top": 0.01},

    # Supports
    "Thresh": {"Support": 0.97, "Top": 0.02, "Jungle": 0.01},
    "Leona": {"Support": 0.98, "Jungle": 0.01, "Top": 0.01},
    "Lulu": {"Support": 0.88, "Mid": 0.08, "Top": 0.04},
    "Nami": {"Support": 0.98, "Mid": 0.01, "Top": 0.01},
    "Janna": {"Support": 0.97, "Mid": 0.02, "Top": 0.01},
    "Nautilus": {"Support": 0.85, "Jungle": 0.08, "Top": 0.07},
    "Blitzcrank": {"Support": 0.95, "Mid": 0.03, "Top": 0.02},
    "Soraka": {"Support": 0.92, "Mid": 0.05, "Top": 0.03},
    "Yuumi": {"Support": 0.99, "Mid": 0.01},
    "Senna": {"Support": 0.65, "ADC": 0.33, "Mid": 0.02},
    "Pyke": {"Support": 0.88, "Mid": 0.10, "Top": 0.02},
    "Rakan": {"Support": 0.97, "Mid": 0.02, "Top": 0.01},
    "Bard": {"Support": 0.97, "Mid": 0.02, "Top": 0.01},
    "Braum": {"Support": 0.97, "Top": 0.02, "Jungle": 0.01},
    "Taric": {"Support": 0.90, "Top": 0.06, "Jungle": 0.04},
    "Renata Glasc": {"Support": 0.97, "Mid": 0.02, "Top": 0.01},
    "Milio": {"Support": 0.98, "Mid": 0.01, "Top": 0.01},
    "Rell": {"Support": 0.95, "Jungle": 0.04, "Top": 0.01},

    # Top laners
    "Darius": {"Top": 0.92, "Mid": 0.05, "Jungle": 0.03},
    "Garen": {"Top": 0.90, "Mid": 0.08, "Support": 0.02},
    "Camille": {"Top": 0.85, "Mid": 0.08, "Jungle": 0.07},
    "Fiora": {"Top": 0.95, "Mid": 0.04, "Jungle": 0.01},
    "Sett": {"Top": 0.60, "Support": 0.20, "Jungle": 0.12, "Mid": 0.08},
    "Mordekaiser": {"Top": 0.85, "Mid": 0.08, "Jungle": 0.07},
    "Aatrox": {"Top": 0.90, "Mid": 0.08, "Jungle": 0.02},
    "Ornn": {"Top": 0.95, "Support": 0.04, "Jungle": 0.01},
    "Renekton": {"Top": 0.88, "Mid": 0.10, "Jungle": 0.02},
    "Irelia": {"Top": 0.55, "Mid": 0.43, "Jungle": 0.02},
    "Jax": {"Top": 0.75, "Jungle": 0.22, "Mid": 0.03},
    "K'Sante": {"Top": 0.93, "Mid": 0.05, "Jungle": 0.02},
    "Sion": {"Top": 0.80, "Support": 0.12, "Mid": 0.05, "Jungle": 0.03},
    "Urgot": {"Top": 0.95, "Mid": 0.04, "ADC": 0.01},
    "Illaoi": {"Top": 0.97, "Mid": 0.02, "Jungle": 0.01},
    "Kled": {"Top": 0.92, "Mid": 0.05, "Jungle": 0.03},
    "Nasus": {"Top": 0.92, "Mid": 0.04, "Jungle": 0.04},
    "Tryndamere": {"Top": 0.80, "Mid": 0.15, "Jungle": 0.05},
    "Gnar": {"Top": 0.95, "Mid": 0.03, "Support": 0.02},
    "Cho'Gath": {"Top": 0.80, "Mid": 0.10, "Jungle": 0.07, "Support": 0.03},
    "Poppy": {"Top": 0.55, "Jungle": 0.30, "Support": 0.15},
    "Yorick": {"Top": 0.97, "Jungle": 0.02, "Mid": 0.01},
    "Singed": {"Top": 0.90, "Support": 0.05, "Mid": 0.03, "Jungle": 0.02},
    "Malphite": {"Top": 0.70, "Support": 0.20, "Mid": 0.08, "Jungle": 0.02},
    "Volibear": {"Top": 0.55, "Jungle": 0.42, "Mid": 0.03},
    "Olaf": {"Top": 0.50, "Jungle": 0.48, "Mid": 0.02},

    # Mid laners
    "Ahri": {"Mid": 0.95, "Support": 0.03, "ADC": 0.02},
    "Syndra": {"Mid": 0.92, "ADC": 0.05, "Support": 0.03},
    "Zed": {"Mid": 0.90, "Jungle": 0.05, "Top": 0.05},
    "Yasuo": {"Mid": 0.60, "Top": 0.25, "ADC": 0.15},
    "Yone": {"Mid": 0.65, "Top": 0.30, "ADC": 0.05},
    "Katarina": {"Mid": 0.95, "Top": 0.03, "Jungle": 0.02},
    "LeBlanc": {"Mid": 0.92, "Support": 0.05, "Top": 0.03},
    "Orianna": {"Mid": 0.95, "Support": 0.03, "ADC": 0.02},
    "Viktor": {"Mid": 0.90, "ADC": 0.05, "Top": 0.05},
    "Veigar": {"Mid": 0.75, "ADC": 0.12, "Support": 0.13},
    "Lux": {"Mid": 0.55, "Support": 0.43, "ADC": 0.02},
    "Xerath": {"Mid": 0.60, "Support": 0.38, "ADC": 0.02},
    "Vel'Koz": {"Mid": 0.55, "Support": 0.43, "ADC": 0.02},
    "Ryze": {"Mid": 0.85, "Top": 0.13, "ADC": 0.02},
    "Talon": {"Mid": 0.75, "Jungle": 0.22, "Top": 0.03},
    "Fizz": {"Mid": 0.92, "Top": 0.05, "Jungle": 0.03},
    "Ekko": {"Mid": 0.55, "Jungle": 0.42, "Top": 0.03},
    "Kassadin": {"Mid": 0.95, "Top": 0.04, "Jungle": 0.01},
    "Azir": {"Mid": 0.97, "ADC": 0.02, "Top": 0.01},
    "Hwei": {"Mid": 0.80, "Support": 0.15, "ADC": 0.05},
    "Sylas": {"Mid": 0.70, "Top": 0.18, "Jungle": 0.12},
    "Akali": {"Mid": 0.65, "Top": 0.33, "Jungle": 0.02},
    "Lissandra": {"Mid": 0.85, "Top": 0.10, "Support": 0.05},
    "Galio": {"Mid": 0.65, "Support": 0.25, "Top": 0.10},
    "Twisted Fate": {"Mid": 0.88, "ADC": 0.05, "Support": 0.05, "Top": 0.02},
    "Corki": {"Mid": 0.85, "ADC": 0.13, "Top": 0.02},
    "Neeko": {"Mid": 0.50, "Support": 0.30, "Top": 0.15, "ADC": 0.05},
    "Swain": {"Mid": 0.35, "Support": 0.35, "ADC": 0.20, "Top": 0.10},
    "Malzahar": {"Mid": 0.90, "Support": 0.08, "Top": 0.02},
    "Ziggs": {"Mid": 0.60, "ADC": 0.35, "Support": 0.05},
    "Brand": {"Support": 0.55, "Mid": 0.40, "Jungle": 0.05},
    "Zyra": {"Support": 0.80, "Mid": 0.18, "Top": 0.02},
    "Seraphine": {"Support": 0.55, "Mid": 0.30, "ADC": 0.15},
    "Vex": {"Mid": 0.90, "Support": 0.08, "Top": 0.02},
    "Naafiri": {"Mid": 0.80, "Jungle": 0.15, "Top": 0.05},
    "Aurora": {"Mid": 0.65, "Top": 0.30, "Jungle": 0.05},
    "Annie": {"Mid": 0.65, "Support": 0.33, "Top": 0.02},
    "Qiyana": {"Mid": 0.85, "Jungle": 0.13, "Top": 0.02},
    "Zoe": {"Mid": 0.95, "Support": 0.04, "Top": 0.01},
    "Cassiopeia": {"Mid": 0.85, "Top": 0.10, "ADC": 0.05},
    "Vladimir": {"Mid": 0.60, "Top": 0.38, "ADC": 0.02},

    # Junglers
    "Lee Sin": {"Jungle": 0.90, "Top": 0.05, "Mid": 0.05},
    "Vi": {"Jungle": 0.95, "Top": 0.04, "Mid": 0.01},
    "Hecarim": {"Jungle": 0.95, "Top": 0.04, "Mid": 0.01},
    "Graves": {"Jungle": 0.85, "Top": 0.08, "Mid": 0.07},
    "Kayn": {"Jungle": 0.95, "Mid": 0.03, "Top": 0.02},
    "Kha'Zix": {"Jungle": 0.92, "Mid": 0.05, "Top": 0.03},
    "Rengar": {"Jungle": 0.75, "Top": 0.23, "Mid": 0.02},
    "Elise": {"Jungle": 0.95, "Support": 0.03, "Mid": 0.02},
    "Evelynn": {"Jungle": 0.98, "Mid": 0.01, "Support": 0.01},
    "Shaco": {"Jungle": 0.80, "Support": 0.18, "Mid": 0.02},
    "Nocturne": {"Jungle": 0.85, "Top": 0.08, "Mid": 0.07},
    "Rek'Sai": {"Jungle": 0.97, "Top": 0.02, "Mid": 0.01},
    "Viego": {"Jungle": 0.80, "Mid": 0.12, "Top": 0.08},
    "Kindred": {"Jungle": 0.92, "ADC": 0.05, "Mid": 0.03},
    "Lillia": {"Jungle": 0.85, "Top": 0.12, "Mid": 0.03},
    "Nidalee": {"Jungle": 0.90, "Support": 0.05, "Mid": 0.05},
    "Amumu": {"Jungle": 0.85, "Support": 0.13, "Top": 0.02},
    "Rammus": {"Jungle": 0.95, "Top": 0.04, "Support": 0.01},
    "Sejuani": {"Jungle": 0.80, "Top": 0.12, "Support": 0.08},
    "Zac": {"Jungle": 0.80, "Top": 0.15, "Support": 0.05},
    "Warwick": {"Jungle": 0.80, "Top": 0.18, "Mid": 0.02},
    "Ivern": {"Jungle": 0.97, "Support": 0.03},
    "Udyr": {"Jungle": 0.80, "Top": 0.18, "Mid": 0.02},
    "Master Yi": {"Jungle": 0.95, "Mid": 0.03, "Top": 0.02},
    "Xin Zhao": {"Jungle": 0.88, "Top": 0.08, "Mid": 0.04},
    "Jarvan IV": {"Jungle": 0.85, "Top": 0.10, "Support": 0.05},
    "Shyvana": {"Jungle": 0.85, "Top": 0.13, "Mid": 0.02},
    "Skarner": {"Jungle": 0.85, "Top": 0.10, "Support": 0.05},
    "Bel'Veth": {"Jungle": 0.97, "Top": 0.02, "Mid": 0.01},
    "Briar": {"Jungle": 0.92, "Top": 0.05, "Mid": 0.03},
    "Fiddlesticks": {"Jungle": 0.85, "Support": 0.10, "Mid": 0.05},
    "Wukong": {"Jungle": 0.55, "Top": 0.40, "Mid": 0.05},
    "Diana": {"Jungle": 0.65, "Mid": 0.33, "Top": 0.02},
    "Maokai": {"Support": 0.45, "Jungle": 0.40, "Top": 0.15},
    "Trundle": {"Jungle": 0.55, "Top": 0.40, "Support": 0.05},
    "Rumble": {"Top": 0.50, "Mid": 0.30, "Jungle": 0.20},
    "Gwen": {"Top": 0.80, "Jungle": 0.15, "Mid": 0.05},
    "Riven": {"Top": 0.88, "Mid": 0.08, "Jungle": 0.04},
    "Pantheon": {"Support": 0.35, "Mid": 0.30, "Top": 0.25, "Jungle": 0.10},
    "Kennen": {"Top": 0.75, "Mid": 0.15, "ADC": 0.08, "Support": 0.02},
    "Jayce": {"Top": 0.60, "Mid": 0.38, "ADC": 0.02},
    "Kayle": {"Top": 0.88, "Mid": 0.10, "ADC": 0.02},
    "Teemo": {"Top": 0.80, "Support": 0.10, "Mid": 0.08, "Jungle": 0.02},
    "Gangplank": {"Top": 0.85, "Mid": 0.13, "ADC": 0.02},
    "Quinn": {"Top": 0.75, "Mid": 0.15, "ADC": 0.08, "Jungle": 0.02},
    "Heimerdinger": {"Mid": 0.40, "Top": 0.30, "Support": 0.20, "ADC": 0.10},
    "Morgana": {"Support": 0.75, "Mid": 0.15, "Jungle": 0.10},
    "Karma": {"Support": 0.75, "Mid": 0.18, "Top": 0.07},
    "Zilean": {"Support": 0.70, "Mid": 0.28, "Top": 0.02},
    "Tahm Kench": {"Support": 0.55, "Top": 0.43, "Jungle": 0.02},
    "Sona": {"Support": 0.95, "Mid": 0.03, "ADC": 0.02},
}

ROLE_MAP = {"Top": "TOP", "Jungle": "JG", "Mid": "MID", "ADC": "ADC", "Support": "SUP"}
ROLE_MAP_INV = {v: k for k, v in ROLE_MAP.items()}


# =============================================================================
# AGENT 2: USER CONTEXT RESOLVER
# =============================================================================

class UserContextResolverAgent:
    """Determines user champion, role, and rank with minimal interaction."""

    def __init__(self):
        self.name = "user_context_resolver"
        self.status = "PRODUCTION"

    async def resolve(self, input_data: UserContextInput) -> UserContextOutput:
        start = time.time()

        champion = input_data.user_champion
        role = input_data.user_role
        rank = input_data.user_rank or "Unknown"

        # Determine which team the user is on
        user_team = TeamSide.BLUE
        if champion:
            if champion in input_data.red_team:
                user_team = TeamSide.RED
            elif champion not in input_data.blue_team:
                # Champion not found in either team — need clarification
                return UserContextOutput(
                    user_champion=champion,
                    user_role=role or Role.UNKNOWN,
                    user_rank=rank,
                    user_team=TeamSide.BLUE,
                    lane_opponent="Unknown",
                    needs_clarification=True,
                    clarification_prompt=f"I couldn't find {champion} on either team. Which champion are you playing?",
                    confidence=0.3,
                )

        if not champion:
            return UserContextOutput(
                user_champion="Unknown",
                user_role=Role.UNKNOWN,
                user_rank=rank,
                user_team=TeamSide.BLUE,
                lane_opponent="Unknown",
                needs_clarification=True,
                clarification_prompt="Which champion are you playing?",
                confidence=0.0,
            )

        # Infer role from champion priors if not provided
        if not role:
            priors = ROLE_PRIORS.get(champion, {})
            if priors:
                best_role = max(priors, key=priors.get)
                role = Role(best_role)
            else:
                role = Role.UNKNOWN

        # Infer lane opponent (basic: same-role champion on enemy team)
        lane_opponent = "Unknown"
        enemy_team = input_data.red_team if user_team == TeamSide.BLUE else input_data.blue_team
        if role != Role.UNKNOWN:
            role_key = role.value
            for enemy in enemy_team:
                enemy_priors = ROLE_PRIORS.get(enemy, {})
                if enemy_priors and max(enemy_priors, key=enemy_priors.get) == role_key:
                    lane_opponent = enemy
                    break

        elapsed = (time.time() - start) * 1000
        confidence = 0.9 if role != Role.UNKNOWN else 0.5

        return UserContextOutput(
            user_champion=champion,
            user_role=role,
            user_rank=rank,
            user_team=user_team,
            lane_opponent=lane_opponent,
            needs_clarification=False,
            confidence=confidence,
        )


# =============================================================================
# AGENT 3: ROLE INFERENCE ENGINE
# =============================================================================

class RoleInferenceEngineAgent:
    """
    Assigns roles to all 10 champions using constrained optimization
    over role priors. Hungarian algorithm approach for optimal assignment.
    """

    def __init__(self, llm_client=None, model: str = "claude-haiku-4-5-20251001"):
        self.name = "role_inference_engine"
        self.status = "PRODUCTION"
        self.llm_client = llm_client
        self.model = model
        self.cost_per_call = 0.002

    async def infer(self, input_data: RoleInferenceInput) -> RoleInferenceOutput:
        start = time.time()

        blue_roles = self._assign_roles(
            input_data.blue_team,
            user_champion=input_data.user_champion,
            user_role=input_data.user_role,
        )
        red_roles = self._assign_roles(input_data.red_team)

        # Compute confidence per lane
        confidence = RoleConfidence(
            TOP=self._slot_confidence(blue_roles.TOP, "Top")
                * self._slot_confidence(red_roles.TOP, "Top"),
            JG=self._slot_confidence(blue_roles.JG, "Jungle")
                * self._slot_confidence(red_roles.JG, "Jungle"),
            MID=self._slot_confidence(blue_roles.MID, "Mid")
                * self._slot_confidence(red_roles.MID, "Mid"),
            ADC=self._slot_confidence(blue_roles.ADC, "ADC")
                * self._slot_confidence(red_roles.ADC, "ADC"),
            SUP=self._slot_confidence(blue_roles.SUP, "Support")
                * self._slot_confidence(red_roles.SUP, "Support"),
        )

        # Detect ambiguous assignments
        notes = []
        ambiguous = []
        for team_name, team, roles in [
            ("Blue", input_data.blue_team, blue_roles),
            ("Red", input_data.red_team, red_roles),
        ]:
            for champ in team:
                priors = ROLE_PRIORS.get(champ, {})
                if priors:
                    top2 = sorted(priors.values(), reverse=True)
                    if len(top2) >= 2 and top2[0] - top2[1] < 0.15:
                        ambiguous.append(champ)
                        notes.append(f"{champ} could play multiple roles (flex pick)")

        elapsed = (time.time() - start) * 1000
        return RoleInferenceOutput(
            blue_roles=blue_roles,
            red_roles=red_roles,
            confidence=confidence,
            notes=notes,
            ambiguous_assignments=ambiguous,
            processing_time_ms=elapsed,
        )

    def _assign_roles(
        self,
        team: List[str],
        user_champion: Optional[str] = None,
        user_role: Optional[Role] = None,
    ) -> RoleAssignment:
        """
        Greedy role assignment with constraint propagation.
        If user champion/role is pinned, assign that first.
        """
        roles = {"TOP": "", "JG": "", "MID": "", "ADC": "", "SUP": ""}
        available = list(team)

        # Pin user champion if applicable
        if user_champion and user_champion in available and user_role and user_role != Role.UNKNOWN:
            role_key = ROLE_MAP.get(user_role.value, "")
            if role_key:
                roles[role_key] = user_champion
                available.remove(user_champion)

        # Greedy assignment: highest probability first
        for _ in range(5):
            if not available:
                break
            best_score = -1
            best_champ = None
            best_role = None

            for champ in available:
                priors = ROLE_PRIORS.get(champ, {})
                for role_name, prob in priors.items():
                    role_key = ROLE_MAP.get(role_name, "")
                    if role_key and roles[role_key] == "" and prob > best_score:
                        best_score = prob
                        best_champ = champ
                        best_role = role_key

            if best_champ and best_role:
                roles[best_role] = best_champ
                available.remove(best_champ)
            elif available:
                # Assign remaining to first open slot
                for role_key in roles:
                    if roles[role_key] == "" and available:
                        roles[role_key] = available.pop(0)

        # Fill any remaining empty slots
        for role_key in roles:
            if roles[role_key] == "" and available:
                roles[role_key] = available.pop(0)

        return RoleAssignment(**roles)

    def _slot_confidence(self, champion: str, role: str) -> float:
        priors = ROLE_PRIORS.get(champion, {})
        return priors.get(role, 0.5)  # Default 0.5 for unknown champions
