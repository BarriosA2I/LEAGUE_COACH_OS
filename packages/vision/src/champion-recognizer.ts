import fs from 'fs';
import path from 'path';
import {
  logger,
  trimmedPath,
  currentPatchVersion,
  type VisionParseInput,
  type VisionParseOutput,
  type VisionSlot,
  type TrimmedChampion,
} from '@league-coach/core';

const TAG = 'vision:champion-recognizer';

/**
 * Loads the trimmed champion list from the current patch vault data
 * and returns a Set of valid champion names (case-insensitive lookup map).
 */
function loadChampionNameMap(version: string): Map<string, string> {
  const champFile = path.join(trimmedPath(version), 'champion-trimmed.json');
  const data: TrimmedChampion[] = JSON.parse(fs.readFileSync(champFile, 'utf-8'));

  const nameMap = new Map<string, string>();
  for (const champ of data) {
    // Map lowercased name -> canonical name for fuzzy lookups
    nameMap.set(champ.name.toLowerCase(), champ.name);
    // Also map by id (e.g. "Aatrox" -> "Aatrox")
    nameMap.set(champ.id.toLowerCase(), champ.name);
  }

  return nameMap;
}

/**
 * Validates a champion name against the known champion pool.
 * Returns the canonical name if found, or null if not recognized.
 */
function validateChampionName(name: string, nameMap: Map<string, string>): string | null {
  const lookup = name.trim().toLowerCase();
  return nameMap.get(lookup) ?? null;
}

/**
 * Recognizes champions from the vision parse input.
 *
 * In FAST MODE, this relies on manual_champions provided by the user.
 * The manual_champions array follows this convention:
 *   - Indices 0-4: blue team champions
 *   - Indices 5-9: red team champions
 *   - Index 0 is assumed to be the user's champion (blue side perspective)
 *
 * If manual_champions is not provided, all 10 slots are marked as unknown,
 * requiring future ML-based champion recognition to fill in.
 *
 * @param input - VisionParseInput with optional manual_champions
 * @returns VisionParseOutput with team rosters and unknown slot indicators
 */
export async function recognizeChampions(input: VisionParseInput): Promise<VisionParseOutput> {
  logger.info(TAG, 'Recognizing champions', {
    hasManual: !!input.manual_champions,
    manualCount: input.manual_champions?.length,
  });

  const version = currentPatchVersion();
  const nameMap = loadChampionNameMap(version);

  // --- Manual champion input (FAST MODE primary path) ---
  if (input.manual_champions && input.manual_champions.length >= 10) {
    const names = input.manual_champions;
    const blueTeam: VisionSlot[] = [];
    const redTeam: VisionSlot[] = [];
    const unknownSlots: number[] = [];

    for (let i = 0; i < 10; i++) {
      const validated = validateChampionName(names[i], nameMap);
      const slot: VisionSlot = {
        champion: validated ?? names[i],
        confidence: validated ? 1.0 : 0.0,
      };

      if (!validated) {
        unknownSlots.push(i);
        logger.warn(TAG, `Unknown champion at slot ${i}: "${names[i]}"`);
      }

      if (i < 5) {
        blueTeam.push(slot);
      } else {
        redTeam.push(slot);
      }
    }

    // User's champion defaults to first entry (index 0) = blue team slot 0
    const userChampion = blueTeam[0].champion;
    const userConfidence = blueTeam[0].confidence;

    return {
      blue_team: blueTeam as [VisionSlot, VisionSlot, VisionSlot, VisionSlot, VisionSlot],
      red_team: redTeam as [VisionSlot, VisionSlot, VisionSlot, VisionSlot, VisionSlot],
      user_champion: userChampion,
      user_confidence: userConfidence,
      unknown_slots: unknownSlots,
    };
  }

  // --- No manual input: all slots unknown (requires ML implementation) ---
  logger.warn(TAG, 'No manual champions provided. All slots marked as unknown.');

  const unknownSlot: VisionSlot = { champion: 'unknown', confidence: 0.0 };
  const allUnknown = Array.from({ length: 5 }, () => ({ ...unknownSlot }));
  const allSlots = Array.from({ length: 10 }, (_, i) => i);

  return {
    blue_team: allUnknown as [VisionSlot, VisionSlot, VisionSlot, VisionSlot, VisionSlot],
    red_team: allUnknown as [VisionSlot, VisionSlot, VisionSlot, VisionSlot, VisionSlot],
    user_champion: 'unknown',
    user_confidence: 0.0,
    unknown_slots: allSlots,
  };
}
