import { z } from 'zod';
import { type AgentDefinition, type AgentResult } from '@league-coach/core';

const LaningMatchupInputSchema = z.object({
  user_champion: z.string(),
  user_role: z.enum(['top', 'jungle', 'mid', 'adc', 'support']),
  enemy_laner: z.string().optional(),
  allies: z.array(z.string()),
  enemies: z.array(z.string()),
});

const LaningMatchupOutputSchema = z.object({
  matchup_tips: z.array(z.string()),
  power_spikes: z.array(z.string()),
  warning: z.string().optional(),
});

export const laningMatchupCoachAgent: AgentDefinition = {
  name: 'laning_matchup_coach',
  description: 'STUB: Provides laning matchup advice. FULL MODE not yet implemented.',
  inputSchema: LaningMatchupInputSchema,
  outputSchema: LaningMatchupOutputSchema,

  async execute(_input: unknown): Promise<AgentResult> {
    const start = Date.now();

    return {
      agent: 'laning_matchup_coach',
      success: true,
      data: {
        matchup_tips: [],
        power_spikes: [],
        warning: 'FULL MODE not implemented -- laning matchup analysis requires LLM integration.',
      },
      duration_ms: Date.now() - start,
    };
  },
};
