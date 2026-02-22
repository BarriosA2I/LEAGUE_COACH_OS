import { type AgentName, type AgentDefinition } from '@league-coach/core';
import { visionParserAgent } from './vision-parser';
import { userContextResolverAgent } from './user-context-resolver';
import { roleInferenceEngineAgent } from './role-inference-engine';
import { canonKnowledgeFetcherAgent } from './canon-knowledge-fetcher';
import { buildAndRunesPlannerAgent } from './build-and-runes-planner';
import { laningMatchupCoachAgent } from './laning-matchup-coach';
import { teamfightCompCoachAgent } from './teamfight-comp-coach';
import { macroObjectivesCoachAgent } from './macro-objectives-coach';
import { finalJudgeValidatorAgent } from './final-judge-validator';

/**
 * Central registry mapping AgentName to its AgentDefinition.
 * All 9 agents are registered here.
 */
export const agentRegistry: Map<AgentName, AgentDefinition> = new Map<AgentName, AgentDefinition>([
  ['vision_parser', visionParserAgent],
  ['user_context_resolver', userContextResolverAgent],
  ['role_inference_engine', roleInferenceEngineAgent],
  ['canon_knowledge_fetcher', canonKnowledgeFetcherAgent],
  ['build_and_runes_planner', buildAndRunesPlannerAgent],
  ['laning_matchup_coach', laningMatchupCoachAgent],
  ['teamfight_comp_coach', teamfightCompCoachAgent],
  ['macro_objectives_coach', macroObjectivesCoachAgent],
  ['final_judge_validator', finalJudgeValidatorAgent],
]);

/**
 * Retrieves an agent definition by name.
 * Throws if the agent is not registered.
 */
export function getAgent(name: AgentName): AgentDefinition {
  const agent = agentRegistry.get(name);
  if (!agent) {
    throw new Error(`Agent "${name}" is not registered in the agent registry.`);
  }
  return agent;
}

/**
 * Returns all registered agent definitions.
 */
export function listAgents(): AgentDefinition[] {
  return [...agentRegistry.values()];
}
