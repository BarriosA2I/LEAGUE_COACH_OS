import { z } from 'zod';

export const RecommendedBuildSchema = z.object({
  starter: z.array(z.string()),
  core_items: z.array(z.string()).min(2).max(4),
  boots: z.string(),
  situational: z.array(z.string()),
});

export type RecommendedBuild = z.infer<typeof RecommendedBuildSchema>;

export const RecommendedRunesSchema = z.object({
  primary_tree: z.string(),
  primary_keystone: z.string(),
  primary_slots: z.array(z.string()).length(3),
  secondary_tree: z.string(),
  secondary_slots: z.array(z.string()).length(2),
});

export type RecommendedRunes = z.infer<typeof RecommendedRunesSchema>;

export const SkillOrderSchema = z.object({
  first_three: z.array(z.string()).length(3),
  max_order: z.array(z.string()),
});

export type SkillOrder = z.infer<typeof SkillOrderSchema>;

export const GameCoachPackageSchema = z.object({
  patch: z.string(),
  timestamp: z.string().datetime(),
  user_champion: z.string(),
  user_role: z.enum(['top', 'jungle', 'mid', 'adc', 'support']),
  blue_team: z.array(z.string()).length(5),
  red_team: z.array(z.string()).length(5),
  recommended_build: RecommendedBuildSchema,
  recommended_runes: RecommendedRunesSchema,
  skill_order: SkillOrderSchema,
  laning_tips: z.array(z.string()),
  teamfight_tips: z.array(z.string()),
  objective_tips: z.array(z.string()),
  confidence: z.number().min(0).max(1),
  warnings: z.array(z.string()),
});

export type GameCoachPackage = z.infer<typeof GameCoachPackageSchema>;
