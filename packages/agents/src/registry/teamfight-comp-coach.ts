import { z } from 'zod';
import { type AgentDefinition, type AgentResult } from '@league-coach/core';

const TeamfightCompInputSchema = z.object({
  user_champion: z.string(),
  user_role: z.enum(['top', 'jungle', 'mid', 'adc', 'support']),
  allies: z.array(z.string()),
  enemies: z.array(z.string()),
});

const TeamfightCompOutputSchema = z.object({
  comp_analysis: z.string(),
  teamfight_strategy: z.array(z.string()),
  warning: z.string().optional(),
});

export const teamfightCompCoachAgent: AgentDefinition = {
  name: 'teamfight_comp_coach',
  description: 'STUB: Analyzes team compositions and suggests teamfight strategies. FULL MODE not yet implemented.',
  inputSchema: TeamfightCompInputSchema,
  outputSchema: TeamfightCompOutputSchema,

  async execute(_input: unknown): Promise<AgentResult> {
    const start = Date.now();

    return {
      agent: 'teamfight_comp_coach',
      success: true,
      data: {
        comp_analysis: '',
        teamfight_strategy: [],
        warning: 'FULL MODE not implemented -- team composition analysis requires LLM integration.',
      },
      duration_ms: Date.now() - start,
    };
  },
};
