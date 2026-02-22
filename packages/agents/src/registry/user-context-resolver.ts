import { z } from 'zod';
import {
  type AgentDefinition,
  type AgentResult,
  VisionParseOutputSchema,
  type VisionParseOutput,
} from '@league-coach/core';

const UserContextInputSchema = z.object({
  vision_output: VisionParseOutputSchema,
});

type UserContextInput = z.infer<typeof UserContextInputSchema>;

const UserContextOutputSchema = z.object({
  user_champion: z.string(),
  user_team: z.enum(['blue', 'red']),
  allies: z.array(z.string()),
  enemies: z.array(z.string()),
});

export type UserContextOutput = z.infer<typeof UserContextOutputSchema>;

export const userContextResolverAgent: AgentDefinition = {
  name: 'user_context_resolver',
  description: 'Extracts the user champion, determines their team (blue/red), and splits allies vs enemies.',
  inputSchema: UserContextInputSchema,
  outputSchema: UserContextOutputSchema,

  async execute(input: unknown): Promise<AgentResult> {
    const start = Date.now();
    try {
      const { vision_output } = UserContextInputSchema.parse(input) as UserContextInput;
      const userChamp = vision_output.user_champion;

      // Determine which team the user is on
      const blueNames = vision_output.blue_team.map((s) => s.champion);
      const redNames = vision_output.red_team.map((s) => s.champion);

      let userTeam: 'blue' | 'red';
      let allies: string[];
      let enemies: string[];

      if (blueNames.includes(userChamp)) {
        userTeam = 'blue';
        allies = blueNames.filter((c) => c !== userChamp);
        enemies = redNames;
      } else if (redNames.includes(userChamp)) {
        userTeam = 'red';
        allies = redNames.filter((c) => c !== userChamp);
        enemies = blueNames;
      } else {
        // Fallback: user champion not found in either team -- assume blue team first slot
        userTeam = 'blue';
        allies = blueNames.filter((c) => c !== userChamp);
        enemies = redNames;
      }

      const output: UserContextOutput = {
        user_champion: userChamp,
        user_team: userTeam,
        allies,
        enemies,
      };

      const validated = UserContextOutputSchema.parse(output);

      return {
        agent: 'user_context_resolver',
        success: true,
        data: validated,
        duration_ms: Date.now() - start,
      };
    } catch (err) {
      return {
        agent: 'user_context_resolver',
        success: false,
        data: null,
        errors: [err instanceof Error ? err.message : String(err)],
        duration_ms: Date.now() - start,
      };
    }
  },
};
