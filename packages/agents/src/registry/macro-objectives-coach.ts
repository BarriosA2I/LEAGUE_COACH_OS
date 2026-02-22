import { z } from 'zod';
import { type AgentDefinition, type AgentResult } from '@league-coach/core';

const MacroObjectivesInputSchema = z.object({
  user_champion: z.string(),
  user_role: z.enum(['top', 'jungle', 'mid', 'adc', 'support']),
  allies: z.array(z.string()),
  enemies: z.array(z.string()),
});

const MacroObjectivesOutputSchema = z.object({
  objective_priority: z.array(z.string()),
  macro_strategy: z.array(z.string()),
  warning: z.string().optional(),
});

export const macroObjectivesCoachAgent: AgentDefinition = {
  name: 'macro_objectives_coach',
  description: 'STUB: Provides macro-level objective guidance. FULL MODE not yet implemented.',
  inputSchema: MacroObjectivesInputSchema,
  outputSchema: MacroObjectivesOutputSchema,

  async execute(_input: unknown): Promise<AgentResult> {
    const start = Date.now();

    return {
      agent: 'macro_objectives_coach',
      success: true,
      data: {
        objective_priority: [],
        macro_strategy: [],
        warning: 'FULL MODE not implemented -- macro objectives analysis requires LLM integration.',
      },
      duration_ms: Date.now() - start,
    };
  },
};
