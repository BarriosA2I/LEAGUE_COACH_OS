"""
================================================================================
AGENT 1: VISION_PARSER
================================================================================
Extracts champion names + team assignment from LoL loading screen screenshots.
Uses Claude's native vision capability for champion recognition.

Author: Barrios A2I | Status: PRODUCTION
================================================================================
"""
import asyncio
import base64
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from schemas.models import (
    ChampionSlot,
    VisionParserInput,
    VisionParserOutput,
)

logger = logging.getLogger(__name__)

# Known champion names for validation (partial list — extend from Data Dragon)
KNOWN_CHAMPIONS = {
    "Aatrox", "Ahri", "Akali", "Akshan", "Alistar", "Amumu", "Anivia",
    "Annie", "Aphelios", "Ashe", "Aurelion Sol", "Aurora", "Azir",
    "Bard", "Bel'Veth", "Blitzcrank", "Brand", "Braum", "Briar",
    "Caitlyn", "Camille", "Cassiopeia", "Cho'Gath", "Corki",
    "Darius", "Diana", "Dr. Mundo", "Draven",
    "Ekko", "Elise", "Evelynn", "Ezreal",
    "Fiddlesticks", "Fiora", "Fizz",
    "Galio", "Gangplank", "Garen", "Gnar", "Gragas", "Graves", "Gwen",
    "Hecarim", "Heimerdinger", "Hwei",
    "Illaoi", "Irelia", "Ivern",
    "Janna", "Jarvan IV", "Jax", "Jayce", "Jhin", "Jinx",
    "K'Sante", "Kai'Sa", "Kalista", "Karma", "Karthus", "Kassadin",
    "Katarina", "Kayle", "Kayn", "Kennen", "Kha'Zix", "Kindred",
    "Kled", "Kog'Maw",
    "LeBlanc", "Lee Sin", "Leona", "Lillia", "Lissandra", "Lucian", "Lulu", "Lux",
    "Malphite", "Malzahar", "Maokai", "Master Yi", "Milio", "Miss Fortune",
    "Mordekaiser", "Morgana",
    "Naafiri", "Nami", "Nasus", "Nautilus", "Neeko", "Nidalee", "Nilah", "Nocturne", "Nunu & Willump",
    "Olaf", "Orianna", "Ornn",
    "Pantheon", "Poppy", "Pyke",
    "Qiyana", "Quinn",
    "Rakan", "Rammus", "Rek'Sai", "Rell", "Renata Glasc", "Renekton",
    "Rengar", "Riven", "Rumble", "Ryze",
    "Samira", "Sejuani", "Senna", "Seraphine", "Sett", "Shaco", "Shen",
    "Shyvana", "Singed", "Sion", "Sivir", "Skarner", "Smolder", "Sona",
    "Soraka", "Swain", "Sylas", "Syndra",
    "Tahm Kench", "Taliyah", "Talon", "Taric", "Teemo", "Thresh",
    "Tristana", "Trundle", "Tryndamere", "Twisted Fate", "Twitch",
    "Udyr", "Urgot",
    "Varus", "Vayne", "Veigar", "Vel'Koz", "Vex", "Vi", "Viego", "Viktor",
    "Vladimir", "Volibear",
    "Warwick", "Wukong",
    "Xayah", "Xerath", "Xin Zhao",
    "Yasuo", "Yone", "Yorick", "Yuumi",
    "Zac", "Zed", "Zeri", "Ziggs", "Zilean", "Zoe", "Zyra",
}

VISION_SYSTEM_PROMPT = """You are an expert League of Legends champion identification system.
You will be shown a loading screen screenshot from a League of Legends game.

Your task:
1. Identify ALL 10 champions shown on the loading screen
2. Separate them into Blue team (left side) and Red team (right side)
3. List them in order from top to bottom as they appear on each side

RULES:
- Use the EXACT official champion name (e.g., "Lee Sin" not "Lee")
- If a champion has a skin that makes them hard to identify, still provide your best guess
- If you truly cannot identify a champion, output "Unknown" for that slot
- The loading screen always shows 5 champions per team

Output ONLY valid JSON in this exact format:
{
  "blue_team": ["Champion1", "Champion2", "Champion3", "Champion4", "Champion5"],
  "red_team": ["Champion1", "Champion2", "Champion3", "Champion4", "Champion5"],
  "confidence": 0.95,
  "notes": ["Any uncertainty notes"]
}"""


class VisionParserAgent:
    """
    Parses LoL loading screen images to extract champion identities.
    
    Uses Claude Vision API for champion recognition. Falls back to
    fuzzy matching against known champion list for validation.
    """

    def __init__(self, llm_client=None, model: str = "claude-sonnet-4-5-20250929"):
        self.name = "vision_parser"
        self.status = "PRODUCTION"
        self.llm_client = llm_client
        self.model = model
        self.cost_per_call = 0.008  # Vision API cost estimate

    async def parse(self, input_data: VisionParserInput) -> VisionParserOutput:
        start = time.time()

        try:
            # Build vision message
            if input_data.image_data.startswith("/") or input_data.image_data.startswith("C:"):
                # File path — read and encode
                image_bytes = Path(input_data.image_data).read_bytes()
                b64_data = base64.b64encode(image_bytes).decode("utf-8")
            else:
                b64_data = input_data.image_data

            media_type = f"image/{input_data.image_format}"

            if self.llm_client is None:
                # Mock response for testing / no client
                return self._mock_response(start)

            # Call Claude Vision
            response = await self.llm_client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": b64_data,
                                },
                            },
                            {
                                "type": "text",
                                "text": VISION_SYSTEM_PROMPT,
                            },
                        ],
                    }
                ],
            )

            # Parse JSON from response
            raw = response.content[0].text
            # Extract JSON from potential markdown code blocks
            if "```" in raw:
                raw = raw.split("```json")[-1].split("```")[0].strip()
            parsed = json.loads(raw)

            # Validate champion names
            blue_team = self._validate_names(parsed.get("blue_team", []))
            red_team = self._validate_names(parsed.get("red_team", []))
            confidence = parsed.get("confidence", 0.85)

            # Build detailed slots
            blue_details = [
                ChampionSlot(
                    champion_name=name,
                    confidence=confidence if name != "Unknown" else 0.0,
                    position_index=i,
                )
                for i, name in enumerate(blue_team)
            ]
            red_details = [
                ChampionSlot(
                    champion_name=name,
                    confidence=confidence if name != "Unknown" else 0.0,
                    position_index=i + 5,
                )
                for i, name in enumerate(red_team)
            ]

            unknown_slots = [
                s.position_index
                for s in blue_details + red_details
                if s.champion_name == "Unknown"
            ]

            elapsed = (time.time() - start) * 1000
            return VisionParserOutput(
                blue_team=blue_team,
                red_team=red_team,
                blue_team_details=blue_details,
                red_team_details=red_details,
                overall_confidence=confidence,
                unknown_slots=unknown_slots,
                processing_time_ms=elapsed,
                cost_usd=self.cost_per_call,
            )

        except Exception as e:
            logger.error(f"Vision parsing failed: {e}")
            elapsed = (time.time() - start) * 1000
            # Return graceful degradation with unknowns
            return VisionParserOutput(
                blue_team=["Unknown"] * 5,
                red_team=["Unknown"] * 5,
                overall_confidence=0.0,
                unknown_slots=list(range(10)),
                processing_time_ms=elapsed,
                cost_usd=self.cost_per_call,
            )

    def _validate_names(self, names: List[str]) -> List[str]:
        """Validate champion names against known roster with fuzzy matching."""
        validated = []
        for name in names:
            if name in KNOWN_CHAMPIONS:
                validated.append(name)
            else:
                # Fuzzy match — check case-insensitive
                match = next(
                    (c for c in KNOWN_CHAMPIONS if c.lower() == name.lower()),
                    None,
                )
                if match:
                    validated.append(match)
                else:
                    # Try substring match
                    match = next(
                        (c for c in KNOWN_CHAMPIONS if name.lower() in c.lower()),
                        None,
                    )
                    validated.append(match if match else "Unknown")

        # Pad to 5 if needed
        while len(validated) < 5:
            validated.append("Unknown")
        return validated[:5]

    def _mock_response(self, start: float) -> VisionParserOutput:
        """Mock response for testing without LLM client."""
        elapsed = (time.time() - start) * 1000
        return VisionParserOutput(
            blue_team=["Jinx", "Thresh", "Lee Sin", "Ahri", "Darius"],
            red_team=["Caitlyn", "Leona", "Vi", "Syndra", "Garen"],
            overall_confidence=0.92,
            unknown_slots=[],
            processing_time_ms=elapsed,
            cost_usd=0.0,
        )
