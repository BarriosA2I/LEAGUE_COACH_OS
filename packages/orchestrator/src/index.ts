import {
  type VisionParseInput,
  type VisionParseOutput,
  type GameCoachPackage,
  type AgentResult,
  type AgentName,
  logger,
  currentPatchVersion,
} from '@league-coach/core';
import {
  getAgent,
  type UserContextOutput,
  type RoleInferenceOutput,
  type CanonKnowledgeOutput,
  type BuildPlannerOutput,
  type FinalJudgeOutput,
} from '@league-coach/agents';

const TAG = 'orchestrator';

// ---------------------------------------------------------------------------
// Pipeline step helper
// ---------------------------------------------------------------------------

interface StepResult<T> {
  success: boolean;
  data: T | null;
  agentResult: AgentResult;
}

async function runStep<T>(agentName: AgentName, input: unknown, stepLabel: string): Promise<StepResult<T>> {
  logger.info(TAG, `Step [${stepLabel}] starting`, { agent: agentName });

  const agent = getAgent(agentName);
  const result = await agent.execute(input);

  logger.info(TAG, `Step [${stepLabel}] completed`, {
    agent: agentName,
    success: result.success,
    duration_ms: result.duration_ms,
  });

  if (!result.success) {
    logger.error(TAG, `Step [${stepLabel}] FAILED`, { errors: result.errors });
    return { success: false, data: null, agentResult: result };
  }

  return { success: true, data: result.data as T, agentResult: result };
}

// ---------------------------------------------------------------------------
// Main pipeline
// ---------------------------------------------------------------------------

export interface PipelineResult {
  success: boolean;
  package: GameCoachPackage | null;
  errors: string[];
  timing: Record<string, number>;
}

/**
 * Runs the full coach pipeline from vision input to validated GAME_COACH_PACKAGE.
 *
 * Pipeline steps:
 *   1. vision_parser         -- parse loading screen / manual input
 *   2. user_context_resolver -- extract user champ, team, allies, enemies
 *   3. role_inference_engine  -- infer user's role
 *   4. canon_knowledge_fetcher -- load champion data, items, runes from vault
 *   5. build_and_runes_planner -- generate build, runes, tips
 *   6. final_judge_validator   -- validate the assembled package
 */
export async function runCoachPipeline(input: VisionParseInput): Promise<PipelineResult> {
  const pipelineStart = Date.now();
  const errors: string[] = [];
  const timing: Record<string, number> = {};

  // Resolve patch version
  let patch: string;
  try {
    patch = currentPatchVersion();
  } catch {
    errors.push('No patch version set. Run: pnpm ingest');
    return { success: false, package: null, errors, timing };
  }

  // -----------------------------------------------------------------------
  // Step 1: vision_parser
  // -----------------------------------------------------------------------
  const step1 = await runStep<VisionParseOutput>('vision_parser', input, '1-vision_parser');
  timing['vision_parser'] = step1.agentResult.duration_ms;
  if (!step1.success || !step1.data) {
    errors.push(...(step1.agentResult.errors || ['vision_parser failed']));
    return { success: false, package: null, errors, timing };
  }
  const visionOutput = step1.data;

  // -----------------------------------------------------------------------
  // Step 2: user_context_resolver
  // -----------------------------------------------------------------------
  const step2 = await runStep<UserContextOutput>('user_context_resolver', { vision_output: visionOutput }, '2-user_context_resolver');
  timing['user_context_resolver'] = step2.agentResult.duration_ms;
  if (!step2.success || !step2.data) {
    errors.push(...(step2.agentResult.errors || ['user_context_resolver failed']));
    return { success: false, package: null, errors, timing };
  }
  const userContext = step2.data;

  // -----------------------------------------------------------------------
  // Step 3: role_inference_engine
  // -----------------------------------------------------------------------
  const step3 = await runStep<RoleInferenceOutput>('role_inference_engine', {
    champion: userContext.user_champion,
    allies: userContext.allies,
  }, '3-role_inference_engine');
  timing['role_inference_engine'] = step3.agentResult.duration_ms;
  if (!step3.success || !step3.data) {
    errors.push(...(step3.agentResult.errors || ['role_inference_engine failed']));
    return { success: false, package: null, errors, timing };
  }
  const roleInference = step3.data;

  // -----------------------------------------------------------------------
  // Step 4: canon_knowledge_fetcher
  // -----------------------------------------------------------------------
  const step4 = await runStep<CanonKnowledgeOutput>('canon_knowledge_fetcher', {
    champion: userContext.user_champion,
    role: roleInference.role,
    patch,
  }, '4-canon_knowledge_fetcher');
  timing['canon_knowledge_fetcher'] = step4.agentResult.duration_ms;
  if (!step4.success || !step4.data) {
    errors.push(...(step4.agentResult.errors || ['canon_knowledge_fetcher failed']));
    return { success: false, package: null, errors, timing };
  }
  const knowledge = step4.data;

  // -----------------------------------------------------------------------
  // Step 5: build_and_runes_planner
  // -----------------------------------------------------------------------
  const step5 = await runStep<BuildPlannerOutput>('build_and_runes_planner', {
    champion: userContext.user_champion,
    role: roleInference.role,
    champion_data: knowledge.champion_data,
    items: knowledge.recommended_items,
    rune_trees: knowledge.rune_trees,
  }, '5-build_and_runes_planner');
  timing['build_and_runes_planner'] = step5.agentResult.duration_ms;
  if (!step5.success || !step5.data) {
    errors.push(...(step5.agentResult.errors || ['build_and_runes_planner failed']));
    return { success: false, package: null, errors, timing };
  }
  const buildPlan = step5.data;

  // -----------------------------------------------------------------------
  // Assemble the GAME_COACH_PACKAGE
  // -----------------------------------------------------------------------
  const warnings: string[] = [];
  if (roleInference.confidence < 0.7) {
    warnings.push(`Role inference confidence is low (${roleInference.confidence.toFixed(2)}): ${roleInference.reasoning}`);
  }

  const blueTeam = visionOutput.blue_team.map((s) => s.champion);
  const redTeam = visionOutput.red_team.map((s) => s.champion);

  const assembledPackage = {
    patch,
    timestamp: new Date().toISOString(),
    user_champion: userContext.user_champion,
    user_role: roleInference.role,
    blue_team: blueTeam,
    red_team: redTeam,
    recommended_build: buildPlan.recommended_build,
    recommended_runes: buildPlan.recommended_runes,
    skill_order: buildPlan.skill_order,
    laning_tips: buildPlan.laning_tips,
    teamfight_tips: buildPlan.teamfight_tips,
    objective_tips: buildPlan.objective_tips,
    confidence: roleInference.confidence,
    warnings,
  };

  // -----------------------------------------------------------------------
  // Step 6: final_judge_validator
  // -----------------------------------------------------------------------
  const step6 = await runStep<FinalJudgeOutput>('final_judge_validator', { package: assembledPackage }, '6-final_judge_validator');
  timing['final_judge_validator'] = step6.agentResult.duration_ms;
  if (!step6.success || !step6.data) {
    errors.push(...(step6.agentResult.errors || ['final_judge_validator failed']));
    return { success: false, package: null, errors, timing };
  }

  const judgeResult = step6.data;

  if (!judgeResult.valid) {
    errors.push('Final validation failed:', ...judgeResult.errors);
    return { success: false, package: null, errors, timing };
  }

  timing['total'] = Date.now() - pipelineStart;
  logger.info(TAG, 'Pipeline complete', { timing });

  return {
    success: true,
    package: judgeResult.package,
    errors: [],
    timing,
  };
}

// ---------------------------------------------------------------------------
// CLI mode: run directly with manual_champions
// ---------------------------------------------------------------------------

if (require.main === module) {
  const args = process.argv.slice(2);

  // Parse --champions and --user flags
  const champIdx = args.indexOf('--champions');
  const userIdx = args.indexOf('--user');

  let manualChampions: string[];
  let userChampion: string | undefined;

  if (champIdx !== -1 && args[champIdx + 1]) {
    // Format: --champions "blue:Teemo,blue:LeeSin,...,red:Darius,..."
    const raw = args[champIdx + 1].replace(/"/g, '');
    manualChampions = raw.split(',').map((s) => {
      // Strip "blue:" or "red:" prefix — ordering determines team
      return s.replace(/^(blue|red):/, '');
    });
    if (userIdx !== -1 && args[userIdx + 1]) {
      userChampion = args[userIdx + 1].replace(/"/g, '');
    }
  } else if (args.length >= 10) {
    // Positional: <champ1> ... <champ10>
    manualChampions = args.slice(0, 10);
  } else {
    console.error('Usage:');
    console.error('  pnpm coach -- --champions "blue:Teemo,blue:LeeSin,...,red:Darius,..." --user Teemo');
    console.error('  pnpm coach -- Teemo LeeSin Syndra Jinx Thresh Darius Elise Ahri Caitlyn Lulu');
    process.exit(1);
  }

  // If --user specified, reorder so that champion is first in blue team
  if (userChampion) {
    const idx = manualChampions.findIndex(
      (c) => c.toLowerCase() === userChampion!.toLowerCase(),
    );
    if (idx > 0 && idx < 5) {
      // Swap to position 0 within blue team
      [manualChampions[0], manualChampions[idx]] = [manualChampions[idx], manualChampions[0]];
    }
  }

  const input: VisionParseInput = {
    image_path: '',
    manual_champions: manualChampions,
  };

  runCoachPipeline(input)
    .then((result) => {
      console.log(JSON.stringify(result, null, 2));
      process.exit(result.success ? 0 : 1);
    })
    .catch((err) => {
      console.error('Pipeline crashed:', err);
      process.exit(1);
    });
}
