import { GameCoachPackageSchema, type GameCoachPackage } from '@league-coach/core';

export interface JudgeResult {
  valid: boolean;
  errors: string[];
  parsed: GameCoachPackage | null;
}

/**
 * Validates an unknown value against the full GameCoachPackageSchema.
 * Returns detailed error messages if validation fails.
 */
export function judgeOutput(output: unknown): JudgeResult {
  const result = GameCoachPackageSchema.safeParse(output);

  if (result.success) {
    return {
      valid: true,
      errors: [],
      parsed: result.data,
    };
  }

  const errors = result.error.issues.map((issue) => {
    const path = issue.path.length > 0 ? issue.path.join('.') : '(root)';
    return `[${path}] ${issue.message} (code: ${issue.code})`;
  });

  return {
    valid: false,
    errors,
    parsed: null,
  };
}
