import { z } from 'zod';
import {
  type AgentDefinition,
  type AgentResult,
  GameCoachPackageSchema,
  type GameCoachPackage,
} from '@league-coach/core';

/**
 * The final judge accepts a partial/assembled GameCoachPackage and validates
 * it against the full Zod schema. This catches any malformed output from
 * upstream agents before the package reaches the user.
 */

const FinalJudgeInputSchema = z.object({
  package: z.unknown(),
});

const FinalJudgeOutputSchema = z.object({
  valid: z.boolean(),
  package: GameCoachPackageSchema.nullable(),
  errors: z.array(z.string()),
});

export type FinalJudgeOutput = z.infer<typeof FinalJudgeOutputSchema>;

export const finalJudgeValidatorAgent: AgentDefinition = {
  name: 'final_judge_validator',
  description: 'Validates the assembled GAME_COACH_PACKAGE against the full schema using Zod safeParse.',
  inputSchema: FinalJudgeInputSchema,
  outputSchema: FinalJudgeOutputSchema,

  async execute(input: unknown): Promise<AgentResult> {
    const start = Date.now();
    try {
      const { package: pkg } = FinalJudgeInputSchema.parse(input);

      const result = GameCoachPackageSchema.safeParse(pkg);

      if (result.success) {
        const output: FinalJudgeOutput = {
          valid: true,
          package: result.data,
          errors: [],
        };

        return {
          agent: 'final_judge_validator',
          success: true,
          data: output,
          duration_ms: Date.now() - start,
        };
      } else {
        const errors = result.error.issues.map(
          (issue) => `${issue.path.join('.')}: ${issue.message}`,
        );

        const output: FinalJudgeOutput = {
          valid: false,
          package: null,
          errors,
        };

        return {
          agent: 'final_judge_validator',
          success: true,
          data: output,
          duration_ms: Date.now() - start,
        };
      }
    } catch (err) {
      return {
        agent: 'final_judge_validator',
        success: false,
        data: null,
        errors: [err instanceof Error ? err.message : String(err)],
        duration_ms: Date.now() - start,
      };
    }
  },
};
