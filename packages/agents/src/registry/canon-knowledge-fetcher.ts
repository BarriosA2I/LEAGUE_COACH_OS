import { z } from 'zod';
import fs from 'fs';
import path from 'path';
import {
  type AgentDefinition,
  type AgentResult,
  TrimmedChampionSchema,
  TrimmedItemSchema,
  RuneTreeSchema,
  type TrimmedChampion,
  type TrimmedItem,
  type RuneTree,
  trimmedPath,
  currentPatchVersion,
} from '@league-coach/core';

const CanonKnowledgeInputSchema = z.object({
  champion: z.string(),
  role: z.enum(['top', 'jungle', 'mid', 'adc', 'support']),
  patch: z.string(),
});

type CanonKnowledgeInput = z.infer<typeof CanonKnowledgeInputSchema>;

const CanonKnowledgeOutputSchema = z.object({
  champion_data: TrimmedChampionSchema,
  recommended_items: z.array(TrimmedItemSchema),
  rune_trees: z.array(RuneTreeSchema),
});

export type CanonKnowledgeOutput = z.infer<typeof CanonKnowledgeOutputSchema>;

export const canonKnowledgeFetcherAgent: AgentDefinition = {
  name: 'canon_knowledge_fetcher',
  description: 'Loads champion data, items, and rune trees from the vault trimmed data for the given patch.',
  inputSchema: CanonKnowledgeInputSchema,
  outputSchema: CanonKnowledgeOutputSchema,

  async execute(input: unknown): Promise<AgentResult> {
    const start = Date.now();
    try {
      const { champion, patch } = CanonKnowledgeInputSchema.parse(input) as CanonKnowledgeInput;

      // Resolve the patch version -- use provided patch or fall back to current
      let version: string;
      try {
        version = patch || currentPatchVersion();
      } catch {
        version = patch;
      }

      const trimDir = trimmedPath(version);

      // Load champions
      const champFilePath = path.join(trimDir, 'champion-trimmed.json');
      if (!fs.existsSync(champFilePath)) {
        throw new Error(`Trimmed champion data not found at ${champFilePath}. Run: pnpm ingest`);
      }
      const allChampions: TrimmedChampion[] = JSON.parse(fs.readFileSync(champFilePath, 'utf-8'));
      const championData = allChampions.find(
        (c) => c.name.toLowerCase() === champion.toLowerCase() || c.id.toLowerCase() === champion.toLowerCase(),
      );
      if (!championData) {
        throw new Error(`Champion "${champion}" not found in trimmed data for patch ${version}`);
      }

      // Load items
      const itemFilePath = path.join(trimDir, 'item-trimmed.json');
      if (!fs.existsSync(itemFilePath)) {
        throw new Error(`Trimmed item data not found at ${itemFilePath}. Run: pnpm ingest`);
      }
      const allItems: TrimmedItem[] = JSON.parse(fs.readFileSync(itemFilePath, 'utf-8'));

      // Load runes
      const runeFilePath = path.join(trimDir, 'rune-trimmed.json');
      if (!fs.existsSync(runeFilePath)) {
        throw new Error(`Trimmed rune data not found at ${runeFilePath}. Run: pnpm ingest`);
      }
      const runeTrees: RuneTree[] = JSON.parse(fs.readFileSync(runeFilePath, 'utf-8'));

      const output: CanonKnowledgeOutput = {
        champion_data: championData,
        recommended_items: allItems,
        rune_trees: runeTrees,
      };

      return {
        agent: 'canon_knowledge_fetcher',
        success: true,
        data: output,
        duration_ms: Date.now() - start,
      };
    } catch (err) {
      return {
        agent: 'canon_knowledge_fetcher',
        success: false,
        data: null,
        errors: [err instanceof Error ? err.message : String(err)],
        duration_ms: Date.now() - start,
      };
    }
  },
};
