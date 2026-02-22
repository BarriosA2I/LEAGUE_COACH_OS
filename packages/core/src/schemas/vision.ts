import { z } from 'zod';

export const VisionSlotSchema = z.object({
  champion: z.string(),
  confidence: z.number().min(0).max(1),
});

export type VisionSlot = z.infer<typeof VisionSlotSchema>;

export const VisionParseInputSchema = z.object({
  image_path: z.string(),
  manual_champions: z.array(z.string()).optional(),
});

export type VisionParseInput = z.infer<typeof VisionParseInputSchema>;

export const VisionParseOutputSchema = z.object({
  blue_team: z.array(VisionSlotSchema).length(5),
  red_team: z.array(VisionSlotSchema).length(5),
  user_champion: z.string(),
  user_confidence: z.number(),
  unknown_slots: z.array(z.number()),
});

export type VisionParseOutput = z.infer<typeof VisionParseOutputSchema>;
