import { z, ZodSchema } from 'zod';

export const AgentNameEnum = z.enum([
  'vision_parser',
  'user_context_resolver',
  'role_inference_engine',
  'canon_knowledge_fetcher',
  'build_and_runes_planner',
  'laning_matchup_coach',
  'teamfight_comp_coach',
  'macro_objectives_coach',
  'final_judge_validator',
]);

export type AgentName = z.infer<typeof AgentNameEnum>;

export const AgentResultSchema = z.object({
  agent: AgentNameEnum,
  success: z.boolean(),
  data: z.unknown(),
  errors: z.array(z.string()).optional(),
  duration_ms: z.number(),
});

export type AgentResult = z.infer<typeof AgentResultSchema>;

export interface AgentDefinition {
  name: AgentName;
  description: string;
  inputSchema: ZodSchema;
  outputSchema: ZodSchema;
  execute: (input: unknown) => Promise<AgentResult>;
}
