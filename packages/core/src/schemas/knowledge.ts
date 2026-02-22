import { z } from 'zod';

export const TrimmedChampionSchema = z.object({
  id: z.string(),
  name: z.string(),
  title: z.string(),
  tags: z.array(z.string()),
  partype: z.string(),
  info: z.object({
    attack: z.number(),
    defense: z.number(),
    magic: z.number(),
    difficulty: z.number(),
  }),
  stats: z.record(z.string(), z.number()),
});

export type TrimmedChampion = z.infer<typeof TrimmedChampionSchema>;

export const TrimmedItemSchema = z.object({
  id: z.string(),
  name: z.string(),
  cost: z.object({
    total: z.number(),
    sell: z.number(),
  }),
  stats: z.record(z.string(), z.number()),
  tags: z.array(z.string()),
  from: z.array(z.string()),
  into: z.array(z.string()),
  description: z.string(),
});

export type TrimmedItem = z.infer<typeof TrimmedItemSchema>;

export const TrimmedRuneSchema = z.object({
  id: z.number(),
  key: z.string(),
  name: z.string(),
  shortDesc: z.string(),
  longDesc: z.string(),
  icon: z.string(),
});

export type TrimmedRune = z.infer<typeof TrimmedRuneSchema>;

export const RuneTreeSchema = z.object({
  id: z.number(),
  key: z.string(),
  name: z.string(),
  slots: z.array(z.array(TrimmedRuneSchema)),
});

export type RuneTree = z.infer<typeof RuneTreeSchema>;

export const PatchManifestSchema = z.object({
  version: z.string(),
  fetched_at: z.string().datetime(),
  champion_count: z.number(),
  item_count: z.number(),
  rune_tree_count: z.number(),
});

export type PatchManifest = z.infer<typeof PatchManifestSchema>;
