import { z } from 'zod';
import fs from 'fs';
import path from 'path';
import {
  type AgentDefinition,
  type AgentResult,
  type Role,
  ROLE_TAG_MAP,
  inferRoles,
  trimmedPath,
  currentPatchVersion,
  type TrimmedChampion,
} from '@league-coach/core';

const RoleInferenceInputSchema = z.object({
  champion: z.string(),
  allies: z.array(z.string()),
});

type RoleInferenceInput = z.infer<typeof RoleInferenceInputSchema>;

const RoleInferenceOutputSchema = z.object({
  role: z.enum(['top', 'jungle', 'mid', 'adc', 'support']),
  confidence: z.number().min(0).max(1),
  reasoning: z.string(),
});

export type RoleInferenceOutput = z.infer<typeof RoleInferenceOutputSchema>;

/**
 * Loads the trimmed champions file and finds the champion entry by name (case-insensitive).
 */
function findChampionData(champName: string): TrimmedChampion | null {
  try {
    const version = currentPatchVersion();
    const trimDir = trimmedPath(version);
    const filePath = path.join(trimDir, 'champion-trimmed.json');
    const data: TrimmedChampion[] = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
    return data.find((c) => c.name.toLowerCase() === champName.toLowerCase() || c.id.toLowerCase() === champName.toLowerCase()) ?? null;
  } catch {
    return null;
  }
}

export const roleInferenceEngineAgent: AgentDefinition = {
  name: 'role_inference_engine',
  description: 'Infers the most likely role for a champion based on their tags and team composition heuristics.',
  inputSchema: RoleInferenceInputSchema,
  outputSchema: RoleInferenceOutputSchema,

  async execute(input: unknown): Promise<AgentResult> {
    const start = Date.now();
    try {
      const { champion, allies } = RoleInferenceInputSchema.parse(input) as RoleInferenceInput;

      const champData = findChampionData(champion);
      let tags: string[] = [];
      if (champData) {
        tags = champData.tags;
      }

      const possibleRoles = inferRoles(tags);
      let role: Role;
      let confidence: number;
      let reasoning: string;

      if (possibleRoles.length === 0) {
        // No mapping found -- default to mid with low confidence
        role = 'mid';
        confidence = 0.3;
        reasoning = `No tag mapping found for champion "${champion}". Defaulting to mid.`;
      } else if (possibleRoles.length === 1) {
        // Unambiguous role
        role = possibleRoles[0];
        confidence = 0.95;
        reasoning = `Champion "${champion}" has tags [${tags.join(', ')}] which map unambiguously to ${role}.`;
      } else {
        // Multiple possible roles -- apply heuristics
        // Priority order: if tags include Marksman, ADC is very likely
        // If tags include Support, support is very likely
        // For Fighter/Tank ambiguity, default to top
        // For Assassin/Mage ambiguity, default to mid

        if (possibleRoles.includes('adc')) {
          role = 'adc';
          confidence = 0.85;
          reasoning = `Champion "${champion}" has Marksman tag. Strongly favoring ADC role.`;
        } else if (possibleRoles.includes('support') && tags.includes('Support')) {
          role = 'support';
          confidence = 0.8;
          reasoning = `Champion "${champion}" has explicit Support tag. Favoring support role.`;
        } else if (possibleRoles.includes('mid') && tags.includes('Assassin')) {
          role = 'mid';
          confidence = 0.7;
          reasoning = `Champion "${champion}" has Assassin tag with multiple possible roles [${possibleRoles.join(', ')}]. Favoring mid.`;
        } else if (possibleRoles.includes('top')) {
          role = 'top';
          confidence = 0.65;
          reasoning = `Champion "${champion}" has tags [${tags.join(', ')}] mapping to [${possibleRoles.join(', ')}]. Defaulting to top as primary role.`;
        } else if (possibleRoles.includes('jungle')) {
          role = 'jungle';
          confidence = 0.6;
          reasoning = `Champion "${champion}" has tags [${tags.join(', ')}] mapping to [${possibleRoles.join(', ')}]. Selecting jungle.`;
        } else {
          role = possibleRoles[0];
          confidence = 0.5;
          reasoning = `Champion "${champion}" has ambiguous roles [${possibleRoles.join(', ')}]. Selecting ${role} as first candidate.`;
        }
      }

      const output: RoleInferenceOutput = { role, confidence, reasoning };
      const validated = RoleInferenceOutputSchema.parse(output);

      return {
        agent: 'role_inference_engine',
        success: true,
        data: validated,
        duration_ms: Date.now() - start,
      };
    } catch (err) {
      return {
        agent: 'role_inference_engine',
        success: false,
        data: null,
        errors: [err instanceof Error ? err.message : String(err)],
        duration_ms: Date.now() - start,
      };
    }
  },
};
